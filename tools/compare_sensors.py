"""Compare the gas channels of rev F logs: the two Figaro sensors and the two MEMS
sensors on the blade, each through its own conditions model and detector.

  python tools/compare_sensors.py FILE.csv [FILE.csv ...]
  python tools/compare_sensors.py --surveys F1 F2          # ids in tools/surveys.json
  python tools/compare_sensors.py --surveys D4 --fake-mems # test aid, see below
  python tools/compare_sensors.py ... --csv [PATH]         # also write a CSV

Input is the app's survey CSV (4 channels: ch4, lpg, mems_a, mems_b). A file listed
in tools/surveys.json gets that entry's exclude_utc and leak_utc windows.

Per channel it reports:
  - clean-air noise after the conditions model: robust SD (scaled MAD) of the
    residual on settled samples outside leak windows (excluded windows are already
    dropped), for the model residual and for the detection residual;
  - temperature and humidity sensitivity: the fitted model's dT and dAH
    coefficients, also in noise units (coefficient / robust SD);
  - airflow sensitivity: slope and partial correlation (controlling for the
    conditions features) of the model residual against the air blade's
    airflow_index column, and the effect of one SD of airflow in noise units;
  - thresholds for matched false-alarm rates: each channel's k (robust sigmas) is
    the smallest on the grid giving at most the target rate of that channel's own
    alarms per clean-air hour, so all channels are compared at the same rate;
  - for each labelled leak pass (leak_utc window) and each event the shipped
    detector closed: peak residual, SNR (peak / clean-air robust SD), and whether
    the channel was raised at each matched rate;
  - response time on leak passes: 10-90 % rise time of the main peak, onset
    relative to the first channel's onset, and cross-correlation lag against CH4;
  - synthetic plumes (replay.py's shape, same size in mV on every channel) at the
    matched rates: detection rate per channel against plume size, with the chance
    rate (the same windows with nothing injected).

The conditions model is fitted on the surveys given (in-sample), each channel on
its own from the conditions features only: no gas channel predicts another and
nothing GPS-derived goes in. GPS is used only to turn times into UTC for display.

--fake-mems is a TEST AID ONLY, for trying this script before any rev F log
exists: it makes up mems_a / mems_b (scaled, lagged, smoothed copies of the CH4 and
LPG readings with noise, a temperature term and an airflow term), a made-up
airflow_index if the log has none, and the warm-up flags. Its numbers say nothing
about real MEMS sensors.

Survey logs and anything derived from them are personal data (GPS tracks): the
optional CSV goes outside the repository (default: a folder in the system temp
directory) and a path inside the repository is refused.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anomaly_core as core  # noqa: E402
import replay as rp  # noqa: E402

FA_TARGETS = (1.0, 0.2)            # false alarms per clean-air hour, per channel
K_GRID = (3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 60.0)
SYNTH_SIZES_MV = (5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 90.0)
MATCH_AFTER_S = 30.0               # a raise this long after a window still counts
PRE_S = 60.0                       # level before a leak window, for rise times
XCORR_MAX_S = 30.0
GRID_S = 0.25
DEFAULT_OUT = Path(tempfile.gettempdir()) / "gas_sensor_compare" / "compare_sensors.csv"


def rsd(x: np.ndarray) -> float:
    """Robust SD: 1.4826 x median absolute deviation."""
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return float("nan")
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


# ---- Loading ----------------------------------------------------------------------------

def fake_mems(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """TEST AID ONLY: add made-up rev F columns to a rev B/E log (see the module
    docstring). Not a model of any real sensor."""
    rng = np.random.default_rng(seed)
    df = df.copy()
    n = len(df)
    t = df["millis_since_boot"].to_numpy(float) / 1000.0
    ch4 = df["ch4_vout_mv"].ffill().bfill().to_numpy(float)
    lpg = df["lpg_vout_mv"].ffill().bfill().to_numpy(float)
    temp = df["temp_c"].ffill().bfill().to_numpy(float)

    def lagged(x, lag_s):
        return np.interp(t - lag_s, t, x)

    def smooth(x, tau_s):
        y = np.empty_like(x)
        y[0] = x[0]
        for i in range(1, len(x)):
            a = 1.0 - math.exp(-max(t[i] - t[i - 1], 0.0) / tau_s)
            y[i] = y[i - 1] + a * (x[i] - y[i - 1])
        return y

    if "airflow_index" in df.columns and np.isfinite(df["airflow_index"].to_numpy(float)).any():
        air = df["airflow_index"].ffill().bfill().to_numpy(float)
    else:
        # A slow random level between still air (0) and brisk flow (~1.5).
        air = np.clip(0.7 + smooth(rng.normal(0.0, 4.0, n), 60.0), 0.0, 1.5)
        df["airflow_index"] = np.round(air, 3)
    t_tc = temp - np.median(temp)
    mems_a = (400.0 + 0.7 * lagged(ch4, 1.0) - 25.0 * smooth(air, 5.0) + 15.0 * t_tc
              + rng.normal(0.0, 1.0, n))
    mems_b = (250.0 + 1.3 * smooth(lagged(lpg, 3.0), 6.0) + 8.0 * smooth(air, 20.0) - 5.0 * t_tc
              + rng.normal(0.0, 0.6, n))
    present = df["ch4_vout_mv"].notna().to_numpy() & df["lpg_vout_mv"].notna().to_numpy()
    df["mems_a_vout_mv"] = np.where(present, np.round(mems_a, 1), np.nan)
    df["mems_b_vout_mv"] = np.where(present, np.round(mems_b, 1), np.nan)
    # Heater on from the first RUNNING row, warm 120 s later (bits 3 and 4).
    run = (df["state"] == "RUNNING").to_numpy()
    t_on = t[np.argmax(run)] if run.any() else t[0]
    df["mems_flags"] = np.where(t >= t_on + 120.0, 0x18, 0x08)
    return df


def load(args) -> list[rp.Survey]:
    manifest = json.loads(rp.MANIFEST.read_text(encoding="utf-8"))["surveys"]
    by_file = {m["file"]: m for m in manifest}
    entries = []
    if args.surveys:
        entries = [m for m in manifest if m["id"] in args.surveys]
        missing = set(args.surveys) - {m["id"] for m in entries}
        if missing:
            sys.exit(f"not in tools/surveys.json: {', '.join(sorted(missing))}")
    for f in args.files:
        path = rp.find_file(f)
        entries.append(by_file.get(path.name, {"id": path.stem, "file": str(path)}))
    if not entries:
        sys.exit("give survey CSV files or --surveys IDS")
    out = []
    for m in entries:
        sv = rp.Survey(**{k: v for k, v in m.items() if not k.startswith("_")})
        sv.df = pd.read_csv(rp.find_file(sv.file))
        if args.fake_mems:
            sv.df = fake_mems(sv.df)
        sv.inputs = rp.to_inputs(sv.df, sv.exclude_utc)
        if core.nch_of(sv.inputs) != core.MAX_NCH:
            sys.exit(f"{sv.id}: no MEMS readings (mems_a_vout_mv / mems_b_vout_mv). "
                     "Use a rev F log, or --fake-mems to try the script.")
        utc = pd.to_datetime(sv.df["utc_iso8601"], errors="coerce")
        t = sv.inputs["t_ms"]
        for a, b in sv.leak_utc:
            w = np.flatnonzero(((utc >= pd.Timestamp(a)) & (utc < pd.Timestamp(b))).to_numpy())
            if len(w):
                sv.leak_ms.append((int(t[w[0]]), int(t[w[-1]]) + 1))
        out.append(sv)
    return out


# ---- Helpers --------------------------------------------------------------------------------

def raises(t: np.ndarray, flag: np.ndarray, merge_ms: float) -> list[tuple[int, int]]:
    """Runs of a channel's anomaly flag, merging runs closer than merge_ms."""
    out: list[list[int]] = []
    edges = np.flatnonzero(np.diff(np.concatenate(([0], flag.astype(np.int8), [0]))))
    for a, b in zip(edges[::2], edges[1::2]):
        ta, tb = int(t[a]), int(t[b - 1])
        if out and ta - out[-1][1] < merge_ms:
            out[-1][1] = tb
        else:
            out.append([ta, tb])
    return [(a, b) for a, b in out]


