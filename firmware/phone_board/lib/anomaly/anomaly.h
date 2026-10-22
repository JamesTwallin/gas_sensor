// Gas anomaly detector: predict what each gas sensor should read from the
// conditions it is in, and flag and fingerprint departures from that prediction.
//
// Plain C99, no Arduino calls, no dynamic allocation: the same file builds into
// the firmware and into the host parity test (tools/anomaly_host). Python twin:
// tools/anomaly_core.py. Any change to the logic must be made in both, and
// `python tools/replay.py parity` must still pass.
//
// Principles (docs/REPORT.md explains them):
//   - Each gas channel is a target, predicted from conditions only: temperature,
//     absolute humidity, their rates of change, airflow (thermistor) and CO.
//     Never from another gas channel. 2 channels (the Figaros) or 4 (MEMS rig, with the
//     two MEMS sensors), set at compile time by ANOM_NCH.
//   - Detection: a channel's residual (reading minus prediction) above k robust
//     sigma for N seconds. Positive departures only. Never suppressed for being
//     stationary; suppressed briefly after large temperature or humidity steps.
//   - Classification afterwards, from the event fingerprint. Nothing is dismissed
//     because both channels moved together.
//   - Everything is causal: each output depends only on past and present samples.
//
// The conditions model is a linear function of the features below. A larger
// shared model can replace anom_predict() without touching detection or
// classification.

#ifndef ANOMALY_H
#define ANOMALY_H

#include <stdint.h>
#include "anomaly_config.h"

