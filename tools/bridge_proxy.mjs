// Plain TCP forwarder: listens on 0.0.0.0:8765 and pipes to 127.0.0.1:8766.
//
// Why: Windows Firewall on this PC allows node.exe inbound but blocks python.exe,
// so the phone cannot reach tools/serial_bridge.py directly over Wi-Fi. Run the
// bridge on the loopback-only port and let Node be the program that listens:
//
//   python tools/serial_bridge.py --listen 127.0.0.1 --http-port 8766
//   node tools/bridge_proxy.mjs
//
// The durable fix is a firewall rule for TCP 8765 (needs an admin shell):
//   New-NetFirewallRule -DisplayName "CH4 bridge" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow
// after which this proxy is unnecessary.

import net from 'node:net';

const LISTEN_PORT = Number(process.argv[2] ?? 8765);
const TARGET_PORT = Number(process.argv[3] ?? 8766);

const server = net.createServer((client) => {
  const upstream = net.connect(TARGET_PORT, '127.0.0.1');
  const drop = () => {
    client.destroy();
    upstream.destroy();
  };
  client.on('error', drop);
  upstream.on('error', drop);
  client.pipe(upstream);
  upstream.pipe(client);
});

server.on('error', (e) => {
  console.error(`bridge_proxy: cannot listen on ${LISTEN_PORT}: ${e.message}`);
  process.exit(1);
});

server.listen(LISTEN_PORT, '0.0.0.0', () => {
  console.log(`bridge_proxy: 0.0.0.0:${LISTEN_PORT} -> 127.0.0.1:${TARGET_PORT}`);
});
