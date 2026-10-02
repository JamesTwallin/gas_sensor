import { describe, expect, it } from 'vitest';
import { CSV_BASELINE_WINDOW_MS, Processor, ledColour, type ProcessorOutput } from '../src/core/processor';
import { parseSample } from '../src/core/protocol';
import { vrlFromTap } from '../src/core/sensor';
import { SimulatedBoard } from '../src/core/simulator';

const S = { warmupMs: 10_000 };

function run(p: Processor, from: number, to: number, step: number, v: (t: number) => number, extra = {}): ProcessorOutput {
  let out!: ProcessorOutput;
  for (let t = from; t <= to; t += step) out = p.push({ t, ch4Mv: v(t), lpgMv: v(t) / 2, ...extra });
  return out;
}

describe('Processor state machine', () => {
  it('WARMUP from boot, then RUNNING, timed by sample timestamps', () => {
    const p = new Processor(S);
    let o = p.push({ t: 250, ch4Mv: 3000, lpgMv: 3000 });
    expect(o.state).toBe('WARMUP');
    expect(o.stateDurationMs).toBe(10_000);
    expect(o.ch4.voutMv).toBe(3000);
    o = run(p, 500, 9_750, 250, () => 3000);
    expect(o.state).toBe('WARMUP');
    expect(o.stateElapsedMs).toBe(9_750);
    o = p.push({ t: 10_000, ch4Mv: 1000, lpgMv: 500 });
    expect(o.state).toBe('RUNNING');
    expect(o.stateDurationMs).toBe(0);
    o = run(p, 10_250, 14_750, 250, () => 1000);
    expect(o.state).toBe('RUNNING');
    expect(o.stateElapsedMs).toBe(4_750);
  });

  it('warm-up ends on the same timestamp whatever the sample interval', () => {
    for (const step of [100, 1000]) {
      const p = new Processor(S);
      let firstRunning = -1;
      for (let t = step; t <= 20_000; t += step) {
        if (p.push({ t, ch4Mv: 1000, lpgMv: 1000 }).state === 'RUNNING' && firstRunning < 0) firstRunning = t;
      }
      expect(firstRunning).toBe(10_000);
    }
  });

  it('runs from the first sample with the default (no) warm-up', () => {
    const p = new Processor();
    expect(p.push({ t: 250, ch4Mv: 3000, lpgMv: 3000 }).state).toBe('RUNNING');
  });

  it('skips warm-up when the board has already been on long enough', () => {
    const p = new Processor(S);
    expect(p.push({ t: 3_600_000, ch4Mv: 1000, lpgMv: 1000 }).state).toBe('RUNNING');
  });

  it('a backwards ms_since_boot (board reboot) restarts from WARMUP', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    const o = p.push({ t: 250, ch4Mv: 3000, lpgMv: 3000 });
    expect(o.rebooted).toBe(true);
    expect(o.state).toBe('WARMUP');
    expect(o.ch4.baselineMv).toBe(0);
  });

  it('heaters off (bit6): HEATER_OFF, then WARMUP timed from heater-on', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    let o = run(p, 40_250, 50_000, 250, () => 100, { heatersOff: true });
    expect(o.state).toBe('HEATER_OFF');
    o = p.push({ t: 60_000, ch4Mv: 3000, lpgMv: 3000 });
    expect(o.state).toBe('WARMUP');
    expect(o.stateElapsedMs).toBe(0);
    o = run(p, 60_250, 69_750, 250, () => 3000);
    expect(o.state).toBe('WARMUP');
    o = p.push({ t: 70_000, ch4Mv: 1000, lpgMv: 1000 });
    expect(o.state).toBe('RUNNING');
    expect(o.ch4.baselineMv).toBe(1000); // the old window was discarded
  });

  it('end-to-end with the simulator: parses, warms up, runs', () => {
    const board = new SimulatedBoard({ seed: 42, meanPlumeGapMs: 30_000 });
    const p = new Processor({ warmupMs: 180_000 });
    const states = new Set<string>();
    let o!: ProcessorOutput;
    for (let i = 0; i < 4 * 60 * 20; i++) {
      const s = parseSample(board.next());
      o = p.push({ t: s.msSinceBoot, ch4Mv: vrlFromTap(s.ch4TapMv, 2), lpgMv: vrlFromTap(s.lpgTapMv, 2) });
      states.add(o.state);
      expect(s.ch4TapMv * 2).toBeGreaterThan(0);
      expect(s.ch4TapMv * 2).toBeLessThan(5000);
    }
    expect(o.state).toBe('RUNNING');
    expect([...states]).toEqual(['WARMUP', 'RUNNING']);
    expect(o.ch4.baselineMv).toBeGreaterThan(0);
  });
});

describe('CSV baseline (rev A columns only; nothing on screen reads it)', () => {
  it('logs 0 until RUNNING, then the first sample', () => {
    const p = new Processor(S);
    expect(p.push({ t: 250, ch4Mv: 3000, lpgMv: 3000 }).ch4.baselineMv).toBe(0);
    const o = p.push({ t: 10_000, ch4Mv: 1000, lpgMv: 500 });
    expect(o.ch4.baselineMv).toBe(1000);
    expect(o.lpg.baselineMv).toBe(500);
  });

  it('is the 15th percentile and holds through a plume', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    const o = run(p, 40_250, 42_000, 250, () => 2000); // 2 s plume
    expect(o.ch4.baselineMv).toBe(1000);
  });

  it('tracks a sustained step once it fills > 85 % of the 2 min window', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    const o = run(p, 40_250, 40_000 + CSV_BASELINE_WINDOW_MS, 250, () => 1300);
    expect(o.ch4.baselineMv).toBe(1300);
  });
});

describe('ledColour', () => {
  it('blue until running, green, red while spiking, off with the heaters', () => {
    expect(ledColour('WARMUP', false)).toEqual([0, 0, 20]);
    expect(ledColour('WARMUP', true)).toEqual([0, 0, 20]);
    expect(ledColour('RUNNING', false)).toEqual([0, 30, 0]);
    expect(ledColour('RUNNING', true)).toEqual([40, 0, 0]);
    expect(ledColour('HEATER_OFF', true)).toEqual([0, 0, 0]);
    expect(ledColour(null, false)).toEqual([0, 0, 20]);
  });
});
