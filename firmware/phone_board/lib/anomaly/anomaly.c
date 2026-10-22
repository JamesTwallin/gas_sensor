// Gas anomaly detector. See anomaly.h for the principles and anomaly_config.h
// for every tunable number. Python twin: tools/anomaly_core.py -- keep the two in
// step, statement for statement, and run `python tools/replay.py parity`.

#include "anomaly.h"

#include <math.h>
#include <string.h>

// Maths in the chosen precision.
#define R(x) ((anom_real)(x))
#if defined(ANOM_REAL_IS_DOUBLE)
#define A_EXP exp
#define A_LOG log
#define A_FABS fabs
#else
#define A_EXP expf
#define A_LOG logf
#define A_FABS fabsf
#endif

#define MAD_SCALE R(1.4826)

const anom_real ANOM_COEF[ANOM_MAX_NCH][ANOM_NFEAT] = {
    ANOM_COEF_CH4, ANOM_COEF_LPG, ANOM_COEF_MEMS_A, ANOM_COEF_MEMS_B,
};

// Per-channel settings, in channel order. SUSTAIN_S stays double: the C code has
// always converted it to milliseconds in double.
static const anom_real K_ON[ANOM_MAX_NCH] = ANOM_K_ON_CH;
static const anom_real K_OFF[ANOM_MAX_NCH] = ANOM_K_OFF_CH;
static const anom_real K_HOLD[ANOM_MAX_NCH] = ANOM_K_HOLD_CH;
static const anom_real K_RAISE[ANOM_MAX_NCH] = ANOM_K_RAISE_CH;
static const anom_real SIGMA_FLOOR[ANOM_MAX_NCH] = ANOM_SIGMA_FLOOR_MV_CH;
static const double SUSTAIN_S[ANOM_MAX_NCH] = ANOM_SUSTAIN_S_CH;

static const char *const CLASS_NAMES[] = {
    "", "NATURAL_GAS", "EXHAUST", "HEAVY_HC", "THERMAL", "LOW_AIRFLOW", "UNRESOLVED", "UNCLASSIFIED",
};

const char *anom_class_name(anom_class c) {
  if ((unsigned)c >= sizeof(CLASS_NAMES) / sizeof(CLASS_NAMES[0])) return "";
  return CLASS_NAMES[c];
}

static const anom_real *shared_coef(int c) { return ANOM_COEF[c]; }

// Scratch for the median: the detector runs on one task only.
static anom_real g_scratch[ANOM_SIGMA_N];

// k-th smallest of a[0..n-1], in place (Hoare quickselect).
static anom_real nth_element(anom_real *a, int n, int k) {
  int lo = 0, hi = n - 1;
  while (lo < hi) {
    anom_real pivot = a[(lo + hi) >> 1];
    int i = lo, j = hi;
    while (i <= j) {
      while (a[i] < pivot) i++;
      while (a[j] > pivot) j--;
      if (i <= j) {
        anom_real tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
        i++;
        j--;
      }
    }
    if (k <= j) hi = j;
    else if (k >= i) lo = i;
    else return a[k];
  }
  return a[k];
}

// Exponential smoothing weight for a step of dt seconds.
static anom_real alpha(anom_real dt_s, anom_real tau_s) { return R(1) - A_EXP(-dt_s / tau_s); }

// Signed difference a - b of two millisecond clocks (wrap-safe).
static int32_t ms_diff(uint32_t a, uint32_t b) { return (int32_t)(a - b); }

static anom_real clampr(anom_real x, anom_real lo, anom_real hi) {
  return x < lo ? lo : (x > hi ? hi : x);
}

anom_real anom_abs_humidity(anom_real temp_c, anom_real rh_pct) {
  // Magnus saturation vapour pressure (hPa), then the ideal gas law.
  anom_real es = R(6.112) * A_EXP(R(17.67) * temp_c / (temp_c + R(243.5)));
  return es * rh_pct * R(2.1674) / (R(273.15) + temp_c);
}

