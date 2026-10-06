// Reads a saved survey CSV back into the map's track, so an old survey can be
// looked at again. Pure, no DOM.
//
// Columns are found by name, not position, so rev A SD-card files (no accuracy,
// slope or spike columns) load too: those draw the route and the Raw map, and
// the Spikes map is simply empty. The recorder writes the latest GPS position on
// every row, so a new fix is wherever lat/lon change; the rows before it are the
// readings "since the previous fix", exactly as the live TrackBuffer sees them.

import { TrackBuffer, type TrackPoint } from './track';

/** `YYYY-MM-DD HH:MM:SS.mmm` UTC (core/csv.ts formatUtc) to epoch ms; null if blank or bad. */
export function parseUtc(s: string): number | null {
  if (!s) return null;
  const t = Date.parse(s.trim().replace(' ', 'T') + (/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? '' : 'Z'));
  return Number.isFinite(t) ? t : null;
}

const num = (s: string | undefined): number | null => {
  if (s === undefined || s.trim() === '') return null;
  const v = Number(s);
  return Number.isFinite(v) ? v : null;
};

export function trackFromCsv(text: string): TrackPoint[] {
  const lines = text.split(/\r?\n/);
  const header = (lines[0] ?? '').replace(/^﻿/, '').split(',').map((h) => h.trim());
  const col = (name: string) => header.indexOf(name);
  const iLat = col('lat');
  const iLon = col('lon');
  if (iLat < 0 || iLon < 0) throw new Error('Not a survey CSV (no lat/lon columns)');
  const iUtc = col('utc_iso8601');
  const iMillis = col('millis_since_boot');
  const iAcc = col('gps_accuracy_m');
  const iFix = col('fix');
  const iMv = col('ch4_vout_mv');
  const iSlope = col('ch4_slope_mv_s');
  const iSpike = col('spike');

  const track = new TrackBuffer();
  let lastPos = '';
  for (let n = 1; n < lines.length; n++) {
    const line = lines[n];
    if (!line) continue;
    const c = line.split(',');
    const lat = num(c[iLat]);
    const lon = num(c[iLon]);
    if (lat !== null && lon !== null && !(lat === 0 && lon === 0)) {
      const pos = `${c[iLat]},${c[iLon]}`;
      if (pos !== lastPos) {
        lastPos = pos;
        const t = (iUtc >= 0 ? parseUtc(c[iUtc]) : null) ?? (iMillis >= 0 ? num(c[iMillis]) : null);
        // Phone files carry the accuracy; rev A files only say fix or no fix.
        const accuracyM = iAcc >= 0 ? num(c[iAcc]) : iFix >= 0 ? (c[iFix] === '1' ? 0 : null) : 0;
        if (t !== null) track.addFix({ lat, lon, accuracyM, timestamp: t });
      }
    }
    const mv = iMv >= 0 ? num(c[iMv]) : null;
    const slope = iSlope >= 0 ? num(c[iSlope]) : null;
    track.addSample(mv ?? NaN, slope, iSpike >= 0 && !!c[iSpike]?.trim());
  }
  return [...track.points()];
}
