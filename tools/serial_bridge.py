#!/usr/bin/env python3
"""USB-serial -> Wi-Fi bridge for the CH4 Survey phone app.

Plug the sensor board into this PC over USB and run this script. It reads the
board's serial CSV, turns every row into the BLE protocol-v1 Sample packet
(docs/phone_board.md) and serves it on the LAN, so a phone running the app in
Expo Go (which has no Bluetooth module) -- or any browser -- can watch the
live read-out:

    ws://<this-pc>:8765/ws     binary frames: 20-byte Sample packets
                               text frames:   the Info JSON (sent on connect)
    http://<this-pc>:8765/     a live bench read-out page
    http://<this-pc>:8765/info the Info JSON plus bridge status

Both board generations are understood, detected per row:

  rev B (firmware/phone_board): the bench CSV the firmware prints alongside
        its BLE notifications. Taps, T/RH, VBAT, heater rail and flags are
        relayed unchanged.
  rev A (legacy/rev_a/src/main.cpp): the SD-card CSV. VOUT is the load voltage, so
        it is sent as tap = VOUT / 2 with tap_ratio 2.0 (the app rebuilds
        VRL = VOUT). No battery on rev A: vbat = 0, flag USB power set.

Control writes from the app (interval, LED) arrive over the socket but the
serial link has no command channel, so they are logged and dropped.

Dependencies: pyserial only (PlatformIO's bundled Python already has it):

    C:\\Users\\<you>\\.platformio\\penv\\Scripts\\python.exe tools\\serial_bridge.py
    python tools/serial_bridge.py --port COM7        # pick the port by hand
    python tools/serial_bridge.py --selftest         # packet encoder checks

The phone must be on the same Wi-Fi as this PC, and Windows Firewall must
allow python.exe inbound on private networks (say yes to the prompt on the
first run, or add a rule for TCP 8765).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import queue
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# Protocol v1 (docs/phone_board.md, "BLE protocol (v1)")
# ---------------------------------------------------------------------------
PROTO_VERSION = 1
SAMPLE_LEN = 20
TEMP_MISSING = -0x8000
U16_MISSING = 0xFFFF

FLAG_USB_POWER = 1 << 0
FLAG_CHARGING = 1 << 1
FLAG_BME_OK = 1 << 2
FLAG_ADS_OK = 1 << 3
FLAG_HEATER_FAULT = 1 << 4
FLAG_BUTTON = 1 << 5
FLAG_HEATERS_OFF = 1 << 6

OP_NAMES = {0x01: "set interval", 0x02: "identify", 0x03: "set LED"}

# Analogue front end, as the rev B Info JSON reports it.
RL_OHM = 40000
TAP_RATIO = 2.0
VC_MV = 5000

REV_A_STATES = ("WARMUP", "BASELINING", "RUNNING")


def _u16(v: float) -> int:
    if v != v or v <= 0:  # NaN or negative
        return 0
    return min(0xFFFF, int(round(v)))


def _num(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v == v else None  # drop NaN


def encode_sample(
    seq: int,
    ms: int,
    ch4_tap_mv: float,
    lpg_tap_mv: float,
    temp_c: float | None,
    humidity_pct: float | None,
    pressure_hpa: float | None,
    vbat_mv: int,
    flags: int,
) -> bytes:
    """The 20-byte little-endian Sample packet, exactly as the firmware sends it."""
    temp = TEMP_MISSING if temp_c is None else max(-32767, min(32767, int(round(temp_c * 100))))
    hum = U16_MISSING if humidity_pct is None else min(0xFFFE, _u16(humidity_pct * 100))
    pres = U16_MISSING if pressure_hpa is None else min(0xFFFE, _u16(pressure_hpa * 10))
    return struct.pack(
        "<BHIHHhHHHB",
        PROTO_VERSION,
        seq & 0xFFFF,
        ms & 0xFFFFFFFF,
        _u16(ch4_tap_mv * 10),
        _u16(lpg_tap_mv * 10),
        temp,
        hum,
        pres,
        _u16(vbat_mv),
        flags & 0xFF,
    )


class Parsed:
    """One decoded CSV row, whichever firmware produced it."""

    __slots__ = ("board", "ms", "seq", "ch4_tap", "lpg_tap", "temp", "hum", "pres", "vbat", "heater", "flags")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def parse_row(line: str, seq_counter: int) -> Parsed | None:
    """Decode a rev B bench row or a rev A log row. None for anything else
    (banners, warnings, the header line, a torn first line)."""
    f = [c.strip() for c in line.split(",")]
    if len(f) < 11:
        return None
    try:
        if f[2] in ("ads", "esp"):
            # rev B: ms,seq,adc,ch4_tap_mv,lpg_tap_mv,ch4_vrl_mv,lpg_vrl_mv,ch4_rs_ohm,
            #        lpg_rs_ohm,temp_c,humidity_pct,pressure_hpa,vbat_mv,heater_mv,flags,...
            if len(f) < 15:
                return None
            return Parsed(
                board="rev-b",
                ms=int(f[0]),
                seq=int(f[1]),
                ch4_tap=float(f[3]),
                lpg_tap=float(f[4]),
                temp=_num(f[9]),
                hum=_num(f[10]),
                pres=_num(f[11]),
                vbat=int(float(f[12] or 0)),
                heater=int(float(f[13] or 0)),
                flags=int(f[14], 0),
            )
        if f[1] in REV_A_STATES:
            # rev A: millis_since_boot,state,ch4_vout_mv,ch4_baseline_mv,ch4_dev_mv,
            #        lpg_vout_mv,lpg_baseline_mv,lpg_dev_mv,temp_c,humidity_pct,pressure_hpa,...
            temp, hum, pres = _num(f[8]), _num(f[9]), _num(f[10])
            flags = FLAG_USB_POWER | FLAG_ADS_OK
            if temp is not None and hum is not None:
                flags |= FLAG_BME_OK
            return Parsed(
                board="rev-a",
                ms=int(f[0]),
                seq=seq_counter & 0xFFFF,
                ch4_tap=float(f[2]) / TAP_RATIO,
                lpg_tap=float(f[5]) / TAP_RATIO,
                temp=temp,
                hum=hum,
                pres=pres,
                vbat=0,
                heater=0,
                flags=flags,
            )
    except (ValueError, IndexError):
        return None
    return None


# ---------------------------------------------------------------------------
# Shared state + fan-out
# ---------------------------------------------------------------------------
class Hub:
    """Latest sample/info plus the queues of every connected socket client."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.clients: dict[int, queue.Queue] = {}
        self.next_id = 0
        self.board = "unknown"
        self.port: str | None = None
        self.port_open = False
        self.rows = 0
        self.ignored = 0
        self.last: Parsed | None = None
        self.last_at = 0.0
        self.last_ms: int | None = None
        self.interval_ms = 250
        self.started = time.time()
        self._intervals: list[float] = []

    def add_client(self) -> tuple[int, queue.Queue]:
        with self.lock:
            cid = self.next_id
            self.next_id += 1
            q: queue.Queue = queue.Queue(maxsize=64)
            self.clients[cid] = q
            return cid, q

    def remove_client(self, cid: int) -> None:
        with self.lock:
            self.clients.pop(cid, None)

    def client_count(self) -> int:
        with self.lock:
            return len(self.clients)

    def info_json(self) -> str:
        with self.lock:
            return json.dumps(
                {
                    "type": "info",
                    "proto": PROTO_VERSION,
                    "fw": "bridge/" + self.board,
                    "board": self.board,
                    "rl_ohm": RL_OHM,
                    "tap_ratio": TAP_RATIO,
                    "vc_mv": VC_MV,
                    "interval_ms": self.interval_ms,
                    "heater_mv": (self.last.heater if self.last else 0) or 0,
                    "link": "usb-serial",
                    "port": self.port,
                }
            )

    def status(self) -> dict:
        with self.lock:
            return {
                "port": self.port,
                "port_open": self.port_open,
                "board": self.board,
                "rows": self.rows,
                "ignored_lines": self.ignored,
                "clients": len(self.clients),
                "seconds_since_sample": None if not self.last_at else round(time.time() - self.last_at, 1),
                "uptime_s": round(time.time() - self.started),
            }

    def publish(self, p: Parsed, packet: bytes, csv_line: str) -> None:
        with self.lock:
            board_changed = p.board != self.board
            self.board = p.board
            self.rows += 1
            self.last = p
            self.last_at = time.time()
            if self.last_ms is not None and 0 < p.ms - self.last_ms < 10_000:
                self._intervals.append(p.ms - self.last_ms)
                if len(self._intervals) >= 16:
                    self._intervals.sort()
                    self.interval_ms = int(self._intervals[len(self._intervals) // 2])
                    self._intervals = []
            self.last_ms = p.ms
            queues = list(self.clients.values())
        if board_changed:
            info = self.info_json()
            for q in queues:
                _offer(q, ("text", info))
        for q in queues:
            _offer(q, ("binary", packet))
            _offer(q, ("text", '{"type":"csv","line":' + json.dumps(csv_line) + "}"))


def _offer(q: queue.Queue, item) -> None:
    """Queue without blocking; a slow client loses its oldest frames, not ours."""
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            pass


# ---------------------------------------------------------------------------
# Serial reader
# ---------------------------------------------------------------------------
def find_port(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    ports = list(list_ports.comports())
    if not ports:
        return None

    def score(p) -> int:
        s = 0
        if p.vid == 0x303A:  # Espressif native USB (ESP32-S3 CDC)
            s += 100
        desc = ((p.description or "") + " " + (p.manufacturer or "")).lower()
        for hint in ("esp32", "espressif", "usb serial", "cp210", "ch340", "ch9102", "silicon labs", "usb-serial"):
            if hint in desc:
                s += 10
        return s

    best = max(ports, key=score)
    return best.device


def serial_loop(hub: Hub, port_arg: str | None, baud: int, echo: bool, stop: threading.Event) -> None:
    try:
        import serial  # pyserial
    except ImportError:
        print("pyserial is not installed: pip install pyserial   (or run with PlatformIO's python)")
        stop.set()
        return

    seq_counter = 0
    announced_none = False
    while not stop.is_set():
        port = find_port(port_arg)
        if not port:
            if not announced_none:
                print("No serial port found. Plug the board in (and switch it on); retrying every 2 s...")
                announced_none = True
            time.sleep(2)
            continue
        announced_none = False
        try:
            # The ESP32-S3's USB-Serial-JTAG resets the chip on a DTR/RTS edge, so
            # open with both held low (set before open: no edge at all). If the
            # firmware then stays silent because it gates output on `if (Serial)`,
            # DTR is raised once below, which costs at most one reboot.
            ser = serial.Serial()
            ser.port = port
            ser.baudrate = baud
            ser.timeout = 1
            ser.dtr = False
            ser.rts = False
            ser.open()
        except Exception as e:  # noqa: BLE001
            print(f"Could not open {port}: {e}. Retrying in 2 s...")
            with hub.lock:
                hub.port, hub.port_open = port, False
            time.sleep(2)
            continue

        print(f"Serial port {port} open at {baud} baud. Waiting for CSV rows...")
        with hub.lock:
            hub.port, hub.port_open = port, True
        silent_since = time.time()
        dtr_raised = False
        warned_silent = False
        try:
            while not stop.is_set():
                raw = ser.readline()
                if not raw:
                    silent_for = time.time() - silent_since
                    if not dtr_raised and silent_for > 5:
                        dtr_raised = True
                        print(f"{port} silent for 5 s: raising DTR in case the firmware waits for a terminal.")
                        ser.dtr = True
                    elif not warned_silent and silent_for > 15:
                        warned_silent = True
                        print(
                            f"{port} is open but silent. Is the firmware flashed? "
                            "(rev B: pio run -d firmware/phone_board -t upload; rev A: pio run -t upload)"
                        )
                    continue
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                p = parse_row(line, seq_counter)
                if p is None:
                    with hub.lock:
                        hub.ignored += 1
                    if echo or ("," not in line):
                        print(f"[{port}] {line}")
                    continue
                silent_since = time.time()
                warned_silent = False
                if p.board == "rev-a":
                    seq_counter += 1
                pkt = encode_sample(p.seq, p.ms, p.ch4_tap, p.lpg_tap, p.temp, p.hum, p.pres, p.vbat, p.flags)
                first = hub.rows == 0
                hub.publish(p, pkt, line)
                if first:
                    print(f"First sample decoded: {p.board} board, ms={p.ms}. Relaying.")
                if echo:
                    print(line)
        except Exception as e:  # noqa: BLE001
            print(f"Serial error on {port}: {e}. Reopening in 2 s...")
        finally:
            try:
                ser.close()
            except Exception:  # noqa: BLE001
                pass
            with hub.lock:
                hub.port_open = False
        time.sleep(2)


# ---------------------------------------------------------------------------
# WebSocket framing (RFC 6455, server side: unmasked out, masked in)
# ---------------------------------------------------------------------------
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_frame(opcode: int, payload: bytes) -> bytes:
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack(">H", n)
    else:
        head += bytes([127]) + struct.pack(">Q", n)
    return head + payload


def ws_read_frame(rfile) -> tuple[int, bytes] | None:
    """Read one client frame. None when the socket closed."""
    h = rfile.read(2)
    if len(h) < 2:
        return None
    opcode = h[0] & 0x0F
    masked = h[1] & 0x80
    n = h[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", rfile.read(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", rfile.read(8))[0]
    key = rfile.read(4) if masked else b""
    data = rfile.read(n) if n else b""
    if len(data) < n:
        return None
    if masked:
        data = bytes(b ^ key[i % 4] for i, b in enumerate(data))
    return opcode, data


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    hub: Hub  # set by main()

    def log_message(self, fmt, *args):  # quieter than the default access log
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/ws":
            return self._websocket()
        if path == "/info":
            d = json.loads(self.hub.info_json())
            d["status"] = self.hub.status()
            return self._send(200, json.dumps(d, indent=1).encode(), "application/json")
        if path in ("/", "/index.html"):
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        self._send(404, b"not found", "text/plain")

    def _websocket(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if self.headers.get("Upgrade", "").lower() != "websocket" or not key:
            return self._send(400, b"websocket upgrade expected", "text/plain")
        accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True

        hub = self.hub
        cid, q = hub.add_client()
        peer = f"{self.client_address[0]}:{self.client_address[1]}"
        print(f"Client connected: {peer} (clients: {hub.client_count()})")
        sock = self.connection
        send_lock = threading.Lock()
        alive = threading.Event()
        alive.set()

        def send(opcode: int, payload: bytes) -> None:
            with send_lock:
                sock.sendall(ws_frame(opcode, payload))

        def reader() -> None:
            try:
                while alive.is_set():
                    fr = ws_read_frame(self.rfile)
                    if fr is None:
                        break
                    opcode, data = fr
                    if opcode == 0x8:  # close
                        try:
                            send(0x8, data[:2])
                        except OSError:
                            pass
                        break
                    if opcode == 0x9:  # ping
                        send(0xA, data)
                    elif opcode in (0x1, 0x2) and data:
                        name = OP_NAMES.get(data[0], f"op 0x{data[0]:02X}")
                        print(f"Control write from {peer} ({name}, {data.hex()}) ignored: serial has no command channel.")
            except OSError:
                pass
            finally:
                alive.clear()

        t = threading.Thread(target=reader, name=f"ws-reader-{cid}", daemon=True)
        t.start()
        try:
            send(0x1, hub.info_json().encode())
            last_ping = time.time()
            while alive.is_set():
                try:
                    kind, payload = q.get(timeout=1.0)
                except queue.Empty:
                    if time.time() - last_ping > 15:
                        send(0x9, b"")  # keep NAT/phone links alive, and detect dead ones
                        last_ping = time.time()
                    continue
                send(0x2 if kind == "binary" else 0x1, payload if isinstance(payload, bytes) else payload.encode())
        except OSError:
            pass
        finally:
            alive.clear()
            hub.remove_client(cid)
            try:
                sock.close()
            except OSError:
                pass
            print(f"Client left: {peer} (clients: {hub.client_count()})")


# ---------------------------------------------------------------------------
# Bench page
# ---------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CH4 bridge</title>
<style>
  :root{--bg:#111110;--fg:#f2efe8;--muted:#9a968c;--card:#1c1b19;--line:#33312d;--ch4:#5ec8ff;--lpg:#ffb454;--bad:#e5484d;--ok:#46a758}
  body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.4 system-ui,Segoe UI,Roboto,sans-serif}
  main{max-width:920px;margin:0 auto;padding:16px}
  h1{font-size:20px;margin:0 0 4px}
  .sub{color:var(--muted);font-size:14px;margin-bottom:12px;word-break:break-all}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:12px 0}
  .cell{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
  .k{color:var(--muted);font-size:13px;font-weight:600}
  .v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums}
  canvas{width:100%;height:220px;background:var(--card);border:1px solid var(--line);border-radius:10px}
  .pill{display:inline-block;padding:3px 10px;border-radius:999px;border:2px solid var(--line);font-weight:600;margin-right:6px}
  .on{border-color:var(--ok)} .off{border-color:var(--bad)}
  pre{color:var(--muted);font-size:12px;white-space:pre-wrap;word-break:break-all}
</style></head><body><main>
<h1>CH4 sensor bridge</h1>
<div class="sub" id="urls"></div>
<div><span class="pill off" id="link">socket: connecting…</span><span class="pill" id="board">board: ?</span><span class="pill" id="rate">0.0 samples/s</span></div>
<div class="grid" id="grid"></div>
<canvas id="chart" width="900" height="220"></canvas>
<div class="sub" style="margin-top:6px"><span style="color:var(--ch4)">■</span> CH4 VRL &nbsp; <span style="color:var(--lpg)">■</span> LPG VRL &nbsp; last 60 s, mV</div>
<pre id="raw"></pre>
</main>
<script>
const $=id=>document.getElementById(id);
const host=location.host;
$('urls').textContent='Phone (Expo Go, Settings → Bridge PC address): '+host.split(':')[0]+'   ·   socket: ws://'+host+'/ws';
const fields=[['CH4 VRL','ch4',' mV'],['LPG VRL','lpg',' mV'],['CH4 Rs','rs4',''],['LPG Rs','rsl',''],['Temp','t',' °C'],['Humidity','h',' %'],['Pressure','p',' hPa'],['Battery','vb',' mV'],['Heater rail','hm',' mV'],['Flags','fl',''],['Seq','seq',''],['Board ms','ms','']];
$('grid').innerHTML=fields.map(f=>`<div class="cell"><div class="k">${f[0]}</div><div class="v" id="f_${f[1]}">—</div></div>`).join('');
let info={rl_ohm:40000,tap_ratio:2,vc_mv:5000};
const pts=[];let times=[];
const rs=(vrl)=>vrl>1?Math.round(info.rl_ohm*(info.vc_mv-vrl)/vrl):null;
const kohm=r=>r===null?'—':r>=1e6?(r/1e6).toFixed(2)+' MΩ':(r/1000).toFixed(1)+' kΩ';
function flagsText(f){const n=[];if(f&1)n.push('USB');if(f&2)n.push('CHG');if(f&4)n.push('T/RH');if(f&8)n.push('ADS');if(f&16)n.push('HTR-FAULT');if(f&32)n.push('BOOT');if(f&64)n.push('HEATERS-OFF');return '0x'+f.toString(16).padStart(2,'0')+(n.length?' '+n.join(' '):'');}
function set(id,v){$('f_'+id).textContent=v;}
function onSample(dv){
  const seq=dv.getUint16(1,true),ms=dv.getUint32(3,true);
  const ch4=dv.getUint16(7,true)/10*info.tap_ratio,lpg=dv.getUint16(9,true)/10*info.tap_ratio;
  const t=dv.getInt16(11,true),h=dv.getUint16(13,true),p=dv.getUint16(15,true),vb=dv.getUint16(17,true),fl=dv.getUint8(19);
  set('ch4',Math.round(ch4));set('lpg',Math.round(lpg));set('rs4',kohm(rs(ch4)));set('rsl',kohm(rs(lpg)));
  set('t',t===-32768?'—':(t/100).toFixed(1)+' °C');set('h',h===65535?'—':(h/100).toFixed(0)+' %');set('p',p===65535?'—':(p/10).toFixed(1)+' hPa');
  set('vb',vb?vb+' mV':'—');set('hm',info.heater_mv?info.heater_mv+' mV':'—');set('fl',flagsText(fl));set('seq',seq);set('ms',ms);
  const now=performance.now();pts.push({x:now,ch4,lpg});times.push(now);
  while(pts.length&&now-pts[0].x>60000)pts.shift();
  times=times.filter(x=>now-x<5000);$('rate').textContent=(times.length/5).toFixed(1)+' samples/s';
  draw();
}
function draw(){
  const c=$('chart'),g=c.getContext('2d'),W=c.width,H=c.height;g.clearRect(0,0,W,H);
  if(pts.length<2)return;
  let lo=Infinity,hi=-Infinity;for(const p of pts){lo=Math.min(lo,p.ch4,p.lpg);hi=Math.max(hi,p.ch4,p.lpg);}
  if(hi-lo<50){const m=(hi+lo)/2;lo=m-25;hi=m+25;}
  const now=pts[pts.length-1].x,x=t=>W-(now-t)/60000*W,y=v=>H-8-(v-lo)/(hi-lo)*(H-16);
  g.strokeStyle='#33312d';g.lineWidth=1;for(let i=0;i<=4;i++){const yy=8+i*(H-16)/4;g.beginPath();g.moveTo(0,yy);g.lineTo(W,yy);g.stroke();}
  g.fillStyle='#9a968c';g.font='12px system-ui';g.fillText(Math.round(hi)+' mV',4,18);g.fillText(Math.round(lo)+' mV',4,H-10);
  for(const [key,col] of [['ch4','#5ec8ff'],['lpg','#ffb454']]){g.strokeStyle=col;g.lineWidth=2;g.beginPath();pts.forEach((p,i)=>{i?g.lineTo(x(p.x),y(p[key])):g.moveTo(x(p.x),y(p[key]))});g.stroke();}
}
function connect(){
  const ws=new WebSocket('ws://'+host+'/ws');ws.binaryType='arraybuffer';
  ws.onopen=()=>{$('link').textContent='socket: connected';$('link').className='pill on';};
  ws.onclose=()=>{$('link').textContent='socket: reconnecting…';$('link').className='pill off';setTimeout(connect,1500);};
  ws.onmessage=ev=>{
    if(typeof ev.data==='string'){const j=JSON.parse(ev.data);
      if(j.type==='info'){info=j;$('board').textContent='board: '+j.board+(j.port?' on '+j.port:'')+' · '+j.interval_ms+' ms';}
      else if(j.type==='csv'){$('raw').textContent=j.line;}
    } else onSample(new DataView(ev.data));
  };
}
connect();
</script></body></html>
"""


# ---------------------------------------------------------------------------
# Self-test: the encoder against the packet layout the app's tests use
# ---------------------------------------------------------------------------
def selftest() -> int:
    pkt = encode_sample(513, 123456, 1234.5, 987.6, 21.37, 55.5, None, 4100, FLAG_ADS_OK | FLAG_BME_OK)
    assert len(pkt) == SAMPLE_LEN, len(pkt)
    v, seq, ms, ch4, lpg, t, h, p, vb, fl = struct.unpack("<BHIHHhHHHB", pkt)
    assert (v, seq, ms) == (1, 513, 123456)
    assert (ch4, lpg) == (12345, 9876)
    assert (t, h, p) == (2137, 5550, U16_MISSING)
    assert (vb, fl) == (4100, FLAG_ADS_OK | FLAG_BME_OK)
    # Missing environment
    pkt = encode_sample(0, 0, 0, 0, None, None, None, 0, 0)
    _, _, _, _, _, t, h, p, _, _ = struct.unpack("<BHIHHhHHHB", pkt)
    assert (t, h, p) == (TEMP_MISSING, U16_MISSING, U16_MISSING)

    rb = parse_row("12345,7,ads,1234.5,987.6,2469,1975,61003,81494,21.37,55.50,,4100,5012,0x0D,1,1", 0)
    assert rb and rb.board == "rev-b" and rb.seq == 7 and rb.flags == 0x0D and rb.pres is None and rb.heater == 5012
    ra = parse_row("5000,RUNNING,2469,2400,69,1975,1900,75,21.37,55.5,1013.2,2026-06-04 14:57:46.123,55.1,-1.2,10.0,8,1", 42)
    assert ra and ra.board == "rev-a" and ra.seq == 42 and abs(ra.ch4_tap - 1234.5) < 1e-6 and ra.flags == (
        FLAG_USB_POWER | FLAG_ADS_OK | FLAG_BME_OK
    )
    assert parse_row("=== CH4 phone board (rev-b) firmware 1.0.0 ===", 0) is None
    assert parse_row("ms,seq,adc,ch4_tap_mv,lpg_tap_mv,ch4_vrl_mv,lpg_vrl_mv,ch4_rs_ohm,lpg_rs_ohm,temp_c,humidity_pct,pressure_hpa,vbat_mv,heater_mv,flags,ble_conn,ble_notify", 0) is None
    assert ws_frame(0x2, b"abc") == b"\x82\x03abc"
    print("selftest ok")
    return 0


def lan_addresses() -> list[str]:
    out: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no packet is sent; picks the default route's address
        out.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for a in socket.gethostbyname_ex(socket.gethostname())[2]:
            if a not in out and not a.startswith("127."):
                out.append(a)
    except OSError:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", help="serial port (default: auto-detect, preferring an Espressif USB device)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--listen", default="0.0.0.0", help="address to serve on (default all interfaces)")
    ap.add_argument("--http-port", type=int, default=8765)
    ap.add_argument("--echo", action="store_true", help="print every serial line")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    hub = Hub()
    Handler.hub = hub
    try:
        server = ThreadingHTTPServer((args.listen, args.http_port), Handler)
    except OSError as e:
        print(f"Cannot listen on {args.listen}:{args.http_port}: {e}")
        return 1
    server.daemon_threads = True

    stop = threading.Event()
    threading.Thread(target=serial_loop, args=(hub, args.port, args.baud, args.echo, stop), name="serial", daemon=True).start()

    addrs = lan_addresses() or ["<this-pc>"]
    print("CH4 serial bridge")
    for a in addrs:
        print(f"  read-out page:  http://{a}:{args.http_port}/")
    print(f"  phone setting:  Bridge PC address = {addrs[0]}   (blank works when Expo runs on this PC)")
    print("  Ctrl+C to stop.")

    def summary() -> None:
        while not stop.is_set():
            time.sleep(5)
            st = hub.status()
            last = hub.last
            if last is None:
                print(f"[status] port={st['port'] or '-'} open={st['port_open']} rows=0 clients={st['clients']}")
            else:
                vrl4, vrll = last.ch4_tap * TAP_RATIO, last.lpg_tap * TAP_RATIO
                t = "—" if last.temp is None else f"{last.temp:.1f}C"
                h = "—" if last.hum is None else f"{last.hum:.0f}%"
                print(
                    f"[status] {last.board} seq={last.seq} ch4={vrl4:.0f}mV lpg={vrll:.0f}mV {t} {h} "
                    f"vbat={last.vbat} flags=0x{last.flags:02X} rows={st['rows']} clients={st['clients']}"
                )

    threading.Thread(target=summary, name="summary", daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
