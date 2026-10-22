// BLE protocol v1 for the rev B phone-companion board.
// Source of truth: docs/phone_board.md, "BLE protocol (v1)". Pure: no DOM, no BLE.

export const SERVICE_UUID = '6d1a0001-8f3e-4b8a-9c57-2f6c0e3a7b10';
export const SAMPLE_CHAR_UUID = '6d1a0002-8f3e-4b8a-9c57-2f6c0e3a7b10';
export const INFO_CHAR_UUID = '6d1a0003-8f3e-4b8a-9c57-2f6c0e3a7b10';
export const CONTROL_CHAR_UUID = '6d1a0004-8f3e-4b8a-9c57-2f6c0e3a7b10';

export const SAMPLE_LENGTH = 20;
/**
 * Version byte of the Sample packet (unchanged since v1). The Info JSON "proto"
 * is 2 on current firmware (rev F added the Gas2 notification); proto 1 and 2
 * share the Sample, Analysis and Event layouts, so both are accepted.
 */
export const PROTOCOL_VERSION = 1;
/** Highest Info JSON "proto" this app understands. */
export const INFO_PROTO_MAX = 2;

export const FLAG_USB_POWER = 1 << 0;
export const FLAG_CHARGING = 1 << 1;
export const FLAG_BME_OK = 1 << 2;
export const FLAG_ADS_OK = 1 << 3;
export const FLAG_HEATER_FAULT = 1 << 4;
export const FLAG_BUTTON = 1 << 5;
/** Firmware has switched the heaters off (low-battery cutoff): gas readings are invalid. */
export const FLAG_HEATERS_OFF = 1 << 6;

const TEMP_MISSING = -0x8000; // 0x8000 as i16
const U16_MISSING = 0xffff;

export interface Flags {
  usbPower: boolean;
  charging: boolean;
  bmeOk: boolean;
  /** false = taps came from the ESP32 fallback ADC */
  adsOk: boolean;
  /** heater rail outside 4.8–5.2 V (only meaningful when adsOk) */
  heaterFault: boolean;
  /** BOOT button pressed since the previous sample: re-zero / mark */
  button: boolean;
  /** bit6: heaters switched off by the firmware (low-battery cutoff) */
  heatersOff: boolean;
}

export interface Sample {
  version: number;
  seq: number;
  msSinceBoot: number;
  /** ADC tap voltage (VRL / tap_ratio), mV */
  ch4TapMv: number;
  lpgTapMv: number;
  tempC: number | null;
  humidityPct: number | null;
  pressureHpa: number | null;
  vbatMv: number;
  flagsRaw: number;
  flags: Flags;
}

export function decodeFlags(raw: number): Flags {
  return {
    usbPower: (raw & FLAG_USB_POWER) !== 0,
    charging: (raw & FLAG_CHARGING) !== 0,
    bmeOk: (raw & FLAG_BME_OK) !== 0,
    adsOk: (raw & FLAG_ADS_OK) !== 0,
    heaterFault: (raw & FLAG_HEATER_FAULT) !== 0,
    button: (raw & FLAG_BUTTON) !== 0,
    heatersOff: (raw & FLAG_HEATERS_OFF) !== 0,
  };
}

function toDataView(buf: DataView | ArrayBuffer | Uint8Array): DataView {
  if (buf instanceof DataView) return buf;
  if (buf instanceof Uint8Array) return new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  return new DataView(buf);
}

/** Parse one 20-byte Sample notification. Throws on wrong length or version. */
export function parseSample(buf: DataView | ArrayBuffer | Uint8Array): Sample {
  const dv = toDataView(buf);
  if (dv.byteLength < SAMPLE_LENGTH) {
    throw new Error(`sample packet too short: ${dv.byteLength} bytes (want ${SAMPLE_LENGTH})`);
  }
  const version = dv.getUint8(0);
  if (version !== PROTOCOL_VERSION) {
    throw new Error(`unsupported sample version ${version}`);
  }
  const temp = dv.getInt16(11, true);
  const hum = dv.getUint16(13, true);
  const pres = dv.getUint16(15, true);
  const flagsRaw = dv.getUint8(19);
  return {
    version,
    seq: dv.getUint16(1, true),
    msSinceBoot: dv.getUint32(3, true),
    ch4TapMv: dv.getUint16(7, true) / 10,
    lpgTapMv: dv.getUint16(9, true) / 10,
    tempC: temp === TEMP_MISSING ? null : temp / 100,
    humidityPct: hum === U16_MISSING ? null : hum / 100,
    pressureHpa: pres === U16_MISSING ? null : pres / 10,
    vbatMv: dv.getUint16(17, true),
    flagsRaw,
    flags: decodeFlags(flagsRaw),
  };
}

