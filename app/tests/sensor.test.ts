import { describe, expect, it } from 'vitest';
import { encodeGas2, parseGas2 } from '../src/core/protocol';
import { MEMS_PULLUP_OHM, MEMS_R_OHM, memsReading, memsRsOhm, rsOhm, vrlFromRs, vrlFromTap } from '../src/core/sensor';

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

describe('rev F MEMS Rs (pull-up included)', () => {
  /** Forward model: the tap voltage a given Rs produces with divider resistors R, 1M pull-up on the tap. */
  function tapFor(rs: number, vc: number, R: number): number {
    const RP = MEMS_PULLUP_OHM;
    // Node N: VN = (VC/Rs + VT/R) / a, a = 1/Rs + 1/R.
    // Node T: (VN - VT)/R + (VC - VT)/RP = VT/R; substitute VN and solve for VT.
    const a = 1 / rs + 1 / R;
    const num = vc / rs / a / R + vc / RP;
    const den = 2 / R + 1 / RP - 1 / (a * R * R);
    return num / den;
  }

  it('uses R = 10k for the 37BPM (A) and 100k for the MiCS-5524 (B)', () => {
    expect(MEMS_R_OHM).toEqual({ a: 10_000, b: 100_000 });
    expect(MEMS_PULLUP_OHM).toBe(1_000_000);
  });

  it('inverts the circuit exactly on both channels', () => {
    for (const R of [MEMS_R_OHM.a, MEMS_R_OHM.b]) {
      for (const rs of [2_000, 20_000, 150_000, 2_000_000]) {
        expect(memsRsOhm(tapFor(rs, 3300, R), 3300, R)! / rs).toBeCloseTo(1, 9);
      }
    }
  });

  it('is missing when no current flows through the sensor or VN reaches VC', () => {
    for (const R of [MEMS_R_OHM.a, MEMS_R_OHM.b]) {
      expect(memsRsOhm(0, 3300, R)).toBeNull();
      expect(memsRsOhm(15, 3300, R)).toBeNull(); // I1 <= 0: only the pull-up's current
      expect(memsRsOhm(2047, 3300, R)).toBeNull(); // no blade: VN >= VC
    }
    // Just under VC/2 still solves on A (VN is a little below VC), giving a small Rs.
    expect(memsRsOhm(1650, 3300, MEMS_R_OHM.a)).toBeGreaterThan(0);
    // The pull-up matters far more on the 100k channel.
    const ideal = (vt: number, R: number) => (2 * R * (3300 - 2 * vt)) / (2 * vt);
    const err = (R: number) => Math.abs(memsRsOhm(400, 3300, R)! / ideal(400, R) - 1);
    expect(err(MEMS_R_OHM.b)).toBeGreaterThan(5 * err(MEMS_R_OHM.a));
  });

  it('uses each channel R and the Gas2 rail, falling back to 3300 mV', () => {
    const f = {
      seq: 1,
      memsATapMv: 400,
      memsBTapMv: 300,
      memsAResMv: null,
      memsASigmaMv: null,
      memsBResMv: null,
      memsBSigmaMv: null,
      flags: 0,
      rail3v3Mv: null,
    };
    const r = memsReading(parseGas2(encodeGas2(f)));
    expect(r.a.voutMv).toBe(800);
    expect(r.b.voutMv).toBe(600); // 2 x tap on both channels
    expect(r.a.rsOhm).toBeCloseTo(memsRsOhm(400, 3300, 10_000)!, 6);
    expect(r.b.rsOhm).toBeCloseTo(memsRsOhm(300, 3300, 100_000)!, 6);
    const r2 = memsReading(parseGas2(encodeGas2({ ...f, memsBTapMv: null, rail3v3Mv: 3200 })));
    expect(r2.a.rsOhm).toBeCloseTo(memsRsOhm(400, 3200, 10_000)!, 6);
    expect(r2.b).toEqual({ voutMv: null, rsOhm: null });
  });
});
