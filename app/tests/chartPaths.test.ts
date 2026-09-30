import { describe, expect, it } from 'vitest';
import type { ChartPoint } from '../src/core/chartData';
import {
  DEFAULT_LAYOUT,
  DEFAULT_RANGE_FLOOR_MV,
  RANGE_PAD,
  MIN_SPAN_MS,
  buildLiveChart,
  buildOverviewChart,
  buildSlopeChart,
  dataRange,
  fitSpan,
  gridLabel,
  gridStep,
  runs,
  type ChartLayout,
} from '../src/ui/chartPaths';

const layout: ChartLayout = { width: 330, height: 150, ...DEFAULT_LAYOUT };

function series(
  n: number,
  stepMs: number,
  value: (i: number) => number,
  baseline: number | null = 100,
  lpgBaseline: number | null = 50,
): ChartPoint[] {
  return Array.from({ length: n }, (_, i) => ({
    t: i * stepMs,
    ch4: value(i),
    lpg: value(i) / 2,
    baseline,
    lpgBaseline,
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
  it('scales each channel to its own data, ignoring the baseline', () => {
    // ch4 3000 (baseline 100 is not drawn and must not widen the range); lpg 1500.
    const pts = series(10, 250, () => 3000);
    const ch4 = buildLiveChart(pts, 2250, 60_000, layout, 150, 'ch4');
    expect(ch4.yMin).toBeGreaterThan(2800);
    expect(ch4.yMax).toBeGreaterThan(3000);
    const lpg = buildLiveChart(pts, 2250, 60_000, layout, 150, 'lpg');
    expect(lpg.yMin).toBeGreaterThan(1300);
    expect(lpg.yMax).toBeGreaterThan(1500);
    expect(lpg.yMax).toBeLessThan(ch4.yMin);
  });

  it('fits the time axis to the data, between 5 s and the full span', () => {
    expect(fitSpan([], 1000, 60_000)).toBe(60_000);
    expect(fitSpan([{ t: 0 }], 1000, 60_000)).toBe(MIN_SPAN_MS);
    expect(fitSpan([{ t: 0 }], 12_000, 60_000)).toBe(12_000);
    expect(fitSpan([{ t: 0 }], 90_000, 60_000)).toBe(60_000);
    // 10 s of data on a 60 s chart: the oldest point sits at the left edge, not 5/6 of the way across.
    const c = buildLiveChart(series(41, 250, () => 500), 10_000, 60_000, layout);
    expect(c.leftLabel).toBe('−10 s');
    const xs = [...c.lines[0].matchAll(/[ML](\S+) /g)].map((m) => parseFloat(m[1]));
    expect(Math.min(...xs)).toBeCloseTo(layout.padL, 0);
    expect(Math.max(...xs)).toBeCloseTo(layout.width, 0);
  });

  it('uses the range floor for a flat trace', () => {
    const flat = buildLiveChart(series(10, 250, () => 3000, null), 2250, 60_000, layout, 200, 'ch4');
    expect(flat.yMax - flat.yMin).toBeCloseTo(200 * (1 + 2 * RANGE_PAD), 6);
  });

  it('draws gridlines with clean labels inside the range', () => {
    const c = buildLiveChart(series(10, 250, () => 3000), 2250, 60_000, layout);
    expect(c.gridLines.length).toBeGreaterThan(0);
    expect(c.gridLines.length).toBeLessThanOrEqual(4);
    expect(c.gridLines.map((g) => g.label)).toEqual(['2.95 V', '3 V', '3.05 V']);
  });

  it('emits one area and one line per gap-free run, and an end marker', () => {
    const pts = [...series(10, 250, () => 500), ...series(10, 250, () => 500).map((p) => ({ ...p, t: p.t + 30_000 }))];
    const c = buildLiveChart(pts, 32_250, 60_000, layout);
    expect(c.areas).toHaveLength(2);
    expect(c.lines).toHaveLength(2);
    expect(c.end).not.toBeNull();
    expect(c.end!.x).toBeCloseTo(layout.width, 0);
  });

  it('produces no geometry for an empty series', () => {
    const c = buildLiveChart([], 0, 60_000, layout);
    expect(c.areas).toEqual([]);
    expect(c.end).toBeNull();
    expect(c.yMin).toBe(0);
    expect(c.yMax).toBe(DEFAULT_RANGE_FLOOR_MV);
  });

  it('keeps every path inside the plot area', () => {
    const c = buildLiveChart(series(200, 250, (i) => 400 + i * 20), 49_750, 60_000, layout);
    const ys = [...c.lines.join(' ').matchAll(/[ML]\S+ (\S+)/g)].map((m) => parseFloat(m[1]));
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(layout.padT - 0.01);
    expect(Math.max(...ys)).toBeLessThanOrEqual(layout.height - layout.padB + 0.01);
  });
});

describe('buildOverviewChart', () => {
  it('scales to the channel range in the window, ignoring the baseline', () => {
    const pts = series(50, 1000, () => 500, 250, 60);
    const ch4 = buildOverviewChart(pts, 49_000, 600_000, layout, 150, 'ch4');
    expect(ch4.yMin).toBeGreaterThan(250);
    expect(ch4.yMax).toBeGreaterThan(500);
    const lpg = buildOverviewChart(pts, 49_000, 600_000, layout, 150, 'lpg');
    expect(lpg.yMin).toBeGreaterThan(60);
    expect(lpg.yMax).toBeGreaterThan(250);
  });

  it('fits the window to the data: 49 s of samples fill the width and label as such', () => {
    const c = buildOverviewChart(series(50, 1000, () => 500), 49_000, 600_000, layout);
    expect(c.leftLabel).toBe('−49 s');
    const xs = [...c.lines[0].matchAll(/[ML](\S+) /g)].map((m) => parseFloat(m[1]));
    expect(Math.min(...xs)).toBeLessThan(layout.padL + 4);
    expect(Math.max(...xs)).toBeGreaterThan(layout.width - 4);
    expect(buildOverviewChart(series(700, 1000, () => 500), 699_000, 600_000, layout).leftLabel).toBe('−10 min');
  });

  it('keeps a brief plume via peak-per-column decimation', () => {
    const pts = series(600, 1000, (i) => (i === 300 ? 4000 : 500));
    const c = buildOverviewChart(pts, 599_000, 600_000, layout);
    const ys = [...c.lines.join(' ').matchAll(/[ML]\S+ (\S+)/g)].map((m) => parseFloat(m[1]));
    // The plume must reach near the top of the plot, not be averaged away.
    expect(Math.min(...ys)).toBeLessThan(layout.padT + 40);
  });

});

describe('spike overlay and derivative panel', () => {
  const withSpikes = (): ChartPoint[] =>
    series(40, 250, (i) => 500 + (i > 20 ? 300 : 0)).map((p, i) => ({
      ...p,
      ch4Slope: i < 4 ? null : i === 21 || i === 22 ? 600 : 2,
      ch4Spike: i === 21 || i === 22,
    }));

  it('marks flagged samples on the live trace', () => {
    const c = buildLiveChart(withSpikes(), 40 * 250, 60_000, layout);
    expect(c.spikeMarks).toHaveLength(2);
    for (const m of c.spikeMarks) {
      expect(m.x).toBeGreaterThan(layout.padL);
      expect(m.y).toBeGreaterThanOrEqual(layout.padT);
      expect(m.y).toBeLessThanOrEqual(layout.height - layout.padB);
    }
    expect(buildLiveChart(series(40, 250, () => 500), 40 * 250, 60_000, layout).spikeMarks).toEqual([]);
  });

  it('derivative panel shares the time axis and has its own limits including zero', () => {
    const live = buildLiveChart(withSpikes(), 40 * 250, 60_000, layout);
    const c = buildSlopeChart(withSpikes(), 40 * 250, 60_000, layout, 'ch4', 150);
    expect(c.lines.length).toBeGreaterThan(0);
    expect(c.yMin).toBeLessThan(0);
    expect(c.yMax).toBeGreaterThan(600);
    expect(c.zeroY).toBeGreaterThan(layout.padT);
    expect(c.zeroY).toBeLessThan(layout.height - layout.padB);
    expect(c.thresholdY).not.toBeNull();
    expect(c.thresholdY!).toBeLessThan(c.zeroY); // above zero on screen
    // Same x for the same sample in both charts.
    expect(c.spikeMarks).toHaveLength(2);
    expect(c.spikeMarks[0].x).toBeCloseTo(live.spikeMarks[0].x, 6);
    // A flat trace still gets a visible range and no marks.
    const flat = buildSlopeChart(series(40, 250, () => 500), 40 * 250, 60_000, layout);
    expect(flat.lines).toEqual([]);
    expect(flat.spikeMarks).toEqual([]);
    expect(flat.yMax - flat.yMin).toBeGreaterThan(20);
  });

  it('overview shows one tick per column with a flagged sample', () => {
    const c = buildOverviewChart(withSpikes(), 40 * 250, 60_000, layout);
    expect(c.spikeTicks.length).toBeGreaterThanOrEqual(1);
    expect(c.spikeTicks.length).toBeLessThanOrEqual(2);
    expect(buildOverviewChart(series(10, 250, () => 500), 2500, 60_000, layout).spikeTicks).toEqual([]);
  });
});