def hours(t: np.ndarray, mask: np.ndarray) -> float:
    dt = np.diff(t, prepend=t[0]) / 3.6e6
    return float(np.sum(np.where(mask & (dt < 10 / 3600), dt, 0.0)))


def overlaps(a: int, b: int, windows) -> bool:
    return any(a < wb and b >= wa for wa, wb in windows)


def raised_in(t: np.ndarray, flag: np.ndarray, a: int, b: int) -> bool:
    w = (t >= a) & (t <= b + MATCH_AFTER_S * 1000)
    return bool(flag[w].any())


def thresholds(cfg: dict, ks) -> dict:
    """Per-channel K_ON (and K_HOLD with it, K_OFF below it), as replay.py tune does."""
    ks = [k if np.isfinite(k) else 1e12 for k in ks]
    return {"ANOM_K_ON_CH": list(ks) + list(cfg["ANOM_K_ON_CH"][len(ks):]),
            "ANOM_K_HOLD_CH": list(ks) + list(cfg["ANOM_K_HOLD_CH"][len(ks):]),
            "ANOM_K_OFF_CH": [min(cfg["ANOM_K_OFF"], k - 1.0) for k in ks] + list(cfg["ANOM_K_OFF_CH"][len(ks):])}


def first_cross_back(tt: np.ndarray, r: np.ndarray, p: int, level: float, lo: int) -> float:
    """Time at which r last rose through level before index p (searching back to lo)."""
    i = p
    while i > lo and r[i - 1] >= level:
        i -= 1
    return float(tt[i]) if i > lo else float("nan")


