import { describe, expect, it } from 'vitest';
import { Processor, ledColour, type ProcessorOutput } from '../src/core/processor';
import { parseSample } from '../src/core/protocol';
import { vrlFromTap } from '../src/core/sensor';
import { SimulatedBoard } from '../src/core/simulator';

const S = {
  warmupMs: 10_000,
  bgWindowMs: 20_000,
  bgPercentile: 0.15,
  classWindowMs: 60_000,
  classRangeFloorMv: 150,
};

function run(p: Processor, from: number, to: number, step: number, v: (t: number) => number, extra = {}): ProcessorOutput {
  let out!: ProcessorOutput;
  for (let t = from; t <= to; t += step) out = p.push({ t, ch4Mv: v(t), lpgMv: v(t) / 2, ...extra });
  return out;
}

describe('Processor state machine', () => {
  it('WARMUP from boot, then RUNNING straight away, timed by sample timestamps', () => {
    const p = new Processor(S);
    let o = p.push({ t: 250, ch4Mv: 3000, lpgMv: 3000 });
    expect(o.state).toBe('WARMUP');
    expect(o.ch4.baselineMv).toBe(0); // rev A logs 0 until a baseline exists
    expect(o.ch4.devMv).toBe(3000);
    expect(o.ch4.level).toBeNull();
    o = run(p, 500, 9_750, 250, () => 3000);
    expect(o.state).toBe('WARMUP');
    expect(o.stateElapsedMs).toBe(9_750);
    o = p.push({ t: 10_000, ch4Mv: 1000, lpgMv: 500 });
    expect(o.state).toBe('RUNNING');
    expect(o.ch4.baselineMv).toBe(1000); // provisional: the one sample it has
    expect(o.ch4.level).toBe('LOW');
    expect(o.baselineAgeMs).toBe(0);
    o = run(p, 10_250, 14_750, 250, () => 1000);
    expect(o.state).toBe('RUNNING');
    expect(o.baselineAgeMs).toBe(4_750);
  });

  it('there is no baselining wait: classification is available from the first running sample', () => {
    for (const step of [100, 1000]) {
      const p = new Processor(S);
      let firstRunning = -1;
      for (let t = step; t <= 20_000; t += step) {
        if (p.push({ t, ch4Mv: 1000, lpgMv: 1000 }).state === 'RUNNING' && firstRunning < 0) firstRunning = t;
      }
      expect(firstRunning).toBe(10_000);
    }
  });

  it('skips warm-up when the board has already been on long enough', () => {
    const p = new Processor(S);
    const o = p.push({ t: 3_600_000, ch4Mv: 1000, lpgMv: 1000 });
    expect(o.state).toBe('RUNNING');
    expect(o.ch4.level).toBe('LOW');
  });

  it('baseline age is capped at the background window', () => {
    const p = new Processor(S);
    const o = run(p, 10_000, 60_000, 250, () => 1000);
    expect(o.baselineAgeMs).toBe(S.bgWindowMs);
  });

  it('baseline is the 15th percentile and holds through a plume; class goes HIGH', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    let o = run(p, 40_250, 42_000, 250, () => 2000); // 2 s plume
    expect(o.state).toBe('RUNNING');
    expect(o.ch4.baselineMv).toBe(1000);
    expect(o.ch4.devMv).toBe(1000);
    expect(o.ch4.level).toBe('HIGH');
    o = run(p, 42_250, 45_000, 250, () => 1000);
    expect(o.ch4.level).toBe('LOW');
  });

  it('baseline tracks a sustained step once it fills > 85 % of the window', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    const o = run(p, 40_250, 60_000, 250, () => 1300);
    expect(o.ch4.baselineMv).toBe(1300);
  });

  it('range floor: small wiggles stay LOW', () => {
    const p = new Processor(S);
    const o = run(p, 10_000, 40_000, 250, (t) => 1000 + ((t / 250) % 2) * 30);
    expect(o.ch4.level).toBe('LOW');
  });

  it('BOOT button (bit5) re-zeroes: fresh windows, still RUNNING', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    const o = p.push({ t: 40_250, ch4Mv: 1500, lpgMv: 700, button: true });
    expect(o.rezeroed).toBe(true);
    expect(o.state).toBe('RUNNING');
    expect(o.ch4.baselineMv).toBe(1500); // window cleared, only the new sample
    expect(o.baselineAgeMs).toBe(0);
  });

  it('app re-zero applies on the next sample', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    p.requestRezero();
    const o = p.push({ t: 40_250, ch4Mv: 1200, lpgMv: 1000 });
    expect(o.rezeroed).toBe(true);
    expect(o.ch4.baselineMv).toBe(1200);
  });

  it('a backwards ms_since_boot (board reboot) restarts from WARMUP', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    const o = p.push({ t: 250, ch4Mv: 3000, lpgMv: 3000 });
    expect(o.rebooted).toBe(true);
    expect(o.state).toBe('WARMUP');
    expect(o.ch4.baselineMv).toBe(0);
  });

  it('heaters off (bit6): HEATER_OFF with no class, then WARMUP timed from heater-on', () => {
    const p = new Processor(S);
    run(p, 10_000, 40_000, 250, () => 1000);
    let o = run(p, 40_250, 50_000, 250, () => 100, { heatersOff: true });
    expect(o.state).toBe('HEATER_OFF');
    expect(o.ch4.level).toBeNull();
    // Button presses are ignored while the heaters are off.
    o = p.push({ t: 50_250, ch4Mv: 100, lpgMv: 100, heatersOff: true, button: true });
    expect(o.state).toBe('HEATER_OFF');
    o = p.push({ t: 60_000, ch4Mv: 3000, lpgMv: 3000 });
    expect(o.state).toBe('WARMUP');
    expect(o.stateElapsedMs).toBe(0);
    o = run(p, 60_250, 69_750, 250, () => 3000);
    expect(o.state).toBe('WARMUP');
    o = p.push({ t: 70_000, ch4Mv: 1000, lpgMv: 1000 });
    expect(o.state).toBe('RUNNING');
    expect(o.ch4.baselineMv).toBe(1000); // old windows were discarded
  });

  it('the class window is 10 min by default and old peaks age out', () => {
    const p = new Processor({ ...S, classWindowMs: 600_000 });
    run(p, 10_000, 40_000, 1000, () => 1000);
    run(p, 41_000, 45_000, 1000, () => 3000); // big plume
    let o = run(p, 46_000, 60_000, 1000, () => 1300); // later, a modest rise
    expect(o.ch4.level).toBe('LOW'); // 300 / 2000 of the range
    o = run(p, 61_000, 700_000, 1000, (t) => (t < 690_000 ? 1000 : 1300));
    expect(o.ch4.level).toBe('HIGH'); // plume aged out: 300 / 300
  });

  it('end-to-end with the simulator: parses, warms up, runs, classifies', () => {
    const board = new SimulatedBoard({ seed: 42, meanPlumeGapMs: 30_000 });
    const p = new Processor({ ...S, warmupMs: 180_000 });
    const levels = new Set<string>();
    let o!: ProcessorOutput;
    for (let i = 0; i < 4 * 60 * 20; i++) {
      const s = parseSample(board.next());
      o = p.push({ t: s.msSinceBoot, ch4Mv: vrlFromTap(s.ch4TapMv, 2), lpgMv: vrlFromTap(s.lpgTapMv, 2), button: s.flags.button });
      if (o.ch4.level) levels.add(o.ch4.level);
      expect(s.ch4TapMv * 2).toBeGreaterThan(0);
      expect(s.ch4TapMv * 2).toBeLessThan(5000);
    }
    expect(o.state).toBe('RUNNING');
    expect(levels.has('LOW')).toBe(true);
    expect(levels.has('HIGH')).toBe(true);
  });
});

describe('ledColour', () => {
  it('uses the rev A colours', () => {
    expect(ledColour('WARMUP', null)).toEqual([0, 0, 20]);
    expect(ledColour('RUNNING', 'LOW')).toEqual([0, 30, 0]);
    expect(ledColour('RUNNING', 'MED')).toEqual([35, 18, 0]);
    expect(ledColour('RUNNING', 'HIGH')).toEqual([40, 0, 0]);
    expect(ledColour('HEATER_OFF', null)).toEqual([0, 0, 0]);
    expect(ledColour(null, null)).toEqual([0, 0, 20]);
  });
});
