import { describe, expect, it } from 'vitest';
import {
  BASE_CELL_M,
  MIN_CELL_PX,
  SCALE_FLOOR,
  binCells,
  cellAt,
  cellMetres,
  cellRects,
  heatColour,
  heatRange,
  inferno,
  metresPerUnit,
  scalePos,
  type HeatCell,
} from '../src/core/heatmap';
import { fromScreen, lonLatToMerc, toScreen, worldPx } from '../src/core/mapView';
import type { TrackPoint } from '../src/core/track';

const LAT = 51.75;
const mPerUnit = metresPerUnit(LAT);
const O = lonLatToMerc(-1.25, LAT);

/** A point `east` / `south` metres from the middle of a 5 m cell. */
function pt(east: number, south: number, ch4Mv: number | null, slope: number | null): TrackPoint {
  const cell = 5 / mPerUnit;
  const cx = (Math.floor(O.mx / cell) + 0.5) * cell;
  const cy = (Math.floor(O.my / cell) + 0.5) * cell;
  return { lat: LAT, lon: -1.25, mx: cx + east / mPerUnit, my: cy + south / mPerUnit, t: 0, ch4Mv, slope, spike: false };
}

describe('cellMetres', () => {
  it('uses the plotter cell size when zoomed in', () => {
    expect(cellMetres(19, LAT)).toBe(BASE_CELL_M);
  });

  it('coarsens on a 1-2-5 ladder so cells stay visible when zoomed out', () => {
    const ladder = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];
    const c = cellMetres(14, LAT);
    expect(ladder).toContain(c);
    expect((c / mPerUnit) * worldPx(14)).toBeGreaterThanOrEqual(MIN_CELL_PX);
    const smaller = ladder[ladder.indexOf(c) - 1];
    expect((smaller / mPerUnit) * worldPx(14)).toBeLessThan(MIN_CELL_PX);
  });
});

describe('binCells', () => {
  // Two points in one 5 m cell, one in the next cell east, one with no reading.
  const pts = [pt(0, 0, 1500, 10), pt(1, 0, 1700, 90), pt(5, 0, 1600, -20), pt(10, 0, null, null)];

  it('averages raw readings per cell and counts the fixes', () => {
    const cells = binCells(pts, 'raw', 5, LAT).sort((a, b) => a.ix - b.ix);
    expect(cells.map((c) => [c.value, c.n])).toEqual([
      [1600, 2],
      [1600, 1],
    ]);
    expect(cells[1].ix - cells[0].ix).toBe(1);
  });

  it('keeps the steepest rise per cell for spikes', () => {
    const cells = binCells(pts, 'spikes', 5, LAT).sort((a, b) => a.ix - b.ix);
    expect(cells.map((c) => c.value)).toEqual([90, -20]);
  });

  it('finds the cell under a tapped point', () => {
    const cells = binCells(pts, 'raw', 5, LAT);
    const hit = cellAt(cells, pts[1].mx, pts[1].my, 5, LAT);
    expect(hit?.n).toBe(2);
    const far = pt(100, 100, null, null);
    expect(cellAt(cells, far.mx, far.my, 5, LAT)).toBeNull();
  });
});

describe('heatRange', () => {
  const cells = (vals: number[]): HeatCell[] => vals.map((value, i) => ({ ix: i, iy: 0, value, n: 1 }));

  it('spans raw cells min to max', () => {
    expect(heatRange(cells([1500, 1620, 1580]), 'raw', 25)).toEqual({ lo: 1500, hi: 1620 });
  });

  it('gives one flat raw value a scale', () => {
    expect(heatRange(cells([1500]), 'raw', 25)).toEqual({ lo: 1500, hi: 1501 });
  });

  it('starts spikes at zero and tops them at the 99th percentile', () => {
    const vals = Array.from({ length: 200 }, (_, i) => i); // 0..199
    vals.push(5000); // one extreme cell
    const r = heatRange(cells(vals), 'spikes', 25)!;
    expect(r.lo).toBe(0);
    expect(r.hi).toBeGreaterThan(190);
    expect(r.hi).toBeLessThan(5000);
  });

  it('never tops the spike scale below the threshold', () => {
    expect(heatRange(cells([1, 3, 2]), 'spikes', 25)).toEqual({ lo: 0, hi: 25 });
  });

  it('returns null with nothing to scale', () => {
    expect(heatRange([], 'raw', 25)).toBeNull();
  });
});

describe('colours', () => {
  it('samples inferno at its ends', () => {
    expect(inferno(0)).toBe('rgb(0,0,4)');
    expect(inferno(1)).toBe('rgb(252,255,164)');
    expect(inferno(2)).toBe('rgb(252,255,164)');
  });

  it('lifts the bottom of the scale off black', () => {
    expect(heatColour(0)).toBe(inferno(SCALE_FLOOR));
    expect(heatColour(1)).toBe(inferno(1));
  });

  it('clamps scale positions', () => {
    const r = { lo: 0, hi: 100 };
    expect(scalePos(-5, r)).toBe(0);
    expect(scalePos(50, r)).toBe(0.5);
    expect(scalePos(500, r)).toBe(1);
  });
});

describe('cellRects', () => {
  it('places cells on screen and drops those out of view', () => {
    const cellM = 5;
    const cell = cellM / mPerUnit;
    const view = { cx: 100.5 * cell, cy: 200.5 * cell, zoom: 19 };
    const size = { width: 300, height: 300 };
    const cells: HeatCell[] = [
      { ix: 100, iy: 200, value: 0, n: 1 }, // the cell at the centre
      { ix: 100000, iy: 200, value: 0, n: 1 }, // far away
    ];
    const rects = cellRects(cells, { lo: 0, hi: 1 }, cellM, LAT, view, size);
    expect(rects).toHaveLength(1);
    const px = cell * worldPx(19);
    expect(rects[0].size).toBeCloseTo(px, 9);
    expect(rects[0].x).toBeCloseTo(150 - px / 2, 6);
    expect(rects[0].y).toBeCloseTo(150 - px / 2, 6);
    expect(rects[0].fill).toBe(heatColour(0));
  });
});

describe('fromScreen', () => {
  it('inverts toScreen', () => {
    const view = { cx: O.mx, cy: O.my, zoom: 17.3 };
    const size = { width: 360, height: 380 };
    const p = { mx: O.mx + 3e-7, my: O.my - 2e-7 };
    const s = toScreen(p, view, size);
    const back = fromScreen(s.x, s.y, view, size);
    expect(back.mx).toBeCloseTo(p.mx, 12);
    expect(back.my).toBeCloseTo(p.my, 12);
  });
});
