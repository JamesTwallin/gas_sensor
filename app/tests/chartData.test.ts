import { describe, expect, it } from 'vitest';
import { ChartBuffer, dynamicYMax, peakPerColumn } from '../src/core/chartData';
import { batteryPercent } from '../src/core/simulator';

describe('chart data', () => {
  it('ChartBuffer keeps the span and slices by time', () => {
    const b = new ChartBuffer(1000);
    for (let t = 0; t <= 2000; t += 250) b.push({ t, ch4: t, lpg: 0, baseline: null });
    expect(b.all().map((p) => p.t)).toEqual([1250, 1500, 1750, 2000]);
    expect(b.since(1500).map((p) => p.t)).toEqual([1750, 2000]);
    expect(b.last?.t).toBe(2000);
    b.clear();
    expect(b.length).toBe(0);
    expect(b.last).toBeNull();
  });

  it('peakPerColumn keeps a one-sample spike', () => {
    const pts = Array.from({ length: 100 }, (_, i) => ({ t: i, v: i === 37 ? 999 : 1 }));
    const cols = peakPerColumn(pts, 0, 100, 10, (p) => p.v);
    expect(cols.length).toBe(10);
    expect(cols[3]).toEqual({ col: 3, peak: 999 });
    expect(cols[4].peak).toBe(1);
  });

  it('peakPerColumn omits empty columns', () => {
    const cols = peakPerColumn([{ t: 5 }, { t: 95 }], 0, 100, 10, () => 1);
    expect(cols.map((c) => c.col)).toEqual([0, 9]);
  });

  it('dynamicYMax: max + 10 %, floored', () => {
    expect(dynamicYMax([100, 200], 1000)).toBe(1000);
    expect(dynamicYMax([3000, 100], 1000)).toBeCloseTo(3300, 6);
  });

  it('battery percent is monotonic and bounded', () => {
    expect(batteryPercent(3000)).toBe(0);
    expect(batteryPercent(4300)).toBe(100);
    let prev = -1;
    for (let v = 3300; v <= 4200; v += 10) {
      const p = batteryPercent(v);
      expect(p).toBeGreaterThanOrEqual(prev);
      prev = p;
    }
  });
});