export interface SampleFields {
  seq: number;
  msSinceBoot: number;
  ch4TapMv: number;
  lpgTapMv: number;
  tempC: number | null;
  humidityPct: number | null;
  pressureHpa: number | null;
  vbatMv: number;
  flagsRaw: number;
}

const clampU16 = (v: number) => Math.max(0, Math.min(0xffff, Math.round(v)));

/** Encode a Sample packet (inverse of parseSample). Used by the simulator and tests. */
export function encodeSample(s: SampleFields): Uint8Array {
  const out = new Uint8Array(SAMPLE_LENGTH);
  const dv = new DataView(out.buffer);
  dv.setUint8(0, PROTOCOL_VERSION);
  dv.setUint16(1, s.seq & 0xffff, true);
  dv.setUint32(3, s.msSinceBoot >>> 0, true);
  dv.setUint16(7, clampU16(s.ch4TapMv * 10), true);
  dv.setUint16(9, clampU16(s.lpgTapMv * 10), true);
  dv.setInt16(
    11,
    s.tempC === null ? TEMP_MISSING : Math.max(-32767, Math.min(32767, Math.round(s.tempC * 100))),
    true,
  );
  // 0xFFFF is the missing sentinel, so real values clamp to 0xFFFE.
  dv.setUint16(13, s.humidityPct === null ? U16_MISSING : Math.min(0xfffe, clampU16(s.humidityPct * 100)), true);
  dv.setUint16(15, s.pressureHpa === null ? U16_MISSING : Math.min(0xfffe, clampU16(s.pressureHpa * 10)), true);
  dv.setUint16(17, clampU16(s.vbatMv), true);
  dv.setUint8(19, s.flagsRaw & 0xff);
  return out;
}

export interface DeviceInfo {
  proto: number;
  fw: string;
  board: string;
  rl_ohm: number;
  tap_ratio: number;
  vc_mv: number;
  interval_ms: number;
  heater_mv: number | null;
  /** Firmware built with the anomaly detector (Analysis/Event characteristics). */
  anomaly: boolean;
  /** Airflow thermistor input built in. */
  airflow: boolean;
  /** CO sensor input built in. */
  co: boolean;
  /** Still-air airflow calibration constant; null when not reported. */
  g_still: number | null;
  /** Where temperature and humidity come from (firmware enum); null when not reported. */
  t_src: number | null;
  /** Rev F: MEMS blade fitted. False on boards without the field. */
  mems: boolean;
  /** Rev F: cumulative MEMS heater-on hours; null when not reported. */
  mems_burnin_h: number | null;
}

/** Values from the spec, used until (or if) the Info characteristic can be read. */
export const DEFAULT_INFO: DeviceInfo = {
  proto: 1,
  fw: '?',
  board: 'rev-b',
  rl_ohm: 40000,
  tap_ratio: 2.0,
  vc_mv: 5000,
  interval_ms: 250,
  heater_mv: null,
  anomaly: false,
  airflow: false,
  co: false,
  g_still: null,
  t_src: null,
  mems: false,
  mems_burnin_h: null,
};

const positive = (v: unknown, fallback: number): number =>
  typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : fallback;

const finite = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
/** 0/1 (or true/false) in the JSON; anything else is false. */
const flag = (v: unknown): boolean => v === true || (typeof v === 'number' && v !== 0);

