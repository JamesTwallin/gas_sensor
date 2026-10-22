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
  encodeAnalysis,
  encodeCalibrateAirflow,
  encodeGas2,
  GAS2_CHAR_UUID,
  GAS2_LENGTH,
  parseAnalysis,
  parseGas2,
  parseEvent,
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
      anomaly: false,
      airflow: false,
      co: false,
      g_still: null,
      t_src: null,
      mems: false,
      mems_burnin_h: null,
    });
  });

  it('still reads a proto 1 board with the detector fields', () => {
    const i = parseInfo(
      '{"proto":1,"fw":"1.1.0","board":"rev-e","rl_ohm":40000,"tap_ratio":2.0,"vc_mv":5000,"interval_ms":250,' +
        '"heater_mv":5012,"anomaly":1,"airflow":0,"co":1,"g_still":0.0123,"t_src":2}',
    );
    expect(i.proto).toBe(1);
    expect(i.board).toBe('rev-e');
    expect(i).toMatchObject({ anomaly: true, airflow: false, co: true, g_still: 0.0123, t_src: 2 });
    expect(i.mems).toBe(false);
    expect(i.mems_burnin_h).toBeNull();
  });

  it('parses a proto 2 rev F Info with the MEMS fields', () => {
    const i = parseInfo(
      '{"proto":2,"fw":"1.2.0","board":"rev-f","rl_ohm":40000,"tap_ratio":2.0,"vc_mv":5000,"interval_ms":250,' +
        '"heater_mv":5001,"anomaly":1,"airflow":1,"co":0,"g_still":0.0000,"t_src":0,"mems":1,"mems_burnin_h":17}',
    );
    expect(i.proto).toBe(2);
    expect(i.board).toBe('rev-f');
    expect(i.mems).toBe(true);
    expect(i.mems_burnin_h).toBe(17);
    expect(i.g_still).toBe(0);
    expect(i.rl_ohm).toBe(40000);
    expect(parseInfo('{"proto":2,"mems":0,"mems_burnin_h":"x"}')).toMatchObject({ mems: false, mems_burnin_h: null });
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

describe('Analysis and Event packets', () => {
  it('round-trips an Analysis packet', () => {
    const bytes = encodeAnalysis({
      seq: 0x1234,
      ch4ResMv: -12.3,
      lpgResMv: 45.6,
      ch4SigmaMv: 3.21,
      lpgSigmaMv: null,
      airflowRawMv: 1110,
      airflowIndex: 0.456,
      coPpm: null,
      flags: 0b1000_0101,
      eventClass: 6,
      eventRatio: 1.37,
    });
    const a = parseAnalysis(bytes);
    expect(a.seq).toBe(0x1234);
    expect(a.ch4ResMv).toBeCloseTo(-12.3, 6);
    expect(a.lpgResMv).toBeCloseTo(45.6, 6);
    expect(a.ch4SigmaMv).toBeCloseTo(3.21, 6);
    expect(a.lpgSigmaMv).toBeNull();
    expect(a.airflowRawMv).toBe(1110);
    expect(a.airflowIndex).toBeCloseTo(0.456, 6);
    expect(a.coPpm).toBeNull();
    expect(a.anomalyCh4).toBe(true);
    expect(a.anomalyLpg).toBe(false);
    expect(a.ready).toBe(true);
    expect(a.calibrating).toBe(true);
    expect(a.eventClass).toBe('UNRESOLVED');
    expect(a.eventRatio).toBeCloseTo(1.4, 6);
  });

  it('marks missing residuals before the detector is ready', () => {
    const a = parseAnalysis(
      encodeAnalysis({
        seq: 1, ch4ResMv: null, lpgResMv: null, ch4SigmaMv: null, lpgSigmaMv: null,
        airflowRawMv: null, airflowIndex: null, coPpm: 3.7, flags: 0, eventClass: 0, eventRatio: 0,
      }),
    );
    expect(a.ch4ResMv).toBeNull();
    expect(a.ready).toBe(false);
    expect(a.coPpm).toBeCloseTo(3.7, 6);
    expect(a.eventClass).toBe('');
    expect(a.eventRatio).toBeNull();
  });

  it('parses a hand-built Event packet', () => {
    const b = new Uint8Array(20);
    const dv = new DataView(b.buffer);
    b[0] = 1;
    dv.setUint16(1, 9, true);
    b[3] = 3; // HEAVY_HC
    b[4] = 77;
    dv.setUint16(5, 125, true); // 12.5 s
    dv.setInt16(7, 155, true); // 15.5 mV
    dv.setInt16(9, 802, true); // 80.2 mV
    dv.setUint16(11, 19, true); // 0.19
    dv.setInt16(13, -40, true); // LPG led by 4 s
    dv.setInt16(15, -0x8000, true);
    dv.setInt16(17, -0x8000, true);
    b[19] = 0b0000_1011;
    const e = parseEvent(b);
    expect(e.eventClass).toBe('HEAVY_HC');
    expect(e.confidence).toBe(77);
    expect(e.durationS).toBeCloseTo(12.5, 6);
    expect(e.ch4PeakMv).toBeCloseTo(15.5, 6);
    expect(e.lpgPeakMv).toBeCloseTo(80.2, 6);
    expect(e.ratio).toBeCloseTo(0.19, 6);
    expect(e.leadS).toBeCloseTo(-4, 6);
    expect(e.airflowMean).toBeNull();
    expect(e.coPeakPpm).toBeNull();
    expect([e.ch4Raised, e.lpgRaised, e.ch4Detected, e.lpgDetected]).toEqual([true, true, false, true]);
  });

  it('encodes the still-air calibration opcode', () => {
    expect(Array.from(encodeCalibrateAirflow())).toEqual([0x04, 60]);
    expect(Array.from(encodeCalibrateAirflow(500))).toEqual([0x04, 255]);
  });
});

describe('Gas2 packet (rev F)', () => {
  it('uses the shared service base', () => {
    expect(GAS2_CHAR_UUID).toBe('6d1a0007-8f3e-4b8a-9c57-2f6c0e3a7b10');
  });

  it('parses a hand-built packet', () => {
    const b = new Uint8Array(GAS2_LENGTH);
    b[0] = 1;
    b.set([0x34, 0x12], 1); // seq 0x1234
    b.set([0x39, 0x30], 3); // mems_a tap 12345 -> 1234.5 mV
    b.set([0xe8, 0x03], 5); // mems_b tap 1000 -> 100.0 mV
    b.set([0x85, 0xff], 7); // mems_a res -123 -> -12.3 mV
    b.set([0x2d, 0x00], 9); // mems_a sigma 45 -> 4.5 mV
    b.set([0x7b, 0x00], 11); // mems_b res 123 -> 12.3 mV
    b.set([0x0a, 0x00], 13); // mems_b sigma 10 -> 1.0 mV
    b[15] = 0b0011_1110; // B anomaly, blade, heater, warm, burn-in done
    b.set([0xe4, 0x0c], 16); // 3300 mV
    const g = parseGas2(b);
    expect(g).toEqual({
      seq: 0x1234,
      memsATapMv: 1234.5,
      memsBTapMv: 100,
      memsAResMv: -12.3,
      memsASigmaMv: 4.5,
      memsBResMv: 12.3,
      memsBSigmaMv: 1,
      flagsRaw: 0b0011_1110,
      anomalyA: false,
      anomalyB: true,
      bladeFitted: true,
      heaterOn: true,
      warm: true,
      burnInDone: true,
      rail3v3Mv: 3300,
    });
  });

  it('maps the missing sentinels to null', () => {
    const b = new Uint8Array(GAS2_LENGTH);
    b[0] = 1;
    b.set([0xff, 0xff, 0xff, 0xff], 3); // both taps
    b.set([0xff, 0x7f, 0xff, 0xff, 0xff, 0x7f, 0xff, 0xff], 7); // res/sigma A and B
    b.set([0xff, 0xff], 16); // rail
    const g = parseGas2(b);
    expect([g.memsATapMv, g.memsBTapMv, g.memsAResMv, g.memsASigmaMv, g.memsBResMv, g.memsBSigmaMv, g.rail3v3Mv]).toEqual(
      [null, null, null, null, null, null, null],
    );
    // 0x8000 is a real (most negative) residual in Gas2, unlike Analysis.
    b.set([0x00, 0x80], 7);
    expect(parseGas2(b).memsAResMv).toBe(-3276.8);
  });

  it('round-trips through encodeGas2, nulls included', () => {
    const f = {
      seq: 65535,
      memsATapMv: 1650.1,
      memsBTapMv: null,
      memsAResMv: -0.4,
      memsASigmaMv: 2.2,
      memsBResMv: null,
      memsBSigmaMv: null,
      flags: 0b0001_0101,
      rail3v3Mv: 3289,
    };
    const bytes = encodeGas2(f);
    expect(bytes.length).toBe(GAS2_LENGTH);
    expect([bytes[18], bytes[19]]).toEqual([0, 0]);
    const g = parseGas2(bytes);
    expect(g.seq).toBe(65535);
    expect(g.memsATapMv).toBeCloseTo(1650.1, 5);
    expect(g.memsBTapMv).toBeNull();
    expect(g.memsAResMv).toBeCloseTo(-0.4, 5);
    expect(g.memsASigmaMv).toBeCloseTo(2.2, 5);
    expect(g.memsBResMv).toBeNull();
    expect(g.memsBSigmaMv).toBeNull();
    expect(g.rail3v3Mv).toBe(3289);
    expect([g.anomalyA, g.anomalyB, g.bladeFitted, g.heaterOn, g.warm, g.burnInDone]).toEqual([
      true,
      false,
      true,
      false,
      true,
      false,
    ]);
    // Real values never collide with the sentinels.
    const big = parseGas2(encodeGas2({ ...f, memsATapMv: 1e9, memsAResMv: 1e9, rail3v3Mv: 1e9 }));
    expect(big.memsATapMv).toBeCloseTo(6553.4, 5);
    expect(big.memsAResMv).toBeCloseTo(3276.6, 5);
    expect(big.rail3v3Mv).toBe(0xfffe);
  });

  it('rejects short packets and unknown versions', () => {
    expect(() => parseGas2(new Uint8Array(19))).toThrow(/too short/);
    const b = encodeGas2({
      seq: 1,
      memsATapMv: null,
      memsBTapMv: null,
      memsAResMv: null,
      memsASigmaMv: null,
      memsBResMv: null,
      memsBSigmaMv: null,
      flags: 0,
      rail3v3Mv: null,
    });
    b[0] = 2;
    expect(() => parseGas2(b)).toThrow(/version/);
  });
});