// ---- Thermistor airflow index ----------------------------------------------------

anom_real anom_thermistor_temp_c(const anom_thermistor *th, anom_real v_mv) {
  anom_real r = th->series_ohm * v_mv / (th->supply_mv - v_mv);
  return R(1) / (R(1) / R(298.15) + A_LOG(r / th->r25_ohm) / th->beta_k) - R(273.15);
}

anom_real anom_thermistor_conductance(const anom_thermistor *th, anom_real v_mv,
                                      anom_real ambient_c, uint8_t *ok) {
  *ok = 0;
  if (!(v_mv > R(10)) || !(v_mv < th->supply_mv - R(10))) return R(0);
  anom_real r = th->series_ohm * v_mv / (th->supply_mv - v_mv);
  anom_real p_mw = v_mv * v_mv / (r * R(1000));  // (mV^2 / ohm) / 1000 = mW
  anom_real rise = anom_thermistor_temp_c(th, v_mv) - ambient_c;
  if (!(rise > th->min_rise_k)) return R(0);
  *ok = 1;
  return p_mw / rise;
}

anom_real anom_airflow_index(const anom_thermistor *th, anom_real v_mv, anom_real ambient_c,
                             uint8_t *ok) {
  anom_real g = anom_thermistor_conductance(th, v_mv, ambient_c, ok);
  if (!*ok || !(th->g_still_mw_k > R(0))) {
    *ok = 0;
    return R(0);
  }
  return g / th->g_still_mw_k - R(1);
}

// ---- Detector ------------------------------------------------------------------------

// One channel back to its power-on state (its next valid sample starts it again).
static void channel_reset(anom_channel *ch, int c) {
  memset(ch, 0, sizeof(*ch));
#if ANOM_USE_RLS
  const anom_real *w = shared_coef(c);
  for (int i = 0; i < ANOM_NFEAT; i++) {
    ch->coef[i] = (double)w[i];
    for (int j = 0; j < ANOM_NFEAT; j++) ch->P[i][j] = (i == j) ? ANOM_RLS_P0 : 0.0;
  }
#else
  (void)c;
#endif
}

static void restart(anom_state *s) {
  uint16_t next_id = s->next_event_id;
  memset(s, 0, sizeof(*s));
  s->next_event_id = next_id;
  for (int c = 0; c < ANOM_NCH; c++) channel_reset(&s->ch[c], c);
}

void anom_init(anom_state *s) {
  memset(s, 0, sizeof(*s));
  s->next_event_id = 1;
  restart(s);
}

static void update_sigma(anom_channel *ch, anom_real floor_mv) {
  int n = ch->ring_count;
  if (n < ANOM_SIGMA_MIN_N) return;
  for (int i = 0; i < n; i++) g_scratch[i] = ch->ring[i];
  anom_real med = nth_element(g_scratch, n, n / 2);
  for (int i = 0; i < n; i++) g_scratch[i] = A_FABS(ch->ring[i] - med);
  anom_real mad = nth_element(g_scratch, n, n / 2);
  anom_real sig = MAD_SCALE * mad;
  ch->sigma = sig > floor_mv ? sig : floor_mv;
  ch->sigma_ok = 1;
}

static void ring_push(anom_channel *ch, anom_real r) {
  ch->ring[ch->ring_head] = r;
  ch->ring_head = (uint16_t)((ch->ring_head + 1) % ANOM_SIGMA_N);
  if (ch->ring_count < ANOM_SIGMA_N) ch->ring_count++;
}

