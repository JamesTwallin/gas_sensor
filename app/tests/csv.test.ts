import { describe, expect, it } from 'vitest';
import { CSV_HEADER, fmt, formatCsvRow, formatUtc, isFix, surveyFileName, type CsvRowInput } from '../src/core/csv';
import { encodeGas2, parseGas2 } from '../src/core/protocol';
import { memsReading } from '../src/core/sensor';

// Exactly the column list in docs/phone_board.md "App CSV".
const SPEC_HEADER =
  'millis_since_boot,state,ch4_vout_mv,ch4_baseline_mv,ch4_dev_mv,' +
  'lpg_vout_mv,lpg_baseline_mv,lpg_dev_mv,temp_c,humidity_pct,pressure_hpa,' +
  'utc_iso8601,lat,lon,alt_m,sats,fix,' +
  'ch4_rs_ohm,lpg_rs_ohm,vbat_mv,gps_accuracy_m,ch4_ppm_est,lpg_ppm_est,' +
  'ch4_slope_mv_s,lpg_slope_mv_s,spike,' +
  'airflow_raw,airflow_index,co_raw,ch4_res_mv,lpg_res_mv,ch4_sigma_mv,lpg_sigma_mv,' +
  'anomaly_ch4,anomaly_lpg,event_class,event_ratio,event_fingerprint,' +
  'mems_a_vout_mv,mems_b_vout_mv,mems_a_rs_ohm,mems_b_rs_ohm,mems_a_res_mv,' +
  'mems_a_sigma_mv,mems_b_res_mv,mems_b_sigma_mv,anomaly_mems_a,anomaly_mems_b,mems_flags';

// The header before rev F (detector columns, no MEMS), which must remain a prefix.
const PRE_REV_F_HEADER = SPEC_HEADER.slice(0, SPEC_HEADER.indexOf(',mems_a_vout_mv'));

// rev A header, from archive/first_prototype/src/main.cpp, which must remain a prefix.
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
    ch4PpmEst: 1234.5,
    lpgPpmEst: 87.2,
    ch4SlopeMvPerS: 12.34,
    lpgSlopeMvPerS: -3.25,
    spike: 'CH4',
    ...over,
  };
}