/** Parse the Info JSON (UTF-8 bytes or string). Missing/invalid fields fall back to defaults. */
export function parseInfo(input: string | DataView | ArrayBuffer | Uint8Array): DeviceInfo {
  let text: string;
  if (typeof input === 'string') {
    text = input;
  } else {
    const dv = toDataView(input);
    text = new TextDecoder('utf-8').decode(new Uint8Array(dv.buffer, dv.byteOffset, dv.byteLength));
  }
  // Tolerate trailing NULs from a fixed-size characteristic buffer.
  text = text.replace(/\0+$/, '').trim();
  const j = JSON.parse(text) as Record<string, unknown>;
  return {
    proto: typeof j.proto === 'number' ? j.proto : DEFAULT_INFO.proto,
    fw: typeof j.fw === 'string' ? j.fw : DEFAULT_INFO.fw,
    board: typeof j.board === 'string' ? j.board : DEFAULT_INFO.board,
    rl_ohm: positive(j.rl_ohm, DEFAULT_INFO.rl_ohm),
    tap_ratio: positive(j.tap_ratio, DEFAULT_INFO.tap_ratio),
    vc_mv: positive(j.vc_mv, DEFAULT_INFO.vc_mv),
    interval_ms: positive(j.interval_ms, DEFAULT_INFO.interval_ms),
    heater_mv: typeof j.heater_mv === 'number' ? j.heater_mv : null,
    anomaly: flag(j.anomaly),
    airflow: flag(j.airflow),
    co: flag(j.co),
    g_still: finite(j.g_still),
    t_src: finite(j.t_src),
    mems: flag(j.mems),
    mems_burnin_h: finite(j.mems_burnin_h),
  };
}

export const OP_SET_INTERVAL = 0x01;
export const OP_IDENTIFY = 0x02;
export const OP_SET_LED = 0x03;

export const INTERVAL_MIN_MS = 100;
export const INTERVAL_MAX_MS = 5000;

export function encodeSetInterval(intervalMs: number): Uint8Array {
  const v = Math.max(INTERVAL_MIN_MS, Math.min(INTERVAL_MAX_MS, Math.round(intervalMs)));
  return new Uint8Array([OP_SET_INTERVAL, v & 0xff, (v >> 8) & 0xff]);
}

export function encodeIdentify(): Uint8Array {
  return new Uint8Array([OP_IDENTIFY]);
}

export function encodeSetLed(r: number, g: number, b: number): Uint8Array {
  const c = (x: number) => Math.max(0, Math.min(255, Math.round(x)));
  return new Uint8Array([OP_SET_LED, c(r), c(g), c(b)]);
}

// ---- Anomaly detector (firmware 1.1.0+): Analysis and Event notifications -------
// docs/phone_board.md, "Analysis" and "Event". Older firmware has neither
// characteristic; the app then leaves the detector CSV columns blank.

export const ANALYSIS_CHAR_UUID = '6d1a0005-8f3e-4b8a-9c57-2f6c0e3a7b10';
export const EVENT_CHAR_UUID = '6d1a0006-8f3e-4b8a-9c57-2f6c0e3a7b10';
export const ANALYSIS_LENGTH = 20;
export const EVENT_LENGTH = 20;
export const ANALYSIS_VERSION = 1;

export const OP_CALIBRATE_AIRFLOW = 0x04;

/** Event classes, indexed by the wire value (0 = none). */
export const EVENT_CLASSES = [
  '',
  'NATURAL_GAS',
  'EXHAUST',
  'HEAVY_HC',
  'THERMAL',
  'LOW_AIRFLOW',
  'UNRESOLVED',
  'UNCLASSIFIED',
] as const;
export type EventClass = (typeof EVENT_CLASSES)[number];

const I16_MISSING = -0x8000;
const className = (v: number): EventClass => EVENT_CLASSES[v] ?? '';

export interface Analysis {
  seq: number;
  /** Detection residuals (mV); null until the detector is ready. */
  ch4ResMv: number | null;
  lpgResMv: number | null;
  /** Robust spread of the residuals (mV); null until known. */
  ch4SigmaMv: number | null;
  lpgSigmaMv: number | null;
  /** Thermistor pin voltage (mV); null when no thermistor is fitted. */
  airflowRawMv: number | null;
  airflowIndex: number | null;
  /** CO reading (ppm); null when no CO sensor is fitted or it is silent. */
  coPpm: number | null;
  anomalyCh4: boolean;
  anomalyLpg: boolean;
  ready: boolean;
  suppressed: boolean;
  eventOpen: boolean;
  calibrating: boolean;
  /** Non-empty only on the sample on which an event closed. */
  eventClass: EventClass;
  /** CH4-to-LPG ratio of that event (0.1 resolution, capped at 25.5); null when no event. */
  eventRatio: number | null;
}

