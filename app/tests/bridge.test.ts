import { describe, expect, it } from 'vitest';
import { BRIDGE_PORT, bridgeLabel, bridgeUrl, hostFromScriptUrl } from '../src/core/bridge';
import { DEFAULT_SETTINGS, sanitizeSettings } from '../src/core/settings';

describe('hostFromScriptUrl', () => {
  it('takes the host out of a Metro bundle URL', () => {
    expect(hostFromScriptUrl('http://192.168.1.20:8081/index.bundle?platform=android&dev=true')).toBe(
      '192.168.1.20',
    );
    expect(hostFromScriptUrl('http://my-pc.local:8081/index.bundle')).toBe('my-pc.local');
    expect(hostFromScriptUrl('exp://10.0.0.7:8081/--/x')).toBe('10.0.0.7');
  });

  it('is null for release bundles and junk', () => {
    expect(hostFromScriptUrl(null)).toBeNull();
    expect(hostFromScriptUrl(undefined)).toBeNull();
    expect(hostFromScriptUrl('')).toBeNull();
    expect(hostFromScriptUrl('index.android.bundle')).toBeNull();
    expect(hostFromScriptUrl('file:///data/app/index.android.bundle')).toBeNull();
  });
});

describe('bridgeUrl', () => {
  it('prefers an explicit host, adding the default port', () => {
    expect(bridgeUrl('192.168.0.9', 'http://1.2.3.4:8081/x')).toBe(`ws://192.168.0.9:${BRIDGE_PORT}/ws`);
    expect(bridgeUrl(' 192.168.0.9:9000 ', null)).toBe('ws://192.168.0.9:9000/ws');
    expect(bridgeUrl('ws://a.b:1/ws', null)).toBe('ws://a.b:1/ws');
  });

  it('falls back to the Metro host', () => {
    expect(bridgeUrl('', 'http://192.168.1.20:8081/index.bundle')).toBe(`ws://192.168.1.20:${BRIDGE_PORT}/ws`);
    expect(bridgeUrl('', null)).toBeNull();
  });
});

describe('bridgeLabel', () => {
  it('shows just the host', () => {
    expect(bridgeLabel(`ws://192.168.1.20:${BRIDGE_PORT}/ws`)).toBe('192.168.1.20');
    expect(bridgeLabel('ws://192.168.1.20:9000/ws')).toBe('192.168.1.20:9000');
  });
});

describe('settings: bridge fields', () => {
  it('defaults off with a blank host', () => {
    expect(DEFAULT_SETTINGS.usbBridge).toBe(false);
    expect(DEFAULT_SETTINGS.bridgeHost).toBe('');
  });

  it('keeps a stored string host and drops the wrong type', () => {
    expect(sanitizeSettings({ bridgeHost: '10.0.0.2', usbBridge: true })).toMatchObject({
      bridgeHost: '10.0.0.2',
      usbBridge: true,
    });
    expect(sanitizeSettings({ bridgeHost: 42 }).bridgeHost).toBe('');
  });
});
