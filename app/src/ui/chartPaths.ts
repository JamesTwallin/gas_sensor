// Chart geometry. The drawing itself is react-native-svg (ui/charts.tsx);
// everything that decides *where* a line goes lives here, pure and DOM-free, so
// it is unit-tested.
//
// Each chart shows ONE channel (CH4 or LPG): the two sit at different voltages
// and respond with different slopes, so a shared axis flattened whichever one
// moved less. Each scales to its own data rather than to 0..VC: clean-air VRL
// sits around 3 V and a plume adds a few hundred mV, so a fixed scale hid the
// signal in the top tenth of the plot. The y-range is the window's min..max,
// widened to at least `rangeFloorMv` (so noise does not fill the plot) plus
// headroom, and it never goes below 0.
//
//  - slope:    the first derivative on its own axis, zero and the spike
//              threshold ruled, spike samples marked; up to the last 60 s.
//              This is the plume indicator and the chart that matters.
//  - live:     VRL as a washed area + line under it, for context.
//  - overview: peak slope per column over up to the last 10 min.
//
// All of them fit their time axis to the data: the span is the time since the
// oldest point on screen, clamped to [MIN_SPAN_MS, spanMs], so a fresh
// connection fills the width instead of squeezing into the right-hand edge.

import { peakPerColumn, type ChartPoint } from '../core/chartData';

export type Series = 'ch4' | 'lpg';

/** Smallest y-span the chart will show (mV): stops noise filling the plot. */
export const DEFAULT_RANGE_FLOOR_MV = 150;
/** Headroom above and below the data range, as a fraction of the span. */
export const RANGE_PAD = 0.15;
/** A gap longer than this between samples breaks the trace. */
export const GAP_MS = 5000;
/** The time axis never shrinks below this, however little data there is. */
export const MIN_SPAN_MS = 5000;

/** Effective span: time covered by the points, clamped to [MIN_SPAN_MS, spanMs]. */
export function fitSpan(pts: readonly { t: number }[], now: number, spanMs: number): number {
  if (!pts.length) return spanMs;
  return Math.max(MIN_SPAN_MS, Math.min(spanMs, now - pts[0].t));
}

function spanLabel(ms: number): string {
  return ms >= 120_000 ? `−${Math.round(ms / 60000)} min` : `−${Math.round(ms / 1000)} s`;
}

export interface ChartLayout {
  width: number;
  height: number;
  padL: number;
  padT: number;
  padB: number;
}

export const DEFAULT_LAYOUT = { padL: 56, padT: 8, padB: 18 };

export interface GridLine {
  y: number;
  label: string;
}

export interface ChartFrame {
  yMin: number;
  yMax: number;
  gridLines: GridLine[];
  /** y of the bottom of the plot (the area fills down to it). */
  axisY: number;
  leftLabel: string;
  rightLabel: string;
}

export interface XY {
  x: number;
  y: number;
}

export const valueOf = (p: ChartPoint, s: Series): number => (s === 'ch4' ? p.ch4 : p.lpg);
export const slopeOf = (p: ChartPoint, s: Series): number | null => (s === 'ch4' ? p.ch4Slope : p.lpgSlope) ?? null;
export const spikeOf = (p: ChartPoint, s: Series): boolean => (s === 'ch4' ? p.ch4Spike : p.lpgSpike) === true;

/** A round number of mV/s at or above the largest |slope| on screen, for the derivative axis. */
export function slopeScale(maxAbs: number): number {
  const steps = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000];
  for (const s of steps) if (maxAbs <= s) return s;
  return Math.ceil(maxAbs / 10000) * 10000;
}

/** min..max of the values, widened to the floor and padded; clamped at 0. */
export function dataRange(values: Iterable<number>, rangeFloorMv: number): { yMin: number; yMax: number } {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (!Number.isFinite(v)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo === Infinity) return { yMin: 0, yMax: Math.max(1, rangeFloorMv) };
  const mid = (lo + hi) / 2;
  const half = (Math.max(hi - lo, rangeFloorMv) / 2) * (1 + 2 * RANGE_PAD);
  const yMin = Math.max(0, mid - half);
  return { yMin, yMax: Math.max(yMin + 1, mid + half) };
}

/** Map mV -> y, clamped into the plot area. */
function makeY(l: ChartLayout, yMin: number, yMax: number): (mv: number) => number {
  const plotH = l.height - l.padB - l.padT;
  const span = yMax - yMin;
  return (mv: number) => l.padT + plotH - ((Math.max(yMin, Math.min(yMax, mv)) - yMin) / span) * plotH;
}

const STEPS = [10, 20, 50, 100, 200, 250, 500, 1000, 2000, 5000];

