// Estimated concentration from sensor resistance, using the Figaro datasheet
// relationships captured in docs/sensors.md. Pure, no DOM.
//
//   Rs/Ro = (ppm / refPpm) ^ exponent            (power law, per gas)
//   Rs/Ro also scales with temperature and humidity (Table 1 of each datasheet,
//   normalised to 20 °C / 65 %RH), so a measured Rs is first divided by that
//   environmental factor before the power law is inverted.
//
// Ro is the sensor's resistance at the reference concentration and it is the
// weak point: Figaro specifies it only within a 10x band per part, so without a
// per-board calibration the estimate is an order of magnitude, not a reading.
// The app therefore ships a datasheet-typical Ro (the geometric mean of the
// specified band) and lets the user replace it from one exposure to a known
// concentration (roFromKnownPpm).

export interface EnvTable {
  temps: number[];
  rhs: number[];
  /** rows[tempIndex][rhIndex]; null where the datasheet has no value. */
  rows: (number | null)[][];
}

export interface GasCurve {
  gas: 'CH4' | 'LPG';
  /** Concentration at which Rs/Ro = 1 (ppm). */
  refPpm: number;
  /** Rs ∝ ppm^exponent. */
  exponent: number;
  /** Datasheet Rs band at refPpm (ohms). */
  roMinOhm: number;
  roMaxOhm: number;
  /** Geometric mean of the band: the default when nothing is calibrated. */
  roTypicalOhm: number;
  /** Range over which the datasheet curve is specified (ppm). */
  minPpm: number;
  maxPpm: number;
  table: EnvTable;
}

const TEMPS = [-10, 0, 10, 20, 30, 40];
const RHS = [35, 50, 65, 95];

/** TGS2611-E00 methane: Table 1 and the specified beta, docs/sensors.md. */
export const TGS2611: GasCurve = {
  gas: 'CH4',
  refPpm: 5000,
  exponent: -0.47,
  roMinOhm: 680,
  roMaxOhm: 6800,
  roTypicalOhm: 2150,
  minPpm: 500,
  maxPpm: 10000,
  table: {
    temps: TEMPS,
    rhs: RHS,
    rows: [
      [null, null, null, 1.51],
      [null, null, 1.45, 1.25],
      [null, 1.33, 1.19, 1.02],
      [1.25, 1.11, 1.0, 0.87],
      [1.05, 0.94, 0.86, 0.77],
      [0.92, 0.82, 0.76, 0.69],
    ],
  },
};

/** TGS2610-D00 LP gas, referenced to iso-butane. */
export const TGS2610: GasCurve = {
  gas: 'LPG',
  refPpm: 1800,
  exponent: -0.53,
  roMinOhm: 680,
  roMaxOhm: 6800,
  roTypicalOhm: 2150,
  minPpm: 500,
  maxPpm: 10000,
  table: {
    temps: TEMPS,
    rhs: RHS,
    rows: [
      [null, null, null, 1.6],
      [null, null, 1.5, 1.35],
      [null, 1.5, 1.23, 1.08],
      [1.52, 1.19, 1.0, 0.85],
      [1.23, 0.94, 0.79, 0.68],
      [0.98, 0.75, 0.61, 0.53],
    ],
  },
};

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** Linear interpolation of `value` across the known (x, y) points; clamps outside. */
function interp(points: { x: number; y: number }[], x: number): number {
  if (points.length === 1) return points[0].y;
  if (x <= points[0].x) return points[0].y;
  const last = points[points.length - 1];
  if (x >= last.x) return last.y;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (x <= b.x) return a.y + ((x - a.x) / (b.x - a.x)) * (b.y - a.y);
  }
  return last.y;
}

/** One table row at a humidity, using only the cells the datasheet gives. */
function rowAt(table: EnvTable, ti: number, rh: number): number | null {
  const pts: { x: number; y: number }[] = [];
  table.rows[ti].forEach((v, ri) => {
    if (v !== null) pts.push({ x: table.rhs[ri], y: v });
  });
  return pts.length ? interp(pts, rh) : null;
}

