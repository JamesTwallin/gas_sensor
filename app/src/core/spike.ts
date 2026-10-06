// Spike detector: the first time-derivative of a channel's load voltage as the
// plume indicator. A plume arrives as a rising edge, so d(VRL)/dt spikes; slow
// drift (warm-up tail, weather, humidity) has a small derivative and is ignored.
// Pure, no DOM.
//
//   slope = (v(t) - v(t - W)) / W     over a W ms window (default 1 s)
//   spike = slope > threshold         (rising edges only; a fixed mV/s setting)
//
// The threshold is a plain number the user sets. An earlier version scaled it
// to the recent noise (a MAD estimate), which made it wander and hard to read
// against the chart; tools/plot_spike.py still has that variant for offline use.

export interface SpikeSettings {
  /** Derivative window (ms). */
  spikeWindowMs: number;
  /** A slope above this is a spike (mV/s). */
  spikeThresholdMvPerS: number;
}

export const DEFAULT_SPIKE: SpikeSettings = {
  spikeWindowMs: 1000,
  spikeThresholdMvPerS: 25,
};

/** Consecutive spike samples closer than this belong to the same burst. */
export const SPIKE_BURST_GAP_MS = 5000;
/**
 * A flagged sample keeps its channel "spiking" for this long, so the state
 * card, the board LED and a video frame hold the alert instead of flickering
 * at the sample rate.
 */
export const SPIKE_HOLD_MS = 2000;

export interface SpikeResult {
  /** mV/s over the window; null until the window has filled. */
  slopeMvPerS: number | null;
  /** The threshold in force (mV/s); null until a slope exists. */
  thresholdMvPerS: number | null;
  spike: boolean;
}

export const NO_SPIKE: SpikeResult = { slopeMvPerS: null, thresholdMvPerS: null, spike: false };

export class SpikeDetector {
  private s: SpikeSettings;
  private ts: number[] = [];
  private vs: number[] = [];
  private start = 0;

  constructor(settings: Partial<SpikeSettings> = {}) {
    this.s = { ...DEFAULT_SPIKE, ...settings };
  }

  get settings(): SpikeSettings {
    return this.s;
  }

  updateSettings(settings: Partial<SpikeSettings>): void {
    this.s = { ...this.s, ...settings };
  }

  reset(): void {
    this.ts = [];
    this.vs = [];
    this.start = 0;
  }

  push(t: number, v: number): SpikeResult {
    const w = this.s.spikeWindowMs;
    // Reference sample: the newest one at least a window old.
    let ref = -1;
    for (let i = this.ts.length - 1; i >= this.start; i--) {
      if (this.ts[i] <= t - w) {
        ref = i;
        break;
      }
    }
    this.ts.push(t);
    this.vs.push(v);
    // Keep two windows of history so the reference sample is always present.
    const cutoff = t - 2 * w;
    while (this.start < this.ts.length - 1 && this.ts[this.start] < cutoff && this.ts[this.start + 1] <= t - w) {
      this.start++;
    }
    if (this.start > 1024 && this.start * 2 > this.ts.length) {
      this.ts = this.ts.slice(this.start);
      this.vs = this.vs.slice(this.start);
      this.start = 0;
    }
    if (ref < 0) return { ...NO_SPIKE };

    const dt = t - this.ts[ref];
    if (dt <= 0) return { ...NO_SPIKE };
    const slope = ((v - this.vs[ref]) * 1000) / dt;
    const threshold = this.s.spikeThresholdMvPerS;
    return { slopeMvPerS: slope, thresholdMvPerS: threshold, spike: slope > threshold };
  }
}
