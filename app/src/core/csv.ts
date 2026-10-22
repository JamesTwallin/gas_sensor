// Survey CSV, docs/phone_board.md "App CSV (backwards compatible)": the rev A
// columns unchanged (so tools/plot_map.py and tools/plot_survey.py keep working),
// then the rev B columns appended, then the concentration estimates, then the
// board's anomaly detector (Analysis / Event packets), then the rev F MEMS
// blade (Gas2 packet; blank on boards without it). Pure, no DOM.

import { formatFingerprint, type Analysis, type EventFingerprint, type Gas2 } from './protocol';
import type { MemsReading } from './sensor';

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
  'airflow_raw',
  'airflow_index',
  'co_raw',
  'ch4_res_mv',
  'lpg_res_mv',
  'ch4_sigma_mv',
  'lpg_sigma_mv',
  'anomaly_ch4',
  'anomaly_lpg',
  'event_class',
  'event_ratio',
  'event_fingerprint',
  'mems_a_vout_mv',
  'mems_b_vout_mv',
  'mems_a_rs_ohm',
  'mems_b_rs_ohm',
  'mems_a_res_mv',
  'mems_a_sigma_mv',
  'mems_b_res_mv',
  'mems_b_sigma_mv',
  'anomaly_mems_a',
  'anomaly_mems_b',
  'mems_flags',
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
  /** The board's Analysis packet for this sample (same seq), if it arrived. */
  analysis?: Analysis | null;
  /** A closed event's fingerprint, written on the row it arrived with. */
  event?: EventFingerprint | null;
  /** Rev F: the Gas2 packet for this sample (same seq) and the values derived from it. */
  mems?: { gas2: Gas2; reading: MemsReading } | null;
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
    ...analysisCells(r.analysis ?? null, r.event ?? null),
    ...memsCells(r.mems ?? null),
  ];
  return cells.join(',');
}

function analysisCells(a: Analysis | null, e: EventFingerprint | null): string[] {
  const fp = e ? formatFingerprint(e) : '';
  if (!a) return ['', '', '', '', '', '', '', '', '', e ? e.eventClass : '', e ? fmt(e.ratio, 2) : '', fp];
  // The Event packet carries the ratio exactly; the Analysis byte is coarse.
  const cls = e ? e.eventClass : a.eventClass;
  const ratio = e ? e.ratio : a.eventRatio;
  return [
    fmt(a.airflowRawMv, 0),
    fmt(a.airflowIndex, 3),
    fmt(a.coPpm, 1),
    fmt(a.ch4ResMv, 1),
    fmt(a.lpgResMv, 1),
    fmt(a.ch4SigmaMv, 2),
    fmt(a.lpgSigmaMv, 2),
    a.anomalyCh4 ? '1' : '0',
    a.anomalyLpg ? '1' : '0',
    cls,
    cls ? fmt(ratio, 2) : '',
    fp,
  ];
}

const MEMS_BLANK: readonly string[] = Array(11).fill('');

function memsCells(m: CsvRowInput['mems'] | null): readonly string[] {
  if (!m) return MEMS_BLANK;
  const { gas2: g, reading: r } = m;
  return [
    fmt(r.a.voutMv, 0),
    fmt(r.b.voutMv, 0),
    fmt(r.a.rsOhm, 0),
    fmt(r.b.rsOhm, 0),
    fmt(g.memsAResMv, 1),
    fmt(g.memsASigmaMv, 1),
    fmt(g.memsBResMv, 1),
    fmt(g.memsBSigmaMv, 1),
    g.anomalyA ? '1' : '0',
    g.anomalyB ? '1' : '0',
    String(g.flagsRaw),
  ];
}

/** Survey file name from the phone clock, same pattern rev A used on the SD card. */
export function surveyFileName(epochMs: number): string {
  const d = new Date(epochMs);
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}_` +
    `${pad(d.getUTCHours())}-${pad(d.getUTCMinutes())}-${pad(d.getUTCSeconds())}.csv`
  );
}
