// Processing + app settings. Pure: persistence lives in services/.

export interface ProcessingSettings {
  /**
   * Heater warm-up after device power-on (ms since boot). The state card reads
   * WARMING UP until then; slope and spike detection run regardless.
   */
  warmupMs: number;
}

export interface AppSettings extends ProcessingSettings {
  simulate: boolean;
  /** Requested device sample interval, sent with opcode 0x01 on connect. */
  intervalMs: number;
  /** Drive the board's status LED from the run state and CH4 spikes (opcode 0x03). */
  driveLed: boolean;
  /** Keep the screen awake while connected or recording. */
  keepAwake: boolean;
  /** Light theme for bright sunlight (dark is the default). */
  lightTheme: boolean;
  /**
   * Correct the ppm estimate for temperature and humidity using the Figaro
   * datasheet tables (on by default). Off = treat every reading as taken at
   * the datasheet reference conditions, 20 °C / 65 %RH. The raw load
   * voltages, Rs and the slope are never compensated.
   */
  envCompensate: boolean;
  /** Spike detector (core/spike.ts): derivative window (ms), robust-sigma threshold, floor (mV/s). */
  spikeWindowMs: number;
  spikeSigma: number;
  spikeFloorMvPerS: number;
  /**
   * Talk to the board through tools/serial_bridge.py on a PC (USB serial
   * relayed over Wi-Fi) instead of Bluetooth. Forced on where the BLE native
   * module is missing, i.e. in Expo Go.
   */
  usbBridge: boolean;
  /** Bridge PC address (host, host:port or ws:// URL). Blank = the PC running Expo. */
  bridgeHost: string;
}

export const DEFAULT_PROCESSING: ProcessingSettings = {
  warmupMs: 0, // no warm-up gate: everything is plotted and detected from the first sample
};

export const DEFAULT_SETTINGS: AppSettings = {
  ...DEFAULT_PROCESSING,
  simulate: false,
  intervalMs: 250,
  driveLed: true,
  keepAwake: true,
  lightTheme: false,
  envCompensate: true,
  spikeWindowMs: 1000,
  spikeSigma: 4,
  spikeFloorMvPerS: 25,
  usbBridge: false,
  bridgeHost: '',
};

/** Merge a stored (possibly partial or stale) object over the defaults, keeping types sane. */
export function sanitizeSettings(raw: unknown): AppSettings {
  const out: AppSettings = { ...DEFAULT_SETTINGS };
  if (!raw || typeof raw !== 'object') return out;
  const r = raw as Record<string, unknown>;
  for (const key of Object.keys(DEFAULT_SETTINGS) as (keyof AppSettings)[]) {
    const def = DEFAULT_SETTINGS[key];
    const v = r[key];
    if (typeof def === 'boolean' && typeof v === 'boolean') (out[key] as boolean) = v;
    if (typeof def === 'string' && typeof v === 'string') (out[key] as string) = v.trim().slice(0, 200);
    if (typeof def === 'number' && typeof v === 'number' && Number.isFinite(v) && v >= 0) {
      (out[key] as number) = v;
    }
  }
  // Phones that stored the old 3 min default (before 2026-09-30) get the new no-warm-up default.
  if (out.warmupMs === 3 * 60_000) out.warmupMs = 0;
  return out;
}
