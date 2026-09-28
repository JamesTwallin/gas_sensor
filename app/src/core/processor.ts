// Port of the rev A signal processing (src/main.cpp) to the phone. Pure, no DOM.
//
//   WARMUP      - the heater is settling and readings are meaningless for
//                 classification (they are still charted and recorded raw). Rev A
//                 timed this from power-on, so it is timed here from the device's
//                 ms_since_boot: connecting to a board that has been on for a
//                 while skips it entirely.
//   RUNNING     - baseline = low percentile of the rolling background window
//                 (tracks slow drift, unmoved by brief plumes), and a
//                 HIGH/MED/LOW class from where the reading sits in its 10 min
//                 min..max range. There is no separate "baselining" wait: the
//                 baseline is provisional while the window is short and simply
//                 firms up as samples arrive. The raw data is what matters and it
//                 is never gated; everything derived can be recomputed from the
//                 CSV later.
//   HEATER_OFF  - flag bit6 (low-battery cutoff): the sensor output is
//                 meaningless, windows are cleared, no class. When the heaters
//                 come back the element is cold, so WARMUP restarts from there.
//
// Differences from rev A, all forced by the move to BLE:
//  - windows are time-based (sample timestamps), since the interval is settable;
//  - a backwards jump in ms_since_boot means the board rebooted, so the heater is
//    cold again: processing restarts from WARMUP with empty windows;
//  - re-zero comes from flag bit5 (BOOT button) or the app, not a GPIO poll. It
//    empties the windows so the baseline restarts from the current reading.

import type { ProcessingSettings } from './settings';
import { DEFAULT_PROCESSING } from './settings';
import { TimeWindow, classifyLevel, percentile, type Level } from './windows';

export type RunState = 'WARMUP' | 'RUNNING' | 'HEATER_OFF';

export interface ProcessorInput {
  /** Device ms_since_boot of the sample. */
  t: number;
  ch4Mv: number;
  lpgMv: number;
  /** Flag bit5: BOOT button pressed -> re-zero. */
  button?: boolean;
  /** Flag bit6: heaters off -> readings invalid. */
  heatersOff?: boolean;
}

export interface ChannelResult {
  voutMv: number;
  /** 0 until the first baseline exists, exactly as rev A logged it. */
  baselineMv: number;
  devMv: number;
  /** null unless RUNNING. */
  level: Level | null;
}

export interface ProcessorOutput {
  t: number;
  state: RunState;
  /** Time spent in the current state, and how long that state lasts (0 for RUNNING). */
  stateElapsedMs: number;
  stateDurationMs: number;
  /** How much history the baseline rests on (ms); short right after a (re)start. */
  baselineAgeMs: number;
  ch4: ChannelResult;
  lpg: ChannelResult;
  /** True when this sample caused a re-zero (button or app). */
  rezeroed: boolean;
  rebooted: boolean;
}

class Channel {
  bg: TimeWindow;
  cls: TimeWindow;
  baselineMv = 0;

  constructor(s: ProcessingSettings) {
    this.bg = new TimeWindow(s.bgWindowMs);
    this.cls = new TimeWindow(s.classWindowMs);
  }

  apply(s: ProcessingSettings): void {
    this.bg.windowMs = s.bgWindowMs;
    this.cls.windowMs = s.classWindowMs;
  }

  clearWindows(): void {
    this.bg.clear();
    this.cls.clear();
  }

  push(t: number, v: number, s: ProcessingSettings): void {
    this.bg.push(t, v);
    this.cls.push(t, v);
    const p = percentile(this.bg.values(), s.bgPercentile);
    if (p !== null) this.baselineMv = p;
  }

  result(v: number, running: boolean, s: ProcessingSettings): ChannelResult {
    return {
      voutMv: v,
      baselineMv: this.baselineMv,
      devMv: v - this.baselineMv,
      level: running ? classifyLevel(v, this.cls.min(), this.cls.max(), s.classRangeFloorMv) : null,
    };
  }
}

export class Processor {
  private s: ProcessingSettings;
  private ch4: Channel;
  private lpg: Channel;
  private _state: RunState | null = null;
  private stateStart = 0;
  /** Timestamp the background window last started filling from. */
  private windowStart = 0;
  private lastT: number | null = null;
  private pendingRezero = false;

