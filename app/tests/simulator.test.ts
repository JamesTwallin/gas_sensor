import { describe, expect, it } from 'vitest';
import { parseInfo, parseSample } from '../src/core/protocol';
import { rsOhm, vrlFromTap } from '../src/core/sensor';
import { SimulatedBoard } from '../src/core/simulator';

describe('SimulatedBoard', () => {
  it('emits valid, sequential packets with a matching Info JSON', () => {
    const b = new SimulatedBoard({ seed: 1 });
    const info = parseInfo(b.infoJson());
    expect(info.rl_ohm).toBe(40000);
    let prev = parseSample(b.next());
    for (let i = 0; i < 100; i++) {
      const s = parseSample(b.next());
      expect(s.seq).toBe((prev.seq + 1) & 0xffff);
      expect(s.msSinceBoot - prev.msSinceBoot).toBe(250);
      expect(s.flags.bmeOk && s.flags.adsOk).toBe(true);
      prev = s;
    }
  });

  it('clean-air Rs after warm-up lands in the TGS2611 / TGS2610 ranges', () => {
    for (const seed of [1, 2, 3, 4, 5]) {
      const b = new SimulatedBoard({ seed, meanPlumeGapMs: 1e12 }); // no plumes
      let s = parseSample(b.next());
      for (let i = 0; i < 4 * 400; i++) s = parseSample(b.next()); // ~400 s
      const rs4 = rsOhm(vrlFromTap(s.ch4TapMv, 2), 40000, 5000)!;
      const rsL = rsOhm(vrlFromTap(s.lpgTapMv, 2), 40000, 5000)!;
      expect(rs4).toBeGreaterThan(12_000 * 0.8);
      expect(rs4).toBeLessThan(125_000 * 1.2);
      expect(rsL).toBeGreaterThan(23_000 * 0.8);
      expect(rsL).toBeLessThan(230_000 * 1.2);
    }
  });

  it('button sets bit5 on exactly one sample; forced heaters-off sets bit6', () => {
    const b = new SimulatedBoard({ seed: 3 });
    b.pressButton();
    expect(parseSample(b.next()).flags.button).toBe(true);
    expect(parseSample(b.next()).flags.button).toBe(false);
    b.setHeatersOff(true);
    for (let i = 0; i < 10; i++) expect(parseSample(b.next()).flags.heatersOff).toBe(true);
    b.setHeatersOff(false);
    expect(parseSample(b.next()).flags.heatersOff).toBe(false);
  });

  it('low-battery cutoff after VBAT < 3.3 V for > 10 s; USB releases it', () => {
    const b = new SimulatedBoard({ seed: 9, intervalMs: 5000, meanPlumeGapMs: 1e12 });
    let s = parseSample(b.next());
    let n = 0;
    while (!s.flags.heatersOff && n++ < 100_000) s = parseSample(b.next());
    expect(s.flags.heatersOff).toBe(true);
    expect(s.vbatMv).toBeLessThan(3300);
    b.setUsb(true);
    s = parseSample(b.next());
    expect(s.flags.heatersOff).toBe(false);
    expect(s.flags.usbPower).toBe(true);
  });
});
