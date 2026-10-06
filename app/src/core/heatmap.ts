// Heatmap for the survey map, the phone version of tools/plot_map.py: the
// track's readings binned onto a square ground grid, one colour per cell on a
// continuous gradient.
//
//  - raw:    mean CH4 VRL per cell (mV), scaled min..max of the cells, like
//            plot_map.py's raw VOUT map.
//  - spikes: steepest CH4 rise per cell (mV/s), scaled from 0 (rises only;
//            falls are not coloured) to the 99th percentile of the cells, so
//            one extreme cell does not wash the rest flat, like --deriv. The
//            top is never below the spike threshold, so a calm survey does
//            not paint its noise in the hottest colours.
//
// Cells are 5 m on the ground like the plotter's, made bigger when zoomed out
// so each stays a visible block on screen. Sizes snap to a 1-2-5 ladder so the
// grid does not shimmer while pinching.
//
// The colour map is inferno (dark = little, bright = a lot), sampled at the
// same stops matplotlib uses.

import { toScreen, worldPx, type MapView, type Size } from './mapView';
import type { TrackPoint } from './track';

export type HeatMode = 'raw' | 'spikes';

/** Ground cell size at full zoom (m), as tools/plot_map.py BIN_SIZE_M. */
export const BASE_CELL_M = 5;
/** Smallest a cell may be drawn (px) before the grid coarsens. */
export const MIN_CELL_PX = 7;
/** Spike scale tops out at this percentile of the cells (plot_map.py DERIV_VMAX_PCT). */
export const SPIKE_TOP_PCT = 99;

/** Ground metres per unit of normalised Mercator at this latitude. */
export function metresPerUnit(lat: number): number {
  return 40_075_016.686 * Math.cos((lat * Math.PI) / 180);
}

/** Cell size (m): BASE_CELL_M, or the next 1-2-5 step that is at least MIN_CELL_PX on screen. */
export function cellMetres(zoom: number, lat: number): number {
  const mPerPx = metresPerUnit(lat) / worldPx(zoom);
  const need = Math.max(BASE_CELL_M, MIN_CELL_PX * mPerPx);
  for (let decade = 1; ; decade *= 10) {
    for (const step of [1, 2, 5]) {
      const c = step * decade;
      if (c >= need) return c;
    }
  }
}

export interface HeatCell {
  ix: number;
  iy: number;
  value: number;
  /** GPS fixes that fell in the cell. */
  n: number;
}

/**
 * Bin points into square cells of `cellM` metres (sized at `lat`, the track's
 * latitude: over a walk the scale barely changes). Raw takes the mean of the
 * points' CH4 VRL; spikes takes the steepest slope. Points without the value
 * are left out.
 */
export function binCells(pts: readonly TrackPoint[], mode: HeatMode, cellM: number, lat: number): HeatCell[] {
  const cell = cellM / metresPerUnit(lat); // in normalised Mercator
  const acc = new Map<string, { ix: number; iy: number; sum: number; n: number; max: number }>();
  for (const p of pts) {
    const v = mode === 'raw' ? p.ch4Mv : p.slope;
    if (v === null || !Number.isFinite(v)) continue;
    const ix = Math.floor(p.mx / cell);
    const iy = Math.floor(p.my / cell);
    const key = `${ix},${iy}`;
    const a = acc.get(key);
    if (a) {
      a.sum += v;
      a.n += 1;
      if (v > a.max) a.max = v;
    } else {
      acc.set(key, { ix, iy, sum: v, n: 1, max: v });
    }
  }
  return [...acc.values()].map((a) => ({ ix: a.ix, iy: a.iy, value: mode === 'raw' ? a.sum / a.n : a.max, n: a.n }));
}

/** The cell under a normalised-Mercator point (a tap), or null if that spot has none. */
export function cellAt(cells: readonly HeatCell[], mx: number, my: number, cellM: number, lat: number): HeatCell | null {
  const cell = cellM / metresPerUnit(lat);
  const ix = Math.floor(mx / cell);
  const iy = Math.floor(my / cell);
  return cells.find((c) => c.ix === ix && c.iy === iy) ?? null;
}

export interface HeatRange {
  lo: number;
  hi: number;
}

function percentile(sorted: number[], pct: number): number {
  if (!sorted.length) return NaN;
  const i = ((sorted.length - 1) * pct) / 100;
  const a = Math.floor(i);
  const b = Math.ceil(i);
  return sorted[a] + (sorted[b] - sorted[a]) * (i - a);
}

/** The colour scale's ends for these cells; null when there is nothing to scale. */
export function heatRange(cells: readonly HeatCell[], mode: HeatMode, thresholdMvPerS: number | null): HeatRange | null {
  if (!cells.length) return null;
  const vals = cells.map((c) => c.value).sort((a, b) => a - b);
  if (mode === 'raw') {
    const lo = vals[0];
    let hi = vals[vals.length - 1];
    if (hi - lo < 1) hi = lo + 1; // one flat value still needs a scale
    return { lo, hi };
  }
  const top = Math.max(percentile(vals, SPIKE_TOP_PCT), thresholdMvPerS ?? 0, 1);
  return { lo: 0, hi: top };
}

/** 0..1 position of a value on the scale, clamped. */
export function scalePos(v: number, r: HeatRange): number {
  return Math.max(0, Math.min(1, (v - r.lo) / (r.hi - r.lo)));
}

// matplotlib inferno at t = 0, 0.1, ..., 1.
const INFERNO: [number, number, number][] = [
  [0, 0, 4],
  [22, 11, 57],
  [66, 10, 104],
  [106, 23, 110],
  [147, 38, 103],
  [188, 55, 84],
  [221, 81, 58],
  [243, 120, 25],
  [252, 165, 10],
  [246, 215, 70],
  [252, 255, 164],
];

export function inferno(t: number): string {
  const x = Math.max(0, Math.min(1, t)) * (INFERNO.length - 1);
  const i = Math.min(INFERNO.length - 2, Math.floor(x));
  const f = x - i;
  const c = INFERNO[i].map((a, k) => Math.round(a + (INFERNO[i + 1][k] - a) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

/** Where the scale starts on inferno: its first tenth is near-black and vanishes on imagery. */
export const SCALE_FLOOR = 0.12;

/** Colour for a 0..1 scale position. */
export function heatColour(t: number): string {
  return inferno(SCALE_FLOOR + (1 - SCALE_FLOOR) * Math.max(0, Math.min(1, t)));
}

export interface CellRect {
  x: number;
  y: number;
  size: number;
  fill: string;
}

/** Screen rectangles for the cells that fall inside the view. */
export function cellRects(
  cells: readonly HeatCell[],
  range: HeatRange,
  cellM: number,
  lat: number,
  view: MapView,
  size: Size,
): CellRect[] {
  const cell = cellM / metresPerUnit(lat);
  const px = cell * worldPx(view.zoom);
  const out: CellRect[] = [];
  for (const c of cells) {
    const s = toScreen({ mx: c.ix * cell, my: c.iy * cell }, view, size);
    if (s.x > size.width || s.y > size.height || s.x + px < 0 || s.y + px < 0) continue;
    out.push({ x: s.x, y: s.y, size: px, fill: heatColour(scalePos(c.value, range)) });
  }
  return out;
}
