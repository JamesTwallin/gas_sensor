// Simulated rev B board: produces protocol-exact Sample packets so the whole app
// (parse -> Rs -> processor -> chart -> CSV) runs without hardware. Pure and
// deterministic for a given seed; the timer lives in services/simDevice.ts.
//
// Model (rough, but shaped like the real thing):
//  - clean-air Rs drawn per board from the spec ranges (TGS2611 12–125 kΩ,
//    TGS2610 23–230 kΩ, log-uniform), with slow random-walk drift + noise;
//    VRL = VC·RL/(RL+Rs) with RL = 40 kΩ;
//  - "initial action": Rs starts low after heater-on and recovers over ~2 min, so
//    VRL reads high during warm-up, as a real TGS element does;
//  - heaters off (flag bit6, low-battery cutoff, or setHeatersOff): the element
//    goes cold and Rs climbs far above clean-air;
//  - plumes arrive at random (Poisson, mean gap ~75 s), rise fast and decay slowly,
//    and scale Rs by (1 + c)^-0.47 (the TGS2611 power law from docs/sensors.md);
//    LPG sees a weaker share;
//  - BME280 temperature / humidity / pressure wander slowly; battery drains.

import {
  encodeSample,
  FLAG_ADS_OK,
  FLAG_BME_OK,
  FLAG_BUTTON,
  FLAG_CHARGING,
  FLAG_HEATERS_OFF,
  FLAG_USB_POWER,
} from './protocol';
import { vrlFromRs } from './sensor';

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Plume {
  start: number;
  rise: number;
  decay: number;
  peak: number; // relative concentration multiplier
}

export interface SimOptions {
  seed?: number;
  rlOhm?: number;
  tapRatio?: number;
  vcMv?: number;
  intervalMs?: number;
  /** Start the board as if it had already been on this long (ms). */
  bootOffsetMs?: number;
  /** Mean gap between plumes, ms. */
  meanPlumeGapMs?: number;
}

export class SimulatedBoard {
  readonly rlOhm: number;
  readonly tapRatio: number;
  readonly vcMv: number;
  intervalMs: number;
  private rnd: () => number;
  private t: number;
  private seq = 0;
  private drift4 = 0;
  private driftL = 0;
  private temp = 20;
  private rsAir4: number;
  private rsAirL: number;
  private cutoff = false; // firmware low-battery cutoff
  private forcedOff = false; // test hook
  private heaterOnAt: number;
  private hum = 55;
  private pres = 1013;
  private vbat = 4150;
  private usb = false;
  private plumes: Plume[] = [];
  private nextPlumeAt: number;
  private button = false;
  private lowSince: number | null = null;
  private meanGap: number;

  constructor(opts: SimOptions = {}) {
    this.rnd = mulberry32(opts.seed ?? 12345);
    this.rlOhm = opts.rlOhm ?? 40000;
    this.tapRatio = opts.tapRatio ?? 2;
    this.vcMv = opts.vcMv ?? 5000;
    this.intervalMs = opts.intervalMs ?? 250;
    this.t = opts.bootOffsetMs ?? 0;
    this.meanGap = opts.meanPlumeGapMs ?? 75_000;
    this.temp = 17 + this.rnd() * 6;
    const logUniform = (lo: number, hi: number) => lo * Math.pow(hi / lo, this.rnd());
    this.rsAir4 = logUniform(12_000, 125_000);
    this.rsAirL = logUniform(23_000, 230_000);
    this.heaterOnAt = 0; // heaters come on at power-on
    this.nextPlumeAt = this.t + 60_000 + this.expGap();
  }

  infoJson(): string {
    return JSON.stringify({
      proto: 1,
      fw: 'sim-1.0.0',
      board: 'simulated',
      rl_ohm: this.rlOhm,
      tap_ratio: this.tapRatio,
      vc_mv: this.vcMv,
      interval_ms: this.intervalMs,
      heater_mv: 5010,
    });
  }

  pressButton(): void {
    this.button = true;
  }

  setUsb(on: boolean): void {
    this.usb = on;
  }

  get heatersOff(): boolean {
    return this.cutoff || this.forcedOff;
  }

  /** Test hook: force the heaters off regardless of the battery. */
  setHeatersOff(off: boolean): void {
    this.updateHeaters(() => (this.forcedOff = off));
  }

  private updateHeaters(change: () => void): void {
    const wasOff = this.heatersOff;
    change();
    if (wasOff && !this.heatersOff) this.heaterOnAt = this.t; // cold start again
  }

  get batteryMv(): number {
    return this.vbat;
  }

