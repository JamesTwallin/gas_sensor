// Anomaly detector settings: every coefficient, threshold and ratio band in one
// place. tools/anomaly_core.py reads this file too (simple "#define NAME value"
// and "#define NAME { a, b, ... }" lines only), so the Python replay and the
// firmware always run the same numbers. Keep each definition on one line.
//
// The block between FIT-BEGIN and FIT-END is rewritten by
// `python tools/replay.py fit --write-config`; edit the rest by hand.
// See docs/REPORT.md for where each value came from.
//
// Per-channel settings ("_CH" arrays, and the coefficient rows) are in the fixed
// channel order ch4, lpg, mems_a, mems_b, always with ANOM_MAX_NCH entries; a
// build with ANOM_NCH = 2 uses the first two. Those first two entries are the
// values the two-channel detector has always used, so replays are unchanged.

#ifndef ANOMALY_CONFIG_H
#define ANOMALY_CONFIG_H

// ---- Gas channels (compile-time) ------------------------------------------------
// 2 normally (the two Figaro sensors), 4 on the MEMS rig (plus the two MEMS sensors on
// the plug-in blade). Each channel runs independently with its own model and
// thresholds; the CH4/LPG ratio, classification and lead time use channels 0
// and 1 only.
#ifndef ANOM_NCH
#define ANOM_NCH 2
#endif
#define ANOM_MAX_NCH 4

// ---- Optional inputs (compile-time) ------------------------------------------
// The airflow thermistor and the CO sensor are not fitted on any board yet, and
// no survey contains them, so both features are off. Turning one on also needs
// non-zero coefficients for its features (refit once surveys include it).
#ifndef ANOM_USE_AIRFLOW
#define ANOM_USE_AIRFLOW 0
#endif
#ifndef ANOM_USE_CO
#define ANOM_USE_CO 0
#endif
// Per-unit adaptation of the coefficients (recursive least squares). Off by default.
#ifndef ANOM_USE_RLS
#define ANOM_USE_RLS 0
#endif

// ---- Timing ----------------------------------------------------------------------
// A gap longer than this between valid samples restarts the detector from scratch.
#define ANOM_GAP_RESET_MS 10000
// After a (re)start, no detection until the baselines and the noise estimate have
// had this long to settle.
#define ANOM_SETTLE_S 120.0

// ---- Slow baselines (exponentially weighted moving averages) ---------------------
// One time constant for the gas baselines and the temperature/humidity baselines,
// so the model relates like-for-like high-pass filtered signals.
#define ANOM_TAU_BASE_S 300.0
// A channel's baseline is frozen while it is anomalous, for at most this long ...
#define ANOM_FREEZE_MAX_S 120.0
// ... after which it follows again, but with this slower time constant.
#define ANOM_TAU_RESUME_S 1200.0

// ---- Rates of change -------------------------------------------------------------
#define ANOM_RATE_WINDOW_MS 10000
// Ring capacity for the rate window: 10 s at 4 Hz is 40 samples. At faster sample
// rates the window shrinks to what fits (the ring holds the most recent samples).
#define ANOM_RATE_RING 64

// ---- Airflow features (thermistor) ------------------------------------------------
// Smoothing time constants that mimic the gas sensors' slower response to airflow.
#define ANOM_AIR_TAU1_S 5.0
#define ANOM_AIR_TAU2_S 30.0
// An event counts as low-airflow when the airflow index stays below this throughout.
#define ANOM_AIR_LOW_INDEX 0.15

// ---- CO hook -------------------------------------------------------------------------
#define ANOM_TAU_CO_BASE_S 300.0
// A CO rise above its own slow baseline larger than this marks exhaust (ppm).
#define ANOM_CO_RISE_PPM 2.0
// Electrochemical CO cells are slow (tens of seconds): keep watching CO this long
// after the gas channels have settled before closing an event.
#define ANOM_CO_TAIL_S 45.0

// ---- Short-timescale stage (optional) ---------------------------------------------
// The conditions model leaves most of its error at timescales of a minute or more
// (airflow changes at stops and in traffic, until the thermistor is fitted). With
// this set above 0, detection works on the model residual minus its own trailing
// average over this time constant (frozen while the channel is anomalous, like the
// baselines), which removes that slow error but also part of any slow, sustained
// rise. 0 = off: detect on the model residual itself. See docs/REPORT.md.
#ifndef ANOM_RES_HP_TAU_S
#define ANOM_RES_HP_TAU_S 15.0
#endif

// ---- Noise estimate (rolling scaled median absolute deviation) ------------------
// Window in samples: 1200 = 5 min at 4 Hz.
#define ANOM_SIGMA_N 1200
// Recompute the median and MAD every this many valid samples (1 s at 4 Hz).
#define ANOM_SIGMA_EVERY 4
// Need at least this many residuals before sigma is trusted.
#define ANOM_SIGMA_MIN_N 240
// Never let sigma drop below this (mV): the electronics alone give ~0.3-0.5 mV.
// MEMS entries: same as the Figaros until MEMS rig surveys say otherwise.
#define ANOM_SIGMA_FLOOR_MV_CH { 1.0, 1.0, 1.0, 1.0 }

