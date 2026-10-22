"""Does the survey data support rev E's airflow input?

  python tools/airflow_check.py   (from the repository root; a few minutes)

End to end through the real detector (tools/anomaly_core.py): each gas channel is
predicted from conditions only; a plume is a held-out residual above k robust sigma
for N s. Variants:
  base   today's inputs (T, absolute humidity, rates)
  fast   + airflow index from GPS speed, as a fast bead would see it (1 s lag)
  slow   + the same through a cheap, slow bead (8 s lag)
GPS speed stands in for the bead because no bead data exists yet. It is car speed,
not air speed at the device: no wind, no idea of the window or how it was held.
"""
import sys
import time

sys.path.insert(0, "tools")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import anomaly_core as core  # noqa: E402
import replay as rp  # noqa: E402

surveys = rp.load_manifest()
base = rp.config()
N_S = base["ANOM_SUSTAIN_S"]


def speed_index(s, lag_s):
    """King's law: heat loss grows with sqrt(air speed). Index ~ sqrt(U), then the
    bead's own first-order lag."""
    v = rp.gps_speed_kmh(s.df, window_s=3.0)
    v = pd.Series(v).ffill().fillna(0.0).to_numpy()
    u = np.sqrt(np.clip(v / 3.6, 0, None))  # sqrt(m/s)
    t = s.inputs["t_ms"] / 1000.0
    out = np.empty_like(u)
    acc = u[0]
    for i in range(len(u)):
        dt = t[i] - t[i - 1] if i else 0.25
        acc += (1 - np.exp(-max(dt, 0) / lag_s)) * (u[i] - acc)
        out[i] = acc
    return 0.3 * out  # rough BR16 scale; the fit absorbs the scale


def with_air(lag):
    out = []
    for s in surveys:
        s2 = rp.Survey(s.id, s.file, s.mode, s.light, s.notes, s.exclude_utc, s.df, dict(s.inputs),
                       s.leak_utc, s.leak_ms)
        if lag is not None:
            s2.inputs["airflow_index"] = speed_index(s, lag)
            s2.inputs["airflow_ok"] = np.ones(len(s.inputs["t_ms"]), bool)
        out.append(s2)
    return out


def rsd(x):
    x = x[np.isfinite(x)]
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


VARIANTS = {"base": (None, 0), "fast": (1.0, 1), "slow": (8.0, 1)}
K_GRID = (4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0)
summary = []
for name, (lag, use_air) in VARIANTS.items():
    t0 = time.time()
    sv = with_air(lag)
    cfg = rp.cfg_with(base, ANOM_USE_AIRFLOW=use_air)
    designs = {s.id: rp.design(s, cfg) for s in sv}
    coefs = {s.id: rp.fit_coefs([designs[o.id] for o in sv if o.id != s.id], cfg) for s in sv}
    # 1. Held-out fit: model residual before and after the detector's high-pass stage
    for s in sv:
        m = rp.metrics(*designs[s.id], coefs[s.id])
        o, _ = core.replay(s.inputs, rp.no_detect(rp.cfg_with(cfg, coefs[s.id])))
        for k, ch in enumerate(core.CHANNELS):
            r = np.where(o["ready"], o["res"][:, k], np.nan)
            summary.append({"variant": name, "survey": s.id, "mode": s.mode, "channel": ch,
                            "r2_held_out": m[k]["r2"], "model_res_rsd_mv": m[k]["rsd_res"],
                            "detector_res_rsd_mv": rsd(r)})
    # 2. False alarms per hour vs k (held out), and 3. synthetic plumes at that k
    rows = []
    for k in K_GRID:
        ck = rp.cfg_with(cfg, ANOM_K_ON=k, ANOM_K_HOLD=k, ANOM_K_OFF=min(base["ANOM_K_OFF"], k - 1.0))
        ev_n = hrs = 0.0
        for s in sv:
            o, ev = core.replay(s.inputs, rp.cfg_with(ck, coefs[s.id]))
            ev_n += len(s.false_events(ev))
            hrs += rp.ready_hours(o, s.inputs["t_ms"])
        rows.append({"k": k, "fa_per_h": ev_n / hrs, "events": int(ev_n), "hours": hrs})
    fa = pd.DataFrame(rows)
    ok = fa[fa.fa_per_h <= 1.0]
    kbest = float(ok.k.min()) if len(ok) else float("nan")
    ck = rp.cfg_with(cfg, ANOM_K_ON=kbest, ANOM_K_HOLD=kbest, ANOM_K_OFF=min(base["ANOM_K_OFF"], kbest - 1.0))
    det = {}
    for a in (20.0, 30.0, 45.0, 90.0):
        det[a] = rp.synth_rate(sv, ck, coefs, a, 0.3)[0]
    print(f"\n=== {name}: lag {lag} s, use_air {use_air}  ({time.time() - t0:.0f} s)")
    print(fa.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print(f"k for <= 1 FA/h: {kbest:g}; synthetic detection (x=0.3, 10 s): "
          + ", ".join(f"{a:g} mV {d:.0%}" for a, d in det.items()), flush=True)

df = pd.DataFrame(summary)
print("\nHeld-out residual robust SD (mV): model residual / after detector high-pass")
piv = df.pivot_table(index=["survey", "mode", "channel"], columns="variant",
                     values=["model_res_rsd_mv", "detector_res_rsd_mv", "r2_held_out"])
print(piv.round(2).to_string())
df.to_csv(rp.REPORT_DIR / "airflow_check.csv", index=False)

print("\nSynthetic detection at fixed k (same thresholds for every variant):")
for name, (lag, use_air) in {"base": (None, 0), "fast": (1.0, 1), "slow": (8.0, 1)}.items():
    sv = with_air(lag)
    cfg = rp.cfg_with(base, ANOM_USE_AIRFLOW=use_air)
    designs = {s.id: rp.design(s, cfg) for s in sv}
    coefs = {s.id: rp.fit_coefs([designs[o.id] for o in sv if o.id != s.id], cfg) for s in sv}
    for k in (6.0, 7.0, 8.0):
        ck = rp.cfg_with(cfg, ANOM_K_ON=k, ANOM_K_HOLD=k, ANOM_K_OFF=min(base["ANOM_K_OFF"], k - 1.0))
        det = {a: rp.synth_rate(sv, ck, coefs, a, 0.3)[0] for a in (30.0, 45.0, 90.0)}
        det_x9 = rp.synth_rate(sv, ck, coefs, 45.0, 0.9)[0]
        print(f"{name} k={k:g}: " + ", ".join(f"{a:g} mV {d:.0%}" for a, d in det.items())
              + f" | 45 mV at x=0.9 {det_x9:.0%}", flush=True)