def response(t: np.ndarray, res: np.ndarray, a: int, b: int, sd: float) -> dict:
    """Main peak of one channel in window [a, b]: rise time and onset."""
    tt = t / 1000.0
    w = np.flatnonzero((t >= a) & (t <= b) & np.isfinite(res))
    if len(w) == 0:
        return {"rise_10_90_s": np.nan, "onset_s": np.nan}
    p = w[np.argmax(res[w])]
    pre = (t >= a - PRE_S * 1000) & (t < a) & np.isfinite(res)
    base = float(np.median(res[pre])) if pre.any() else 0.0
    amp = float(res[p]) - base
    if not (amp > 3 * sd):
        return {"rise_10_90_s": np.nan, "onset_s": np.nan}
    lo = int(np.searchsorted(t, a - PRE_S * 1000))
    r = np.nan_to_num(res, nan=base)
    t10 = first_cross_back(tt, r, p, base + 0.1 * amp, lo)
    t90 = first_cross_back(tt, r, p, base + 0.9 * amp, lo)
    return {"rise_10_90_s": t90 - t10, "onset_s": t10}


def xcorr_lag(t: np.ndarray, x: np.ndarray, y: np.ndarray, a: int, b: int) -> float:
    """Lag (s) of y behind x that maximises their correlation over [a, b] padded;
    positive means y lags x."""
    t0, t1 = (a / 1000.0) - XCORR_MAX_S, (b / 1000.0) + XCORR_MAX_S
    g = np.arange(t0, t1, GRID_S)
    tt = t / 1000.0
    ok_x, ok_y = np.isfinite(x), np.isfinite(y)
    if ok_x.sum() < 10 or ok_y.sum() < 10:
        return float("nan")
    xi = np.interp(g, tt[ok_x], x[ok_x])
    yi = np.interp(g, tt[ok_y], y[ok_y])
    xi -= xi.mean()
    yi -= yi.mean()
    m = int(XCORR_MAX_S / GRID_S)
    best, best_lag = -np.inf, float("nan")
    for L in range(-m, m + 1):
        if L >= 0:
            c = np.dot(xi[:len(xi) - L], yi[L:])
        else:
            c = np.dot(xi[-L:], yi[:len(yi) + L])
        if c > best:
            best, best_lag = c, L * GRID_S
    return best_lag


