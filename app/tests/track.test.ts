import { describe, expect, it } from 'vitest';
import { lonLatToMerc, type MapView } from '../src/core/mapView';
import { MAX_TRACK_POINTS, TRACK_GAP_MS, TRACK_MAX_ACCURACY_M, TrackBuffer, routePaths, type TrackPoint } from '../src/core/track';

const fix = (i: number, extra: Partial<{ accuracyM: number | null; timestamp: number }> = {}) => ({
  lat: 51.75 + i * 0.0001,
  lon: -1.25,
  accuracyM: 5,
  timestamp: 1_000_000 + i * 1000,
  ...extra,
});

describe('TrackBuffer', () => {
  it('keeps the mean VRL and the steepest slope between fixes', () => {
    const t = new TrackBuffer();
    t.addSample(1500, 10, false);
    t.addSample(1600, 40, false);
    t.addSample(1700, -30, false);
    t.addFix(fix(0));
    t.addFix(fix(1)); // no samples in between
    const [a, b] = t.points();
    expect(a.ch4Mv).toBe(1600);
    expect(a.slope).toBe(40);
    expect(a.spike).toBe(false);
    expect(b.ch4Mv).toBeNull();
    expect(b.slope).toBeNull();
  });

  it('carries the spike flag to the next fix only', () => {
    const t = new TrackBuffer();
    t.addSample(1500, 5, true);
    t.addFix(fix(0));
    t.addSample(1500, 5, false);
    t.addFix(fix(1));
    expect(t.points().map((p) => p.spike)).toEqual([true, false]);
  });

  it('keeps a reading with no slope yet', () => {
    const t = new TrackBuffer();
    t.addSample(1500, null, false);
    t.addFix(fix(0));
    expect(t.points()[0].ch4Mv).toBe(1500);
    expect(t.points()[0].slope).toBeNull();
  });

  it('skips poor and repeated fixes', () => {
    const t = new TrackBuffer();
    expect(t.addFix(fix(0, { accuracyM: TRACK_MAX_ACCURACY_M + 1 }))).toBe(false);
    expect(t.addFix(fix(0, { accuracyM: null }))).toBe(false);
    expect(t.addFix(fix(0))).toBe(true);
    expect(t.addFix(fix(0))).toBe(false); // same timestamp
    expect(t.length).toBe(1);
  });

  it('projects each point once', () => {
    const t = new TrackBuffer();
    t.addFix(fix(3));
    const m = lonLatToMerc(fix(3).lon, fix(3).lat);
    expect(t.points()[0].mx).toBe(m.mx);
    expect(t.points()[0].my).toBe(m.my);
  });

  it('drops the oldest points past the cap, and clears', () => {
    const t = new TrackBuffer();
    for (let i = 0; i < MAX_TRACK_POINTS + 5; i++) t.addFix(fix(i));
    expect(t.length).toBe(MAX_TRACK_POINTS);
    expect(t.points()[0].t).toBe(fix(5).timestamp);
    t.clear();
    expect(t.length).toBe(0);
    expect(t.addFix(fix(0))).toBe(true); // timestamps start over after a clear
  });
});

// A straight north-south walk, 10 px per point at VIEW.
function walk(n: number): TrackPoint[] {
  return Array.from({ length: n }, (_, i) => ({
    lat: 0,
    lon: 0,
    mx: 0.5,
    my: 0.5 + i * 10e-9,
    t: i * 1000,
    ch4Mv: 1500,
    slope: 0,
    spike: false,
  }));
}
const SIZE = { width: 200, height: 200 };
const VIEW: MapView = { cx: 0.5, cy: 0.5, zoom: Math.log2(10 / (256 * 10e-9)) };

describe('routePaths', () => {
  it('draws one path for an unbroken track', () => {
    expect(routePaths(walk(4), VIEW, SIZE)).toEqual(['M100.0 100.0L100.0 110.0L100.0 120.0L100.0 130.0']);
  });

  it('breaks the line across a GPS gap', () => {
    const pts = walk(4);
    pts[2] = { ...pts[2], t: pts[1].t + TRACK_GAP_MS + 1 };
    pts[3] = { ...pts[3], t: pts[2].t + 1000 };
    expect(routePaths(pts, VIEW, SIZE)).toEqual(['M100.0 100.0L100.0 110.0', 'M100.0 120.0L100.0 130.0']);
  });

  it('thins points that land on top of each other but keeps the end', () => {
    const zoomedOut: MapView = { ...VIEW, zoom: VIEW.zoom - 4 }; // 0.625 px per step
    // 1.875 px is the first step at least 1.5 px from the start; 2.5 px is the end.
    expect(routePaths(walk(5), zoomedOut, SIZE)).toEqual(['M100.0 100.0L100.0 101.9L100.0 102.5']);
  });

  it('draws nothing for fewer than two points', () => {
    expect(routePaths(walk(1), VIEW, SIZE)).toEqual([]);
    expect(routePaths([], VIEW, SIZE)).toEqual([]);
  });
});