/** A tick step giving at most four gridlines across the span. */
export function gridStep(spanMv: number): number {
  for (const s of STEPS) if (spanMv / s <= 4) return s;
  return STEPS[STEPS.length - 1];
}

export function gridLabel(mv: number): string {
  if (mv >= 1000) return `${(mv / 1000).toFixed(2).replace(/\.?0+$/, '')} V`;
  return `${Math.round(mv)} mV`;
}

function frame(l: ChartLayout, yMin: number, yMax: number, leftLabel: string, rightLabel: string): ChartFrame {
  const y = makeY(l, yMin, yMax);
  const step = gridStep(yMax - yMin);
  const gridLines: GridLine[] = [];
  const first = Math.ceil(yMin / step) * step;
  for (let level = first; level <= yMax; level += step) {
    // Keep labels clear of the top and bottom edges.
    if (level - yMin < step * 0.25 || yMax - level < step * 0.25) continue;
    gridLines.push({ y: Math.round(y(level)) + 0.5, label: gridLabel(level) });
  }
  return { yMin, yMax, gridLines, axisY: y(yMin) + 0.5, leftLabel, rightLabel };
}

/** Split into runs with no gap longer than GAP_MS. */
export function runs<T extends { t: number }>(pts: readonly T[]): T[][] {
  const out: T[][] = [];
  let cur: T[] = [];
  for (const p of pts) {
    if (cur.length && p.t - cur[cur.length - 1].t > GAP_MS) {
      out.push(cur);
      cur = [];
    }
    cur.push(p);
  }
  if (cur.length) out.push(cur);
  return out;
}

const n = (v: number) => (Math.round(v * 100) / 100).toString();

function polyline(pts: readonly XY[]): string {
  return pts.map((p, i) => `${i ? 'L' : 'M'}${n(p.x)} ${n(p.y)}`).join(' ');
}

/** A polyline closed down to the axis, for the filled area under a trace. */
function area(pts: readonly XY[], axisY: number): string {
  if (pts.length < 2) return '';
  return `M${n(pts[0].x)} ${n(axisY)} ${polyline(pts).slice(1)} L${n(pts[pts.length - 1].x)} ${n(axisY)} Z`;
}

export interface LiveChart extends ChartFrame {
  /** Filled areas, one per gap-free run. */
  areas: string[];
  lines: string[];
  /** Newest point of the trace, for the end marker; null without data. */
  end: XY | null;
  /** Where the trace sits on each sample the detector flagged. */
  spikeMarks: XY[];
}

export function buildLiveChart(
  pts: readonly ChartPoint[],
  now: number,
  spanMs: number,
  l: ChartLayout,
  rangeFloorMv = DEFAULT_RANGE_FLOOR_MV,
  series: Series = 'ch4',
): LiveChart {
  const { yMin, yMax } = dataRange(
    (function* () {
      for (const p of pts) yield valueOf(p, series);
    })(),
    rangeFloorMv,
  );
  const span = fitSpan(pts, now, spanMs);
  const f = frame(l, yMin, yMax, spanLabel(span), 'now');
  const y = makeY(l, yMin, yMax);
  const plotW = l.width - l.padL;
  const x = (t: number) => l.padL + ((t - (now - span)) / span) * plotW;

  const areas: string[] = [];
  const lines: string[] = [];
  let end: XY | null = null;
  for (const run of runs(pts)) {
    if (run.length < 2) continue;
    const xy = run.map((p) => ({ x: x(p.t), y: y(valueOf(p, series)) }));
    areas.push(area(xy, f.axisY));
    lines.push(polyline(xy));
    end = xy[xy.length - 1];
  }

  const spikeMarks: XY[] = [];
  for (const p of pts) if (spikeOf(p, series)) spikeMarks.push({ x: x(p.t), y: y(valueOf(p, series)) });

  return { ...f, areas, lines, end, spikeMarks };
}

// ---- derivative panel -----------------------------------------------------------
// Shares the live chart's time axis (same fitSpan, same x mapping) but has its
// own y-limits: the slopes' own min..max, always including zero, with headroom.
// Zero is ruled; the spike threshold is ruled when known; flagged samples are
// marked on the trace.

const SLOPE_STEPS = [5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000];

export interface SlopeChart {
  yMin: number;
  yMax: number;
  gridLines: GridLine[];
  /** y of zero mV/s. */
  zeroY: number;
  lines: string[];
  spikeMarks: XY[];
  /** y of the current threshold, or null when none is known. */
  thresholdY: number | null;
  leftLabel: string;
  rightLabel: string;
}

interface SlopeSample {
  t: number;
  slope: number | null;
  spike: boolean;
}