# ---- Analysis -------------------------------------------------------------------------------

def analyse(surveys: list[rp.Survey], args) -> dict:
    cfg = rp.config()
    nch = core.MAX_NCH
    names = core.CHANNEL_NAMES[:nch]
    merge_ms = cfg["ANOM_MERGE_GAP_S"] * 1000

    designs = {s.id: rp.design(s, cfg) for s in surveys}
    coef = rp.fit_coefs(list(designs.values()), cfg)
    c_fit = rp.cfg_with(cfg, coef)

    # Detection off: the residuals for noise and sensitivity. Shipped settings:
    # the residuals for peaks and SNR, and the events.
    nd, ship = {}, {}
    for s in surveys:
        nd[s.id] = core.replay(s.inputs, rp.no_detect(c_fit))[0]
        ship[s.id] = core.replay(s.inputs, c_fit)

    # ---- per-channel noise and sensitivities
    chan_rows = []
    feats = [i for i in np.flatnonzero(rp.feature_mask(cfg)) if i != core.F_BIAS]
    sd_res = {}
    for k, ch in enumerate(names):
        mr, dr, air, X = [], [], [], []
        for s in surveys:
            feat, target, settled = designs[s.id]
            sel = settled & np.isfinite(target[:, k])
            fk = rp.chan_feat(feat, k)
            mr.append(target[sel, k] - fk[sel] @ coef[k])
            o = nd[s.id]
            ok = o["ch_ready"][:, k] & ~s.in_leak(s.inputs["t_ms"])
            dr.append(o["res"][ok, k])
            a = s.df["airflow_index"].to_numpy(float) if "airflow_index" in s.df.columns else np.full(len(s.df), np.nan)
            air.append(a[sel])
            X.append(fk[sel][:, feats])
        mr, dr, air, X = np.concatenate(mr), np.concatenate(dr), np.concatenate(air), np.vstack(X)
        sd_m, sd_d = rsd(mr), rsd(dr)
        sd_res[ch] = sd_d
        row = {"channel": ch, "model_res_rsd_mv": sd_m, "det_res_rsd_mv": sd_d,
               "r2": rp.metrics(np.concatenate([designs[s.id][0] for s in surveys]),
                                np.vstack([designs[s.id][1] for s in surveys]),
                                np.concatenate([designs[s.id][2] for s in surveys]), coef)[k]["r2"],
               "dT_mv_per_c": coef[k, core.F_DT], "dAH_mv_per_gm3": coef[k, core.F_DAH],
               "dT_noise_per_c": coef[k, core.F_DT] / sd_m, "dAH_noise_per_gm3": coef[k, core.F_DAH] / sd_m}
        ok = np.isfinite(air) & np.isfinite(mr)
        if ok.sum() > 100 and np.std(air[ok]) > 0:
            A = np.column_stack([np.ones(ok.sum()), air[ok]])
            slope = float(np.linalg.lstsq(A, mr[ok], rcond=None)[0][1])
            # Partial correlation: both residualised on the conditions features.
            Z = np.column_stack([np.ones(ok.sum()), X[ok]])
            ra = air[ok] - Z @ np.linalg.lstsq(Z, air[ok], rcond=None)[0]
            rr = mr[ok] - Z @ np.linalg.lstsq(Z, mr[ok], rcond=None)[0]
            row.update(air_slope_mv_per_index=slope, air_partial_r=float(np.corrcoef(ra, rr)[0, 1]),
                       air_1sd_noise=slope * float(np.std(air[ok])) / sd_m)
        else:
            row.update(air_slope_mv_per_index=np.nan, air_partial_r=np.nan, air_1sd_noise=np.nan)
        chan_rows.append(row)

    # ---- false alarms per channel against k
    sweep = {}   # k -> {survey: anomaly [n, nch]}
    fa_rows = []
    for kv in K_GRID:
        c = rp.cfg_with(c_fit, **thresholds(cfg, [kv] * nch))
        sweep[kv] = {}
        n_fa = np.zeros(nch)
        hrs = np.zeros(nch)
        for s in surveys:
            o, _ = core.replay(s.inputs, c)
            sweep[kv][s.id] = o["anomaly"]
            t = s.inputs["t_ms"]
            clean = ~s.in_leak(t)
            for k in range(nch):
                n_fa[k] += sum(not overlaps(a, b, s.leak_ms) for a, b in raises(t, o["anomaly"][:, k], merge_ms))
                hrs[k] += hours(t, o["ch_ready"][:, k] & clean)
        for k in range(nch):
            fa_rows.append({"k": kv, "channel": names[k], "alarms": int(n_fa[k]), "hours": hrs[k],
                            "fa_per_h": n_fa[k] / hrs[k] if hrs[k] > 0 else np.nan})
        print(f"  k = {kv:g}: " + ", ".join(f"{names[k]} {n_fa[k]:.0f}" for k in range(nch)) + " alarms",
              file=sys.stderr, flush=True)
    fa = pd.DataFrame(fa_rows)
    matched = {}   # target -> [k per channel] (inf: no k on the grid is quiet enough)
    for target in FA_TARGETS:
        ks = []
        for ch in names:
            ok = fa[(fa.channel == ch) & (fa.fa_per_h <= target)].sort_values("k")
            ks.append(float(ok.iloc[0].k) if len(ok) else float("inf"))
        matched[target] = ks
    for row in chan_rows:
        k = names.index(row["channel"])
        for target in FA_TARGETS:
            kk = matched[target][k]
            row[f"k_at_{target:g}_per_h"] = kk
            got = fa[(fa.channel == row["channel"]) & (fa.k == kk)]
            row[f"fa_per_h_at_{target:g}"] = float(got.fa_per_h.iloc[0]) if len(got) else np.nan

    def detected_at(target, s, k, a, b):
        kk = matched[target][k]
        if not np.isfinite(kk):
            return False
        return raised_in(s.inputs["t_ms"], sweep[kk][s.id][:, k], a, b)

    # ---- labelled leak passes and shipped events
    win_rows = []
    for s in surveys:
        t = s.inputs["t_ms"]
        o, events = ship[s.id]
        utc = pd.to_datetime(s.df["utc_iso8601"], errors="coerce")
        items = [("leak", f"leak {i + 1}", a, b, "") for i, (a, b) in enumerate(s.leak_ms)]
        items += [("event", f"event #{e.id}", e.t_start_ms, e.t_end_ms, e.class_name) for e in events]
        for kind, label, a, b, cls in items:
            u = utc.iloc[int(np.clip(np.searchsorted(t, a), 0, len(t) - 1))]
            resp = [response(t, o["res"][:, k], a, b, sd_res[ch]) for k, ch in enumerate(names)]
            onsets = [r["onset_s"] for r in resp]
            first = np.nanmin(onsets) if np.isfinite(onsets).any() else np.nan
            for k, ch in enumerate(names):
                w = (t >= a) & (t <= b) & np.isfinite(o["res"][:, k])
                peak = float(np.max(o["res"][w, k])) if w.any() else np.nan
                row = {"survey": s.id, "kind": kind, "item": label, "utc_start": str(u)[:19], "class": cls,
                       "duration_s": (b - a) / 1000.0, "channel": ch, "peak_res_mv": peak,
                       "snr": peak / sd_res[ch] if sd_res[ch] > 0 else np.nan}
                for target in FA_TARGETS:
                    row[f"detected_at_{target:g}"] = detected_at(target, s, k, a, b)
                if kind == "leak":
                    row["rise_10_90_s"] = resp[k]["rise_10_90_s"]
                    row["onset_vs_first_s"] = onsets[k] - first
                    row["xcorr_lag_vs_ch4_s"] = xcorr_lag(t, o["res"][:, 0], o["res"][:, k], a, b)
                win_rows.append(row)
    wins = pd.DataFrame(win_rows)

    # ---- synthetic plumes at the matched rates
    syn_rows = []
    if not args.no_synth:
        for target in FA_TARGETS:
            c = rp.cfg_with(c_fit, **thresholds(cfg, matched[target]))
            hits = {(a, k): 0 for a in args.sizes for k in range(nch)}
            chance = np.zeros(nch)
            n = 0
            for s in surveys:
                t = s.inputs["t_ms"]
                times = rp.plume_times(s, c, 0.0)
                if len(times) == 0:
                    continue
                o0, _ = core.replay(s.inputs, c)
                n += len(times)
                for k in range(nch):
                    chance[k] += sum(raised_in(t, o0["anomaly"][:, k], t0, t0 + rp.PLUME_EXPOSURE_S * 1000)
                                     for t0 in times)
                for a_mv in args.sizes:
                    o, _ = core.replay(rp.inject(s, times, a_mv, 0.0, amps={ch: a_mv for ch in names}), c)
                    for k in range(nch):
                        hits[(a_mv, k)] += sum(raised_in(t, o["anomaly"][:, k], t0, t0 + rp.PLUME_EXPOSURE_S * 1000)
                                               for t0 in times)
                print(f"  synthetic plumes at {target:g}/h: {s.id} done", file=sys.stderr, flush=True)
            for a_mv in args.sizes:
                for k, ch in enumerate(names):
                    syn_rows.append({"fa_per_h": target, "size_mv": a_mv, "channel": ch,
                                     "k": matched[target][k], "plumes": n,
                                     "detected": hits[(a_mv, k)] / n if n else np.nan,
                                     "chance": chance[k] / n if n else np.nan})
    return {"channels": pd.DataFrame(chan_rows), "fa": fa, "windows": wins, "synth": pd.DataFrame(syn_rows),
            "coef": coef, "hours": {s.id: hours(s.inputs["t_ms"], ship[s.id][0]["ready"]) for s in surveys}}


