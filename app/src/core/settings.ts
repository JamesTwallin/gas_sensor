// Processing + app settings. Pure: persistence lives in services/.

export interface ProcessingSettings {
  /** Heater warm-up after device power-on before readings are classified (ms since boot). */
  warmupMs: number;
  /** Rolling background window for the percentile baseline. */
  bgWindowMs: number;
  /** Percentile (0–1) of the background window taken as the baseline. */
  bgPercentile: number;
  /** HIGH/MED/LOW classification window. */
  classWindowMs: number;
  /** Minimum min..max span (mV) before thirds mean anything. */
  classRangeFloorMv: number;
}

export interface AppSettings extends ProcessingSettings {
  simulate: boolean;
  /** Requested device sample interval, sent with opcode 0x01 on connect. */
  intervalMs: number;
  /** Drive the board's status LED from the CH4 class (opcode 0x03). */
  driveLed: boolean;
  /** Keep the screen awake while connected or recording. */
  keepAwake: boolean;
  /** Light theme for bright sunlight (dark is the default). */
  lightTheme: boolean;
  /**
   * Correct the ppm estimate for temperature and humidity using the Figaro
   * datasheet tables (on by default). Off = treat every reading as taken at
   * the datasheet reference conditions, 20 °C / 65 %RH. The raw load
   * voltages, Rs and the HIGH/MED/LOW classifier are never compensated.
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

/**
 * Field defaults. Rev A shipped a 15 s bench warm-up; a real survey wants
 * minutes -- the Figaro "initial action" alone is minutes. Windows, percentile
 * and range floor are the rev A values. There is no baselining wait: the
 * baseline is provisional from the first sample and firms up as the window fills.
 */
export const DEFAULT_PROCESSING: ProcessingSettings = {
  warmupMs: 0, // no warm-up gate: everything is plotted and detected from the first sample

  bgWindowMs: 2 * 60_000,
  bgPercentile: 0.15,
  classWindowMs: 10 * 60_000,
  classRangeFloorMv: 150,
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
  out.bgPercentile = Math.min(1, out.bgPercentile);
  // Phones that stored the old 3 min default (before 2026-09-30) get the new no-warm-up default.
  if (out.warmupMs === 3 * 60_000) out.warmupMs = 0;
  return out;
}