#ifdef __cplusplus
extern "C" {
#endif

// Float on the device; the host parity build uses double so the Python twin can
// be matched exactly.
#ifndef ANOM_REAL
#define ANOM_REAL float
#endif
typedef ANOM_REAL anom_real;

// Channel indices, fixed everywhere (firmware, BLE, app CSV, tools). ANOM_NCH
// (anomaly_config.h) is how many of them this build runs: 2 or 4.
enum { ANOM_CH4 = 0, ANOM_LPG = 1, ANOM_MEMS_A = 2, ANOM_MEMS_B = 3 };
#if ANOM_NCH < 2 || ANOM_NCH > ANOM_MAX_NCH
#error "ANOM_NCH must be between 2 and ANOM_MAX_NCH"
#endif

// Feature indices into the coefficient arrays (anomaly_config.h).
enum {
  ANOM_F_BIAS = 0,
  ANOM_F_DT,        // temperature minus its slow baseline, degC
  ANOM_F_DAH,       // absolute humidity minus its slow baseline, g/m3
  ANOM_F_DT_RATE,   // temperature rate of change over ~10 s, degC/s
  ANOM_F_DAH_RATE,  // absolute humidity rate of change over ~10 s, g/m3/s
  ANOM_F_DT_SLOW,   // dT smoothed (the sensor cans lag the air), degC
  ANOM_F_AIR,       // airflow index
  ANOM_F_AIR_S1,    // airflow index smoothed, short
  ANOM_F_AIR_S2,    // airflow index smoothed, long
  ANOM_F_CO,        // CO minus its slow baseline, ppm
  ANOM_NFEAT
};

typedef enum {
  ANOM_CLASS_NONE = 0,
  ANOM_CLASS_NATURAL_GAS = 1,
  ANOM_CLASS_EXHAUST = 2,
  ANOM_CLASS_HEAVY_HC = 3,
  ANOM_CLASS_THERMAL = 4,
  ANOM_CLASS_LOW_AIRFLOW = 5,
  ANOM_CLASS_UNRESOLVED = 6,
  ANOM_CLASS_UNCLASSIFIED = 7,
} anom_class;

const char *anom_class_name(anom_class c);

typedef struct {
  uint32_t t_ms;             // sample time, ms (monotonic)
  anom_real gas_mv[ANOM_NCH];  // sensor load voltage VRL, mV
  anom_real temp_c;
  anom_real rh_pct;
  anom_real airflow_index;   // from anom_airflow_index(); ignored unless airflow_ok
  anom_real co_ppm;          // ignored unless co_ok
  uint8_t valid;             // heaters on and warm, gas ADC and T/RH readings good
  // Per-channel validity, bit c for channel c. Channels 0 and 1 (the Figaros)
  // follow 'valid' alone, exactly as before, so bits 0 and 1 are ignored. A
  // channel from 2 up is used only when 'valid' and its bit are both set (e.g.
  // MEMS heater on and past warm-up, reading present); an invalid channel is not
  // updated and raises nothing.
  uint8_t ch_valid;
  uint8_t airflow_ok;
  uint8_t co_ok;
} anom_input;

// Fingerprint of one event, complete when the event closes.
typedef struct {
  uint16_t id;
  anom_class cls;
  uint8_t confidence;          // 0-100, heuristic until labelled data exists
  uint32_t t_start_ms;         // first channel onset (channels 0 and 1)
  uint32_t t_end_ms;           // last sample with a channel raised
  anom_real peak_res_mv[ANOM_NCH];
  anom_real peak_sigma[ANOM_NCH];  // peak residual in units of sigma
  uint32_t t_peak_ms[ANOM_NCH];
  uint8_t raised[ANOM_NCH];    // detected, or peak >= K_RAISE sigma
  uint8_t detected[ANOM_NCH];  // passed the full detection rule
  // Peaks of channels 2 and up are taken over the samples of the event on which
  // that channel was valid and ready; all zero if there were none.
  anom_real ratio;             // CH4 peak residual / LPG peak residual (capped 99)
  anom_real lead_s;            // LPG onset minus CH4 onset: > 0 means CH4 led
  uint8_t lead_known;          // both onsets seen
  uint8_t thermal;             // coincided with a temperature/humidity step
  uint8_t airflow_known;
  anom_real airflow_mean;
  anom_real airflow_min;
  uint8_t low_airflow;         // whole event below ANOM_AIR_LOW_INDEX
  uint8_t co_known;
  anom_real co_peak_ppm;       // peak CO rise above its baseline
} anom_event;

typedef struct {
  uint8_t ready;               // baselines settled and sigma trusted (channels 0, 1)
  uint8_t ch_ready[ANOM_NCH];  // per channel; equals ready for channels 0 and 1
  anom_real feat[ANOM_NFEAT];
  anom_real target_mv[ANOM_NCH];  // reading minus its slow baseline
  anom_real pred_mv[ANOM_NCH];
  anom_real model_res_mv[ANOM_NCH];  // target minus prediction
  anom_real res_mv[ANOM_NCH];     // detection residual: model_res, minus its trailing
                                  // average when ANOM_RES_HP_TAU_S > 0
  anom_real sigma_mv[ANOM_NCH];   // robust sigma of res_mv
  uint8_t exceed[ANOM_NCH];    // residual above K_ON sigma on this sample
  uint8_t anomaly[ANOM_NCH];   // channel raised (detection rule met)
  uint8_t suppressed;          // within SUPPRESS_S of a T/RH step
  uint8_t event_open;
  uint8_t event_closed;        // an event finished on this sample: see event
  anom_event event;
} anom_output;

// Per-channel state. Fixed size; sizeof(anom_state) is a few tens of kB at the
// default ANOM_SIGMA_N.
typedef struct {
  uint8_t started;             // seen a valid sample since the last (re)start
  uint32_t start_ms;           // first valid sample of this channel's run
  uint32_t last_ms;            // last valid sample of this channel
  anom_real base;              // slow gas baseline
  anom_real freeze_s;          // how long the baseline has been held
  anom_real res_ref;           // trailing average of the model residual (HP stage)
  anom_real ring[ANOM_SIGMA_N];  // recent residuals for the MAD
  uint16_t ring_head;
  uint16_t ring_count;
  anom_real sigma;
  uint8_t sigma_ok;
  uint32_t run_start_ms;       // start of the current run above K_ON
  uint8_t in_run;
  uint8_t active;
  uint8_t above_lead;          // residual currently above K_LEAD sigma
  uint32_t lead_cross_ms;      // when it last rose above K_LEAD sigma
#if ANOM_USE_RLS
  // Always double: the covariance update with slow forgetting drifts in float.
  double coef[ANOM_NFEAT];
  double P[ANOM_NFEAT][ANOM_NFEAT];
#endif
} anom_channel;

typedef struct {
  uint32_t t_ms;
  anom_real temp_c;
  anom_real ah;
} anom_rate_sample;

typedef struct {
  uint8_t started;
  uint32_t last_t_ms;
  uint32_t start_t_ms;
  uint32_t n_valid;            // valid samples since (re)start
  anom_real t_base, ah_base, dt_slow;
  anom_real air_s1, air_s2;
  uint8_t air_started;
  anom_real co_base;
  uint8_t co_started;
  anom_rate_sample rate_ring[ANOM_RATE_RING];
  uint16_t rate_head, rate_count;
  uint32_t suppress_until_ms;
  uint8_t suppress_armed;
  uint32_t last_step_ms;       // last time a rate passed the THERMAL threshold
  uint8_t step_seen;
  anom_channel ch[ANOM_NCH];
  // Open event and its running fingerprint.
  uint8_t ev_open;
  uint32_t ev_last_active_ms;
  uint16_t next_event_id;
  anom_event ev;
  uint8_t ev_peak_known[ANOM_NCH];  // peak initialised for this event
  uint8_t ev_onset_known[ANOM_NCH];
  uint32_t ev_onset_ms[ANOM_NCH];
  anom_real ev_air_sum;
  uint32_t ev_air_n;
  uint8_t ev_air_all_low;
} anom_state;

// Shared coefficients (from anomaly_config.h), one row per channel in the fixed
// channel order; a 2-channel build uses the first two rows.
extern const anom_real ANOM_COEF[ANOM_MAX_NCH][ANOM_NFEAT];

void anom_init(anom_state *s);
// Process one sample. out is fully written on every call.
void anom_step(anom_state *s, const anom_input *in, anom_output *out);

// Absolute humidity (g/m3) from temperature (degC) and relative humidity (%).
anom_real anom_abs_humidity(anom_real temp_c, anom_real rh_pct);

// Airflow index from a self-heated thermistor (docs/HARDWARE.md):
//   conductance G = P / (T_bead - T_ambient), P = V^2 / R  (mW/K)
//   index = G / G_still - 1   (0 in still air, rising with airflow, King's law)
// Returns 0 and sets *ok = 0 when the reading is unusable.
typedef struct {
  anom_real supply_mv;     // divider supply
  anom_real series_ohm;    // series resistor (supply side)
  anom_real r25_ohm;       // thermistor R at 25 degC
  anom_real beta_k;        // thermistor B value
  anom_real g_still_mw_k;  // still-air conductance from calibration
  anom_real min_rise_k;    // below this rise the index is not trusted
} anom_thermistor;

anom_real anom_thermistor_temp_c(const anom_thermistor *th, anom_real v_mv);
anom_real anom_thermistor_conductance(const anom_thermistor *th, anom_real v_mv,
                                      anom_real ambient_c, uint8_t *ok);
anom_real anom_airflow_index(const anom_thermistor *th, anom_real v_mv,
                             anom_real ambient_c, uint8_t *ok);

#ifdef __cplusplus
}
#endif

#endif  // ANOMALY_H
