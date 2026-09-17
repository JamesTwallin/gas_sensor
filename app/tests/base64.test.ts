import { describe, expect, it } from 'vitest';
import { base64ToBytes, base64ToUtf8, bytesToBase64 } from '../src/core/base64';
import { encodeSample, parseSample } from '../src/core/protocol';

const bytes = (...v: number[]) => Uint8Array.from(v);

describe('base64', () => {
  it('matches known vectors', () => {
    expect(bytesToBase64(bytes())).toBe('');
    expect(bytesToBase64(bytes(0x66))).toBe('Zg==');
    expect(bytesToBase64(bytes(0x66, 0x6f))).toBe('Zm8=');
    expect(bytesToBase64(bytes(0x66, 0x6f, 0x6f))).toBe('Zm9v');
    expect(bytesToBase64(bytes(0xff, 0xfe, 0xfd))).toBe('//79');
  });

  it('round-trips every byte value', () => {
    const all = Uint8Array.from({ length: 256 }, (_, i) => i);
    expect(base64ToBytes(bytesToBase64(all))).toEqual(all);
  });

  it('round-trips at each padding length', () => {
    for (let n = 0; n <= 8; n++) {
      const b = Uint8Array.from({ length: n }, (_, i) => (i * 37) & 0xff);
      expect(base64ToBytes(bytesToBase64(b))).toEqual(b);
    }
  });

  it('accepts the URL-safe alphabet and ignores whitespace', () => {
    expect(base64ToBytes('//79')).toEqual(base64ToBytes('__79'));
    expect(base64ToBytes('Zm9v\n')).toEqual(bytes(0x66, 0x6f, 0x6f));
  });

  it('rejects junk', () => {
    expect(() => base64ToBytes('Zm9v$')).toThrow();
  });

  it('carries a Sample packet unchanged', () => {
    const pkt = encodeSample({
      seq: 4242,
      msSinceBoot: 1234567,
      ch4TapMv: 812.3,
      lpgTapMv: 455.1,
      tempC: 19.25,
      humidityPct: 61.5,
      pressureHpa: 1008.4,
      vbatMv: 3912,
      flagsRaw: 0b0100_1101,
    });
    const s = parseSample(base64ToBytes(bytesToBase64(pkt)));
    expect(s.seq).toBe(4242);
    expect(s.msSinceBoot).toBe(1234567);
    expect(s.vbatMv).toBe(3912);
    expect(s.flags.heatersOff).toBe(true);
  });

  it('decodes the Info JSON as UTF-8', () => {
    const json = '{"proto":1,"fw":"1.0.0","board":"rev-b","note":"±5 °C"}';
    const utf8 = new TextEncoder().encode(json);
    expect(base64ToUtf8(bytesToBase64(utf8))).toBe(json);
  });
});
