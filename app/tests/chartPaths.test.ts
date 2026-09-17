import { describe, expect, it } from 'vitest';
import type { ChartPoint } from '../src/core/chartData';
import {
  DEFAULT_LAYOUT,
  buildLiveChart,
  buildOverviewChart,
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

describe('buildLiveChart', () => {
  it('floors the scale at 1 V and adds 10 % headroom above it', () => {
    expect(buildLiveChart(series(10, 250, () => 200), 2250, 60_000, layout).yMax).toBe(1000);
    const tall = buildLiveChart(series(10, 250, () => 2000), 2250, 60_000, layout);
    expect(tall.yMax).toBeCloseTo(2200, 6);
  });

  it('draws a grid line per volt below the top', () => {
    const c = buildLiveChart(series(10, 250, () => 3000), 2250, 60_000, layout);
    expect(c.gridLines.map((g) => g.label)).toEqual(['1V', '2V', '3V']);
  });

  it('emits one area and one line per gap-free run', () => {
    const pts = [...series(10, 250, () => 500), ...series(10, 250, () => 500).map((p) => ({ ...p, t: p.t + 30_000 }))];
    const c = buildLiveChart(pts, 32_250, 60_000, layout);
    expect(c.ch4Areas).toHaveLength(2);
    expect(c.ch4Lines).toHaveLength(2);
    expect(c.lpgLines).toHaveLength(2);
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
    expect(c.yMax).toBe(1000);
  });

  it('keeps every path inside the plot area', () => {
    const c = buildLiveChart(series(200, 250, (i) => 400 + i * 20), 49_750, 60_000, layout);
    const ys = [...c.ch4Lines.join(' ').matchAll(/[ML]\S+ (\S+)/g)].map((m) => parseFloat(m[1]));
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(layout.padT - 0.01);
    expect(Math.max(...ys)).toBeLessThanOrEqual(layout.height - layout.padB + 0.01);
  });
});

describe('buildOverviewChart', () => {
  it('uses a fixed 0..VC scale', () => {
    expect(buildOverviewChart(series(50, 1000, () => 500), 49_000, 600_000, 5000, layout).yMax).toBe(5000);
  });

  it('keeps a brief plume via peak-per-column decimation', () => {
    const pts = series(600, 1000, (i) => (i === 300 ? 4000 : 500));
    const c = buildOverviewChart(pts, 599_000, 600_000, 5000, layout);
    const ys = [...c.ch4Lines.join(' ').matchAll(/[ML]\S+ (\S+)/g)].map((m) => parseFloat(m[1]));
    // The plume must reach near the top of the plot, not be averaged away.
    expect(Math.min(...ys)).toBeLessThan(layout.padT + 40);
  });

  it('rules the current baseline across the window', () => {
    const c = buildOverviewChart(series(50, 1000, () => 500, 250), 49_000, 600_000, 5000, layout);
    expect(c.baselineRule).not.toBeNull();
    expect(c.baselineRule!.x2).toBe(layout.width);
  });

  it('has no baseline rule when the last point has none', () => {
    const c = buildOverviewChart(series(50, 1000, () => 500, null), 49_000, 600_000, 5000, layout);
    expect(c.baselineRule).toBeNull();
  });
});
