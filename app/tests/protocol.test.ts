import { describe, expect, it } from 'vitest';
import {
  DEFAULT_INFO,
  FLAG_ADS_OK,
  FLAG_BME_OK,
  FLAG_BUTTON,
  FLAG_HEATERS_OFF,
  FLAG_USB_POWER,
  SAMPLE_LENGTH,
  decodeFlags,
  encodeIdentify,
  encodeSample,
  encodeSetInterval,
  encodeSetLed,
  parseInfo,
  parseSample,
} from '../src/core/protocol';

/** Hand-built packet, byte by byte, independent of encodeSample. */
function handPacket(): Uint8Array {
  const b = new Uint8Array(20);
  b[0] = 1; // version
  b.set([0x34, 0x12], 1); // seq 0x1234
  b.set([0x78, 0x56, 0x34, 0x12], 3); // ms 0x12345678
  b.set([0x10, 0x27], 7); // ch4_tap 10000 -> 1000.0 mV
  b.set([0x39, 0x30], 9); // lpg_tap 12345 -> 1234.5 mV
  b.set([0x3d, 0xf6], 11); // temp -2499 -> -24.99 C
  b.set([0x88, 0x13], 13); // hum 5000 -> 50.00 %
  b.set([0x9a, 0x27], 15); // pres 10138 -> 1013.8 hPa
  b.set([0x68, 0x10], 17); // vbat 4200 mV
  b[19] = 0b0010_1101; // USB, BME ok, ADS ok, button
  return b;
}

describe('parseSample', () => {
  it('decodes every field little-endian with the spec scaling', () => {
    const s = parseSample(handPacket());
    expect(s.version).toBe(1);
    expect(s.seq).toBe(0x1234);
    expect(s.msSinceBoot).toBe(0x12345678);
    expect(s.ch4TapMv).toBeCloseTo(1000.0, 6);
    expect(s.lpgTapMv).toBeCloseTo(1234.5, 6);
    expect(s.tempC).toBeCloseTo(-24.99, 6);
    expect(s.humidityPct).toBeCloseTo(50.0, 6);
    expect(s.pressureHpa).toBeCloseTo(1013.8, 6);
    expect(s.vbatMv).toBe(4200);
    expect(s.flags).toEqual({
      usbPower: true,
      charging: false,
      bmeOk: true,
      adsOk: true,
      heaterFault: false,
      button: true,
      heatersOff: false,
    });
  });

  it('maps the missing sentinels to null', () => {
    const b = handPacket();
    b.set([0x00, 0x80], 11); // 0x8000
    b.set([0xff, 0xff], 13);
    b.set([0xff, 0xff], 15);
    const s = parseSample(b);
    expect(s.tempC).toBeNull();
    expect(s.humidityPct).toBeNull();
    expect(s.pressureHpa).toBeNull();
  });

  it('handles u32 ms and u16 seq at their maxima', () => {
    const b = handPacket();
    b.set([0xff, 0xff], 1);
    b.set([0xff, 0xff, 0xff, 0xff], 3);
    const s = parseSample(b);
    expect(s.seq).toBe(65535);
    expect(s.msSinceBoot).toBe(4294967295);
  });

  it('accepts a DataView with an offset (as BLE stacks deliver)', () => {
    const big = new Uint8Array(30);
    big.set(handPacket(), 5);
    const s = parseSample(new DataView(big.buffer, 5, 20));
    expect(s.seq).toBe(0x1234);
    expect(s.vbatMv).toBe(4200);
  });

  it('rejects short packets and unknown versions', () => {
    expect(() => parseSample(new Uint8Array(19))).toThrow(/short/);
    const b = handPacket();
    b[0] = 2;
    expect(() => parseSample(b)).toThrow(/version/);
  });

  it('decodes heater flags bit4 and bit6', () => {
    expect(decodeFlags(1 << 4).heaterFault).toBe(true);
    expect(decodeFlags(FLAG_HEATERS_OFF).heatersOff).toBe(true);
    expect(decodeFlags(0xff)).toEqual({
      usbPower: true,
      charging: true,
      bmeOk: true,
      adsOk: true,
      heaterFault: true,
      button: true,
      heatersOff: true,
    });
  });

  it('round-trips through encodeSample', () => {
    const pkt = encodeSample({
      seq: 70000, // wraps
      msSinceBoot: 123456,
      ch4TapMv: 1111.1,
      lpgTapMv: 0,
      tempC: 21.37,
      humidityPct: null,
      pressureHpa: 998.2,
      vbatMv: 3777,
      flagsRaw: FLAG_USB_POWER | FLAG_BME_OK | FLAG_ADS_OK | FLAG_BUTTON,
    });
    expect(pkt.length).toBe(SAMPLE_LENGTH);
    const s = parseSample(pkt);
    expect(s.seq).toBe(70000 & 0xffff);
    expect(s.msSinceBoot).toBe(123456);
    expect(s.ch4TapMv).toBeCloseTo(1111.1, 6);
    expect(s.tempC).toBeCloseTo(21.37, 6);
    expect(s.humidityPct).toBeNull();
    expect(s.pressureHpa).toBeCloseTo(998.2, 6);
    expect(s.vbatMv).toBe(3777);
    expect(s.flags.button).toBe(true);
  });
});

describe('parseInfo', () => {
  it('parses the spec example', () => {
    const j =
      '{"proto":1,"fw":"1.0.0","board":"rev-b","rl_ohm":40000,"tap_ratio":2.0,"vc_mv":5000,"interval_ms":250,"heater_mv":5012}';
    expect(parseInfo(new TextEncoder().encode(j))).toEqual({
      proto: 1,
      fw: '1.0.0',
      board: 'rev-b',
      rl_ohm: 40000,
      tap_ratio: 2,
      vc_mv: 5000,
      interval_ms: 250,
      heater_mv: 5012,
    });
  });

  it('falls back to defaults for missing or invalid fields and ignores trailing NULs', () => {
    const i = parseInfo('{"rl_ohm":0,"tap_ratio":"x"}\0\0');
    expect(i.rl_ohm).toBe(DEFAULT_INFO.rl_ohm);
    expect(DEFAULT_INFO.rl_ohm).toBe(40000);
    expect(i.tap_ratio).toBe(2);
    expect(i.vc_mv).toBe(5000);
    expect(i.heater_mv).toBeNull();
  });
});

describe('control encoding', () => {
  it('encodes opcodes', () => {
    expect([...encodeSetInterval(250)]).toEqual([0x01, 0xfa, 0x00]);
    expect([...encodeSetInterval(99999)]).toEqual([0x01, 0x88, 0x13]); // clamped to 5000
    expect([...encodeSetInterval(1)]).toEqual([0x01, 100, 0]);
    expect([...encodeIdentify()]).toEqual([0x02]);
    expect([...encodeSetLed(35, 18, 0)]).toEqual([0x03, 35, 18, 0]);
    expect([...encodeSetLed(300, -5, 1.4)]).toEqual([0x03, 255, 0, 1]);
  });
});