/** Shared by the live panel and the overview: samples in, paths and rules out. */
function slopeGeometry(
  samples: readonly SlopeSample[],
  t0: number,
  span: number,
  l: ChartLayout,
  thresholdMvPerS: number | null,
  gapMs: number,
  leftLabel: string,
  rightLabel: string,
): SlopeChart {
  const ok = (s: number | null): s is number => s !== null && Number.isFinite(s);
  let lo = 0;
  let hi = 0;
  for (const p of samples) {
    if (!ok(p.slope)) continue;
    if (p.slope < lo) lo = p.slope;
    if (p.slope > hi) hi = p.slope;
  }
  if (thresholdMvPerS !== null && thresholdMvPerS > hi) hi = thresholdMvPerS;
  // At least ±10 mV/s of range so a flat trace is a visible flat line, then headroom.
  hi = Math.max(hi, 10);
  lo = Math.min(lo, -10);
  const pad = (hi - lo) * RANGE_PAD;
  const yMin = lo - pad;
  const yMax = hi + pad;
  const y = makeY(l, yMin, yMax);

  let step = SLOPE_STEPS[SLOPE_STEPS.length - 1];
  for (const s of SLOPE_STEPS) {
    if ((yMax - yMin) / s <= 4) {
      step = s;
      break;
    }
  }
  const gridLines: GridLine[] = [];
  for (let level = Math.ceil(yMin / step) * step; level <= yMax; level += step) {
    if (level === 0 || level - yMin < step * 0.25 || yMax - level < step * 0.25) continue;
    gridLines.push({ y: Math.round(y(level)) + 0.5, label: String(level) });
  }

  const plotW = l.width - l.padL;
  const x = (t: number) => l.padL + ((t - t0) / span) * plotW;

  const lines: string[] = [];
  const spikeMarks: XY[] = [];
  let seg: XY[] = [];
  let prevT = -Infinity;
  for (const p of samples) {
    if (!ok(p.slope) || p.t - prevT > gapMs) {
      if (seg.length > 1) lines.push(polyline(seg));
      seg = [];
    }
    prevT = p.t;
    if (!ok(p.slope)) continue;
    const at = { x: x(p.t), y: y(p.slope) };
    seg.push(at);
    if (p.spike) spikeMarks.push(at);
  }
  if (seg.length > 1) lines.push(polyline(seg));

  return {
    yMin,
    yMax,
    gridLines,
    zeroY: Math.round(y(0)) + 0.5,
    lines,
    spikeMarks,
    thresholdY: thresholdMvPerS !== null ? y(thresholdMvPerS) : null,
    leftLabel,
    rightLabel,
  };
}

export function buildSlopeChart(
  pts: readonly ChartPoint[],
  now: number,
  spanMs: number,
  l: ChartLayout,
  series: Series = 'ch4',
  thresholdMvPerS: number | null = null,
): SlopeChart {
  const span = fitSpan(pts, now, spanMs);
  const samples = pts.map((p) => ({ t: p.t, slope: slopeOf(p, series), spike: spikeOf(p, series) }));
  return slopeGeometry(samples, now - span, span, l, thresholdMvPerS, GAP_MS, spanLabel(span), 'now');
}

/**
 * The overview strip: the largest slope in each 2 px column over up to the
 * last `spanMs`, so a plume edge a few samples long is not lost between
 * pixels. A column is marked when any sample in it was flagged.
 */
export function buildSlopeOverview(
  pts: readonly ChartPoint[],
  now: number,
  spanMs: number,
  l: ChartLayout,
  series: Series = 'ch4',
  thresholdMvPerS: number | null = null,
): SlopeChart {
  const plotW = l.width - l.padL;
  const cols = Math.max(1, Math.floor(plotW / 2));
  const span = fitSpan(pts, now, spanMs);
  const t0 = now - span;
  const colMs = span / cols;
  const peaks = peakPerColumn(pts, t0, now, cols, (p) => slopeOf(p, series) ?? -Infinity);

  const spikeCols = new Set<number>();
  for (const p of pts) {
    if (p.t < t0 || p.t > now || !spikeOf(p, series)) continue;
    spikeCols.add(Math.min(cols - 1, Math.floor((p.t - t0) / colMs)));
  }

  const samples = peaks.map((p) => ({ t: t0 + (p.col + 0.5) * colMs, slope: p.peak, spike: spikeCols.has(p.col) }));
  // Columns without samples break the line (so a link drop reads as a gap).
  return slopeGeometry(samples, t0, span, l, thresholdMvPerS, GAP_MS + 2 * colMs, spanLabel(span), 'now');
}