#if ANOM_USE_RLS
// One recursive-least-squares step towards target, in double precision. The bias
// is never adapted (a unit must not learn a place's offset), and every other
// coefficient stays within ANOM_RLS_MAX_REL of its shared value.
static void rls_update(anom_channel *ch, const anom_real *xr, anom_real target, const anom_real *w0) {
  double x[ANOM_NFEAT], px[ANOM_NFEAT], k[ANOM_NFEAT];
  for (int i = 0; i < ANOM_NFEAT; i++) x[i] = (double)xr[i];
  double e = (double)target;
  for (int i = 0; i < ANOM_NFEAT; i++) e -= ch->coef[i] * x[i];
  double denom = ANOM_RLS_LAMBDA;
  for (int i = 0; i < ANOM_NFEAT; i++) {
    px[i] = 0;
    for (int j = 0; j < ANOM_NFEAT; j++) px[i] += ch->P[i][j] * x[j];
    denom += x[i] * px[i];
  }
  for (int i = 0; i < ANOM_NFEAT; i++) k[i] = px[i] / denom;
  for (int i = 1; i < ANOM_NFEAT; i++) {
    double w = (double)w0[i];
    double lim = ANOM_RLS_MAX_REL * fabs(w);
    double v = ch->coef[i] + k[i] * e;
    ch->coef[i] = v < w - lim ? w - lim : (v > w + lim ? w + lim : v);
  }
  for (int i = 0; i < ANOM_NFEAT; i++)
    for (int j = 0; j < ANOM_NFEAT; j++)
      ch->P[i][j] = (ch->P[i][j] - k[i] * px[j]) / ANOM_RLS_LAMBDA;
}
#endif

// Classification and confidence use channels 0 and 1 (CH4, LPG) only.
static void classify(anom_event *ev) {
  for (int c = 0; c < ANOM_NCH; c++)
    ev->raised[c] = (uint8_t)(ev->detected[c] || ev->peak_sigma[c] >= K_RAISE[c]);
  anom_real denom = ev->peak_res_mv[ANOM_LPG];
  if (denom < SIGMA_FLOOR[ANOM_LPG]) denom = SIGMA_FLOOR[ANOM_LPG];
  ev->ratio = clampr(ev->peak_res_mv[ANOM_CH4] / denom, R(0), R(99));

  // Strength of the stronger channel relative to its own K_ON. With equal K_ON on
  // both (as shipped) this is exactly (larger peak - K_ON) / K_ON, as before.
  anom_real s0 = (ev->peak_sigma[ANOM_CH4] - K_ON[ANOM_CH4]) / K_ON[ANOM_CH4];
  anom_real s1 = (ev->peak_sigma[ANOM_LPG] - K_ON[ANOM_LPG]) / K_ON[ANOM_LPG];
  anom_real strength = clampr(s0 > s1 ? s0 : s1, R(0), R(1));
  anom_real detect_conf = R(0.5) + R(0.5) * strength;
  anom_real margin = R(1);

  uint8_t both = ev->raised[ANOM_CH4] && ev->raised[ANOM_LPG];
  uint8_t co_rise = ev->co_known && ev->co_peak_ppm > R(ANOM_CO_RISE_PPM);
  anom_class cls;
  if (ev->thermal) {
    cls = ANOM_CLASS_THERMAL;
  } else if (both) {
    if (co_rise) {
      cls = ANOM_CLASS_EXHAUST;
    } else if (ev->ratio <= R(ANOM_HEAVY_RATIO_MAX)) {
      cls = ANOM_CLASS_HEAVY_HC;
      margin = R(0.5) + R(0.5) * clampr(R(1) - ev->ratio / R(ANOM_HEAVY_RATIO_MAX), R(0), R(1));
    } else if (ANOM_NG_BAND_VALID && ev->ratio >= R(ANOM_NG_RATIO_LO) &&
               ev->ratio <= R(ANOM_NG_RATIO_HI) &&
               ((ev->co_known && !co_rise) || ANOM_NG_WITHOUT_CO)) {
      cls = ANOM_CLASS_NATURAL_GAS;
      // Closeness to the band's geometric centre, in log space.
      anom_real lo = R(ANOM_NG_RATIO_LO) > R(0.01) ? R(ANOM_NG_RATIO_LO) : R(0.01);
      anom_real hi = R(ANOM_NG_RATIO_HI) > lo ? R(ANOM_NG_RATIO_HI) : lo * R(1.01);
      anom_real half = R(0.5) * A_LOG(hi / lo);
      anom_real off = A_FABS(A_LOG(ev->ratio > lo ? ev->ratio : lo) - R(0.5) * A_LOG(hi * lo));
      margin = R(0.5) + R(0.5) * clampr(R(1) - off / half, R(0), R(1));
    } else if (ev->low_airflow) {
      cls = ANOM_CLASS_LOW_AIRFLOW;
    } else {
      cls = ANOM_CLASS_UNRESOLVED;
    }
  } else if (ev->raised[ANOM_LPG]) {
    cls = ANOM_CLASS_HEAVY_HC;
  } else if (ev->low_airflow) {
    cls = ANOM_CLASS_LOW_AIRFLOW;
  } else {
    cls = ANOM_CLASS_UNCLASSIFIED;
  }
  ev->cls = cls;
  ev->confidence = (uint8_t)(R(100) * detect_conf * margin + R(0.5));
}