  constructor(settings: Partial<ProcessingSettings> = {}) {
    this.s = { ...DEFAULT_PROCESSING, ...settings };
    this.ch4 = new Channel(this.s);
    this.lpg = new Channel(this.s);
  }

  get state(): RunState | null {
    return this._state;
  }

  get settings(): ProcessingSettings {
    return this.s;
  }

  /** Live settings change; windows re-prune on the next sample. */
  updateSettings(settings: Partial<ProcessingSettings>): void {
    this.s = { ...this.s, ...settings };
    this.ch4.apply(this.s);
    this.lpg.apply(this.s);
  }

  /** Re-zero from the app UI; applied on the next sample (it needs a timestamp). */
  requestRezero(): void {
    this.pendingRezero = true;
  }

  /** Forget everything (new device). */
  reset(): void {
    this._state = null;
    this.lastT = null;
    this.pendingRezero = false;
    this.ch4 = new Channel(this.s);
    this.lpg = new Channel(this.s);
  }

  private startRunning(t: number): void {
    this._state = 'RUNNING';
    this.stateStart = t;
    this.windowStart = t;
    this.ch4.clearWindows();
    this.lpg.clearWindows();
  }

  push(input: ProcessorInput): ProcessorOutput {
    const { t, ch4Mv, lpgMv } = input;
    let rebooted = false;
    let rezeroed = false;

    if (this.lastT !== null && t < this.lastT) {
      // ms_since_boot went backwards: the board restarted and its heater is cold.
      this.reset();
      rebooted = true;
    }
    this.lastT = t;

    if (this._state === null) {
      if (t < this.s.warmupMs) {
        this._state = 'WARMUP';
        this.stateStart = 0; // warm-up is timed from device power-on
      } else {
        this.startRunning(t);
      }
    }

    if (input.heatersOff) {
      if (this._state !== 'HEATER_OFF') {
        this._state = 'HEATER_OFF';
        this.stateStart = t;
        this.ch4.clearWindows();
        this.lpg.clearWindows();
      }
      this.pendingRezero = false;
    } else if (this._state === 'HEATER_OFF') {
      this._state = 'WARMUP';
      this.stateStart = t; // heater back on now: warm-up is timed from here
    }

    if (this._state !== 'HEATER_OFF' && (input.button || this.pendingRezero)) {
      this.pendingRezero = false;
      if (this._state === 'RUNNING') {
        this.windowStart = t;
        this.ch4.clearWindows();
        this.lpg.clearWindows();
      }
      rezeroed = true;
    }

    if (this._state === 'WARMUP' && t - this.stateStart >= this.s.warmupMs) {
      this.startRunning(t);
    }

    if (this._state === 'RUNNING') {
      this.ch4.push(t, ch4Mv, this.s);
      this.lpg.push(t, lpgMv, this.s);
    }

    const state = this._state as RunState;
    const running = state === 'RUNNING';
    return {
      t,
      state,
      stateElapsedMs: t - this.stateStart,
      stateDurationMs: state === 'WARMUP' ? this.s.warmupMs : 0,
      baselineAgeMs: running ? Math.min(t - this.windowStart, this.s.bgWindowMs) : 0,
      ch4: this.ch4.result(ch4Mv, running, this.s),
      lpg: this.lpg.result(lpgMv, running, this.s),
      rezeroed,
      rebooted,
    };
  }
}

export type Rgb = [number, number, number];

/**
 * Status LED colour, rev A values: dim blue until RUNNING, then green / amber /
 * red for CH4 LOW / MED / HIGH (LOW also when there is no class yet). Off while
 * the heaters are off, to save the battery that caused the cutoff.
 */
export function ledColour(state: RunState | null, level: Level | null): Rgb {
  if (state === 'HEATER_OFF') return [0, 0, 0];
  if (state !== 'RUNNING') return [0, 0, 20];
  switch (level) {
    case 'HIGH':
      return [40, 0, 0];
    case 'MED':
      return [35, 18, 0];
    default:
      return [0, 30, 0];
  }
}
