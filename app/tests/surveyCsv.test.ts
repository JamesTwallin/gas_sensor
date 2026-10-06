import { describe, expect, it } from 'vitest';
import { CSV_HEADER, formatCsvRow, type CsvRowInput } from '../src/core/csv';
import { parseUtc, trackFromCsv } from '../src/core/surveyCsv';

const T0 = Date.UTC(2026, 9, 1, 12, 0, 0);

const row = (i: number, fixI: number | null, extra: Partial<CsvRowInput> = {}): string =>
  formatCsvRow({
    millisSinceBoot: 60_000 + i * 100,
    state: 'RUNNING',
    ch4VoutMv: 1500 + i,
    ch4BaselineMv: 1500,
    lpgVoutMv: 1200,
    lpgBaselineMv: 1200,
    tempC: 20,
    humidityPct: 50,
    pressureHpa: 1013,
    phoneTimeMs: T0 + i * 100,
    gps:
      fixI === null
        ? null
        : { lat: 51.75 + fixI * 0.0001, lon: -1.25, altM: 60, accuracyM: 5, timestamp: T0 + fixI * 1000 },
    ch4RsOhm: 10_000,
    lpgRsOhm: 10_000,
    vbatMv: 3900,
    ch4SlopeMvPerS: i,
    lpgSlopeMvPerS: 0,
    spike: '',
    ...extra,
  });

describe('parseUtc', () => {
  it('reads the recorder format as UTC', () => {
    expect(parseUtc('2026-10-01 12:00:00.250')).toBe(T0 + 250);
    expect(parseUtc('')).toBeNull();
    expect(parseUtc('garbage')).toBeNull();
  });
});

describe('trackFromCsv', () => {
  it('turns a recorded file back into the track the live map drew', () => {
    // 3 samples per fix; the first rows have no position yet.
    const rows = [row(0, null), row(1, null)];
    for (let i = 2; i < 11; i++) rows.push(row(i, Math.floor((i - 2) / 3)));
    rows[6] = row(6, 1, { spike: 'CH4' });
    const pts = trackFromCsv([CSV_HEADER, ...rows, ''].join('\r\n'));
    expect(pts).toHaveLength(3);
    expect(pts[0].lat).toBeCloseTo(51.75, 6);
    expect(pts[0].ch4Mv).toBeCloseTo(1500.5); // rows 0 and 1, before the first fix
    expect(pts[1].ch4Mv).toBeCloseTo(1503); // rows 2..4
    expect(pts[1].slope).toBe(4);
    expect(pts[1].spike).toBe(false);
    expect(pts[2].spike).toBe(true); // row 6 is before the third fix
    expect(pts[1].t - pts[0].t).toBe(300);
  });

  it('skips fixes too coarse for the map', () => {
    const coarse = row(3, 1).replace(/,5\.0,/, ',80.0,');
    const pts = trackFromCsv([CSV_HEADER, row(0, 0), coarse, row(6, 2)].join('\n'));
    expect(pts.map((p) => p.lat.toFixed(4))).toEqual(['51.7500', '51.7502']);
  });

  it('loads a rev A file (no accuracy, slope or spike columns)', () => {
    const header = 'millis_since_boot,state,ch4_vout_mv,utc_iso8601,lat,lon,fix';
    const text = [
      header,
      '1000,RUNNING,1500,2026-10-01 12:00:00.000,51.750000,-1.250000,1',
      '2000,RUNNING,1520,2026-10-01 12:00:01.000,51.750100,-1.250000,1',
      '3000,RUNNING,1540,2026-10-01 12:00:02.000,51.750200,-1.250000,0',
      '4000,RUNNING,1560,,,,0',
    ].join('\n');
    const pts = trackFromCsv(text);
    expect(pts).toHaveLength(2);
    expect(pts[1].ch4Mv).toBe(1500);
    expect(pts[1].slope).toBeNull();
  });

  it('rejects a file that is not a survey', () => {
    expect(() => trackFromCsv('name,value\na,1\n')).toThrow(/Not a survey/);
  });
});
