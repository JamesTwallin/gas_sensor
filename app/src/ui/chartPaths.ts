// Chart geometry, ported from the web app's canvas renderer (src/ui/charts.ts).
// The drawing itself is react-native-svg (ui/charts.tsx); everything that decides
// *where* a line goes lives here, pure and DOM-free, so it is unit-tested.
//
//  - live:     CH4 VRL as a filled area, LPG as a line, CH4 baseline dotted; 0 V
//              floor, dynamic top (max + 10 %, never under 1 V); dashed 1 V grid.
//  - overview: last 10 min of CH4, peak-per-column, fixed 0..VC scale, baseline
//              dotted, same 1 V grid.

import { dynamicYMax, peakPerColumn, type ChartPoint } from '../core/chartData';

export const GRID_STEP_MV = 1000;
export const LIVE_FLOOR_MV = 1000;
/** A gap longer than this between samples breaks the trace. */
export const GAP_MS = 5000;

export interface ChartLayout {
  width: number;
  height: number;
  padL: number;
  padT: number;
  padB: number;
}

export const DEFAULT_LAYOUT = { padL: 30, padT: 6, padB: 20 };

export interface GridLine {
  y: number;
  label: string;
}

export interface ChartFrame {
  yMax: number;
  gridLines: GridLine[];
  /** y of the 0 mV axis. */
  axisY: number;
  leftLabel: string;
  rightLabel: string;
}

/** Map mV -> y, clamped into the plot area. */
function makeY(l: ChartLayout, yMax: number): (mv: number) => number {
  const plotH = l.height - l.padB - l.padT;
  return (mv: number) => l.padT + plotH - (Math.max(0, Math.min(yMax, mv)) / yMax) * plotH;
}

function frame(l: ChartLayout, yMax: number, leftLabel: string, rightLabel: string): ChartFrame {
  const y = makeY(l, yMax);
  const gridLines: GridLine[] = [];
  for (let level = GRID_STEP_MV; level < yMax; level += GRID_STEP_MV) {
    gridLines.push({ y: Math.round(y(level)) + 0.5, label: `${level / 1000}V` });
  }
  return { yMax, gridLines, axisY: y(0) + 0.5, leftLabel, rightLabel };
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

function polyline(pts: readonly { x: number; y: number }[]): string {
  return pts.map((p, i) => `${i ? 'L' : 'M'}${n(p.x)} ${n(p.y)}`).join(' ');
}

/** A polyline closed down to the axis, for the filled area under a trace. */
function area(pts: readonly { x: number; y: number }[], axisY: number): string {
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
}

export function buildLiveChart(
  pts: readonly ChartPoint[],
  now: number,
  spanMs: number,
  l: ChartLayout,
): LiveChart {
  const yMax = dynamicYMax(
    (function* () {
      for (const p of pts) {
        yield p.ch4;
        yield p.lpg;
      }
    })(),
    LIVE_FLOOR_MV,
  );
  const f = frame(l, yMax, `−${Math.round(spanMs / 1000)} s`, 'now');
  const y = makeY(l, yMax);
  const plotW = l.width - l.padL;
  const x = (t: number) => l.padL + ((t - (now - spanMs)) / spanMs) * plotW;

  const ch4Areas: string[] = [];
  const ch4Lines: string[] = [];
  const lpgLines: string[] = [];
  for (const run of runs(pts)) {
    if (run.length < 2) continue;
    const ch4 = run.map((p) => ({ x: x(p.t), y: y(p.ch4) }));
    const lpg = run.map((p) => ({ x: x(p.t), y: y(p.lpg) }));
    ch4Areas.push(area(ch4, f.axisY));
    ch4Lines.push(polyline(ch4));
    lpgLines.push(polyline(lpg));
  }

  // The baseline breaks on a link gap and wherever there is no trusted baseline.
  const baselineLines: string[] = [];
  let seg: { x: number; y: number }[] = [];
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

  return { ...f, ch4Areas, ch4Lines, lpgLines, baselineLines };
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
  fullScaleMv: number,
  l: ChartLayout,
): OverviewChart {
  const yMax = Math.max(GRID_STEP_MV, fullScaleMv);
  const f = frame(l, yMax, `−${Math.round(spanMs / 60000)} min`, 'now');
  const y = makeY(l, yMax);
  const plotW = l.width - l.padL;
  const cols = Math.max(1, Math.floor(plotW / 2)); // one column per 2 px
  const t0 = now - spanMs;
  const colX = (col: number) => l.padL + ((col + 0.5) / cols) * plotW;
  const peaks = peakPerColumn(pts, t0, now, cols, (p) => p.ch4);

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

  const last = pts.length ? pts[pts.length - 1] : null;
  const baselineRule =
    last && last.baseline !== null
      ? { x1: peaks.length ? colX(peaks[0].col) : l.padL, x2: l.width, y: y(last.baseline) }
      : null;

  return { ...f, ch4Areas, ch4Lines, baselineRule };
}