void anom_step(anom_state *s, const anom_input *in, anom_output *out) {
  memset(out, 0, sizeof(*out));
  if (!in->valid) return;

  uint32_t t = in->t_ms;
  if (s->started && ms_diff(t, s->last_t_ms) > ANOM_GAP_RESET_MS) restart(s);

  anom_real ah = anom_abs_humidity(in->temp_c, in->rh_pct);
  anom_real dt = R(0);
  if (!s->started) {
    s->started = 1;
    s->start_t_ms = t;
    s->t_base = in->temp_c;
    s->ah_base = ah;
    s->dt_slow = R(0);
  } else {
    dt = R(ms_diff(t, s->last_t_ms)) / R(1000);
    if (dt < R(0)) dt = R(0);
  }
  s->last_t_ms = t;
  s->n_valid++;

  // Conditions: deviations from their own slow baselines.
  anom_real a_base = alpha(dt, R(ANOM_TAU_BASE_S));
  s->t_base += a_base * (in->temp_c - s->t_base);
  s->ah_base += a_base * (ah - s->ah_base);
  anom_real d_t = in->temp_c - s->t_base;
  anom_real d_ah = ah - s->ah_base;
  s->dt_slow += alpha(dt, R(ANOM_TAU_T_SLOW_S)) * (d_t - s->dt_slow);

  // Rates over ~10 s: against the newest stored sample at least a window old.
  anom_rate_sample *rs = &s->rate_ring[s->rate_head];
  rs->t_ms = t;
  rs->temp_c = in->temp_c;
  rs->ah = ah;
  s->rate_head = (uint16_t)((s->rate_head + 1) % ANOM_RATE_RING);
  if (s->rate_count < ANOM_RATE_RING) s->rate_count++;
  anom_real t_rate = R(0), ah_rate = R(0);
  for (int i = 1; i < s->rate_count; i++) {
    const anom_rate_sample *r =
        &s->rate_ring[(s->rate_head + ANOM_RATE_RING - 1 - i) % ANOM_RATE_RING];
    int32_t age = ms_diff(t, r->t_ms);
    if (age >= ANOM_RATE_WINDOW_MS) {
      anom_real span = R(age) / R(1000);
      t_rate = (in->temp_c - r->temp_c) / span;
      ah_rate = (ah - r->ah) / span;
      break;
    }
  }

  // Airflow and CO hooks.
  anom_real air = R(0), air_s1 = R(0), air_s2 = R(0), co_dev = R(0);
  uint8_t air_ok = 0, co_ok = 0;
#if ANOM_USE_AIRFLOW
  if (in->airflow_ok) {
    air_ok = 1;
    air = in->airflow_index;
    if (!s->air_started) {
      s->air_started = 1;
      s->air_s1 = air;
      s->air_s2 = air;
    } else {
      s->air_s1 += alpha(dt, R(ANOM_AIR_TAU1_S)) * (air - s->air_s1);
      s->air_s2 += alpha(dt, R(ANOM_AIR_TAU2_S)) * (air - s->air_s2);
    }
    air_s1 = s->air_s1;
    air_s2 = s->air_s2;
  }
#endif
#if ANOM_USE_CO
  if (in->co_ok) {
    co_ok = 1;
    if (!s->co_started) {
      s->co_started = 1;
      s->co_base = in->co_ppm;
    } else {
      s->co_base += alpha(dt, R(ANOM_TAU_CO_BASE_S)) * (in->co_ppm - s->co_base);
    }
    co_dev = in->co_ppm - s->co_base;
  }
#endif

  anom_real *f = out->feat;
  f[ANOM_F_BIAS] = R(1);
  f[ANOM_F_DT] = d_t;
  f[ANOM_F_DAH] = d_ah;
  f[ANOM_F_DT_RATE] = t_rate;
  f[ANOM_F_DAH_RATE] = ah_rate;
  f[ANOM_F_DT_SLOW] = s->dt_slow;
  f[ANOM_F_AIR] = air;
  f[ANOM_F_AIR_S1] = air_s1;
  f[ANOM_F_AIR_S2] = air_s2;
  f[ANOM_F_CO] = co_dev;

  // Temperature/humidity steps: suppression and the THERMAL marker.
  anom_real tr = A_FABS(t_rate), ar = A_FABS(ah_rate);
  if (tr > R(ANOM_STEP_T_RATE) || ar > R(ANOM_STEP_AH_RATE)) {
    s->suppress_until_ms = t + (uint32_t)(ANOM_SUPPRESS_S * 1000.0);
    s->suppress_armed = 1;
  }
  uint8_t suppressed = s->suppress_armed && ms_diff(s->suppress_until_ms, t) > 0;
  if (tr > R(ANOM_THERMAL_T_RATE) || ar > R(ANOM_THERMAL_AH_RATE)) {
    s->last_step_ms = t;
    s->step_seen = 1;
  }

  uint8_t ready = ms_diff(t, s->start_t_ms) >= (int32_t)(ANOM_SETTLE_S * 1000.0) &&
                  s->ch[0].sigma_ok && s->ch[1].sigma_ok;

  for (int c = 0; c < ANOM_NCH; c++) {
    anom_channel *ch = &s->ch[c];
    // Channels 0 and 1 follow in->valid (already checked); later ones need their bit.
    if (c > ANOM_LPG && !((in->ch_valid >> c) & 1u)) {
      ch->in_run = 0;
      ch->active = 0;
      ch->above_lead = 0;
      continue;
    }
    // Per-channel start and gap restart. For channels 0 and 1 this always agrees
    // with the detector-wide start above (same samples), so nothing changes there.
    if (ch->started && ms_diff(t, ch->last_ms) > ANOM_GAP_RESET_MS) channel_reset(ch, c);
    anom_real dt_c = R(0);
    if (!ch->started) {
      ch->started = 1;
      ch->start_ms = t;
      ch->base = in->gas_mv[c];
      if (c > ANOM_LPG) {
        // A MEMS channel usually starts minutes after the others (its warm-up), when
        // the temperature and humidity features are no longer zero. Put its baseline
        // where the conditions model says it would be had it been running all along
        // (the reading minus the non-bias part of the prediction), so its residual
        // starts as the Figaro channels' do. Conditions only, never another channel.
        const anom_real *w0 = shared_coef(c);
        anom_real p = R(0);
        for (int i = ANOM_F_BIAS + 1; i < ANOM_NFEAT; i++) p += w0[i] * f[i];
        ch->base -= p;
      }
    } else {
      dt_c = R(ms_diff(t, ch->last_ms)) / R(1000);
      if (dt_c < R(0)) dt_c = R(0);
    }
    ch->last_ms = t;
    // Channels from 2 up start later (MEMS warm-up), so they also settle on their own.
    uint8_t c_ready = ready;
    if (c > ANOM_LPG)
      c_ready = ready && ms_diff(t, ch->start_ms) >= (int32_t)(ANOM_SETTLE_S * 1000.0) && ch->sigma_ok;

    anom_real target = in->gas_mv[c] - ch->base;
    anom_real pred = R(0);
#if ANOM_USE_RLS
    for (int i = 0; i < ANOM_NFEAT; i++) pred += (anom_real)ch->coef[i] * f[i];
#else
    const anom_real *w = shared_coef(c);
    for (int i = 0; i < ANOM_NFEAT; i++) pred += w[i] * f[i];
#endif
    anom_real model_res = target - pred;
    anom_real res = model_res;
    if (ANOM_RES_HP_TAU_S > 0) res = model_res - ch->res_ref;
    anom_real sig = ch->sigma;
    uint8_t exceed = c_ready && res > K_ON[c] * sig;

    if (exceed && !suppressed) {
      if (!ch->in_run) {
        ch->in_run = 1;
        ch->run_start_ms = t;
      }
    } else {
      ch->in_run = 0;
    }
    if (ch->active) {
      if (!(c_ready && res > K_OFF[c] * sig)) ch->active = 0;
    } else if (ch->in_run && ms_diff(t, ch->run_start_ms) >= (int32_t)(SUSTAIN_S[c] * 1000.0)) {
      ch->active = 1;
    }
    uint8_t above = c_ready && res > R(ANOM_K_LEAD) * sig;
    if (above && !ch->above_lead) ch->lead_cross_ms = t;
    ch->above_lead = above;

    // Baseline: frozen while the channel is anomalous, up to FREEZE_MAX_S.
    uint8_t hold = exceed || ch->active || (c_ready && res > K_HOLD[c] * sig);
    uint8_t learn = 1;
    if (!hold) {
      ch->base += alpha(dt_c, R(ANOM_TAU_BASE_S)) * (in->gas_mv[c] - ch->base);
      if (ANOM_RES_HP_TAU_S > 0) ch->res_ref += alpha(dt_c, R(ANOM_RES_HP_TAU_S)) * (model_res - ch->res_ref);
      ch->freeze_s = R(0);
    } else {
      ch->freeze_s += dt_c;
      if (ch->freeze_s > R(ANOM_FREEZE_MAX_S)) {
        ch->base += alpha(dt_c, R(ANOM_TAU_RESUME_S)) * (in->gas_mv[c] - ch->base);
        if (ANOM_RES_HP_TAU_S > 0)
          ch->res_ref += alpha(dt_c, R(ANOM_TAU_RESUME_S)) * (model_res - ch->res_ref);
      } else {
        learn = 0;
      }
    }
    if (learn) ring_push(ch, res);
#if ANOM_USE_RLS
    if (!hold && c_ready) rls_update(ch, f, target, shared_coef(c));
#endif

    out->ch_ready[c] = c_ready;
    out->target_mv[c] = target;
    out->pred_mv[c] = pred;
    out->model_res_mv[c] = model_res;
    out->res_mv[c] = res;
    out->sigma_mv[c] = sig;
    out->exceed[c] = exceed;
    out->anomaly[c] = ch->active;
  }
  if (s->n_valid % ANOM_SIGMA_EVERY == 0) {
    for (int c = 0; c < ANOM_NCH; c++) update_sigma(&s->ch[c], SIGMA_FLOOR[c]);
  }
  out->ready = ready;
  out->suppressed = suppressed;

  // ---- Event: open while either Figaro channel is raised, then fingerprint ----
  uint8_t any_active = s->ch[ANOM_CH4].active || s->ch[ANOM_LPG].active;
  anom_event *ev = &s->ev;
  if (any_active) {
    if (!s->ev_open) {
      s->ev_open = 1;
      memset(ev, 0, sizeof(*ev));
      ev->id = s->next_event_id++;
      uint8_t have_start = 0;
      for (int c = 0; c < ANOM_NCH; c++) {
        s->ev_peak_known[c] = 0;
        s->ev_onset_known[c] = 0;
        if (c <= ANOM_LPG && s->ch[c].active &&
            (!have_start || ms_diff(s->ch[c].run_start_ms, ev->t_start_ms) < 0)) {
          ev->t_start_ms = s->ch[c].run_start_ms;
          have_start = 1;
        }
      }
      s->ev_air_sum = R(0);
      s->ev_air_n = 0;
      s->ev_air_all_low = 1;
      ev->co_peak_ppm = R(0);
    }
    s->ev_last_active_ms = t;
  }
  if (s->ev_open) {
    for (int c = 0; c < ANOM_NCH; c++) {
      // Only samples on which the channel is valid and ready count (for channels 0
      // and 1 that is every sample while an event is open). The first one sets the
      // peak, as the opening sample always has for channels 0 and 1.
      if (!out->ch_ready[c]) continue;
      anom_real r = out->res_mv[c];
      anom_real z = r / out->sigma_mv[c];
      if (!s->ev_peak_known[c]) {
        s->ev_peak_known[c] = 1;
        ev->peak_res_mv[c] = r;
        ev->peak_sigma[c] = z;
        ev->t_peak_ms[c] = t;
      } else {
        if (r > ev->peak_res_mv[c]) {
          ev->peak_res_mv[c] = r;
          ev->t_peak_ms[c] = t;
        }
        if (z > ev->peak_sigma[c]) ev->peak_sigma[c] = z;
      }
      if (s->ch[c].active) ev->detected[c] = 1;
      if (c <= ANOM_LPG && !s->ev_onset_known[c] && s->ch[c].above_lead) {
        s->ev_onset_known[c] = 1;
        s->ev_onset_ms[c] = s->ch[c].lead_cross_ms;
      }
    }
    if (s->step_seen &&
        (int64_t)s->last_step_ms >= (int64_t)ev->t_start_ms - (int64_t)(ANOM_THERMAL_PRE_S * 1000.0) &&
        (int64_t)s->last_step_ms <= (int64_t)ev->t_start_ms + (int64_t)(ANOM_THERMAL_POST_S * 1000.0)) {
      ev->thermal = 1;
    }
    if (air_ok) {
      if (s->ev_air_n == 0 || air < ev->airflow_min) ev->airflow_min = air;
      s->ev_air_sum += air;
      s->ev_air_n++;
      if (!(air < R(ANOM_AIR_LOW_INDEX))) s->ev_air_all_low = 0;
    }
    if (co_ok) {
      if (!ev->co_known || co_dev > ev->co_peak_ppm) ev->co_peak_ppm = co_dev;
      ev->co_known = 1;
    }
    int32_t tail_ms = (int32_t)(ANOM_MERGE_GAP_S * 1000.0);
#if ANOM_USE_CO
    if (tail_ms < (int32_t)(ANOM_CO_TAIL_S * 1000.0)) tail_ms = (int32_t)(ANOM_CO_TAIL_S * 1000.0);
#endif
    if (!any_active && ms_diff(t, s->ev_last_active_ms) >= tail_ms) {
      ev->t_end_ms = s->ev_last_active_ms;
      if (s->ev_onset_known[ANOM_CH4] && s->ev_onset_known[ANOM_LPG]) {
        ev->lead_known = 1;
        ev->lead_s = R((int32_t)(s->ev_onset_ms[ANOM_LPG] - s->ev_onset_ms[ANOM_CH4])) / R(1000);
      }
      if (s->ev_air_n > 0) {
        ev->airflow_known = 1;
        ev->airflow_mean = s->ev_air_sum / R(s->ev_air_n);
        ev->low_airflow = s->ev_air_all_low;
      }
      classify(ev);
      out->event_closed = 1;
      out->event = *ev;
      s->ev_open = 0;
    }
  }
  out->event_open = s->ev_open;
}
