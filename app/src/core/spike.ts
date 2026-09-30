// Spike detector: the first time-derivative of a channel's load voltage as the
// plume indicator. A plume arrives as a rising edge, so d(VRL)/dt spikes; slow
// drift (warm-up tail, weather, humidity) has a small derivative and is ignored.
// Pure, no DOM. Mirrors tools/plot_spike.py.
//
//   slope     = (v(t) - v(t - W)) / W            over a W ms window (default 1 s)
//   threshold = max(k * 1.4826 * MAD(slopes over the last 2 min), floor)
//   spike     = slope > threshold                (rising edges only)
//
// The MAD term adapts to the channel's own noise; the floor stops a very quiet
// trace from flagging its own jitter. The controller runs it whenever the
// heaters are on; the first seconds after power-on ramp steeply and may flag.

import { TimeWindow, percentile } from './windows';

export interface SpikeSettings {
  /** Derivative window (ms). */
  spikeWindowMs: number;
  /** Threshold in robust sigmas of the recent derivative noise. */
  spikeSigma: number;
  /** Threshold never drops below this (mV/s). */
  spikeFloorMvPerS: number;
}

export const DEFAULT_SPIKE: SpikeSettings = {
  spikeWindowMs: 1000,
  spikeSigma: 4,
  spikeFloorMvPerS: 25,
};

/** How much derivative history the noise estimate rests on. */
export const SPIKE_NOISE_WINDOW_MS = 120_000;
/** Fewer slopes than this and only the floor is used (the MAD would be meaningless). */
const MIN_NOISE_SAMPLES = 20;
/** Consecutive spike samples closer than this belong to the same burst. */
export const SPIKE_BURST_GAP_MS = 5000;

export interface SpikeResult {
  /** mV/s over the window; null until the window has filled. */
  slopeMvPerS: number | null;
  /** Current threshold (mV/s); null until a slope exists. */
  thresholdMvPerS: number | null;
  spike: boolean;
}

export const NO_SPIKE: SpikeResult = { slopeMvPerS: null, thresholdMvPerS: null, spike: false };

export class SpikeDetector {
  private s: SpikeSettings;
  private ts: number[] = [];
  private vs: number[] = [];
  private start = 0;
  private slopes = new TimeWindow(SPIKE_NOISE_WINDOW_MS);

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
    this.slopes.clear();
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
    this.slopes.push(t, slope);

    let threshold = this.s.spikeFloorMvPerS;
    if (this.slopes.length >= MIN_NOISE_SAMPLES) {
      const all = this.slopes.values();
      const med = percentile(all, 0.5) ?? 0;
      const mad = percentile(
        all.map((x) => Math.abs(x - med)),
        0.5,
      );
      if (mad !== null) threshold = Math.max(threshold, this.s.spikeSigma * 1.4826 * mad);
    }
    return { slopeMvPerS: slope, thresholdMvPerS: threshold, spike: slope > threshold };
  }
}
