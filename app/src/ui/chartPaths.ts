// Chart geometry. The drawing itself is react-native-svg (ui/charts.tsx);
// everything that decides *where* a line goes lives here, pure and DOM-free, so
// it is unit-tested.
//
// Both charts scale to the data rather than to 0..VC: clean-air VRL sits around
// 3 V and a plume adds a few hundred mV, so a fixed scale hid the signal in the
// top tenth of the plot. The y-range is the window's min..max, widened to at
// least `rangeFloorMv` (the classifier's own range floor, so the chart and the
// HIGH/MED/LOW thirds agree on what "a change" is) plus headroom, and it never
// goes below 0.
//
//  - live:     CH4 VRL as a washed area + line, LPG as a line, CH4 baseline
//              dotted; last 60 s.
//  - overview: last 10 min of CH4, peak-per-column, current baseline ruled.

import { peakPerColumn, type ChartPoint } from '../core/chartData';

/** Smallest y-span the chart will show (mV): stops noise filling the plot. */
export const DEFAULT_RANGE_FLOOR_MV = 150;
/** Headroom above and below the data range, as a fraction of the span. */
export const RANGE_PAD = 0.15;
/** A gap longer than this between samples breaks the trace. */
export const GAP_MS = 5000;

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
  /** Filled CH4 areas, one per gap-free run. */
  ch4Areas: string[];
  ch4Lines: string[];
  lpgLines: string[];
  /** Dotted baseline, broken wherever there is no trusted baseline or a link gap. */
  baselineLines: string[];
  /** Newest point of each trace, for the end marker; null without data. */
  ch4End: XY | null;
  lpgEnd: XY | null;
}

export function buildLiveChart(
  pts: readonly ChartPoint[],
  now: number,
  spanMs: number,
  l: ChartLayout,
  rangeFloorMv = DEFAULT_RANGE_FLOOR_MV,
): LiveChart {
  const { yMin, yMax } = dataRange(
    (function* () {
      for (const p of pts) {
        yield p.ch4;
        yield p.lpg;
        if (p.baseline !== null) yield p.baseline;
      }
    })(),
    rangeFloorMv,
  );
  const f = frame(l, yMin, yMax, `−${Math.round(spanMs / 1000)} s`, 'now');
  const y = makeY(l, yMin, yMax);
  const plotW = l.width - l.padL;
  const x = (t: number) => l.padL + ((t - (now - spanMs)) / spanMs) * plotW;

  const ch4Areas: string[] = [];
  const ch4Lines: string[] = [];
  const lpgLines: string[] = [];
  let ch4End: XY | null = null;
  let lpgEnd: XY | null = null;
  for (const run of runs(pts)) {
    if (run.length < 2) continue;
    const ch4 = run.map((p) => ({ x: x(p.t), y: y(p.ch4) }));
    const lpg = run.map((p) => ({ x: x(p.t), y: y(p.lpg) }));
    ch4Areas.push(area(ch4, f.axisY));
    ch4Lines.push(polyline(ch4));
    lpgLines.push(polyline(lpg));
    ch4End = ch4[ch4.length - 1];
    lpgEnd = lpg[lpg.length - 1];
  }

  // The baseline breaks on a link gap and wherever there is no trusted baseline.
  const baselineLines: string[] = [];
  let seg: XY[] = [];
  let prevT = -Infinity;
  for (const p of pts) {
    if (p.baseline === null || p.t - prevT > GAP_MS) {
      if (seg.length > 1) baselineLines.push(polyline(seg));
      seg = [];
    }
    prevT = p.t;
    if (p.baseline === null) continue;
    seg.push({ x: x(p.t), y: y(p.baseline) });
  }
  if (seg.length > 1) baselineLines.push(polyline(seg));

  return { ...f, ch4Areas, ch4Lines, lpgLines, baselineLines, ch4End, lpgEnd };
}

export interface OverviewChart extends ChartFrame {
  ch4Areas: string[];
  ch4Lines: string[];
  /** Flat current-baseline rule across the window, or null when there is none. */
  baselineRule: { x1: number; x2: number; y: number } | null;
}

export function buildOverviewChart(
  pts: readonly ChartPoint[],
  now: number,
  spanMs: number,
  l: ChartLayout,
  rangeFloorMv = DEFAULT_RANGE_FLOOR_MV,
): OverviewChart {
  const plotW = l.width - l.padL;
  const cols = Math.max(1, Math.floor(plotW / 2)); // one column per 2 px
  const t0 = now - spanMs;
  const peaks = peakPerColumn(pts, t0, now, cols, (p) => p.ch4);
  const last = pts.length ? pts[pts.length - 1] : null;

  const { yMin, yMax } = dataRange(
    (function* () {
      for (const p of pts) if (p.t >= t0) yield p.ch4;
      if (last && last.baseline !== null) yield last.baseline;
    })(),
    rangeFloorMv,
  );
  const f = frame(l, yMin, yMax, `−${Math.round(spanMs / 60000)} min`, 'now');
  const y = makeY(l, yMin, yMax);
  const colX = (col: number) => l.padL + ((col + 0.5) / cols) * plotW;

  // Columns without samples break the line (so a link drop reads as a gap).
  const maxColGap = Math.ceil((GAP_MS / spanMs) * cols) + 1;
  const segs: { col: number; peak: number }[][] = [];
  for (const p of peaks) {
    const seg = segs[segs.length - 1];
    if (seg && p.col - seg[seg.length - 1].col <= maxColGap) seg.push(p);
    else segs.push([p]);
  }

  const ch4Areas: string[] = [];
  const ch4Lines: string[] = [];
  for (const seg of segs) {
    if (seg.length < 2) continue;
    const xy = seg.map((p) => ({ x: colX(p.col), y: y(p.peak) }));
    ch4Areas.push(area(xy, f.axisY));
    ch4Lines.push(polyline(xy));
  }

  const baselineRule =
    last && last.baseline !== null
      ? { x1: peaks.length ? colX(peaks[0].col) : l.padL, x2: l.width, y: y(last.baseline) }
      : null;

  return { ...f, ch4Areas, ch4Lines, baselineRule };
}