export function parseAnalysis(buf: DataView | ArrayBuffer | Uint8Array): Analysis {
  const dv = toDataView(buf);
  if (dv.byteLength < ANALYSIS_LENGTH) throw new Error(`analysis packet too short: ${dv.byteLength} bytes`);
  const version = dv.getUint8(0);
  if (version !== ANALYSIS_VERSION) throw new Error(`unsupported analysis version ${version}`);
  const i16 = (o: number, scale: number) => {
    const v = dv.getInt16(o, true);
    return v === I16_MISSING ? null : v / scale;
  };
  const flags = dv.getUint8(17);
  const sigma = (o: number) => {
    const v = dv.getUint16(o, true);
    return v === 0 ? null : v / 100;
  };
  const raw = dv.getUint16(11, true);
  const co = dv.getUint16(15, true);
  const cls = className(dv.getUint8(18));
  return {
    seq: dv.getUint16(1, true),
    ch4ResMv: i16(3, 10),
    lpgResMv: i16(5, 10),
    ch4SigmaMv: sigma(7),
    lpgSigmaMv: sigma(9),
    airflowRawMv: raw === 0 ? null : raw,
    airflowIndex: i16(13, 1000),
    coPpm: co === U16_MISSING ? null : co / 10,
    anomalyCh4: (flags & 1) !== 0,
    anomalyLpg: (flags & 2) !== 0,
    ready: (flags & 4) !== 0,
    suppressed: (flags & 8) !== 0,
    eventOpen: (flags & 16) !== 0,
    calibrating: (flags & 128) !== 0,
    eventClass: cls,
    eventRatio: cls ? dv.getUint8(19) / 10 : null,
  };
}

export interface AnalysisFields {
  seq: number;
  ch4ResMv: number | null;
  lpgResMv: number | null;
  ch4SigmaMv: number | null;
  lpgSigmaMv: number | null;
  airflowRawMv: number | null;
  airflowIndex: number | null;
  coPpm: number | null;
  flags: number;
  eventClass: number;
  eventRatio: number;
}

const i16Or = (v: number | null, scale: number) =>
  v === null ? I16_MISSING : Math.max(-32767, Math.min(32767, Math.round(v * scale)));

/** Inverse of parseAnalysis. Used by tests and the simulator. */
export function encodeAnalysis(a: AnalysisFields): Uint8Array {
  const out = new Uint8Array(ANALYSIS_LENGTH);
  const dv = new DataView(out.buffer);
  dv.setUint8(0, ANALYSIS_VERSION);
  dv.setUint16(1, a.seq & 0xffff, true);
  dv.setInt16(3, i16Or(a.ch4ResMv, 10), true);
  dv.setInt16(5, i16Or(a.lpgResMv, 10), true);
  dv.setUint16(7, a.ch4SigmaMv === null ? 0 : clampU16(a.ch4SigmaMv * 100), true);
  dv.setUint16(9, a.lpgSigmaMv === null ? 0 : clampU16(a.lpgSigmaMv * 100), true);
  dv.setUint16(11, a.airflowRawMv === null ? 0 : clampU16(a.airflowRawMv), true);
  dv.setInt16(13, i16Or(a.airflowIndex, 1000), true);
  dv.setUint16(15, a.coPpm === null ? U16_MISSING : Math.min(0xfffe, clampU16(a.coPpm * 10)), true);
  dv.setUint8(17, a.flags & 0xff);
  dv.setUint8(18, a.eventClass & 0xff);
  dv.setUint8(19, Math.max(0, Math.min(255, Math.round(a.eventRatio * 10))));
  return out;
}

