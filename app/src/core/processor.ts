// Run-state tracking on the phone, descended from the rev A signal processing
// (legacy/rev_a/src/main.cpp). Pure, no DOM.
//
//   WARMUP      - the heater is settling (heaterWarmupMs, 3 min by default):
//                 the slope is charted but no spike is flagged. Rev A timed this
//                 from power-on, so it is timed here from the device's
//                 ms_since_boot: connecting to a board that has been on for a
//                 while skips it entirely.
//   RUNNING     - normal operation.
//   HEATER_OFF  - flag bit6 (low-battery cutoff): the sensor output is
//                 meaningless. When the heaters come back the element is cold,
//                 so WARMUP restarts from there.
//
// A backwards jump in ms_since_boot means the board rebooted, so the heater is
// cold again: tracking restarts from WARMUP.
//
// The app no longer classifies readings (rev A's HIGH/MED/LOW) or shows a
// baseline: the absolute level wanders with temperature, humidity and airflow,
// so the plume indicator is the slope (core/spike.ts). The rolling-percentile
// baseline survives here only to fill the rev A *_baseline_mv / *_dev_mv CSV
// columns, with the rev A parameters fixed, so tools/plot_survey.py and
// tools/plot_map.py keep working on phone recordings. Nothing on screen reads it.

import type { ProcessingSettings } from './settings';
import { DEFAULT_PROCESSING } from './settings';
import { TimeWindow, percentile } from './windows';

export type RunState = 'WARMUP' | 'RUNNING' | 'HEATER_OFF';

/** The CSV-only baseline: the rev A 15th percentile of the last 2 min. */
export const CSV_BASELINE_WINDOW_MS = 2 * 60_000;
export const CSV_BASELINE_PERCENTILE = 0.15;

export interface ProcessorInput {
  /** Device ms_since_boot of the sample. */
  t: number;
  ch4Mv: number;
  lpgMv: number;
  /** Flag bit6: heaters off -> readings invalid. */
  heatersOff?: boolean;
}

export interface ChannelResult {
  voutMv: number;
  /** CSV only. 0 until the first baseline exists, exactly as rev A logged it. */
  baselineMv: number;
}

export interface ProcessorOutput {
  t: number;
  state: RunState;
  /** Time spent in the current state, and how long that state lasts (0 for RUNNING). */
  stateElapsedMs: number;
  stateDurationMs: number;
  ch4: ChannelResult;
  lpg: ChannelResult;
  rebooted: boolean;
}

class Channel {
  private bg = new TimeWindow(CSV_BASELINE_WINDOW_MS);
  baselineMv = 0;

  clear(): void {
    this.bg.clear();
  }

  push(t: number, v: number): void {
    this.bg.push(t, v);
    const p = percentile(this.bg.values(), CSV_BASELINE_PERCENTILE);
    if (p !== null) this.baselineMv = p;
  }
}

export class Processor {
  private s: ProcessingSettings;
  private ch4 = new Channel();
  private lpg = new Channel();
  private _state: RunState | null = null;
  private stateStart = 0;
  private lastT: number | null = null;

  constructor(settings: Partial<ProcessingSettings> = {}) {
    this.s = { ...DEFAULT_PROCESSING, ...settings };
  }

  get state(): RunState | null {
    return this._state;
  }

  get settings(): ProcessingSettings {
    return this.s;
  }

  updateSettings(settings: Partial<ProcessingSettings>): void {
    this.s = { ...this.s, ...settings };
  }

  /** Forget everything (new device). */
  reset(): void {
    this._state = null;
    this.lastT = null;
    this.ch4 = new Channel();
    this.lpg = new Channel();
  }

  private startRunning(t: number): void {
    this._state = 'RUNNING';
    this.stateStart = t;
    this.ch4.clear();
    this.lpg.clear();
  }

  push(input: ProcessorInput): ProcessorOutput {
    const { t, ch4Mv, lpgMv } = input;
    let rebooted = false;

    if (this.lastT !== null && t < this.lastT) {
      // ms_since_boot went backwards: the board restarted and its heater is cold.
      this.reset();
      rebooted = true;
    }
    this.lastT = t;

    if (this._state === null) {
      if (t < this.s.heaterWarmupMs) {
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
        this.ch4.clear();
        this.lpg.clear();
      }
    } else if (this._state === 'HEATER_OFF') {
      this._state = 'WARMUP';
      this.stateStart = t; // heater back on now: warm-up is timed from here
    }

    if (this._state === 'WARMUP' && t - this.stateStart >= this.s.heaterWarmupMs) {
      this.startRunning(t);
    }

    if (this._state === 'RUNNING') {
      this.ch4.push(t, ch4Mv);
      this.lpg.push(t, lpgMv);
    }

    const state = this._state as RunState;
    return {
      t,
      state,
      stateElapsedMs: t - this.stateStart,
      stateDurationMs: state === 'WARMUP' ? this.s.heaterWarmupMs : 0,
      ch4: { voutMv: ch4Mv, baselineMv: this.ch4.baselineMv },
      lpg: { voutMv: lpgMv, baselineMv: this.lpg.baselineMv },
      rebooted,
    };
  }
}

export type Rgb = [number, number, number];

/**
 * Status LED colour: dim blue until RUNNING, then green, red while the CH4
 * slope is over the spike threshold. Off while the heaters are off, to save the
 * battery that caused the cutoff.
 */
export function ledColour(state: RunState | null, spiking: boolean): Rgb {
  if (state === 'HEATER_OFF') return [0, 0, 0];
  if (state !== 'RUNNING') return [0, 0, 20];
  return spiking ? [40, 0, 0] : [0, 30, 0];
}
