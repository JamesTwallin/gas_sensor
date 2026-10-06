// The survey track behind the map: one point per GPS fix while recording,
// carrying what the sensor read since the previous fix, and the route line
// drawn under the heatmap (core/heatmap.ts does the cells and colours).
//
// Each point keeps both things the map can show, so the Raw / Spikes toggle
// needs no second recording:
//  - ch4Mv: the MEAN CH4 VRL over the samples since the last fix, like
//    tools/plot_map.py's raw VOUT map;
//  - slope: the STEEPEST CH4 slope (mV/s) since the last fix, like
//    plot_map.py --deriv. Steepest, not mean: a plume is a short, sharp rise
//    and averaging it with the flat samples either side would hide it.

import { lonLatToMerc, toScreen, type MapView, type Size } from './mapView';

export interface TrackPoint {
  lat: number;
  lon: number;
  mx: number;
  my: number;
  /** Phone epoch ms of the fix. */
  t: number;
  /** Mean CH4 VRL (mV) since the previous fix; null with no readings. */
  ch4Mv: number | null;
  /** Steepest CH4 slope (mV/s) since the previous fix; null with no slope yet. */
  slope: number | null;
  /** A sample on either channel was flagged as a spike since the previous fix. */
  spike: boolean;
}

/** A gap longer than this between fixes breaks the route line. */
export const TRACK_GAP_MS = 15_000;
/** Fixes worse than this are not drawn (a wandering fix scribbles over the map). */
export const TRACK_MAX_ACCURACY_M = 25;
/** Longest track kept: about five and a half hours at one fix a second. */
export const MAX_TRACK_POINTS = 20_000;

export class TrackBuffer {
  private pts: TrackPoint[] = [];
  private mvSum = 0;
  private mvN = 0;
  private maxSlope: number | null = null;
  private spike = false;
  private lastFixT = -Infinity;

  get length(): number {
    return this.pts.length;
  }

  points(): readonly TrackPoint[] {
    return this.pts;
  }

  clear(): void {
    this.pts = [];
    this.resetPending();
    this.lastFixT = -Infinity;
  }

  private resetPending(): void {
    this.mvSum = 0;
    this.mvN = 0;
    this.maxSlope = null;
    this.spike = false;
  }

  /** One sensor sample: CH4 VRL and slope, and whether either channel spiked. */
  addSample(ch4Mv: number, ch4SlopeMvPerS: number | null, spike: boolean): void {
    if (Number.isFinite(ch4Mv)) {
      this.mvSum += ch4Mv;
      this.mvN += 1;
    }
    if (ch4SlopeMvPerS !== null && (this.maxSlope === null || ch4SlopeMvPerS > this.maxSlope)) {
      this.maxSlope = ch4SlopeMvPerS;
    }
    if (spike) this.spike = true;
  }

  /** One GPS fix. Returns true when a point was added. */
  addFix(fix: { lat: number; lon: number; accuracyM: number | null; timestamp: number }): boolean {
    if (fix.accuracyM === null || fix.accuracyM > TRACK_MAX_ACCURACY_M) return false;
    if (fix.timestamp <= this.lastFixT) return false;
    this.lastFixT = fix.timestamp;
    const m = lonLatToMerc(fix.lon, fix.lat);
    this.pts.push({
      lat: fix.lat,
      lon: fix.lon,
      mx: m.mx,
      my: m.my,
      t: fix.timestamp,
      ch4Mv: this.mvN ? this.mvSum / this.mvN : null,
      slope: this.maxSlope,
      spike: this.spike,
    });
    if (this.pts.length > MAX_TRACK_POINTS) this.pts.splice(0, this.pts.length - MAX_TRACK_POINTS);
    this.resetPending();
    return true;
  }
}

/**
 * The route as SVG path data in screen px, one path per unbroken stretch
 * (a GPS gap starts a new one). Points closer than `minStepPx` to the last
 * drawn one are skipped so a long survey zoomed out stays cheap; the last
 * point of each stretch is always kept.
 */
export function routePaths(pts: readonly TrackPoint[], view: MapView, size: Size, minStepPx = 1.5): string[] {
  const out: string[] = [];
  let parts: string[] = [];
  let lx = 0;
  let ly = 0;
  const fmt = (v: number) => v.toFixed(1);
  const flush = () => {
    if (parts.length > 1) out.push(parts.join(''));
    parts = [];
  };
  for (let i = 0; i < pts.length; i++) {
    const p = toScreen(pts[i], view, size);
    const gap = i > 0 && pts[i].t - pts[i - 1].t > TRACK_GAP_MS;
    if (gap) flush();
    if (!parts.length) {
      parts.push(`M${fmt(p.x)} ${fmt(p.y)}`);
    } else {
      const endOfStretch = i === pts.length - 1 || pts[i + 1].t - pts[i].t > TRACK_GAP_MS;
      if (Math.hypot(p.x - lx, p.y - ly) < minStepPx && !endOfStretch) continue;
      parts.push(`L${fmt(p.x)} ${fmt(p.y)}`);
    }
    lx = p.x;
    ly = p.y;
  }
  flush();
  return out;
}
