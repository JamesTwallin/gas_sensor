import { describe, expect, it } from 'vitest';
import { NO_SPIKE, SpikeDetector, type SpikeResult } from '../src/core/spike';

// Deterministic "noise": a small triangle wave.
const noise = (t: number) => ((t / 250) % 4 < 2 ? 1 : -1) * 1.5;

function feed(d: SpikeDetector, from: number, to: number, v: (t: number) => number, step = 250): SpikeResult[] {
  const out: SpikeResult[] = [];
  for (let t = from; t <= to; t += step) out.push(d.push(t, v(t)));
  return out;
}

describe('SpikeDetector', () => {
  it('needs a full window before it reports a slope', () => {
    const d = new SpikeDetector({ spikeWindowMs: 1000 });
    expect(d.push(0, 1000)).toEqual(NO_SPIKE);
    expect(d.push(500, 1000).slopeMvPerS).toBeNull();
    expect(d.push(1000, 1000).slopeMvPerS).toBe(0);
  });

  it('measures the slope in mV/s over the window', () => {
    const d = new SpikeDetector({ spikeWindowMs: 1000 });
    const r = feed(d, 0, 5000, (t) => 2000 + 0.1 * t); // +100 mV/s
    expect(r[r.length - 1].slopeMvPerS).toBeCloseTo(100, 6);
  });

  it('flags a rising edge within a second and not the flat trace around it', () => {
    const d = new SpikeDetector();
    const quiet = feed(d, 0, 60_000, (t) => 2000 + noise(t));
    expect(quiet.some((r) => r.spike)).toBe(false);
    // A plume: +600 mV over 3 s, then hold.
    const rise = feed(d, 60_250, 63_000, (t) => 2000 + noise(t) + ((t - 60_000) / 3000) * 600);
    const first = rise.findIndex((r) => r.spike);
    expect(first).toBeGreaterThanOrEqual(0);
    expect(first).toBeLessThan(6); // within ~1.5 s of the edge
    const hold = feed(d, 63_250, 90_000, (t) => 2600 + noise(t));
    expect(hold.slice(8).some((r) => r.spike)).toBe(false); // settles once the edge has passed
  });

  it('the threshold is the setting, fixed, and slow drift below it is ignored', () => {
    const d = new SpikeDetector({ spikeThresholdMvPerS: 25 });
    const r = feed(d, 0, 120_000, (t) => 2000 + noise(t) + 0.01 * t); // +10 mV/s ramp
    expect(r.some((x) => x.spike)).toBe(false);
    expect(r[r.length - 1].thresholdMvPerS).toBe(25);
    // Noise does not move it.
    const noisy = feed(new SpikeDetector({ spikeThresholdMvPerS: 25 }), 0, 60_000, (t) => 2000 + ((t / 250) % 6 < 3 ? 60 : -60));
    expect(noisy[noisy.length - 1].thresholdMvPerS).toBe(25);
    // Falling edges are not spikes.
    const fall = feed(new SpikeDetector(), 0, 5000, (t) => 3000 - 0.5 * t);
    expect(fall.some((x) => x.spike)).toBe(false);
  });

  it('reset forgets history', () => {
    const d = new SpikeDetector();
    feed(d, 0, 10_000, () => 2000);
    d.reset();
    expect(d.push(20_000, 2000)).toEqual(NO_SPIKE);
  });
});