# ---- Output -----------------------------------------------------------------------------------

def yn(x) -> str:
    return "yes" if x else "no"


def report(res: dict, surveys, args) -> None:
    pd.set_option("display.width", 250)
    ids = ", ".join(s.id for s in surveys)
    print(f"# Sensor comparison: {ids}\n")
    if args.fake_mems:
        print("**TEST DATA: the MEMS channels (and airflow_index, if the log had none) were made up by "
              "--fake-mems. These numbers say nothing about real MEMS sensors.**\n")
    hrs = sum(res["hours"].values())
    print(f"Ready time {hrs:.2f} h. Conditions model fitted on these surveys (in-sample). "
          f"False-alarm rates are per clean-air hour; with {hrs:.1f} h, a rate below "
          f"{1 / max(hrs, 1e-9):.2f}/h means no alarms at all.\n")

    ch = res["channels"].copy()
    print("## Noise, sensitivities and matched thresholds\n")
    cols = {"channel": "channel", "model_res_rsd_mv": "noise model res (mV)", "det_res_rsd_mv": "noise det res (mV)",
            "r2": "model R2", "dT_mv_per_c": "dT (mV/C)", "dT_noise_per_c": "dT (noise/C)",
            "dAH_mv_per_gm3": "dAH (mV per g/m3)", "dAH_noise_per_gm3": "dAH (noise per g/m3)",
            "air_slope_mv_per_index": "airflow slope (mV/index)", "air_partial_r": "airflow partial r",
            "air_1sd_noise": "1 SD airflow (noise)"}
    for t in FA_TARGETS:
        cols[f"k_at_{t:g}_per_h"] = f"k at {t:g}/h"
        cols[f"fa_per_h_at_{t:g}"] = f"actual /h at {t:g}"
    print(ch[list(cols)].rename(columns=cols).to_markdown(index=False, floatfmt=".3g"), "\n")

    w = res["windows"]
    if len(w):
        leaks = w[w.kind == "leak"]
        if len(leaks):
            print("## Labelled leak passes\n")
            c = ["survey", "item", "utc_start", "channel", "peak_res_mv", "snr"] + \
                [f"detected_at_{t:g}" for t in FA_TARGETS] + ["rise_10_90_s", "onset_vs_first_s", "xcorr_lag_vs_ch4_s"]
            d = leaks[c].copy()
            for t in FA_TARGETS:
                d[f"detected_at_{t:g}"] = d[f"detected_at_{t:g}"].map(yn)
            print(d.to_markdown(index=False, floatfmt=".3g"), "\n")
            print("rise: 10-90 % of the main peak; onset: the 10 % point, relative to the first channel; "
                  "xcorr lag: positive means the channel lags CH4.\n")
        evs = w[w.kind == "event"]
        if len(evs):
            print("## Events closed by the shipped detector\n")
            c = ["survey", "item", "utc_start", "class", "channel", "peak_res_mv", "snr"] + \
                [f"detected_at_{t:g}" for t in FA_TARGETS]
            d = evs[c].copy()
            for t in FA_TARGETS:
                d[f"detected_at_{t:g}"] = d[f"detected_at_{t:g}"].map(yn)
            print(d.to_markdown(index=False, floatfmt=".3g"), "\n")
    syn = res["synth"]
    if len(syn):
        print("## Synthetic plumes at matched false-alarm rates\n")
        print(f"Assumed plume shape ({rp.PLUME_EXPOSURE_S:g} s exposure through a {rp.PLUME_TAU_S:g} s "
              "first-order response), the same size in mV on every channel. Real gas gives each channel "
              "a different size: only leak passes measure that.\n")
        for t in FA_TARGETS:
            d = syn[syn.fa_per_h == t]
            piv = d.pivot_table(index="size_mv", columns="channel", values="detected", sort=False)
            chance = d.groupby("channel", sort=False).chance.first()
            piv.loc["chance"] = chance
            print(f"At {t:g} false alarms/h ({int(d.plumes.iloc[0])} plumes per size):\n")
            print(piv.to_markdown(floatfmt=".2f"), "\n")


