import { describe, expect, it } from 'vitest';
import type { ChartPoint } from '../src/core/chartData';
import {
  DEFAULT_LAYOUT,
  DEFAULT_RANGE_FLOOR_MV,
  RANGE_PAD,
  buildLiveChart,
  buildOverviewChart,
  dataRange,
  gridLabel,
  gridStep,
  runs,
  type ChartLayout,
} from '../src/ui/chartPaths';

const layout: ChartLayout = { width: 330, height: 150, ...DEFAULT_LAYOUT };

function series(n: number, stepMs: number, value: (i: number) => number, baseline: number | null = 100): ChartPoint[] {
  return Array.from({ length: n }, (_, i) => ({
    t: i * stepMs,
    ch4: value(i),
    lpg: value(i) / 2,
    baseline,
  }));
}

describe('runs', () => {
  it('splits on gaps longer than 5 s', () => {
    const pts = [{ t: 0 }, { t: 250 }, { t: 500 }, { t: 9000 }, { t: 9250 }];
    expect(runs(pts).map((r) => r.length)).toEqual([3, 2]);
  });

  it('keeps a dense series in one run', () => {
    expect(runs(series(40, 250, () => 500))).toHaveLength(1);
  });
});

describe('dataRange', () => {
  it('centres a narrow range on the data and widens it to the floor plus padding', () => {
    const r = dataRange([3000, 3010, 3005], 150);
    const half = (150 / 2) * (1 + 2 * RANGE_PAD);
    expect(r.yMin).toBeCloseTo(3005 - half, 6);
    expect(r.yMax).toBeCloseTo(3005 + half, 6);
  });

  it('follows a wide range with headroom', () => {
    const r = dataRange([1000, 2000], 150);
    expect(r.yMin).toBeCloseTo(1500 - 500 * (1 + 2 * RANGE_PAD), 6);
    expect(r.yMax).toBeCloseTo(1500 + 500 * (1 + 2 * RANGE_PAD), 6);
  });

  it('never goes below 0 mV', () => {
    expect(dataRange([10, 20], 150).yMin).toBe(0);
  });

  it('has a sane default with no data', () => {
    expect(dataRange([], 150)).toEqual({ yMin: 0, yMax: 150 });
  });
});

describe('grid', () => {
  it('picks a step giving at most four lines', () => {
    expect(gridStep(195)).toBe(50);
    expect(gridStep(1725)).toBe(500);
    expect(gridStep(4000)).toBe(1000);
  });

  it('labels in mV below a volt and in V above', () => {
    expect(gridLabel(250)).toBe('250 mV');
    expect(gridLabel(3000)).toBe('3 V');
    expect(gridLabel(3250)).toBe('3.25 V');
    expect(gridLabel(3500)).toBe('3.5 V');
  });
});

describe('buildLiveChart', () => {
  it('scales to the data of both series plus the baseline', () => {
    // ch4 3000, lpg 1500, baseline 100 -> range 100..3000 padded.
    const c = buildLiveChart(series(10, 250, () => 3000), 2250, 60_000, layout);
    expect(c.yMin).toBeLessThan(100);
    expect(c.yMax).toBeGreaterThan(3000);
    expect(c.yMax).toBeLessThan(3000 + 2900 * RANGE_PAD + 1);
  });

  it('uses the range floor for a flat trace', () => {
    const c = buildLiveChart(series(10, 250, () => 3000, null), 2250, 60_000, layout, 200);
    // ch4 3000, lpg 1500: the natural span is 1500, so the floor of 200 does not apply...
    expect(c.yMax - c.yMin).toBeCloseTo(1500 * (1 + 2 * RANGE_PAD), 6);
    // ...but with a single flat value it does.
    const flat = buildLiveChart(
      series(10, 250, () => 3000, null).map((p) => ({ ...p, lpg: 3000 })),
      2250,
      60_000,
      layout,
      200,
    );
    expect(flat.yMax - flat.yMin).toBeCloseTo(200 * (1 + 2 * RANGE_PAD), 6);
  });

  it('draws gridlines with clean labels inside the range', () => {
    const c = buildLiveChart(series(10, 250, () => 3000), 2250, 60_000, layout);
    expect(c.gridLines.length).toBeGreaterThan(0);
    expect(c.gridLines.length).toBeLessThanOrEqual(4);
    expect(c.gridLines.map((g) => g.label)).toEqual(['1 V', '2 V', '3 V']);
  });

  it('emits one area and one line per gap-free run, and an end marker', () => {
    const pts = [...series(10, 250, () => 500), ...series(10, 250, () => 500).map((p) => ({ ...p, t: p.t + 30_000 }))];
    const c = buildLiveChart(pts, 32_250, 60_000, layout);
    expect(c.ch4Areas).toHaveLength(2);
    expect(c.ch4Lines).toHaveLength(2);
    expect(c.lpgLines).toHaveLength(2);
    expect(c.ch4End).not.toBeNull();
    expect(c.ch4End!.x).toBeCloseTo(layout.width, 0);
  });

  it('breaks the baseline where there is none', () => {
    const pts = series(30, 250, () => 500).map((p, i) => ({ ...p, baseline: i >= 10 && i < 20 ? null : 100 }));
    const c = buildLiveChart(pts, 7250, 60_000, layout);
    expect(c.baselineLines).toHaveLength(2);
  });

  it('produces no geometry for an empty series', () => {
    const c = buildLiveChart([], 0, 60_000, layout);
    expect(c.ch4Areas).toEqual([]);
    expect(c.baselineLines).toEqual([]);
    expect(c.ch4End).toBeNull();
    expect(c.yMin).toBe(0);
    expect(c.yMax).toBe(DEFAULT_RANGE_FLOOR_MV);
  });

  it('keeps every path inside the plot area', () => {
    const c = buildLiveChart(series(200, 250, (i) => 400 + i * 20), 49_750, 60_000, layout);
    const ys = [...c.ch4Lines.join(' ').matchAll(/[ML]\S+ (\S+)/g)].map((m) => parseFloat(m[1]));
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(layout.padT - 0.01);
    expect(Math.max(...ys)).toBeLessThanOrEqual(layout.height - layout.padB + 0.01);
  });
});

describe('buildOverviewChart', () => {
  it('scales to the CH4 range in the window plus the current baseline', () => {
    const c = buildOverviewChart(series(50, 1000, () => 500, 250), 49_000, 600_000, layout);
    expect(c.yMin).toBeLessThan(250);
    expect(c.yMax).toBeGreaterThan(500);
  });

  it('keeps a brief plume via peak-per-column decimation', () => {
    const pts = series(600, 1000, (i) => (i === 300 ? 4000 : 500));
    const c = buildOverviewChart(pts, 599_000, 600_000, layout);
    const ys = [...c.ch4Lines.join(' ').matchAll(/[ML]\S+ (\S+)/g)].map((m) => parseFloat(m[1]));
    // The plume must reach near the top of the plot, not be averaged away.
    expect(Math.min(...ys)).toBeLessThan(layout.padT + 40);
  });

  it('rules the current baseline across the window', () => {
    const c = buildOverviewChart(series(50, 1000, () => 500, 250), 49_000, 600_000, layout);
    expect(c.baselineRule).not.toBeNull();
    expect(c.baselineRule!.x2).toBe(layout.width);
  });

  it('has no baseline rule when the last point has none', () => {
    const c = buildOverviewChart(series(50, 1000, () => 500, null), 49_000, 600_000, layout);
    expect(c.baselineRule).toBeNull();
  });
});
