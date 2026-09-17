import { describe, expect, it } from 'vitest';
import { rsOhm, vrlFromRs, vrlFromTap } from '../src/core/sensor';

describe('load-circuit math', () => {
  it('VRL = tap x tap_ratio', () => {
    expect(vrlFromTap(1250, 2)).toBe(2500);
  });

  it('Rs = RL (VC - VRL) / VRL', () => {
    expect(rsOhm(2500, 40000, 5000)).toBeCloseTo(40000, 6); // Rs = RL at VC/2
    expect(rsOhm(1000, 40000, 5000)).toBeCloseTo(160000, 6);
    expect(rsOhm(4000, 20000, 5000)).toBeCloseTo(5000, 6);
  });

  it('guards VRL near 0 and VRL >= VC', () => {
    expect(rsOhm(0, 40000, 5000)).toBeNull();
    expect(rsOhm(0.5, 40000, 5000)).toBeNull();
    expect(rsOhm(Number.NaN, 40000, 5000)).toBeNull();
    expect(rsOhm(5000, 40000, 5000)).toBe(0);
    expect(rsOhm(5100, 40000, 5000)).toBe(0);
  });

  it('vrlFromRs inverts rsOhm across the clean-air range', () => {
    for (const rs of [12_000, 50_000, 125_000, 230_000]) {
      const vrl = vrlFromRs(rs, 40000, 5000);
      expect(rsOhm(vrl, 40000, 5000)).toBeCloseTo(rs, 3);
    }
  });
});
