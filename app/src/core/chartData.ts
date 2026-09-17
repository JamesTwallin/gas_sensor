// History for the charts: the last N minutes of VRL + baseline, and the rev A
// peak-per-column decimation for the overview (so a brief plume is not lost
// between pixels). Pure, no DOM.

export interface ChartPoint {
  t: number;
  ch4: number;
  lpg: number;
  /** null while there is no trusted baseline (warm-up, heaters off). */
  baseline: number | null;
}

export class ChartBuffer {
  private pts: ChartPoint[] = [];
  private start = 0;

  constructor(public spanMs: number) {}

  clear(): void {
    this.pts = [];
    this.start = 0;
  }

  push(p: ChartPoint): void {
    this.pts.push(p);
    const cutoff = p.t - this.spanMs;
    while (this.start < this.pts.length && this.pts[this.start].t <= cutoff) this.start++;
    if (this.start > 2048 && this.start * 2 > this.pts.length) {
      this.pts = this.pts.slice(this.start);
      this.start = 0;
    }
  }

  get length(): number {
    return this.pts.length - this.start;
  }

  get last(): ChartPoint | null {
    return this.length ? this.pts[this.pts.length - 1] : null;
  }

  /** Points with t > since, oldest first. */
  since(since: number): ChartPoint[] {
    let lo = this.start;
    let hi = this.pts.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (this.pts[mid].t <= since) lo = mid + 1;
      else hi = mid;
    }
    return this.pts.slice(lo);
  }

  all(): ChartPoint[] {
    return this.pts.slice(this.start);
  }
}

export interface Column {
  /** Column index, 0 = left edge. */
  col: number;
  peak: number;
}

/**
 * Decimate a time range [t0, t1] to `cols` columns, taking the peak of `value` per
 * column. Columns with no samples are omitted (gaps stay gaps).
 */
export function peakPerColumn<T extends { t: number }>(
  pts: readonly T[],
  t0: number,
  t1: number,
  cols: number,
  value: (p: T) => number,
): Column[] {
  if (cols <= 0 || t1 <= t0) return [];
  const peaks = new Array<number>(cols).fill(-Infinity);
  const span = t1 - t0;
  for (const p of pts) {
    if (p.t < t0 || p.t > t1) continue;
    const c = Math.min(cols - 1, Math.floor(((p.t - t0) / span) * cols));
    const v = value(p);
    if (v > peaks[c]) peaks[c] = v;
  }
  const out: Column[] = [];
  for (let c = 0; c < cols; c++) if (peaks[c] !== -Infinity) out.push({ col: c, peak: peaks[c] });
  return out;
}

/** Rev A live-chart top: largest value on screen + 10 % headroom, never below the floor. */
export function dynamicYMax(values: Iterable<number>, floorMv: number): number {
  let m = 0;
  for (const v of values) if (v > m) m = v;
  return Math.max(floorMv, m * 1.1);
}
