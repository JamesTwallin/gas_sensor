// Bare TGS load-circuit math (docs/phone_board.md, "Gas sensor circuit").
//   VRL = V_tap × tap_ratio
//   Rs  = RL × (VC − VRL) / VRL
// Pure functions, no DOM.

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
