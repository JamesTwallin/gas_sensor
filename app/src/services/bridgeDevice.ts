// The board via tools/serial_bridge.py on a PC, over a WebSocket.
//
// Same bytes as BLE: binary frames are 20-byte Sample packets, text frames are
// the Info JSON (the bridge also sends {"type":"csv"} lines for its own web
// page; those are ignored here). Control writes are forwarded but the serial
// link has no command channel, so the bridge drops them. Auto-reconnect with
// capped backoff, like BleDeviceLink.

import { parseInfo } from '../core/protocol';
import { bridgeLabel } from '../core/bridge';
import type { DeviceLink, LinkHandlers } from './device';

const CONNECT_TIMEOUT_MS = 8000;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class BridgeDeviceLink implements DeviceLink {
  readonly kind = 'bridge' as const;
  readonly name: string;
  private ws: WebSocket | null = null;
  private wantConnected = false;
  private connected = false;
  private reconnecting = false;

  constructor(
    readonly url: string,
    private h: LinkHandlers,
    private onReady: () => void,
  ) {
    this.name = `USB bridge ${bridgeLabel(url)}`;
  }

  async connect(): Promise<void> {
    this.wantConnected = true;
    try {
      await this.open();
    } catch (e) {
      void this.scheduleReconnect(message(e));
    }
  }

  private open(): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      this.h.onStatus(this.reconnecting ? 'reconnecting' : 'connecting', this.name);
      const ws = new WebSocket(this.url);
      ws.binaryType = 'arraybuffer';
      let settled = false;
      const fail = (err: Error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        try {
          ws.close();
        } catch {
          /* never opened */
        }
        reject(err);
      };
      const timer = setTimeout(() => fail(new Error(`no answer from ${bridgeLabel(this.url)}`)), CONNECT_TIMEOUT_MS);

      ws.onopen = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        this.ws = ws;
        this.connected = true;
        this.h.onStatus('connected', this.name);
        this.onReady();
        resolve();
      };
      ws.onmessage = (ev: WebSocketMessageEvent) => {
        const data: unknown = ev.data;
        if (typeof data === 'string') {
          try {
            const j = JSON.parse(data) as { type?: string };
            if (j.type === 'info') this.h.onInfo(parseInfo(data));
          } catch (e) {
            console.warn('bridge text frame', e);
          }
        } else if (data instanceof ArrayBuffer) {
          try {
            this.h.onSample(new DataView(data));
          } catch (e) {
            console.warn('bad sample payload', e);
          }
        }
      };
      ws.onerror = (ev: Event) => {
        const msg = (ev as { message?: string }).message ?? 'WebSocket error';
        if (!settled) fail(new Error(msg));
        else if (this.wantConnected) console.warn('bridge socket', msg);
      };
      ws.onclose = (ev: WebSocketCloseEvent) => {
        if (!settled) return fail(new Error(`closed (${ev.code})`));
        if (this.ws !== ws) return;
        this.ws = null;
        this.connected = false;
        if (this.wantConnected) void this.scheduleReconnect('link dropped');
        else this.h.onStatus('idle');
      };
    });
  }

  private async scheduleReconnect(reason: string): Promise<void> {
    if (this.reconnecting) return;
    this.reconnecting = true;
    let delay = 1000;
    while (this.wantConnected && !this.connected) {
      this.h.onStatus('reconnecting', `${reason}; retrying in ${Math.round(delay / 1000)} s`);
      await sleep(delay);
      if (!this.wantConnected) break;
      try {
        await this.open();
      } catch (e) {
        reason = message(e);
      }
      delay = Math.min(10_000, delay * 2);
    }
    this.reconnecting = false;
  }

  async disconnect(): Promise<void> {
    this.wantConnected = false;
    const ws = this.ws;
    this.ws = null;
    this.connected = false;
    try {
      ws?.close();
    } catch {
      /* already gone */
    }
    this.h.onStatus('idle');
  }

  async control(bytes: Uint8Array): Promise<void> {
    const ws = this.ws;
    if (!ws || !this.connected) return;
    try {
      ws.send(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer);
    } catch (e) {
      console.warn('Control write failed', e);
    }
  }
}

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
