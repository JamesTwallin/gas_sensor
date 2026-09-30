// Survey CSV, docs/phone_board.md "App CSV (backwards compatible)": the rev A
// columns unchanged (so tools/plot_map.py and tools/plot_survey.py keep working),
// then the rev B columns appended, then the concentration estimates. Pure, no DOM.

export const CSV_COLUMNS = [
  'millis_since_boot',
  'state',
  'ch4_vout_mv',
  'ch4_baseline_mv',
  'ch4_dev_mv',
  'lpg_vout_mv',
  'lpg_baseline_mv',
  'lpg_dev_mv',
  'temp_c',
  'humidity_pct',
  'pressure_hpa',
  'utc_iso8601',
  'lat',
  'lon',
  'alt_m',
  'sats',
  'fix',
  'ch4_rs_ohm',
  'lpg_rs_ohm',
  'vbat_mv',
  'gps_accuracy_m',
  'ch4_ppm_est',
  'lpg_ppm_est',
  'ch4_slope_mv_s',
  'lpg_slope_mv_s',
  'spike',
] as const;

export const CSV_HEADER = CSV_COLUMNS.join(',');

/** fix = 1 when horizontal accuracy is at or under this (spec). */
export const FIX_ACCURACY_M = 25;
/** A position older than this is still written, but never counts as a fix. */
export const FIX_MAX_AGE_MS = 10_000;

export interface GpsFix {
  lat: number;
  lon: number;
  altM: number | null;
  accuracyM: number | null;
  /** Phone epoch ms when the fix was taken. */
  timestamp: number;
}

export interface CsvRowInput {
  millisSinceBoot: number;
  state: string;
  ch4VoutMv: number;
  ch4BaselineMv: number;
  lpgVoutMv: number;
  lpgBaselineMv: number;
  tempC: number | null;
  humidityPct: number | null;
  pressureHpa: number | null;
  /** Phone epoch ms at which the sample was received. */
  phoneTimeMs: number;
  gps: GpsFix | null;
  ch4RsOhm: number | null;
  lpgRsOhm: number | null;
  vbatMv: number;
  /** Datasheet-curve estimates (core/ppm.ts); blank when Rs is unknown. */
  ch4PpmEst?: number | null;
  lpgPpmEst?: number | null;
  /** First derivative of VRL (core/spike.ts), mV/s; blank until the window fills. */
  ch4SlopeMvPerS?: number | null;
  lpgSlopeMvPerS?: number | null;
  /** Which channels flagged a spike on this sample: '', 'CH4', 'LPG' or 'CH4+LPG'. */
  spike?: string;
}

const pad = (n: number, w = 2) => String(n).padStart(w, '0');

/** Phone UTC as `YYYY-MM-DD HH:MM:SS.mmm` (the rev A utc_iso8601 format). */
export function formatUtc(epochMs: number): string {
  const d = new Date(epochMs);
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}.` +
    pad(d.getUTCMilliseconds(), 3)
  );
}

/** printf("%.Nf") equivalent; blank for null / non-finite. Avoids "-0". */
export function fmt(v: number | null | undefined, digits: number): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '';
  const s = v.toFixed(digits);
  return /^-0(\.0*)?$/.test(s) ? s.slice(1) : s;
}

export function isFix(gps: GpsFix | null, phoneTimeMs: number): boolean {
  if (!gps) return false;
  if (gps.accuracyM === null || gps.accuracyM > FIX_ACCURACY_M) return false;
  return Math.abs(phoneTimeMs - gps.timestamp) <= FIX_MAX_AGE_MS;
}

export function formatCsvRow(r: CsvRowInput): string {
  const g = r.gps;
  const cells = [
    String(Math.round(r.millisSinceBoot)),
    r.state,
    fmt(r.ch4VoutMv, 0),
    fmt(r.ch4BaselineMv, 0),
    fmt(r.ch4VoutMv - r.ch4BaselineMv, 0),
    fmt(r.lpgVoutMv, 0),
    fmt(r.lpgBaselineMv, 0),
    fmt(r.lpgVoutMv - r.lpgBaselineMv, 0),
    fmt(r.tempC, 2),
    fmt(r.humidityPct, 1),
    fmt(r.pressureHpa, 1),
    formatUtc(r.phoneTimeMs),
    g ? fmt(g.lat, 6) : '',
    g ? fmt(g.lon, 6) : '',
    g ? fmt(g.altM, 1) : '',
    '', // sats: phones don't expose it
    isFix(g, r.phoneTimeMs) ? '1' : '0',
    fmt(r.ch4RsOhm, 0),
    fmt(r.lpgRsOhm, 0),
    String(Math.round(r.vbatMv)),
    g ? fmt(g.accuracyM, 1) : '',
    fmt(r.ch4PpmEst, 0),
    fmt(r.lpgPpmEst, 0),
    fmt(r.ch4SlopeMvPerS, 1),
    fmt(r.lpgSlopeMvPerS, 1),
    r.spike ?? '',
  ];
  return cells.join(',');
}

/** Survey file name from the phone clock, same pattern rev A used on the SD card. */
export function surveyFileName(epochMs: number): string {
  const d = new Date(epochMs);
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}_` +
    `${pad(d.getUTCHours())}-${pad(d.getUTCMinutes())}-${pad(d.getUTCSeconds())}.csv`
  );
}