/** One closed event's fingerprint (the Event notification). */
export interface EventFingerprint {
  id: number;
  eventClass: EventClass;
  /** 0-100, a heuristic until labelled events exist. */
  confidence: number;
  durationS: number;
  ch4PeakMv: number;
  lpgPeakMv: number;
  ratio: number;
  /** LPG onset minus CH4 onset (s): positive = CH4 led. Null when not known. */
  leadS: number | null;
  airflowMean: number | null;
  coPeakPpm: number | null;
  ch4Raised: boolean;
  lpgRaised: boolean;
  ch4Detected: boolean;
  lpgDetected: boolean;
  thermal: boolean;
  lowAirflow: boolean;
}

export function parseEvent(buf: DataView | ArrayBuffer | Uint8Array): EventFingerprint {
  const dv = toDataView(buf);
  if (dv.byteLength < EVENT_LENGTH) throw new Error(`event packet too short: ${dv.byteLength} bytes`);
  const version = dv.getUint8(0);
  if (version !== ANALYSIS_VERSION) throw new Error(`unsupported event version ${version}`);
  const i16 = (o: number, scale: number) => {
    const v = dv.getInt16(o, true);
    return v === I16_MISSING ? null : v / scale;
  };
  const f = dv.getUint8(19);
  return {
    id: dv.getUint16(1, true),
    eventClass: className(dv.getUint8(3)),
    confidence: dv.getUint8(4),
    durationS: dv.getUint16(5, true) / 10,
    ch4PeakMv: dv.getInt16(7, true) / 10,
    lpgPeakMv: dv.getInt16(9, true) / 10,
    ratio: dv.getUint16(11, true) / 100,
    leadS: i16(13, 10),
    airflowMean: i16(15, 1000),
    coPeakPpm: i16(17, 10),
    ch4Raised: (f & 1) !== 0,
    lpgRaised: (f & 2) !== 0,
    ch4Detected: (f & 4) !== 0,
    lpgDetected: (f & 8) !== 0,
    thermal: (f & 16) !== 0,
    lowAirflow: (f & 32) !== 0,
  };
}

/** `key=value;...` for the CSV's event_fingerprint column. */
export function formatFingerprint(e: EventFingerprint): string {
  const v = (x: number | null, d: number) => (x === null ? '' : x.toFixed(d));
  return [
    `id=${e.id}`,
    `class=${e.eventClass}`,
    `confidence=${e.confidence}`,
    `duration_s=${e.durationS.toFixed(1)}`,
    `ch4_peak_mv=${e.ch4PeakMv.toFixed(1)}`,
    `lpg_peak_mv=${e.lpgPeakMv.toFixed(1)}`,
    `ratio=${e.ratio.toFixed(2)}`,
    `lead_s=${v(e.leadS, 1)}`,
    `airflow_mean=${v(e.airflowMean, 3)}`,
    `co_peak_ppm=${v(e.coPeakPpm, 1)}`,
    `ch4_raised=${e.ch4Raised ? 1 : 0}`,
    `lpg_raised=${e.lpgRaised ? 1 : 0}`,
    `ch4_detected=${e.ch4Detected ? 1 : 0}`,
    `lpg_detected=${e.lpgDetected ? 1 : 0}`,
    `thermal=${e.thermal ? 1 : 0}`,
    `low_airflow=${e.lowAirflow ? 1 : 0}`,
  ].join(';');
}

export function encodeCalibrateAirflow(seconds = 60): Uint8Array {
  return new Uint8Array([OP_CALIBRATE_AIRFLOW, Math.max(1, Math.min(255, Math.round(seconds)))]);
}

// ---- Gas2 (rev F MEMS blade) -----------------------------------------------------
// Sent once per sample right after the Sample packet with the same seq, only by
// rev F firmware. Boards without the characteristic leave the MEMS columns blank.

export const GAS2_CHAR_UUID = '6d1a0007-8f3e-4b8a-9c57-2f6c0e3a7b10';
export const GAS2_LENGTH = 20;
export const GAS2_VERSION = 1;

export const GAS2_ANOMALY_A = 1 << 0;
export const GAS2_ANOMALY_B = 1 << 1;
export const GAS2_BLADE = 1 << 2;
export const GAS2_HEATER_ON = 1 << 3;
export const GAS2_WARM = 1 << 4;
export const GAS2_BURNIN_DONE = 1 << 5;