  private gauss(): number {
    const u = Math.max(1e-12, this.rnd());
    const v = this.rnd();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  private expGap(): number {
    return -Math.log(Math.max(1e-9, this.rnd())) * this.meanGap;
  }

  private plumeLevel(t: number): number {
    let c = 0;
    for (const p of this.plumes) {
      const dt = t - p.start;
      if (dt < 0) continue;
      c += dt < p.rise ? p.peak * (dt / p.rise) : p.peak * Math.exp(-(dt - p.rise) / p.decay);
    }
    return c;
  }

  /** Advance one interval and return the next Sample packet. */
  next(): Uint8Array {
    this.t += this.intervalMs;
    const t = this.t;
    const dtS = this.intervalMs / 1000;

    if (t >= this.nextPlumeAt) {
      this.plumes.push({
        start: t,
        rise: 1000 + this.rnd() * 4000,
        decay: 2000 + this.rnd() * 12000,
        peak: 0.5 + this.rnd() * this.rnd() * 12,
      });
      this.nextPlumeAt = t + this.expGap();
    }
    this.plumes = this.plumes.filter((p) => t - p.start < p.rise + p.decay * 8);

    // Slow bounded random-walk drift of the clean-air baseline (fraction of Rs).
    this.drift4 = Math.max(-0.15, Math.min(0.15, this.drift4 + this.gauss() * 0.002 * Math.sqrt(dtS)));
    this.driftL = Math.max(-0.15, Math.min(0.15, this.driftL + this.gauss() * 0.002 * Math.sqrt(dtS)));

    // Initial action: Rs depressed after power-on, recovering over ~2 min.
    const initial = 1 - 0.7 * Math.exp(-(t - this.heaterOnAt) / 45_000);
    // Cold element: very high resistance, gas response gone.
    const cold = this.heatersOff ? 30 : 1;
    const c = this.heatersOff ? 0 : this.plumeLevel(t);

    const rs4 = this.rsAir4 * cold * (1 + this.drift4) * initial * Math.pow(1 + c, -0.47) * (1 + this.gauss() * 0.006);
    const rsL = this.rsAirL * cold * (1 + this.driftL) * initial * Math.pow(1 + 0.25 * c, -0.53) * (1 + this.gauss() * 0.006);
    const vrl4 = vrlFromRs(Math.max(50, rs4), this.rlOhm, this.vcMv);
    const vrlL = vrlFromRs(Math.max(50, rsL), this.rlOhm, this.vcMv);

    this.temp += this.gauss() * 0.003;
    this.hum = Math.max(10, Math.min(95, this.hum + this.gauss() * 0.01));
    this.pres += this.gauss() * 0.01;
    if (this.usb) this.vbat = Math.min(4200, this.vbat + 0.02 * dtS);
    else this.vbat = Math.max(3100, this.vbat - (this.heatersOff ? 0.005 : 0.05) * dtS);

    let flags = FLAG_BME_OK | FLAG_ADS_OK;
    if (this.usb) flags |= FLAG_USB_POWER | (this.vbat < 4190 ? FLAG_CHARGING : 0);
    // Firmware low-battery cutoff (docs/phone_board.md flag bit6): heaters off
    // after VBAT < 3.3 V for > 10 s on battery; released when VBAT > 3.5 V or on USB.
    if (!this.usb && this.vbat < 3300) {
      this.lowSince ??= t;
      if (!this.cutoff && t - this.lowSince > 10_000) this.updateHeaters(() => (this.cutoff = true));
    } else {
      this.lowSince = null;
    }
    if (this.cutoff && (this.usb || this.vbat > 3500)) this.updateHeaters(() => (this.cutoff = false));
    if (this.heatersOff) flags |= FLAG_HEATERS_OFF;
    if (this.button) {
      flags |= FLAG_BUTTON;
      this.button = false;
    }

    const pkt = encodeSample({
      seq: this.seq,
      msSinceBoot: t,
      ch4TapMv: vrl4 / this.tapRatio,
      lpgTapMv: vrlL / this.tapRatio,
      tempC: this.temp,
      humidityPct: this.hum,
      pressureHpa: this.pres,
      vbatMv: this.vbat,
      flagsRaw: flags,
    });
    this.seq = (this.seq + 1) & 0xffff;
    return pkt;
  }
}

/** Rough LiPo state of charge from resting voltage (single cell). */
export function batteryPercent(vbatMv: number): number {
  const curve: [number, number][] = [
    [3300, 0],
    [3500, 5],
    [3600, 10],
    [3700, 25],
    [3750, 40],
    [3800, 55],
    [3900, 70],
    [4000, 82],
    [4100, 92],
    [4200, 100],
  ];
  if (vbatMv <= curve[0][0]) return 0;
  for (let i = 1; i < curve.length; i++) {
    const [v1, p1] = curve[i];
    const [v0, p0] = curve[i - 1];
    if (vbatMv <= v1) return Math.round(p0 + ((vbatMv - v0) / (v1 - v0)) * (p1 - p0));
  }
  return 100;
}