def write_csv(res: dict, path: Path) -> None:
    path = path.resolve()
    if rp.REPO.resolve() in path.parents:
        sys.exit(f"refusing to write survey-derived data inside the repository: {path}")
    parts = []
    for name in ("channels", "fa", "windows", "synth"):
        d = res[name]
        if len(d):
            d = d.copy()
            d.insert(0, "table", name)
            parts.append(d)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(parts, ignore_index=True).to_csv(path, index=False)
    print(f"Wrote {path}", file=sys.stderr)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="app survey CSVs (rev F)")
    ap.add_argument("--surveys", nargs="*", help="survey ids from tools/surveys.json")
    ap.add_argument("--fake-mems", action="store_true",
                    help="TEST AID: make up MEMS channels from a rev B/E log")
    ap.add_argument("--csv", nargs="?", const=str(DEFAULT_OUT), metavar="PATH",
                    help=f"also write all tables to one CSV (default {DEFAULT_OUT}); never inside the repo")
    ap.add_argument("--no-synth", action="store_true", help="skip the synthetic plumes (faster)")
    ap.add_argument("--sizes", nargs="*", type=float, default=list(SYNTH_SIZES_MV),
                    help="synthetic plume sizes, mV")
    args = ap.parse_args(argv)
    surveys = load(args)
    res = analyse(surveys, args)
    report(res, surveys, args)
    if args.csv:
        write_csv(res, Path(args.csv))


if __name__ == "__main__":
    main()