/**
 * Rs/Ro multiplier for the ambient conditions relative to 20 °C / 65 %RH
 * (1.0 there). Bilinear over the datasheet table, clamped to its edges; rows
 * with sparse cells interpolate over what they have.
 */
export function envFactor(table: EnvTable, tempC: number, rh: number): number {
  const t = clamp(tempC, table.temps[0], table.temps[table.temps.length - 1]);
  const h = clamp(rh, table.rhs[0], table.rhs[table.rhs.length - 1]);
  const pts: { x: number; y: number }[] = [];
  table.temps.forEach((temp, ti) => {
    const v = rowAt(table, ti, h);
    if (v !== null) pts.push({ x: temp, y: v });
  });
  return pts.length ? interp(pts, t) : 1;
}

function factorFor(curve: GasCurve, tempC: number | null, rh: number | null): number {
  return tempC === null || rh === null ? 1 : envFactor(curve.table, tempC, rh);
}

/**
 * Estimated ppm from Rs (ohms) and Ro (ohms), corrected for temperature and
 * humidity when known. Null when Rs is unknown or either resistance is not
 * positive. Not clamped to the curve's specified range; see fmtPpm.
 */
export function estimatePpm(
  rsOhm: number | null,
  roOhm: number,
  tempC: number | null,
  rh: number | null,
  curve: GasCurve,
): number | null {
  if (rsOhm === null || !(rsOhm > 0) || !(roOhm > 0)) return null;
  const ratio = rsOhm / roOhm / factorFor(curve, tempC, rh);
  const ppm = curve.refPpm * Math.pow(ratio, 1 / curve.exponent);
  return Number.isFinite(ppm) ? ppm : null;
}

/** Ro (ohms) implied by reading Rs while the sensor sits in a known concentration. */
export function roFromKnownPpm(
  rsOhm: number,
  ppm: number,
  tempC: number | null,
  rh: number | null,
  curve: GasCurve,
): number {
  return rsOhm / (factorFor(curve, tempC, rh) * Math.pow(ppm / curve.refPpm, curve.exponent));
}

export interface ChannelCalibration {
  roOhm: number;
  /** The concentration the sensor was in when Ro was taken. */
  ppm: number;
  /** Phone epoch ms. */
  at: number;
  tempC: number | null;
  rh: number | null;
}

export interface Calibration {
  ch4: ChannelCalibration | null;
  lpg: ChannelCalibration | null;
}

export const NO_CALIBRATION: Calibration = { ch4: null, lpg: null };

export function roFor(cal: ChannelCalibration | null, curve: GasCurve): number {
  return cal && cal.roOhm > 0 ? cal.roOhm : curve.roTypicalOhm;
}

function channel(raw: unknown): ChannelCalibration | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
  const roOhm = num(r.roOhm);
  const ppm = num(r.ppm);
  const at = num(r.at);
  if (roOhm === null || roOhm <= 0 || ppm === null || ppm <= 0 || at === null) return null;
  return { roOhm, ppm, at, tempC: num(r.tempC), rh: num(r.rh) };
}

export function sanitizeCalibration(raw: unknown): Calibration {
  if (!raw || typeof raw !== 'object') return { ...NO_CALIBRATION };
  const r = raw as Record<string, unknown>;
  return { ch4: channel(r.ch4), lpg: channel(r.lpg) };
}

/** Thousands separators without relying on Intl (Hermes support varies). */
export function withCommas(n: number): string {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * "<500", "~1,200" (two significant figures) or ">10,000": the curve is only
 * specified over minPpm..maxPpm, and the estimate is never better than ~2 s.f.
 */
export function fmtPpm(ppm: number | null, curve: GasCurve): string {
  if (ppm === null) return '—';
  if (ppm < curve.minPpm) return `<${withCommas(curve.minPpm)}`;
  if (ppm > curve.maxPpm) return `>${withCommas(curve.maxPpm)}`;
  const mag = Math.pow(10, Math.floor(Math.log10(ppm)) - 1);
  return `~${withCommas(Math.round(ppm / mag) * mag)}`;
}