// ---- Detection (per channel, positive departures only) --------------------------
// One entry per channel (ch4, lpg, mems_a, mems_b). The MEMS entries are copies of
// the Figaro values and are NOT tuned: rerun `replay.py tune` / compare_sensors.py
// once MEMS rig surveys exist.
// A residual above K_ON robust sigma, held for SUSTAIN_S, raises the channel.
#define ANOM_K_ON_CH { 10.0, 10.0, 10.0, 10.0 }
#define ANOM_SUSTAIN_S_CH { 8.0, 8.0, 8.0, 8.0 }
// The channel stays raised until the residual falls below K_OFF sigma.
#define ANOM_K_OFF_CH { 3.0, 3.0, 3.0, 3.0 }
// Baselines (and the short-timescale reference) stop following a channel as soon
// as its residual passes K_HOLD sigma, so a rising plume is not absorbed before
// it reaches K_ON. Set equal to K_ON to freeze only on the detection threshold.
#ifndef ANOM_K_HOLD_CH
#define ANOM_K_HOLD_CH { 10.0, 10.0, 10.0, 10.0 }
#endif

// ---- Suppression after temperature or humidity steps ----------------------------
// |dT/dt| or |d(abs humidity)/dt| over the rate window above these blocks new
// detections for SUPPRESS_S. Being stationary never suppresses anything.
#define ANOM_STEP_T_RATE 0.06
#define ANOM_STEP_AH_RATE 0.06
#define ANOM_SUPPRESS_S 30.0

// ---- Event fingerprint and classification ----------------------------------------
// Events open and close on the Figaro channels (0 and 1) only. MEMS channels raise
// their own anomaly flags and record their peaks within an event, nothing else.
// Close an event once neither Figaro channel has been raised for this long.
#define ANOM_MERGE_GAP_S 5.0
// A channel counts as "raised" during an event if it was detected, or if its peak
// residual reached K_RAISE sigma (so a weak response on the other channel counts).
#define ANOM_K_RAISE_CH { 3.0, 3.0, 3.0, 3.0 }
// Onset for the "which channel leads" measure: residual crossing K_LEAD sigma.
#define ANOM_K_LEAD 3.0
// A smaller temperature/humidity rate that, if it comes up to THERMAL_PRE_S before
// an event's onset or within THERMAL_POST_S after it, marks the event THERMAL.
// Steps later in an event do not count: they are usually its effect, not its
// cause (stopping in a plume warms the case air), and with a 5 % chance of a step
// in any second, almost every long event would otherwise be marked. The confirmed
// leak of 11 Oct 2026 was marked THERMAL that way.
#define ANOM_THERMAL_T_RATE 0.03
#define ANOM_THERMAL_AH_RATE 0.03
#define ANOM_THERMAL_PRE_S 20.0
#define ANOM_THERMAL_POST_S 5.0
// CH4-to-LPG peak residual ratio at or below this is "strongly LPG-led" (HEAVY_HC).
#define ANOM_HEAVY_RATIO_MAX 0.4
// Natural gas band for the CH4-to-LPG ratio. NOT MEASURED: there has been no
// positive-control survey on this hardware, so NATURAL_GAS is never assigned
// (VALID 0) and both-channel events are UNRESOLVED. See docs/PROTOCOL.md.
#define ANOM_NG_BAND_VALID 0
#define ANOM_NG_RATIO_LO 0.0
#define ANOM_NG_RATIO_HI 0.0
// Without a CO sensor exhaust cannot be ruled out; only allow NATURAL_GAS without
// CO if this is set deliberately.
#define ANOM_NG_WITHOUT_CO 0

// ---- Recursive least squares (only with ANOM_USE_RLS) -----------------------------
// Forgetting factor per sample: 0.99998 is a memory of ~50000 samples (~3.5 h).
#define ANOM_RLS_LAMBDA 0.99998
#define ANOM_RLS_P0 0.01
// Each adapted coefficient is kept within this fraction of its shared value.
#define ANOM_RLS_MAX_REL 0.5

// ---- Conditions model --------------------------------------------------------------
// Feature order (see anomaly.h): bias, dT, dAH, dT/dt, dAH/dt, dT slow,
//   airflow index, airflow smoothed 1, airflow smoothed 2, CO deviation.
// Units: degC, g/m3, degC/s, g/m3/s, degC, index, index, index, ppm. Output mV.
// One row per channel, each fitted on its own (`replay.py fit` writes every row
// it has data for). ANOM_COEF_MEMS_A/B are a neutral all-zero model (prediction
// 0, so the residual is just the reading minus its slow baseline) until they are
// fitted from MEMS rig surveys.
#define ANOM_TAU_T_SLOW_S 60.0
// FIT-BEGIN
#define ANOM_COEF_CH4 { 5.31152, 66.4906, 19.0137, 120.901, -108.94, -20.8299, 0.0, 0.0, 0.0, 0.0 }
#define ANOM_COEF_LPG { 9.7932, 59.2586, 17.5835, 23.4529, -86.7051, -7.96977, 0.0, 0.0, 0.0, 0.0 }
#define ANOM_COEF_MEMS_A { 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0 }
#define ANOM_COEF_MEMS_B { 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0 }
// FIT-END

#endif  // ANOMALY_CONFIG_H
