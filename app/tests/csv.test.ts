import { describe, expect, it } from 'vitest';
import { CSV_HEADER, fmt, formatCsvRow, formatUtc, isFix, surveyFileName, type CsvRowInput } from '../src/core/csv';

// Exactly the column list in docs/phone_board.md "App CSV".
const SPEC_HEADER =
  'millis_since_boot,state,ch4_vout_mv,ch4_baseline_mv,ch4_dev_mv,' +
  'lpg_vout_mv,lpg_baseline_mv,lpg_dev_mv,temp_c,humidity_pct,pressure_hpa,' +
  'utc_iso8601,lat,lon,alt_m,sats,fix,' +
  'ch4_rs_ohm,lpg_rs_ohm,vbat_mv,gps_accuracy_m';

// rev A header, from src/main.cpp, which must remain a prefix.
const REV_A_HEADER =
  'millis_since_boot,state,ch4_vout_mv,ch4_baseline_mv,ch4_dev_mv,' +
  'lpg_vout_mv,lpg_baseline_mv,lpg_dev_mv,' +
  'temp_c,humidity_pct,pressure_hpa,' +
  'utc_iso8601,lat,lon,alt_m,sats,fix';

const T = Date.UTC(2026, 8, 17, 9, 5, 7, 42); // 2026-09-17 09:05:07.042

function base(over: Partial<CsvRowInput> = {}): CsvRowInput {
  return {
    millisSinceBoot: 123456,
    state: 'RUNNING',
    ch4VoutMv: 2222.4,
    ch4BaselineMv: 2100.6,
    lpgVoutMv: 1666.5,
    lpgBaselineMv: 1650,
    tempC: 21.456,
    humidityPct: 55.55,
    pressureHpa: 1013.25,
    phoneTimeMs: T,
    gps: { lat: 51.5074567, lon: -0.1277583, altM: 35.26, accuracyM: 4.83, timestamp: T - 500 },
    ch4RsOhm: 50000.4,
    lpgRsOhm: 80012.6,
    vbatMv: 3987,
    ...over,
  };
}

describe('CSV', () => {
  it('header is exactly the spec column order, rev A columns first', () => {
    expect(CSV_HEADER).toBe(SPEC_HEADER);
    expect(CSV_HEADER.startsWith(REV_A_HEADER + ',')).toBe(true);
  });

  it('formats a full row', () => {
    const row = formatCsvRow(base());
    expect(row).toBe(
      '123456,RUNNING,2222,2101,122,1667,1650,17,21.46,55.5,1013.3,' +
        '2026-09-17 09:05:07.042,51.507457,-0.127758,35.3,,1,50000,80013,3987,4.8',
    );
    expect(row.split(',').length).toBe(SPEC_HEADER.split(',').length);
  });

  it('dev is vout − baseline before rounding, like rev A (%.0f of the difference)', () => {
    const row = formatCsvRow(base({ ch4VoutMv: 1000.4, ch4BaselineMv: 999.6 }));
    expect(row.split(',').slice(2, 5)).toEqual(['1000', '1000', '1']);
  });

  it('blank for missing environment, GPS, Rs; fix 0; column count constant', () => {
    const row = formatCsvRow(base({ tempC: null, humidityPct: null, pressureHpa: null, gps: null, ch4RsOhm: null, lpgRsOhm: null, state: 'WARMUP', ch4BaselineMv: 0, lpgBaselineMv: 0 }));
    const cells = row.split(',');
    expect(cells.length).toBe(21);
    expect(cells[1]).toBe('WARMUP');
    expect(cells[3]).toBe('0');
    expect(cells.slice(8, 11)).toEqual(['', '', '']);
    expect(cells[11]).toBe('2026-09-17 09:05:07.042'); // phone clock is always there
    expect(cells.slice(12, 17)).toEqual(['', '', '', '', '0']);
    expect(cells.slice(17)).toEqual(['', '', '3987', '']);
  });

  it('fix = 1 only when accuracy ≤ 25 m and the fix is fresh', () => {
    const gps = { lat: 1, lon: 2, altM: null, accuracyM: 25, timestamp: T };
    expect(isFix(gps, T)).toBe(true);
    expect(isFix({ ...gps, accuracyM: 25.1 }, T)).toBe(false);
    expect(isFix({ ...gps, accuracyM: null }, T)).toBe(false);
    expect(isFix({ ...gps, timestamp: T - 30_000 }, T)).toBe(false);
    expect(isFix(null, T)).toBe(false);
    const cells = formatCsvRow(base({ gps: { ...gps, accuracyM: 60 } })).split(',');
    expect(cells[12]).toBe('1.000000'); // position still written
    expect(cells[14]).toBe(''); // altitude unknown
    expect(cells[16]).toBe('0');
    expect(cells[20]).toBe('60.0');
  });

  it('utc format pads every field', () => {
    expect(formatUtc(Date.UTC(2027, 0, 2, 3, 4, 5, 6))).toBe('2027-01-02 03:04:05.006');
  });

  it('fmt avoids -0 and blanks non-finite', () => {
    expect(fmt(-0.4, 0)).toBe('0');
    expect(fmt(-0.004, 2)).toBe('0.00');
    expect(fmt(-1.5, 0)).toBe('-2');
    expect(fmt(Infinity, 0)).toBe('');
    expect(fmt(null, 1)).toBe('');
  });

  it('file name matches the rev A SD-card pattern', () => {
    expect(surveyFileName(T)).toBe('2026-09-17_09-05-07.csv');
  });
});
