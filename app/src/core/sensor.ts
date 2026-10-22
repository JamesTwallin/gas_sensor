// Bare TGS load-circuit math (docs/phone_board.md, "Gas sensor circuit").
//   VRL = V_tap × tap_ratio
//   Rs  = RL × (VC − VRL) / VRL
// Pure functions, no DOM.

import type { Gas2 } from './protocol';

/** Below this VRL (mV) the division is meaningless (open sensor / ADC floor). */
export const VRL_MIN_MV = 1;

export function vrlFromTap(tapMv: number, tapRatio: number): number {
  return tapMv * tapRatio;
}

/**
 * Sensor resistance in ohms, or null when VRL is ~0 (Rs would be infinite:
 * disconnected element, cold heater, or dead ADC). VRL at or above VC gives 0.
 */
export function rsOhm(vrlMv: number, rlOhm: number, vcMv: number): number | null {
  if (!Number.isFinite(vrlMv) || vrlMv < VRL_MIN_MV) return null;
  if (vrlMv >= vcMv) return 0;
  return (rlOhm * (vcMv - vrlMv)) / vrlMv;
}

/** Inverse of rsOhm: the VRL a given Rs produces. Used by the simulator. */
export function vrlFromRs(rs: number, rlOhm: number, vcMv: number): number {
  return (vcMv * rlOhm) / (rs + rlOhm);
}

// ---- Rev F MEMS blade --------------------------------------------------------
// +3V3 -> sensor (Rs) -> node N -> R -> tap T -> R -> GND; the ADC reads T, and
// the main board adds a 1M pull-up to +3V3 on T (blade detection). VC is the
// measured 3V3 rail. R depends on the channel: sensor A (SY-CH4-37BPM) 10k,
// sensor B (MiCS-5524) 100k. Rs is solved exactly, pull-up included:
//   I1 = VT/R - (VC - VT)/RP,  VN = VT + R*I1,  Rs = (VC - VN)/I1
// (without the pull-up this is the usual Rs = 2R(VC - 2VT)/(2VT)).

/** Half of each channel's load (RL = 2R): A = SY-CH4-37BPM, B = MiCS-5524. */
export const MEMS_R_OHM = { a: 10_000, b: 100_000 } as const;
export const MEMS_PULLUP_OHM = 1_000_000;
/** VRL = tap x 2 (the R/R divider), the same definition ch4_vout_mv uses. */
export const MEMS_TAP_RATIO = 2;
/** VC when the Gas2 packet has no rail reading. */
export const MEMS_VC_FALLBACK_MV = 3300;

/**
 * MEMS sensor resistance (ohms) from the tap voltage, for a channel whose divider
 * resistors are rOhm each; null when I1 <= 0 or VN >= VC (no solution).
 */
export function memsRsOhm(tapMv: number, vcMv: number, rOhm: number): number | null {
  if (!Number.isFinite(tapMv) || !Number.isFinite(vcMv) || !(rOhm > 0)) return null;
  const i1 = tapMv / rOhm - (vcMv - tapMv) / MEMS_PULLUP_OHM; // mA
  if (!(i1 > 0)) return null;
  const vn = tapMv + rOhm * i1;
  if (vn >= vcMv) return null;
  return (vcMv - vn) / i1;
}

export interface MemsChannel {
  /** Nominal VRL (mV) = tap x 2: the same quantity as ch4_vout_mv. Null when missing. */
  voutMv: number | null;
  rsOhm: number | null;
}

export interface MemsReading {
  a: MemsChannel;
  b: MemsChannel;
}

export function memsReading(g: Gas2): MemsReading {
  const vc = g.rail3v3Mv ?? MEMS_VC_FALLBACK_MV;
  const ch = (tap: number | null, r: number): MemsChannel =>
    tap === null
      ? { voutMv: null, rsOhm: null }
      : { voutMv: vrlFromTap(tap, MEMS_TAP_RATIO), rsOhm: memsRsOhm(tap, vc, r) };
  return { a: ch(g.memsATapMv, MEMS_R_OHM.a), b: ch(g.memsBTapMv, MEMS_R_OHM.b) };
}
