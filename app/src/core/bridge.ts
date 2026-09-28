// USB-bridge addressing. tools/serial_bridge.py on a PC relays the board's USB
// serial stream as protocol-v1 packets over a WebSocket, for Expo Go (which has
// no Bluetooth module) and for bench work. Pure: no networking here.

export const BRIDGE_PORT = 8765;

/**
 * Host of the Metro / Expo dev server this JS bundle was loaded from, taken
 * from the bundle URL (e.g. "http://192.168.0.105:8081/index.bundle?..."),
 * or null for a release bundle / unknown URL.
 */
export function hostFromScriptUrl(scriptURL: string | null | undefined): string | null {
  if (!scriptURL) return null;
  const m = /^[a-z][a-z0-9+.-]*:\/\/(\[[^\]]+\]|[^/:?#]+)(?::\d+)?/i.exec(scriptURL);
  if (!m) return null;
  return m[1];
}

/**
 * The bridge's WebSocket URL. An explicit setting wins: a host ("192.168.0.9"),
 * host:port, or a full ws:// URL. Blank means "the PC that served the bundle",
 * i.e. the machine running Expo, which is normally also the one with the board
 * plugged in. Null when neither is known.
 */
export function bridgeUrl(setting: string, scriptURL?: string | null): string | null {
  const s = setting.trim();
  if (s) {
    if (/^wss?:\/\//i.test(s)) return s;
    const hasPort = /:\d+$/.test(s) && !/^\[.*\]$/.test(s);
    return `ws://${s}${hasPort ? '' : `:${BRIDGE_PORT}`}/ws`;
  }
  const host = hostFromScriptUrl(scriptURL);
  return host ? `ws://${host}:${BRIDGE_PORT}/ws` : null;
}

/** Short label for the link pill: the host without scheme, port or path. */
export function bridgeLabel(url: string): string {
  const m = /^wss?:\/\/([^/]+)/i.exec(url);
  return m ? m[1].replace(new RegExp(`:${BRIDGE_PORT}$`), '') : url;
}