describe('CSV', () => {
  it('header is exactly the spec column order, rev A columns first', () => {
    expect(CSV_HEADER).toBe(SPEC_HEADER);
    expect(CSV_HEADER.startsWith(REV_A_HEADER + ',')).toBe(true);
    expect(PRE_REV_F_HEADER.endsWith(',event_fingerprint')).toBe(true);
    expect(CSV_HEADER.startsWith(PRE_REV_F_HEADER + ',')).toBe(true);
    expect(CSV_HEADER.split(',').length - PRE_REV_F_HEADER.split(',').length).toBe(11);
  });

  it('formats a full row', () => {
    const row = formatCsvRow(base());
    expect(row).toBe(
      '123456,RUNNING,2222,2101,122,1667,1650,17,21.46,55.5,1013.3,' +
        '2026-09-17 09:05:07.042,51.507457,-0.127758,35.3,,1,50000,80013,3987,4.8,1235,87,12.3,-3.3,CH4' +
        ',,,,,,,,,,,,' +
        ',,,,,,,,,,,',
    );
    expect(row.split(',').length).toBe(SPEC_HEADER.split(',').length);
  });

  it('writes the Analysis packet and a closed event', () => {
    const analysis = {
      seq: 7,
      ch4ResMv: 12.34,
      lpgResMv: -1.2,
      ch4SigmaMv: 3.456,
      lpgSigmaMv: 2.5,
      airflowRawMv: null,
      airflowIndex: null,
      coPpm: null,
      anomalyCh4: true,
      anomalyLpg: false,
      ready: true,
      suppressed: false,
      eventOpen: false,
      calibrating: false,
      eventClass: 'UNRESOLVED' as const,
      eventRatio: 1.5,
    };
    const event = {
      id: 3,
      eventClass: 'UNRESOLVED' as const,
      confidence: 61,
      durationS: 12.5,
      ch4PeakMv: 40.2,
      lpgPeakMv: 30.1,
      ratio: 1.34,
      leadS: -0.5,
      airflowMean: null,
      coPeakPpm: null,
      ch4Raised: true,
      lpgRaised: true,
      ch4Detected: true,
      lpgDetected: false,
      thermal: false,
      lowAirflow: false,
    };
    const cells = formatCsvRow(base({ analysis, event })).split(',');
    expect(cells.length).toBe(SPEC_HEADER.split(',').length);
    expect(cells.slice(26, 37)).toEqual(['', '', '', '12.3', '-1.2', '3.46', '2.50', '1', '0', 'UNRESOLVED', '1.34']);
    expect(cells[37]).toBe(
      'id=3;class=UNRESOLVED;confidence=61;duration_s=12.5;ch4_peak_mv=40.2;lpg_peak_mv=30.1;ratio=1.34;' +
        'lead_s=-0.5;airflow_mean=;co_peak_ppm=;ch4_raised=1;lpg_raised=1;ch4_detected=1;lpg_detected=0;' +
        'thermal=0;low_airflow=0',
    );
  });

  it('dev is vout − baseline before rounding, like rev A (%.0f of the difference)', () => {
    const row = formatCsvRow(base({ ch4VoutMv: 1000.4, ch4BaselineMv: 999.6 }));
    expect(row.split(',').slice(2, 5)).toEqual(['1000', '1000', '1']);
  });

  it('blank for missing environment, GPS, Rs, estimates; fix 0; column count constant', () => {
    const row = formatCsvRow(
      base({
        tempC: null,
        humidityPct: null,
        pressureHpa: null,
        gps: null,
        ch4RsOhm: null,
        lpgRsOhm: null,
        ch4PpmEst: null,
        lpgPpmEst: undefined,
        ch4SlopeMvPerS: null,
        lpgSlopeMvPerS: undefined,
        spike: '',
        state: 'WARMUP',
        ch4BaselineMv: 0,
        lpgBaselineMv: 0,
      }),
    );
    const cells = row.split(',');
    expect(cells.length).toBe(49);
    expect(cells[1]).toBe('WARMUP');
    expect(cells[3]).toBe('0');
    expect(cells.slice(8, 11)).toEqual(['', '', '']);
    expect(cells[11]).toBe('2026-09-17 09:05:07.042'); // phone clock is always there
    expect(cells.slice(12, 17)).toEqual(['', '', '', '', '0']);
    expect(cells.slice(17, 26)).toEqual(['', '', '3987', '', '', '', '', '', '']);
    expect(cells.slice(26).every((c) => c === '')).toBe(true);
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

  it('writes the rev F MEMS cells from a Gas2 packet', () => {
    const gas2 = parseGas2(
      encodeGas2({
        seq: 7,
        memsATapMv: 412.3,
        memsBTapMv: null,
        memsAResMv: -1.24,
        memsASigmaMv: 0.8,
        memsBResMv: null,
        memsBSigmaMv: null,
        flags: 0b0011_1101,
        rail3v3Mv: 3300,
      }),
    );
    const reading = memsReading(gas2);
    const cells = formatCsvRow(base({ mems: { gas2, reading } })).split(',');
    expect(cells.length).toBe(SPEC_HEADER.split(',').length);
    const tail = cells.slice(-11);
    // vout = tap x 2, exactly as ch4_vout_mv = tap x tap_ratio.
    expect(tail[0]).toBe('825');
    expect(tail[1]).toBe('');
    expect(Number(tail[2])).toBe(Math.round(reading.a.rsOhm!));
    expect(tail.slice(3)).toEqual(['', '-1.2', '0.8', '', '', '1', '0', '61']);
  });

  it('file name matches the rev A SD-card pattern', () => {
    expect(surveyFileName(T)).toBe('2026-09-17_09-05-07.csv');
  });
});
