import { describe, expect, it } from 'vitest';
import {
  TGS2610,
  TGS2611,
  envFactor,
  estimatePpm,
  fmtPpm,
  roFor,
  roFromKnownPpm,
  sanitizeCalibration,
  withCommas,
} from '../src/core/ppm';

describe('envFactor', () => {
  it('is 1 at the datasheet reference point', () => {
    expect(envFactor(TGS2611.table, 20, 65)).toBeCloseTo(1, 6);
    expect(envFactor(TGS2610.table, 20, 65)).toBeCloseTo(1, 6);
  });

  it('interpolates between table cells', () => {
    // 20 C, halfway between 65 % (1.00) and 95 % (0.87)
    expect(envFactor(TGS2611.table, 20, 80)).toBeCloseTo(0.935, 6);
    // 65 %RH, halfway between 20 C (1.00) and 30 C (0.86)
    expect(envFactor(TGS2611.table, 25, 65)).toBeCloseTo(0.93, 6);
  });

  it('clamps outside the table and copes with sparse rows', () => {
    expect(envFactor(TGS2611.table, 60, 65)).toBeCloseTo(0.76, 6);
    expect(envFactor(TGS2611.table, 20, 10)).toBeCloseTo(1.25, 6);
    // -10 C only has a 95 % cell: use it at any humidity.
    expect(envFactor(TGS2611.table, -10, 40)).toBeCloseTo(1.51, 6);
  });
});

describe('estimatePpm', () => {
  it('returns the reference concentration when Rs = Ro at reference conditions', () => {
    expect(estimatePpm(2150, 2150, 20, 65, TGS2611)).toBeCloseTo(5000, 6);
    expect(estimatePpm(2150, 2150, null, null, TGS2610)).toBeCloseTo(1800, 6);
  });

  it('follows the power law: Rs falling to 0.60x means 3x the ppm (beta spec)', () => {
    const at3000 = estimatePpm(1000, 2150, 20, 65, TGS2611)!;
    const at9000 = estimatePpm(600, 2150, 20, 65, TGS2611)!;
    expect(at9000 / at3000).toBeCloseTo(3, 1);
  });

  it('removes the humidity effect: a wetter reading of the same gas gives the same ppm', () => {
    const dry = estimatePpm(2150, 2150, 20, 65, TGS2611)!;
    // At 20 C / 95 %RH the same gas reads Rs/Ro 0.87x lower.
    const wet = estimatePpm(2150 * 0.87, 2150, 20, 95, TGS2611)!;
    expect(wet).toBeCloseTo(dry, 3);
  });

  it('is null for unknown Rs or a bad Ro', () => {
    expect(estimatePpm(null, 2150, 20, 65, TGS2611)).toBeNull();
    expect(estimatePpm(0, 2150, 20, 65, TGS2611)).toBeNull();
    expect(estimatePpm(2150, 0, 20, 65, TGS2611)).toBeNull();
  });
});

describe('roFromKnownPpm', () => {
  it('round-trips with estimatePpm', () => {
    const ro = roFromKnownPpm(4000, 1200, 28, 40, TGS2611);
    expect(estimatePpm(4000, ro, 28, 40, TGS2611)).toBeCloseTo(1200, 6);
  });

  it('gives Rs itself at the reference concentration and conditions', () => {
    expect(roFromKnownPpm(3210, 5000, 20, 65, TGS2611)).toBeCloseTo(3210, 6);
  });
});

describe('calibration records', () => {
  it('falls back to the datasheet-typical Ro', () => {
    expect(roFor(null, TGS2611)).toBe(2150);
    expect(roFor({ roOhm: 1500, ppm: 5000, at: 1, tempC: null, rh: null }, TGS2611)).toBe(1500);
  });

  it('sanitizes stored records', () => {
    expect(sanitizeCalibration(null)).toEqual({ ch4: null, lpg: null });
    expect(sanitizeCalibration({ ch4: { roOhm: -1, ppm: 5000, at: 1 } }).ch4).toBeNull();
    expect(sanitizeCalibration({ lpg: { roOhm: 900, ppm: 1800, at: 5, tempC: 21, rh: 'x' } }).lpg).toEqual({
      roOhm: 900,
      ppm: 1800,
      at: 5,
      tempC: 21,
      rh: null,
    });
  });
});

describe('fmtPpm', () => {
  it('rounds to two significant figures with commas', () => {
    expect(fmtPpm(1234, TGS2611)).toBe('~1,200');
    expect(fmtPpm(823, TGS2611)).toBe('~820');
    expect(fmtPpm(5000, TGS2611)).toBe('~5,000');
  });

  it('marks the ends of the specified range', () => {
    expect(fmtPpm(120, TGS2611)).toBe('<500');
    expect(fmtPpm(50000, TGS2611)).toBe('>10,000');
    expect(fmtPpm(null, TGS2611)).toBe('—');
  });

  it('withCommas', () => {
    expect(withCommas(999)).toBe('999');
    expect(withCommas(1000)).toBe('1,000');
    expect(withCommas(1234567.4)).toBe('1,234,567');
  });
});
