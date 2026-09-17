import { describe, expect, it } from 'vitest';
import { TimeWindow, classifyLevel, nthElement, percentile } from '../src/core/windows';

describe('percentile (rev A: sorted[floor(p*(n-1))])', () => {
  it('matches the sorted index', () => {
    const vals = [9, 1, 8, 2, 7, 3, 6, 4, 5, 0];
    const sorted = [...vals].sort((a, b) => a - b);
    for (const p of [0, 0.15, 0.5, 0.99, 1]) {
      expect(percentile(vals, p)).toBe(sorted[Math.floor(p * (vals.length - 1))]);
    }
    expect(vals).toEqual([9, 1, 8, 2, 7, 3, 6, 4, 5, 0]); // input untouched
  });

  it('empty and single', () => {
    expect(percentile([], 0.15)).toBeNull();
    expect(percentile([42], 0.15)).toBe(42);
  });

  it('nthElement agrees with sort on random data with duplicates', () => {
    let seed = 7;
    const rnd = () => (seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31;
    for (let trial = 0; trial < 200; trial++) {
      const n = 1 + Math.floor(rnd() * 300);
      const arr = Array.from({ length: n }, () => Math.floor(rnd() * 20));
      const k = Math.floor(rnd() * n);
      const sorted = [...arr].sort((a, b) => a - b);
      expect(nthElement([...arr], k)).toBe(sorted[k]);
    }
  });

  it('15th percentile ignores a brief plume in a 2-min window', () => {
    const w = new TimeWindow(120_000);
    for (let t = 250; t <= 120_000; t += 250) {
      const plume = t > 100_000 && t < 115_000 ? 2000 : 0; // 15 s = 12.5 % of the window
      w.push(t, 1000 + (t % 1000 === 0 ? 5 : 0) + plume);
    }
    expect(w.length).toBe(480); // = rev A BG_WINDOW_SAMPLES at 250 ms
    expect(percentile(w.values(), 0.15)).toBe(1000);
  });
});

describe('TimeWindow', () => {
  it('keeps samples with t in (latest - window, latest]', () => {
    const w = new TimeWindow(1000);
    [0, 250, 500, 750, 1000, 1250].forEach((t) => w.push(t, t));
    expect(w.values()).toEqual([500, 750, 1000, 1250]);
    expect(w.min()).toBe(500);
    expect(w.max()).toBe(1250);
  });

  it('is time-based: a slower interval holds fewer samples', () => {
    const fast = new TimeWindow(120_000);
    const slow = new TimeWindow(120_000);
    for (let t = 0; t <= 600_000; t += 100) fast.push(t, 1);
    for (let t = 0; t <= 600_000; t += 1000) slow.push(t, 1);
    expect(fast.length).toBe(1200);
    expect(slow.length).toBe(120);
  });

  it('drops everything after a long gap', () => {
    const w = new TimeWindow(1000);
    w.push(0, 1);
    w.push(500, 2);
    w.push(10_000, 3);
    expect(w.values()).toEqual([3]);
  });

  it('survives compaction with correct contents', () => {
    const w = new TimeWindow(1000);
    for (let t = 0; t < 100_000; t += 10) w.push(t, t);
    expect(w.length).toBe(100);
    expect(w.min()).toBe(99_000);
    expect(w.max()).toBe(99_990);
  });

  it('empty min/max are null', () => {
    const w = new TimeWindow(1000);
    expect(w.min()).toBeNull();
    expect(w.max()).toBeNull();
  });
});

describe('classifyLevel', () => {
  it('thirds of the window range (0.34 / 0.67 as rev A)', () => {
    expect(classifyLevel(1000, 1000, 2000, 150)).toBe('LOW');
    expect(classifyLevel(1339, 1000, 2000, 150)).toBe('LOW');
    expect(classifyLevel(1340, 1000, 2000, 150)).toBe('MED');
    expect(classifyLevel(1669, 1000, 2000, 150)).toBe('MED');
    expect(classifyLevel(1670, 1000, 2000, 150)).toBe('HIGH');
    expect(classifyLevel(2000, 1000, 2000, 150)).toBe('HIGH');
  });

  it('range floor keeps a quiet trace LOW', () => {
    expect(classifyLevel(1020, 1000, 1020, 0)).toBe('HIGH'); // no floor: noise reads HIGH
    expect(classifyLevel(1020, 1000, 1020, 150)).toBe('LOW');
    expect(classifyLevel(1060, 1000, 1100, 150)).toBe('MED'); // 60/150 = 0.4
  });

  it('empty window gives null; flat window with zero floor gives LOW', () => {
    expect(classifyLevel(1, null, null, 150)).toBeNull();
    expect(classifyLevel(5, 5, 5, 0)).toBe('LOW');
  });
});
