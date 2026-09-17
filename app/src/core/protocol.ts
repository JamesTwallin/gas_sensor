// BLE protocol v1 for the rev B phone-companion board.
// Source of truth: docs/phone_board.md, "BLE protocol (v1)". Pure: no DOM, no BLE.

export const SERVICE_UUID = '6d1a0001-8f3e-4b8a-9c57-2f6c0e3a7b10';
export const SAMPLE_CHAR_UUID = '6d1a0002-8f3e-4b8a-9c57-2f6c0e3a7b10';
export const INFO_CHAR_UUID = '6d1a0003-8f3e-4b8a-9c57-2f6c0e3a7b10';
export const CONTROL_CHAR_UUID = '6d1a0004-8f3e-4b8a-9c57-2f6c0e3a7b10';

export const SAMPLE_LENGTH = 20;
export const PROTOCOL_VERSION = 1;

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
};

const positive = (v: unknown, fallback: number): number =>
  typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : fallback;

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