/** Gas2 marks a missing signed value with 0x7FFF (not 0x8000 as Sample/Analysis do). */
const I16_MAX_MISSING = 0x7fff;

export interface Gas2 {
  seq: number;
  /** ADC tap voltages (mV, 0.1 mV resolution); VRL = 2 x tap. Null when missing. */
  memsATapMv: number | null;
  memsBTapMv: number | null;
  /** Detector residuals and spreads (mV); null when missing. */
  memsAResMv: number | null;
  memsASigmaMv: number | null;
  memsBResMv: number | null;
  memsBSigmaMv: number | null;
  flagsRaw: number;
  anomalyA: boolean;
  anomalyB: boolean;
  bladeFitted: boolean;
  heaterOn: boolean;
  /** Past the MEMS warm-up. */
  warm: boolean;
  burnInDone: boolean;
  /** Measured 3V3 rail (mV); null when missing. */
  rail3v3Mv: number | null;
}

export function parseGas2(buf: DataView | ArrayBuffer | Uint8Array): Gas2 {
  const dv = toDataView(buf);
  if (dv.byteLength < GAS2_LENGTH) throw new Error(`gas2 packet too short: ${dv.byteLength} bytes`);
  const version = dv.getUint8(0);
  if (version !== GAS2_VERSION) throw new Error(`unsupported gas2 version ${version}`);
  const u16 = (o: number, scale: number) => {
    const v = dv.getUint16(o, true);
    return v === U16_MISSING ? null : v / scale;
  };
  const i16 = (o: number) => {
    const v = dv.getInt16(o, true);
    return v === I16_MAX_MISSING ? null : v / 10;
  };
  const f = dv.getUint8(15);
  return {
    seq: dv.getUint16(1, true),
    memsATapMv: u16(3, 10),
    memsBTapMv: u16(5, 10),
    memsAResMv: i16(7),
    memsASigmaMv: u16(9, 10),
    memsBResMv: i16(11),
    memsBSigmaMv: u16(13, 10),
    flagsRaw: f,
    anomalyA: (f & GAS2_ANOMALY_A) !== 0,
    anomalyB: (f & GAS2_ANOMALY_B) !== 0,
    bladeFitted: (f & GAS2_BLADE) !== 0,
    heaterOn: (f & GAS2_HEATER_ON) !== 0,
    warm: (f & GAS2_WARM) !== 0,
    burnInDone: (f & GAS2_BURNIN_DONE) !== 0,
    rail3v3Mv: u16(16, 1),
  };
}

export interface Gas2Fields {
  seq: number;
  memsATapMv: number | null;
  memsBTapMv: number | null;
  memsAResMv: number | null;
  memsASigmaMv: number | null;
  memsBResMv: number | null;
  memsBSigmaMv: number | null;
  flags: number;
  rail3v3Mv: number | null;
}

// Real values clamp one short of their sentinels.
const u16Or = (v: number | null, scale: number) => (v === null ? U16_MISSING : Math.min(0xfffe, clampU16(v * scale)));
const i16Or7f = (v: number | null) =>
  v === null ? I16_MAX_MISSING : Math.max(-32768, Math.min(0x7ffe, Math.round(v * 10)));

/** Inverse of parseGas2. Used by tests and the simulator. */
export function encodeGas2(g: Gas2Fields): Uint8Array {
  const out = new Uint8Array(GAS2_LENGTH);
  const dv = new DataView(out.buffer);
  dv.setUint8(0, GAS2_VERSION);
  dv.setUint16(1, g.seq & 0xffff, true);
  dv.setUint16(3, u16Or(g.memsATapMv, 10), true);
  dv.setUint16(5, u16Or(g.memsBTapMv, 10), true);
  dv.setInt16(7, i16Or7f(g.memsAResMv), true);
  dv.setUint16(9, u16Or(g.memsASigmaMv, 10), true);
  dv.setInt16(11, i16Or7f(g.memsBResMv), true);
  dv.setUint16(13, u16Or(g.memsBSigmaMv, 10), true);
  dv.setUint8(15, g.flags & 0xff);
  dv.setUint16(16, u16Or(g.rail3v3Mv, 1), true);
  dv.setUint16(18, 0, true);
  return out;
}
