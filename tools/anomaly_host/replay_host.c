// Host build of the firmware anomaly detector, for the C-versus-Python parity
// check (`python tools/replay.py parity`). Reads samples from a CSV file and
// writes the detector's outputs, one row per input row, plus one row per closed
// event to a second file.
//
//   replay_host <in.csv> <out.csv> <events.csv>
//
// Input columns (header line required, order fixed):
//   t_ms,ch4_mv,lpg_mv,temp_c,rh_pct,valid,airflow_index,airflow_ok,co_ppm,co_ok
// and, in a build with -DANOM_NCH=4, then:
//   mems_a_mv,mems_a_ok,mems_b_mv,mems_b_ok
//
// Built by tools/replay.py with zig cc (pip install ziglang), in double precision
// (-DANOM_REAL=double -DANOM_REAL_IS_DOUBLE) and in the device's single precision,
// once with -DANOM_NCH=2 and once with -DANOM_NCH=4.

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "anomaly.h"

static anom_state g_state;  // tens of kB: keep it off the stack

static const char *const CH_NAMES[ANOM_MAX_NCH] = {"ch4", "lpg", "mems_a", "mems_b"};

#define NCOL (10 + 2 * (ANOM_NCH - 2))

// "name0_suffix,name1_suffix,..." for every channel, comma-terminated.
static void header_group(FILE *f, const char *suffix) {
  for (int c = 0; c < ANOM_NCH; c++) fprintf(f, "%s_%s,", CH_NAMES[c], suffix);
}

int main(int argc, char **argv) {
  if (argc != 4) {
    fprintf(stderr, "usage: %s in.csv out.csv events.csv\n", argv[0]);
    return 2;
  }
  FILE *fi = fopen(argv[1], "r");
  FILE *fo = fopen(argv[2], "w");
  FILE *fe = fopen(argv[3], "w");
  if (!fi || !fo || !fe) {
    fprintf(stderr, "cannot open files\n");
    return 1;
  }
  char line[1024];
  if (!fgets(line, sizeof(line), fi)) return 1;  // header

  fprintf(fo, "valid,ready,suppressed,event_open,");
  header_group(fo, "target");
  header_group(fo, "pred");
  header_group(fo, "res");
  header_group(fo, "sigma");
  header_group(fo, "anom");
  fprintf(fo, "event_class,event_ratio\n");
  fprintf(fe, "id,class,confidence,t_start_ms,t_end_ms,");
  header_group(fe, "peak_res_mv");
  header_group(fe, "peak_sigma");
  header_group(fe, "t_peak_ms");
  header_group(fe, "raised");
  header_group(fe, "detected");
  fprintf(fe, "ratio,lead_known,lead_s,thermal,airflow_known,"
              "airflow_mean,airflow_min,low_airflow,co_known,co_peak_ppm\n");

  anom_init(&g_state);
  anom_input in;
  anom_output out;
  while (fgets(line, sizeof(line), fi)) {
    double v[NCOL] = {0};
    char *p = line;
    for (int i = 0; i < NCOL; i++) {
      v[i] = strtod(p, &p);
      if (*p == ',') p++;
    }
    memset(&in, 0, sizeof(in));
    in.t_ms = (uint32_t)v[0];
    in.gas_mv[ANOM_CH4] = (anom_real)v[1];
    in.gas_mv[ANOM_LPG] = (anom_real)v[2];
    in.temp_c = (anom_real)v[3];
    in.rh_pct = (anom_real)v[4];
    in.valid = (uint8_t)(v[5] != 0);
    in.airflow_index = (anom_real)v[6];
    in.airflow_ok = (uint8_t)(v[7] != 0);
    in.co_ppm = (anom_real)v[8];
    in.co_ok = (uint8_t)(v[9] != 0);
    for (int c = 2; c < ANOM_NCH; c++) {
      in.gas_mv[c] = (anom_real)v[10 + 2 * (c - 2)];
      if (v[11 + 2 * (c - 2)] != 0) in.ch_valid |= (uint8_t)(1u << c);
    }
    anom_step(&g_state, &in, &out);
    fprintf(fo, "%d,%d,%d,%d,", in.valid, out.ready, out.suppressed, out.event_open);
    for (int c = 0; c < ANOM_NCH; c++) fprintf(fo, "%.17g,", (double)out.target_mv[c]);
    for (int c = 0; c < ANOM_NCH; c++) fprintf(fo, "%.17g,", (double)out.pred_mv[c]);
    for (int c = 0; c < ANOM_NCH; c++) fprintf(fo, "%.17g,", (double)out.res_mv[c]);
    for (int c = 0; c < ANOM_NCH; c++) fprintf(fo, "%.17g,", (double)out.sigma_mv[c]);
    for (int c = 0; c < ANOM_NCH; c++) fprintf(fo, "%d,", out.anomaly[c]);
    fprintf(fo, "%d,%.17g\n", out.event_closed ? (int)out.event.cls : 0,
            out.event_closed ? (double)out.event.ratio : 0.0);
    if (out.event_closed) {
      const anom_event *e = &out.event;
      fprintf(fe, "%u,%s,%u,%lu,%lu,", e->id, anom_class_name(e->cls), e->confidence,
              (unsigned long)e->t_start_ms, (unsigned long)e->t_end_ms);
      for (int c = 0; c < ANOM_NCH; c++) fprintf(fe, "%.17g,", (double)e->peak_res_mv[c]);
      for (int c = 0; c < ANOM_NCH; c++) fprintf(fe, "%.17g,", (double)e->peak_sigma[c]);
      for (int c = 0; c < ANOM_NCH; c++) fprintf(fe, "%lu,", (unsigned long)e->t_peak_ms[c]);
      for (int c = 0; c < ANOM_NCH; c++) fprintf(fe, "%u,", e->raised[c]);
      for (int c = 0; c < ANOM_NCH; c++) fprintf(fe, "%u,", e->detected[c]);
      fprintf(fe, "%.17g,%u,%.17g,%u,%u,%.17g,%.17g,%u,%u,%.17g\n", (double)e->ratio, e->lead_known,
              (double)e->lead_s, e->thermal, e->airflow_known, (double)e->airflow_mean,
              (double)e->airflow_min, e->low_airflow, e->co_known, (double)e->co_peak_ppm);
    }
  }
  fclose(fi);
  fclose(fo);
  fclose(fe);
  return 0;
}
