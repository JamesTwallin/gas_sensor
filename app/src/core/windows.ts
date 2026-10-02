// Time-based rolling windows. Rev A sized its rings in samples
// (WINDOW_MS / SAMPLE_INTERVAL_MS); the sample interval is configurable over BLE
// now, so windows here are defined by sample timestamps instead: a window of W ms
// holds every sample with t in (t_latest − W, t_latest]. At a steady 250 ms that
// is exactly the rev A ring length. Pure, no DOM.

export class TimeWindow {
  private ts: number[] = [];
  private vs: number[] = [];
  private start = 0;

  constructor(public windowMs: number) {}

  get length(): number {
    return this.ts.length - this.start;
  }

  clear(): void {
    this.ts = [];
    this.vs = [];
    this.start = 0;
  }

  push(t: number, v: number): void {
    this.ts.push(t);
    this.vs.push(v);
    this.prune(t);
  }

  /** Drop samples at or older than t − windowMs. */
  prune(now: number): void {
    const cutoff = now - this.windowMs;
    while (this.start < this.ts.length && this.ts[this.start] <= cutoff) this.start++;
    // Compact occasionally so the backing arrays don't grow without bound.
    if (this.start > 1024 && this.start * 2 > this.ts.length) {
      this.ts = this.ts.slice(this.start);
      this.vs = this.vs.slice(this.start);
      this.start = 0;
    }
  }

  values(): number[] {
    return this.vs.slice(this.start);
  }

  forEach(fn: (t: number, v: number) => void): void {
    for (let i = this.start; i < this.ts.length; i++) fn(this.ts[i], this.vs[i]);
  }

  min(): number | null {
    if (this.length === 0) return null;
    let m = Infinity;
    for (let i = this.start; i < this.vs.length; i++) if (this.vs[i] < m) m = this.vs[i];
    return m;
  }

  max(): number | null {
    if (this.length === 0) return null;
    let m = -Infinity;
    for (let i = this.start; i < this.vs.length; i++) if (this.vs[i] > m) m = this.vs[i];
    return m;
  }
}

/** k-th smallest (0-based) of arr, in place (Hoare quickselect, like std::nth_element). */
export function nthElement(arr: number[], k: number): number {
  let lo = 0;
  let hi = arr.length - 1;
  while (lo < hi) {
    const pivot = arr[(lo + hi) >> 1];
    let i = lo;
    let j = hi;
    while (i <= j) {
      while (arr[i] < pivot) i++;
      while (arr[j] > pivot) j--;
      if (i <= j) {
        const tmp = arr[i];
        arr[i] = arr[j];
        arr[j] = tmp;
        i++;
        j--;
      }
    }
    if (k <= j) hi = j;
    else if (k >= i) lo = i;
    else return arr[k];
  }
  return arr[k];
}

/**
 * The rev A percentile: index k = floor(p × (n − 1)) of the sorted window, no
 * interpolation. Returns null for an empty window.
 */
export function percentile(values: readonly number[], p: number): number | null {
  const n = values.length;
  if (n === 0) return null;
  const k = Math.floor(p * (n - 1));
  return nthElement(values.slice(), Math.max(0, Math.min(n - 1, k)));
}
