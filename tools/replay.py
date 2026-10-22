"""Replay logged surveys through the gas anomaly detector, sample by sample.

The detector logic lives in tools/anomaly_core.py, a statement-for-statement
twin of the firmware's lib/anomaly/anomaly.c; both read their settings from
firmware/phone_board/lib/anomaly/anomaly_config.h.

Subcommands (run from the repository root, in the gas_sensor conda env):

  python tools/replay.py run FILE.csv [--out DIR]
        Replay one app survey CSV; write the per-sample log fields and the event
        fingerprints next to it (or in DIR).
  python tools/replay.py fit [--write-config]
        Fit the linear conditions model for each gas channel on the surveys in
        tools/surveys.json, with leave-one-survey-out testing.
  python tools/replay.py tune [--write-config]
        Choose k (robust sigmas) and N (seconds sustained) for ~1 false alarm/hour.
  python tools/replay.py synth
        Inject synthetic plumes into held-out surveys; detection-rate curves.
  python tools/replay.py parity
        Build the C core for the host and check it matches this Python twin.
  python tools/replay.py report
        Everything above plus plots, written to docs/report/.

Input is the app's survey CSV (docs/phone_board.md, "App CSV"). The gas inputs
are ch4_vout_mv / lpg_vout_mv (the sensor load voltage VRL), and on rev F logs
also mems_a_vout_mv / mems_b_vout_mv (the two MEMS sensors, same definition). A
log with MEMS readings runs 4 channels, any other 2; every subcommand takes both.
Each channel has its own conditions model; no gas channel is an input to
another's. Position, speed and time of day are never model inputs; they are only
used here for reporting (distance for false alarms per km, and labelling drives
and walks).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anomaly_core as core  # noqa: E402

REPO = core.REPO
TOOLS = REPO / "tools"
MANIFEST = TOOLS / "surveys.json"
REPORT_DIR = REPO / "docs" / "report"
DATA_DIRS = (TOOLS / "data", REPO)
CLASS_NAMES = core.CLASS_NAMES


# ---- Loading -------------------------------------------------------------------------

@dataclass
class Survey:
    id: str
    file: str
    mode: str = ""
    light: str = ""
    notes: str = ""
    exclude_utc: list = field(default_factory=list)
    df: pd.DataFrame | None = None
    inputs: dict | None = None
    # Known gas (a confirmed leak) in these UTC windows: kept in the replay, but left
    # out of fitting, of false-alarm counts and of synthetic-plume injection.
    leak_utc: list = field(default_factory=list)
    leak_ms: list = field(default_factory=list)

    def in_leak(self, t_ms: np.ndarray) -> np.ndarray:
        m = np.zeros(len(t_ms), bool)
        for a, b in self.leak_ms:
            m |= (t_ms >= a) & (t_ms < b)
        return m

    def false_events(self, events) -> list:
        """Events that do not overlap a known-leak window."""
        return [e for e in events
                if not any(e.t_start_ms < b and e.t_end_ms >= a for a, b in self.leak_ms)]

    @property
    def hours_valid(self) -> float:
        v = self.inputs["valid"]
        t = self.inputs["t_ms"]
        dt = np.diff(t, prepend=t[0]) / 3.6e6
        return float(np.sum(np.where(v & (dt < 10 / 3600), dt, 0.0)))


def find_file(name: str) -> Path:
    p = Path(name)
    if p.exists():
        return p
    for d in DATA_DIRS:
        if (d / name).exists():
            return d / name
    raise FileNotFoundError(f"{name} not found in tools/data/ or the repository root")


def to_inputs(df: pd.DataFrame, exclude_utc=()) -> dict:
    """App CSV rows -> detector inputs. A row is valid when the app was RUNNING
    (heaters on and warm) and the gas and T/RH readings are present."""
    t = df["millis_since_boot"].to_numpy(np.int64)
    ch4 = df["ch4_vout_mv"].to_numpy(float)
    lpg = df["lpg_vout_mv"].to_numpy(float)
    tc = df["temp_c"].to_numpy(float)
    rh = df["humidity_pct"].to_numpy(float)
    valid = ((df["state"] == "RUNNING").to_numpy()
             & np.isfinite(ch4) & np.isfinite(lpg) & np.isfinite(tc) & np.isfinite(rh)
             & (ch4 > 1) & (lpg > 1))
    if exclude_utc:
        utc = pd.to_datetime(df["utc_iso8601"], errors="coerce")
        for a, b in exclude_utc:
            valid &= ~((utc >= pd.Timestamp(a)) & (utc < pd.Timestamp(b))).to_numpy()
    inp = {"t_ms": t, "ch4_mv": np.nan_to_num(ch4), "lpg_mv": np.nan_to_num(lpg),
           "temp_c": np.nan_to_num(tc), "rh_pct": np.nan_to_num(rh), "valid": valid}
    # Rev F: the MEMS channels, when the log has any reading for them (the app
    # writes the columns blank for boards without the MEMS blade). A MEMS sample is
    # used when the row is valid, the reading is present, and (if the log has
    # mems_flags) the board says the MEMS heater is past its warm-up (bit 4).
    for ch in core.CHANNEL_NAMES[2:]:
        col = f"{ch}_vout_mv"
        if col not in df.columns or not np.isfinite(df[col].to_numpy(float)).any():
            break
        g = df[col].to_numpy(float)
        ok = valid & np.isfinite(g) & (g > 1)
        if "mems_flags" in df.columns:
            fl = df["mems_flags"].to_numpy(float)
            ok &= np.isfinite(fl) & ((np.nan_to_num(fl).astype(np.int64) & 0x10) != 0)
        inp[f"{ch}_mv"] = np.nan_to_num(g)
        inp[f"{ch}_ok"] = ok
    if "mems_a_mv" in inp and "mems_b_mv" not in inp:
        # Both or neither: the detector runs 2 or 4 channels.
        inp["mems_b_mv"] = np.zeros(len(t))
        inp["mems_b_ok"] = np.zeros(len(t), bool)
    # Columns that only newer logs have (thermistor airflow, CO sensor).
    if "airflow_index" in df.columns:
        a = df["airflow_index"].to_numpy(float)
        inp["airflow_index"] = np.nan_to_num(a)
        inp["airflow_ok"] = np.isfinite(a)
    if "co_ppm" in df.columns:
        c = df["co_ppm"].to_numpy(float)
        inp["co_ppm"] = np.nan_to_num(c)
        inp["co_ok"] = np.isfinite(c)
    # A reboot (time going backwards) would confuse the clocks: never seen in the
    # app logs so far, but refuse rather than replay nonsense.
    if np.any(np.diff(t) < 0):
        raise ValueError("millis_since_boot goes backwards (board rebooted): split the file first")
    return inp


def load_manifest(only: list[str] | None = None) -> list[Survey]:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out = []
    for s in m["surveys"]:
        if only and s["id"] not in only:
            continue
        sv = Survey(**{k: v for k, v in s.items() if not k.startswith("_")})
        sv.df = pd.read_csv(find_file(sv.file))
        sv.inputs = to_inputs(sv.df, sv.exclude_utc)
        if sv.leak_utc:
            utc = pd.to_datetime(sv.df["utc_iso8601"], errors="coerce")
            t = sv.inputs["t_ms"]
            for a, b in sv.leak_utc:
                w = np.flatnonzero(((utc >= pd.Timestamp(a)) & (utc < pd.Timestamp(b))).to_numpy())
                if len(w):
                    sv.leak_ms.append((int(t[w[0]]), int(t[w[-1]]) + 1))
        out.append(sv)
    return out


def gps_km(df: pd.DataFrame, mask=None) -> float:
    """Distance travelled (km) from the logged track. Reporting only."""
    lat = df["lat"].to_numpy(float)
    lon = df["lon"].to_numpy(float)
    ok = (df["fix"].to_numpy() == 1) & np.isfinite(lat) & np.isfinite(lon)
    if mask is not None:
        ok &= mask
    lat, lon = lat[ok], lon[ok]
    if len(lat) < 2:
        return 0.0
    x = np.radians(lon) * math.cos(math.radians(float(np.mean(lat)))) * 6371.0
    y = np.radians(lat) * 6371.0
    step = np.hypot(np.diff(x), np.diff(y))
    return float(np.sum(step[step < 0.1]))


def gps_speed_kmh(df: pd.DataFrame, window_s: float = 10.0) -> np.ndarray:
    """Offline speed over a trailing window. Reporting and plots only."""
    t = df["millis_since_boot"].to_numpy(float) / 1000.0
    lat = df["lat"].to_numpy(float)
    lon = df["lon"].to_numpy(float)
    x = np.radians(lon) * math.cos(math.radians(float(np.nanmean(lat)))) * 6371e3
    y = np.radians(lat) * 6371e3
    j = np.searchsorted(t, t - window_s)
    dist = np.hypot(x - x[j], y - y[j])
    dt = t - t[j]
    with np.errstate(invalid="ignore", divide="ignore"):
        v = np.where(dt > window_s / 2, dist / dt * 3.6, np.nan)
    return v


# ---- Config handling -----------------------------------------------------------------

def config(**overrides) -> dict:
    """Settings from anomaly_config.h. A per-channel setting given by its scalar
    name (e.g. ANOM_K_ON=8.0) is set on every channel."""
    cfg = core.load_config()
    for name, val in overrides.items():
        core.set_param(cfg, name, val)
    return cfg


def no_detect(cfg: dict) -> dict:
    """Detection off: baselines never freeze, so features and targets do not
    depend on the coefficients. Used for fitting."""
    c = dict(cfg)
    core.set_param(c, "ANOM_K_ON", 1e12)
    core.set_param(c, "ANOM_K_HOLD", 1e12)
    c["ANOM_K_LEAD"] = 1e12
    return c


def figaro_only(cfg: dict, name: str, value) -> list:
    """A per-channel setting's array with channels 0 and 1 (CH4, LPG) set to value
    and the MEMS entries kept: what `tune --write-config` writes, as the false-alarm
    count it tunes on comes from the Figaro channels' events."""
    arr = list(cfg[name + "_CH"])
    arr[core.CH4] = arr[core.LPG] = value
    return arr


def fmt_coef(w) -> str:
    return "{ " + ", ".join(f"{x:.6g}" if x != 0 else "0.0" for x in w) + " }"


def fmt_num(x: float) -> str:
    s = f"{x:.6g}"
    return s if any(ch in s for ch in ".e") else s + ".0"


def write_config(values: dict) -> None:
    """Rewrite `#define NAME value` lines in anomaly_config.h in place."""
    text = core.CONFIG_H.read_text(encoding="utf-8")
    for name, val in values.items():
        if isinstance(val, (list, tuple, np.ndarray)) and name.startswith("ANOM_COEF_"):
            s = fmt_coef(val)
        elif isinstance(val, (list, tuple, np.ndarray)):
            s = "{ " + ", ".join(fmt_num(float(x)) for x in val) + " }"
        elif isinstance(val, float):
            s = f"{val:.6g}"
            if not any(ch in s for ch in ".e"):
                s += ".0"
        else:
            s = str(val)
        pat = re.compile(rf"^(#define {name}) .*$", re.M)
        if not pat.search(text):
            raise KeyError(name)
        text = pat.sub(lambda m: f"{m.group(1)} {s}", text, count=1)
    core.CONFIG_H.write_text(text, encoding="utf-8")


# ---- Fitting ----------------------------------------------------------------------------

def feature_mask(cfg: dict) -> np.ndarray:
    """Which features the model may use: airflow and CO only when switched on."""
    m = np.ones(core.NFEAT, bool)
    if not cfg["ANOM_USE_AIRFLOW"]:
        m[[core.F_AIR, core.F_AIR_S1, core.F_AIR_S2]] = False
    if not cfg["ANOM_USE_CO"]:
        m[core.F_CO] = False
    return m


def settled_mask(t: np.ndarray, valid: np.ndarray, cfg: dict) -> np.ndarray:
    """Valid samples at least ANOM_SETTLE_S after each (re)start of a run."""
    settled = np.zeros(len(t), bool)
    start = None
    last = None
    for i in np.flatnonzero(valid):
        if last is None or t[i] - last > cfg["ANOM_GAP_RESET_MS"]:
            start = t[i]
        last = t[i]
        settled[i] = t[i] - start >= cfg["ANOM_SETTLE_S"] * 1000
    return settled


def design(survey: Survey, cfg: dict):
    """Features and targets with detection off (the fitting view of a survey).

    target is [n, channels] and feat [n, NFEAT] for a 2-channel survey. Channels
    from 2 up (MEMS) start later and can drop out on their own, so on a 4-channel
    survey their targets are NaN wherever that channel is not valid or has not yet
    settled since its own (re)start, and feat is [n, channels, NFEAT] (see
    chan_feat()): the detector starts a MEMS channel's baseline at the reading
    minus the non-bias prediction w.f0 (anomaly.c). Replayed here with a zero row,
    the baseline starts at the reading, and as the difference then decays as
    exp(-(t' - t0) / tau) (t' the previous sample, as each target uses the baseline
    before its own update), target = w.(f - f0 exp(-(t' - t0) / tau)) for the
    non-bias features: still linear in w, and independent of the coefficients."""
    c = no_detect(cfg)
    nch = core.nch_of(survey.inputs)
    for k in range(core.NCH, nch):
        c[core.COEF_KEYS[k]] = [0.0] * core.NFEAT
    o, _ = core.replay(survey.inputs, c)
    t = survey.inputs["t_ms"]
    # Settled samples only: skip the first ANOM_SETTLE_S after each (re)start.
    settled = settled_mask(t, o["valid"], cfg)
    settled &= ~survey.in_leak(t)
    target, feat = o["target"], o["feat"]
    if nch > core.NCH:
        target = target.copy()
        feat = np.repeat(o["feat"][:, None, :], nch, axis=1)
        tau_ms = cfg["ANOM_TAU_BASE_S"] * 1000.0
        for k in range(core.NCH, nch):
            vk = o["ch_valid"][:, k]
            target[~settled_mask(t, vk, cfg), k] = np.nan
            idx = np.flatnonzero(vk)
            if not len(idx):
                continue
            # The channel's own runs: it restarts after a gap, as in the detector.
            cut = np.flatnonzero(np.diff(t[idx]) > cfg["ANOM_GAP_RESET_MS"]) + 1
            for run in np.split(idx, cut):
                i0 = run[0]
                # A sample's target uses the baseline as the previous sample left it.
                prev = np.concatenate(([t[i0]], t[run[:-1]]))
                decay = np.exp(-(prev - t[i0]) / tau_ms)
                feat[run, k, 1:] -= decay[:, None] * o["feat"][i0, 1:][None, :]
    return feat, target, settled


def chan_feat(feat: np.ndarray, k: int) -> np.ndarray:
    """A design's features for channel k (the same for every channel on a
    2-channel survey)."""
    return feat if feat.ndim == 2 else feat[:, k, :]


def robust_lstsq(X: np.ndarray, y: np.ndarray, iters: int = 20) -> np.ndarray:
    """Huber regression by iteratively reweighted least squares."""
    w = np.ones(len(y))
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    for _ in range(iters):
        r = y - X @ beta
        s = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-9
        c = 1.345 * s
        w = np.where(np.abs(r) <= c, 1.0, c / np.abs(r))
        sw = np.sqrt(w)
        beta_new = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0]
        if np.allclose(beta_new, beta, rtol=1e-6, atol=1e-9):
            beta = beta_new
            break
        beta = beta_new
    return beta


def fit_coefs(designs: list, cfg: dict) -> np.ndarray:
    """Coefficients [channels, NFEAT] fitted on the given (feat, target, settled)
    tuples, one channel at a time from the conditions features only. channels is
    the most any design has (2 or 4); a channel is fitted on the designs that have
    it, and a channel none of them has keeps its row from cfg."""
    mask = feature_mask(cfg)
    nch = max(d[1].shape[1] for d in designs)
    coef = np.zeros((nch, core.NFEAT))
    for k in range(nch):
        ds = [d for d in designs if d[1].shape[1] > k]
        sel = [d[2] & np.isfinite(d[1][:, k]) for d in ds]
        if not ds or sum(int(s.sum()) for s in sel) < core.NFEAT:
            coef[k] = cfg[core.COEF_KEYS[k]]
            continue
        X = np.vstack([chan_feat(d[0], k)[s] for d, s in zip(ds, sel)])
        y = np.concatenate([d[1][s, k] for d, s in zip(ds, sel)])
        coef[k, mask] = robust_lstsq(X[:, mask], y)
    return coef


def metrics(feat, target, settled, coef) -> list[dict]:
    out = []
    for k in range(target.shape[1]):
        sel = settled & np.isfinite(target[:, k])
        y = target[sel, k]
        r = y - chan_feat(feat, k)[sel] @ coef[k]
        var_y = np.var(y)
        out.append({
            "r2": 1 - np.var(r) / var_y if var_y > 0 else float("nan"),
            "sd_target": float(np.std(y)),
            "sd_res": float(np.std(r)),
            "rsd_res": float(1.4826 * np.median(np.abs(r - np.median(r)))),
        })
    return out


def cmd_fit(args) -> dict:
    cfg = config()
    surveys = load_manifest(args.surveys)
    designs = {s.id: design(s, cfg) for s in surveys}
    names = [core.FEATURES[i] for i in np.flatnonzero(feature_mask(cfg))]
    print(f"Features: {', '.join(names)}")
    print("\nLeave-one-survey-out (fit on the others, test on this one):")
    rows = []
    loso_coef = {}
    for s in surveys:
        train = [designs[o.id] for o in surveys if o.id != s.id]
        coef = fit_coefs(train, cfg)
        loso_coef[s.id] = coef
        m_test = metrics(*designs[s.id], coef)
        m_in = metrics(*designs[s.id], fit_coefs([designs[s.id]], cfg))
        for k, ch in enumerate(core.CHANNEL_NAMES[:designs[s.id][1].shape[1]]):
            rows.append({"survey": s.id, "mode": s.mode, "channel": ch,
                         "sd_target_mv": m_test[k]["sd_target"],
                         "r2_held_out": m_test[k]["r2"], "sd_res_held_out_mv": m_test[k]["sd_res"],
                         "robust_sd_held_out_mv": m_test[k]["rsd_res"],
                         "r2_own_fit": m_in[k]["r2"]})
    table = pd.DataFrame(rows)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    coef = fit_coefs(list(designs.values()), cfg)
    print("\nAll surveys pooled:")
    for k, ch in enumerate(core.CHANNEL_NAMES[:len(coef)]):
        print(f"  {ch}: " + ", ".join(f"{core.FEATURES[i]}={coef[k, i]:.4g}"
                                      for i in np.flatnonzero(feature_mask(cfg))))
    if args.write_config:
        # Every channel the surveys have data for (rows 0-1 always, MEMS rows once
        # rev F surveys are in the manifest).
        write_config({core.COEF_KEYS[k]: coef[k] for k in range(len(coef))})
        print(f"\nWrote coefficients to {core.CONFIG_H.relative_to(REPO)}")
    return {"table": table, "coef": coef, "loso_coef": loso_coef, "designs": designs}


# ---- Running ----------------------------------------------------------------------------

def run_survey(inputs: dict, cfg: dict):
    return core.replay(inputs, cfg)


def events_frame(events, survey: Survey | None = None) -> pd.DataFrame:
    rows = [e.as_dict() for e in events]
    df = pd.DataFrame(rows)
    if survey is not None and len(df):
        df.insert(0, "survey", survey.id)
        t = survey.inputs["t_ms"]
        utc = pd.to_datetime(survey.df["utc_iso8601"], errors="coerce")
        idx = np.searchsorted(t, df["t_start_ms"].to_numpy())
        idx = np.clip(idx, 0, len(t) - 1)
        df.insert(1, "utc_start", utc.iloc[idx].to_numpy())
        df["lat"] = survey.df["lat"].to_numpy()[idx]
        df["lon"] = survey.df["lon"].to_numpy()[idx]
        sp = gps_speed_kmh(survey.df)
        df["gps_speed_kmh_report_only"] = sp[idx]
    return df


LOG_FIELDS = ("airflow_raw", "airflow_index", "co_raw", "ch4_res_mv", "lpg_res_mv",
              "ch4_sigma_mv", "lpg_sigma_mv", "anomaly_ch4", "anomaly_lpg",
              "event_class", "event_ratio")
# Rev F (4 channels) adds these after the above, as the app CSV does.
MEMS_LOG_FIELDS = ("mems_a_res_mv", "mems_a_sigma_mv", "mems_b_res_mv", "mems_b_sigma_mv",
                   "anomaly_mems_a", "anomaly_mems_b")


def log_columns(df: pd.DataFrame, o: dict) -> pd.DataFrame:
    """The new per-sample log fields, formatted as the app writes them."""
    v = o["valid"] & o["ready"]
    out = pd.DataFrame(index=df.index)
    out["airflow_raw"] = df["airflow_raw"] if "airflow_raw" in df.columns else ""
    out["airflow_index"] = df["airflow_index"] if "airflow_index" in df.columns else ""
    out["co_raw"] = df["co_raw"] if "co_raw" in df.columns else ""
    for k, ch in enumerate(core.CHANNELS):
        out[f"{ch}_res_mv"] = np.where(v, np.round(o["res"][:, k], 1), np.nan)
        out[f"{ch}_sigma_mv"] = np.where(v, np.round(o["sigma"][:, k], 2), np.nan)
    out["anomaly_ch4"] = o["anomaly"][:, 0].astype(int)
    out["anomaly_lpg"] = o["anomaly"][:, 1].astype(int)
    out["event_class"] = [CLASS_NAMES[c] for c in o["event_class"]]
    out["event_ratio"] = np.where(o["event_class"] > 0, np.round(o["event_ratio"], 2), np.nan)
    nch = o["res"].shape[1]
    for k in range(core.NCH, nch):
        ch = core.CHANNEL_NAMES[k]
        vk = o["ch_ready"][:, k]
        out[f"{ch}_res_mv"] = np.where(vk, np.round(o["res"][:, k], 1), np.nan)
        out[f"{ch}_sigma_mv"] = np.where(vk, np.round(o["sigma"][:, k], 2), np.nan)
    for k in range(core.NCH, nch):
        out[f"anomaly_{core.CHANNEL_NAMES[k]}"] = o["anomaly"][:, k].astype(int)
    return out


def cmd_run(args) -> None:
    cfg = config()
    path = find_file(args.file)
    df = pd.read_csv(path)
    inputs = to_inputs(df)
    o, events = run_survey(inputs, cfg)
    out_dir = Path(args.out) if args.out else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    pd.concat([df, log_columns(df, o)], axis=1).to_csv(out_dir / f"{stem}_replay.csv", index=False)
    sv = Survey(id=stem, file=str(path), df=df, inputs=inputs)
    events_frame(events, sv).to_csv(out_dir / f"{stem}_events.csv", index=False)
    print(f"{len(events)} events; wrote {stem}_replay.csv and {stem}_events.csv to {out_dir}")


# ---- Tuning for a false-alarm target -------------------------------------------------------

TAU_GRID = (60.0, 120.0, 300.0)
K_GRID = (4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0)
N_GRID = (1.0, 2.0, 4.0, 8.0)
TARGET_FA_PER_H = 1.0


def cfg_with(base: dict, coef: np.ndarray | None = None, **kw) -> dict:
    """A copy of base with coefficient rows (one per channel given) and settings
    replaced. A per-channel setting given by its scalar name is set on every
    channel; pass NAME_CH=[...] to set channels separately."""
    c = dict(base)
    if coef is not None:
        for k in range(len(coef)):
            c[core.COEF_KEYS[k]] = list(coef[k])
    for name, val in kw.items():
        core.set_param(c, name, val)
    return c


def loso_coefs(surveys: list[Survey], cfg: dict) -> dict:
    designs = {s.id: design(s, cfg) for s in surveys}
    return {s.id: fit_coefs([designs[o.id] for o in surveys if o.id != s.id], cfg) for s in surveys}


def ready_hours(o: dict, t: np.ndarray) -> float:
    dt = np.diff(t, prepend=t[0]) / 3.6e6
    return float(np.sum(np.where(o["ready"] & (dt < 10 / 3600), dt, 0.0)))


def ready_km(s: Survey, o: dict) -> float:
    return gps_km(s.df, o["ready"])


def false_alarm_scan(surveys, base_cfg, taus=TAU_GRID, ks=K_GRID, ns=N_GRID):
    """Every survey is held out in turn (model fitted on the others). With no known
    leak in any survey, every event counts as a false alarm -- which is an upper
    bound: some of them may be real."""
    rows = []
    coefs = {}
    for tau in taus:
        cfg_tau = cfg_with(base_cfg, ANOM_TAU_BASE_S=tau)
        coefs[tau] = loso_coefs(surveys, cfg_tau)
        for k in ks:
            for n in ns:
                for s in surveys:
                    c = cfg_with(cfg_tau, coefs[tau][s.id], ANOM_K_ON=k, ANOM_SUSTAIN_S=n,
                                 ANOM_K_OFF=min(base_cfg["ANOM_K_OFF"], k - 1.0))
                    o, ev = core.replay(s.inputs, c)
                    rows.append({"tau": tau, "k": k, "n": n, "survey": s.id, "mode": s.mode,
                                 "events": len(s.false_events(ev)), "hours": ready_hours(o, s.inputs["t_ms"]),
                                 "km": ready_km(s, o)})
    return pd.DataFrame(rows), coefs


def pooled(scan: pd.DataFrame) -> pd.DataFrame:
    g = scan.groupby(["tau", "k", "n"]).agg(events=("events", "sum"), hours=("hours", "sum"),
                                              km=("km", "sum")).reset_index()
    g["fa_per_h"] = g["events"] / g["hours"]
    g["fa_per_km"] = g["events"] / g["km"]
    return g


# ---- Synthetic plumes -----------------------------------------------------------------------

PLUME_SIZES_MV = (10.0, 20.0, 30.0, 45.0, 60.0, 90.0, 135.0)
PLUME_X = (0.1, 0.3, 0.6, 0.9, 2.0)  # 2.0: LPG-led, like the 11 Oct 2026 leak (0.26-0.58 CH4:LPG)
PLUME_EXPOSURE_S = 10.0   # ASSUMED: gas present for 10 s
PLUME_TAU_S = 4.0         # ASSUMED: first-order sensor response, both channels
PLUME_SPACING_S = 240.0
PLUME_MATCH_S = 30.0      # an event starting within this of the plume's end counts


def plume_shape(t_rel_s: np.ndarray, exposure_s: float = PLUME_EXPOSURE_S) -> np.ndarray:
    """Top-hat exposure through a first-order sensor, normalised to a peak of 1.
    The shape is assumed, not measured."""
    d, tau = exposure_s, PLUME_TAU_S
    y = np.where(t_rel_s < 0, 0.0,
                 np.where(t_rel_s < d, 1 - np.exp(-t_rel_s / tau),
                          (1 - np.exp(-d / tau)) * np.exp(-(t_rel_s - d) / tau)))
    return y / (1 - math.exp(-d / tau))


def plume_times(s: Survey, cfg: dict, offset_s: float = 0.0, exposure_s: float = PLUME_EXPOSURE_S) -> np.ndarray:
    """Injection start times (ms) in settled, valid stretches of a survey."""
    t = s.inputs["t_ms"]
    v = s.inputs["valid"]
    settle_ms = (cfg["ANOM_SETTLE_S"] + cfg["ANOM_SIGMA_N"] / 4 / 2) * 1000
    out = []
    i0 = None
    starts = []
    for i in range(len(t)):
        if v[i] and (i0 is None or t[i] - t[i - 1] > cfg["ANOM_GAP_RESET_MS"] or not v[i - 1]):
            i0 = i
            starts.append(t[i])
    # Segment starts and ends.
    seg = []
    cur = None
    for i in range(len(t)):
        if v[i]:
            if cur is None or t[i] - t[cur[1]] > cfg["ANOM_GAP_RESET_MS"]:
                if cur is not None:
                    seg.append(cur)
                cur = [i, i]
            else:
                cur[1] = i
    if cur is not None:
        seg.append(cur)
    for a, b in seg:
        t0 = t[a] + settle_ms + offset_s * 1000
        while t0 + (exposure_s + 60) * 1000 < t[b]:
            if not any(t0 < lb + 60_000 and t0 + (exposure_s + 60) * 1000 > la for la, lb in s.leak_ms):
                out.append(t0)
            t0 += PLUME_SPACING_S * 1000
    return np.array(out, dtype=np.int64)


def inject(s: Survey, times_ms: np.ndarray, a_mv: float, x: float,
           exposure_s: float = PLUME_EXPOSURE_S, amps: dict | None = None) -> dict:
    """Add plumes: a_mv to CH4 and x * a_mv to LPG, or, with amps, the given size
    (mV) to each named channel instead (e.g. {"ch4": 30, "mems_a": 30})."""
    inp = dict(s.inputs)
    t = inp["t_ms"]
    add = np.zeros(len(t))
    for t0 in times_ms:
        lo, hi = np.searchsorted(t, [t0, t0 + (exposure_s + 10 * PLUME_TAU_S) * 1000])
        add[lo:hi] += plume_shape((t[lo:hi] - t0) / 1000.0, exposure_s)
    if amps is None:
        amps = {"ch4": a_mv, "lpg": x * a_mv}
    for ch, a in amps.items():
        inp[f"{ch}_mv"] = inp[f"{ch}_mv"] + a * add
    return inp


def matched(times_ms: np.ndarray, starts_ms: np.ndarray, ends_ms: np.ndarray,
            exposure_s: float = PLUME_EXPOSURE_S) -> np.ndarray:
    """Which plumes have an event overlapping their window."""
    hit = np.zeros(len(times_ms), bool)
    for i, t0 in enumerate(times_ms):
        w_end = t0 + (exposure_s + PLUME_MATCH_S) * 1000
        hit[i] = bool(np.any((starts_ms <= w_end) & (ends_ms >= t0)))
    return hit


def event_bounds(events) -> tuple[np.ndarray, np.ndarray]:
    return (np.array([e.t_start_ms for e in events], np.int64),
            np.array([e.t_end_ms for e in events], np.int64))


def synth_rate(surveys, cfg, coefs, a_mv, x, offsets=(0.0, 120.0), exposure_s=PLUME_EXPOSURE_S):
    """Detection rate for plumes of size a_mv (CH4) and x*a_mv (LPG) injected into
    held-out surveys, with the model fitted without the survey. Also returns the
    chance rate: the same windows matched against events with nothing injected."""
    hits = n = chance = 0
    for s in surveys:
        c = cfg_with(cfg, coefs[s.id])
        _, ev0 = core.replay(s.inputs, c)
        s0, e0 = event_bounds(ev0)
        for off in offsets:
            times = plume_times(s, c, off, exposure_s)
            if len(times) == 0:
                continue
            _, ev = core.replay(inject(s, times, a_mv, x, exposure_s), c)
            st, en = event_bounds(ev)
            hits += int(matched(times, st, en, exposure_s).sum())
            chance += int(matched(times, s0, e0, exposure_s).sum())
            n += len(times)
    return hits / max(n, 1), chance / max(n, 1), n


# Reference only (report, never firmware): detection on CH4 minus beta x LPG.

def causal_mad_detect(t, r, valid, cfg, k, n_s):
    """The detector's sigma/sustain rules on a single residual series."""
    N = cfg["ANOM_SIGMA_N"]
    ring = np.zeros(N)
    head = count = 0
    sigma = 0.0
    sig_ok = False
    in_run = active = False
    run_start = 0
    freeze = 0.0
    last_t = None
    start_t = None
    nval = 0
    ev_s, ev_e = [], []
    open_ev = False
    last_active = 0
    for i in range(len(t)):
        if not valid[i]:
            continue
        ti = int(t[i])
        if last_t is None or ti - last_t > cfg["ANOM_GAP_RESET_MS"]:
            ring[:] = 0
            head = count = 0
            sigma, sig_ok, in_run, active, freeze = 0.0, False, False, False, 0.0
            start_t = ti
            nval = 0
            open_ev = False
            dt = 0.0
        else:
            dt = (ti - last_t) / 1000.0
        last_t = ti
        nval += 1
        ready = ti - start_t >= cfg["ANOM_SETTLE_S"] * 1000 and sig_ok
        x = r[i]
        exceed = ready and x > k * sigma
        if exceed:
            if not in_run:
                in_run, run_start = True, ti
        else:
            in_run = False
        if active:
            if not (ready and x > min(cfg["ANOM_K_OFF"], k - 1) * sigma):
                active = False
        elif in_run and ti - run_start >= n_s * 1000:
            active = True
        hold = exceed or active
        learn = True
        if hold:
            freeze += dt
            learn = freeze > cfg["ANOM_FREEZE_MAX_S"]
        else:
            freeze = 0.0
        if learn:
            ring[head] = x
            head = (head + 1) % N
            count = min(count + 1, N)
        if nval % cfg["ANOM_SIGMA_EVERY"] == 0 and count >= cfg["ANOM_SIGMA_MIN_N"]:
            v = ring[:count]
            med = np.partition(v, count // 2)[count // 2]
            mad = np.partition(np.abs(v - med), count // 2)[count // 2]
            sigma = max(MAD_SCALE * mad, cfg["ANOM_SIGMA_FLOOR_MV"])
            sig_ok = True
        if active:
            if not open_ev:
                open_ev = True
                ev_s.append(run_start)
            last_active = ti
        elif open_ev and ti - last_active >= cfg["ANOM_MERGE_GAP_S"] * 1000:
            open_ev = False
            ev_e.append(last_active)
    if open_ev:
        ev_e.append(last_active)
    return np.array(ev_s, np.int64), np.array(ev_e, np.int64)


MAD_SCALE = core.MAD_SCALE


def subtraction_series(s: Survey, cfg: dict, beta: float) -> np.ndarray:
    _, y, _ = design(s, cfg)
    return y[:, 0] - beta * y[:, 1]


def fit_beta(surveys: list[Survey], cfg: dict) -> float:
    ys = [design(s, cfg) for s in surveys]
    y4 = np.concatenate([y[st, 0] for _, y, st in ys])
    yl = np.concatenate([y[st, 1] for _, y, st in ys])
    return float(robust_lstsq(yl[:, None], y4)[0])


def targets_for(inputs: dict, cfg: dict) -> np.ndarray:
    """Gas targets (reading minus slow baseline) with detection off."""
    o, _ = core.replay(inputs, no_detect(cfg))
    return o["target"]


def tune_subtraction(surveys, cfg, betas, ks=(4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0, 20.0)):
    """Threshold for the CH4 - beta x LPG reference that gives <= 1 false alarm/hour."""
    best = None
    for k in ks:
        ev = hrs = 0.0
        for s in surveys:
            y = targets_for(s.inputs, cfg)
            st, _ = causal_mad_detect(s.inputs["t_ms"], y[:, 0] - betas[s.id] * y[:, 1], s.inputs["valid"],
                                      cfg, k, cfg["ANOM_SUSTAIN_S"])
            o, _ = core.replay(s.inputs, no_detect(cfg))
            ev += len(st)
            hrs += ready_hours(o, s.inputs["t_ms"])
        if ev / hrs <= TARGET_FA_PER_H:
            best = (k, ev / hrs)
            break
    return best


def synth_subtraction_rate(surveys, cfg, betas, k, a_mv, x, exposure_s, offsets=(0.0, 120.0)):
    hits = n = 0
    for s in surveys:
        for off in offsets:
            times = plume_times(s, cfg, off, exposure_s)
            if len(times) == 0:
                continue
            inp = inject(s, times, a_mv, x, exposure_s)
            y = targets_for(inp, cfg)
            st, en = causal_mad_detect(inp["t_ms"], y[:, 0] - betas[s.id] * y[:, 1], inp["valid"], cfg, k,
                                       cfg["ANOM_SUSTAIN_S"])
            hits += int(matched(times, st, en, exposure_s).sum())
            n += len(times)
    return hits / max(n, 1), n


def cmd_tune(args) -> dict:
    surveys = load_manifest(args.surveys)
    base = config()
    tau = base["ANOM_TAU_BASE_S"]
    hold_follows_k = base["ANOM_K_HOLD"] == base["ANOM_K_ON"]
    coefs = loso_coefs(surveys, base)
    rows = []
    for k in K_GRID:
        for n in N_GRID:
            c0 = cfg_with(base, ANOM_K_ON=k, ANOM_SUSTAIN_S=n, ANOM_K_OFF=min(base["ANOM_K_OFF"], k - 1.0),
                          ANOM_K_HOLD=k if hold_follows_k else min(base["ANOM_K_HOLD"], k))
            for s in surveys:
                o, ev = core.replay(s.inputs, cfg_with(c0, coefs[s.id]))
                rows.append({"k": k, "n": n, "survey": s.id, "mode": s.mode, "events": len(s.false_events(ev)),
                             "hours": ready_hours(o, s.inputs["t_ms"]), "km": ready_km(s, o)})
    scan = pd.DataFrame(rows)
    p = scan.groupby(["k", "n"]).agg(events=("events", "sum"), hours=("hours", "sum"), km=("km", "sum")).reset_index()
    p["fa_per_h"] = p.events / p.hours
    p["fa_per_km"] = p.events / p.km
    print(f"Held-out false alarms per hour (tau {tau:g} s, high-pass {base['ANOM_RES_HP_TAU_S']:g} s):")
    print(p.pivot_table(index="n", columns="k", values="fa_per_h").round(2).to_string())
    choice = None
    for n in N_GRID:
        ok = p[(p.n == n) & (p.fa_per_h <= TARGET_FA_PER_H)].sort_values("k")
        if ok.empty:
            continue
        k = float(ok.iloc[0].k)
        c = cfg_with(base, ANOM_K_ON=k, ANOM_SUSTAIN_S=n, ANOM_K_OFF=min(base["ANOM_K_OFF"], k - 1.0),
                     ANOM_K_HOLD=k if hold_follows_k else min(base["ANOM_K_HOLD"], k))
        det = synth_rate(surveys, c, coefs, 45.0, 0.3)[0]
        print(f"  N = {n:g} s: smallest k at <= {TARGET_FA_PER_H:g}/h is {k:g} "
              f"({ok.iloc[0].fa_per_h:.2f}/h); 45 mV synthetic plume detection {det:.0%}")
        if choice is None or det > choice[2]:
            choice = (k, n, det)
    if choice and args.write_config:
        k, n, _ = choice
        vals = {"ANOM_K_ON_CH": figaro_only(base, "ANOM_K_ON", k),
                "ANOM_SUSTAIN_S_CH": figaro_only(base, "ANOM_SUSTAIN_S", n),
                "ANOM_K_OFF_CH": figaro_only(base, "ANOM_K_OFF", min(base["ANOM_K_OFF"], k - 1.0))}
        if hold_follows_k:
            vals["ANOM_K_HOLD_CH"] = figaro_only(base, "ANOM_K_HOLD", k)
        write_config(vals)
        print(f"Wrote k = {k:g}, N = {n:g} s (CH4 and LPG entries) to {core.CONFIG_H.relative_to(REPO)}")
    return {"scan": scan, "pooled": p, "choice": choice}


def cmd_synth(args) -> pd.DataFrame:
    surveys = load_manifest(args.surveys)
    cfg = config()
    coefs = loso_coefs(surveys, cfg)
    designs = {s.id: design(s, cfg) for s in surveys}
    betas = {}
    for s in surveys:
        tr = [designs[o.id] for o in surveys if o.id != s.id]
        y4 = np.concatenate([d[1][d[2], 0] for d in tr])
        yl = np.concatenate([d[1][d[2], 1] for d in tr])
        betas[s.id] = float(robust_lstsq(yl[:, None], y4)[0])
    sub = tune_subtraction(surveys, cfg, betas)
    print(f"Subtraction reference: beta (LOSO) {', '.join(f'{k} {v:.2f}' for k, v in betas.items())}; "
          f"k for <= 1/h: {sub[0] if sub else 'none'}")
    rows = []
    for exposure in (10.0, 60.0):
        for x in PLUME_X:
            for a in PLUME_SIZES_MV:
                det, chance, n = synth_rate(surveys, cfg, coefs, a, x, exposure_s=exposure)
                sdet = synth_subtraction_rate(surveys, cfg, betas, sub[0], a, x, exposure)[0] if sub else float("nan")
                rows.append({"exposure_s": exposure, "x": x, "a_mv": a, "plumes": n, "detected": det,
                             "chance": chance, "subtraction_detected": sdet})
                print(f"  exposure {exposure:g} s, x {x}, A {a:g} mV: {det:.0%} (subtraction {sdet:.0%}), n={n}",
                      flush=True)
    df = pd.DataFrame(rows)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(REPORT_DIR / "synthetic.csv", index=False)
    return df


# ---- Report: plots and tables -----------------------------------------------------------

INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
C_CH4 = "#2a78d6"
C_LPG = "#eb6834"
C_MEMS_A = "#1baf7a"
C_MEMS_B = "#8a5cc2"
CH_COLOURS = (C_CH4, C_LPG, C_MEMS_A, C_MEMS_B)
CH_LABELS = ("CH4", "LPG", "MEMS A", "MEMS B")
C_X = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")


def _style(ax):
    ax.grid(True, color=GRID, lw=0.6)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.yaxis.label.set_color(INK2)


def plot_survey(s: Survey, o: dict, events, cfg, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = s.inputs["t_ms"]
    tm = (t - t[0]) / 60000.0
    v = s.inputs["valid"]
    r = o["ready"]
    nan = lambda a, m: np.where(m, a, np.nan)  # noqa: E731
    nch = o["res"].shape[1]
    fig, axes = plt.subplots(4 + nch, 1, figsize=(11, 12 + 2 * (nch - 2)), sharex=True,
                             gridspec_kw={"height_ratios": [1.2, 0.8, 0.8] + [1.2] * nch + [1.4]})
    ax = axes[0]
    for k in range(nch):
        vk = v if k < core.NCH else s.inputs[f"{core.CHANNEL_NAMES[k]}_ok"]
        ax.plot(tm, nan(s.inputs[f"{core.CHANNEL_NAMES[k]}_mv"], vk), color=CH_COLOURS[k], lw=0.8,
                label=f"{CH_LABELS[k]} sensor")
    ax.set_ylabel("load voltage, mV")
    ax.legend(loc="upper right", fontsize=8, frameon=False)
    ax.set_title(f"{s.id} ({s.mode}, {s.light}) - {s.file}", loc="left", fontsize=10, color=INK)
    axes[1].plot(tm, nan(s.inputs["temp_c"], v), color=INK2, lw=0.8)
    axes[1].set_ylabel("temperature, °C")
    ah = np.array([core.abs_humidity(a, b) for a, b in zip(s.inputs["temp_c"], s.inputs["rh_pct"])])
    axes[2].plot(tm, nan(ah, v), color=INK2, lw=0.8)
    axes[2].set_ylabel("abs. humidity, g/m³")
    for k in range(nch):
        ch, col, ax = CH_LABELS[k], CH_COLOURS[k], axes[3 + k]
        ax.plot(tm, nan(o["target"][:, k], v), color=col, lw=0.8, label=f"{ch} reading minus slow baseline")
        ax.plot(tm, nan(o["pred"][:, k], v), color=INK, lw=0.8, alpha=0.75, label="expected from conditions")
        ax.set_ylabel(f"{ch}, mV")
        ax.legend(loc="upper right", fontsize=8, frameon=False)
    ax = axes[3 + nch]
    with np.errstate(invalid="ignore", divide="ignore"):
        z = o["res"] / np.where(o["sigma"] > 0, o["sigma"], np.nan)
    for k in range(nch):
        rk = r if k < core.NCH else o["ch_ready"][:, k]
        ax.plot(tm, nan(z[:, k], rk), color=CH_COLOURS[k], lw=0.7, label=CH_LABELS[k])
    ax.axhline(cfg["ANOM_K_ON"], color=INK2, lw=0.8, ls="--")
    ax.text(tm[-1], cfg["ANOM_K_ON"], f" k = {cfg['ANOM_K_ON']:g}", va="bottom", ha="right", fontsize=8, color=INK2)
    ax.set_ylabel("residual / sigma")
    ax.set_ylim(-8, max(4 * cfg["ANOM_K_ON"], 10))
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    for e in events:
        a = (e.t_start_ms - t[0]) / 60000.0
        b = (e.t_end_ms - t[0]) / 60000.0
        for axx in axes:
            axx.axvspan(a, max(b, a + 0.05), color="#c3c2b7", alpha=0.35, lw=0)
        ax.text(a, ax.get_ylim()[1], f"#{e.id} {e.class_name}", rotation=90, va="top", ha="right",
                fontsize=7, color=INK)
    ex = ~v
    if ex.any():
        for axx in axes:
            axx.fill_between(tm, 0, 1, where=ex, transform=axx.get_xaxis_transform(), color="#f0efec", lw=0)
    axes[-1].set_xlabel("minutes from start of file")
    for axx in axes:
        _style(axx)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_synth(df: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True, sharey=True)
    for i, exposure in enumerate((10.0, 60.0)):
        for j, (col, title) in enumerate((("detected", "independent per-channel detection (firmware)"),
                                          ("subtraction_detected", "CH4 minus LPG subtraction (reference only)"))):
            ax = axes[i, j]
            for xi, x in enumerate(PLUME_X):
                d = df[(df.exposure_s == exposure) & (df.x == x)]
                ax.plot(d.a_mv, d[col], color=C_X[xi], lw=2, marker="o", ms=4, label=f"LPG gets {x:g} × A")
                if j == 1:  # the left-hand curves converge; the legend names them
                    ax.text(d.a_mv.iloc[-1] * 1.03, d[col].iloc[-1], f"{x:g}", color=INK2, fontsize=8, va="center")
            ax.set_title(f"{title}\nassumed plume: {exposure:g} s exposure", fontsize=9, color=INK, loc="left")
            ax.set_ylim(-0.03, 1.03)
            _style(ax)
            if j == 0:
                ax.set_ylabel("fraction of plumes detected")
            if i == 1:
                ax.set_xlabel("CH4 plume size A, mV")
    axes[0, 0].legend(fontsize=8, frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def cmd_report(args) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    surveys = load_manifest(args.surveys)
    cfg = config()
    lines = ["# Generated by `python tools/replay.py report`. Do not edit by hand.\n"]
    # Fit metrics.
    fit = cmd_fit(argparse.Namespace(surveys=args.surveys, write_config=False))
    lines += ["## Conditions model, leave-one-survey-out\n", fit["table"].to_markdown(index=False, floatfmt=".3f"), ""]
    coef = fit["coef"]
    ct = pd.DataFrame(coef[:, feature_mask(cfg)], index=list(CH_LABELS[:len(coef)]),
                      columns=[core.FEATURES[i] for i in np.flatnonzero(feature_mask(cfg))])
    lines += ["## Coefficients (all surveys pooled)\n", ct.to_markdown(floatfmt=".4g"), ""]
    # Per survey replay with the shipped config (LOSO coefficients, so each survey is unseen).
    coefs = fit["loso_coef"]
    fa_rows, ev_rows = [], []
    for s in surveys:
        c = cfg_with(cfg, coefs[s.id])
        o, ev = core.replay(s.inputs, c)
        hrs, km = ready_hours(o, s.inputs["t_ms"]), ready_km(s, o)
        n_fa = len(s.false_events(ev))
        row = {"survey": s.id, "mode": s.mode, "hours_ready": hrs, "km_ready": km, "events": n_fa,
               "leak_events": len(ev) - n_fa,
               "per_hour": n_fa / hrs if hrs else float("nan"),
               "per_km": n_fa / km if km else float("nan"),
               "ch4_sigma_median_mv": float(np.nanmedian(np.where(o["ready"], o["sigma"][:, 0], np.nan))),
               "lpg_sigma_median_mv": float(np.nanmedian(np.where(o["ready"], o["sigma"][:, 1], np.nan))),
               "suppressed_fraction": float(o["suppressed"][o["ready"]].mean()) if o["ready"].any() else 0}
        # MEMS channels (rev F surveys): their sigma, and how many times each was
        # raised (they never open events, so they are counted here instead).
        for k in range(core.NCH, o["res"].shape[1]):
            ch = core.CHANNEL_NAMES[k]
            rk = o["ch_ready"][:, k]
            row[f"{ch}_sigma_median_mv"] = float(np.median(o["sigma"][rk, k])) if rk.any() else float("nan")
            a = o["anomaly"][:, k]
            row[f"{ch}_raised"] = int(np.sum(a[1:] & ~a[:-1]) + a[0])
        fa_rows.append(row)
        ev_rows.append(events_frame(ev, s))
        plot_survey(s, o, ev, c, REPORT_DIR / f"survey_{s.id}.png")
    fa = pd.DataFrame(fa_rows)
    tot = {"survey": "all", "mode": "", "hours_ready": fa.hours_ready.sum(), "km_ready": fa.km_ready.sum(),
           "events": fa.events.sum()}
    tot["per_hour"] = tot["events"] / tot["hours_ready"]
    tot["per_km"] = tot["events"] / tot["km_ready"]
    fa = pd.concat([fa, pd.DataFrame([tot])], ignore_index=True)
    lines += ["## Events on held-out surveys with the shipped settings\n", fa.to_markdown(index=False, floatfmt=".3f"), ""]
    nonempty = [e.dropna(axis=1, how="all") for e in ev_rows if len(e)]
    evs = pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame()
    if len(evs):
        evs.to_csv(REPORT_DIR / "events.csv", index=False)
        cols = ["survey", "event_id", "utc_start", "class", "confidence", "duration_s", "ch4_peak_res_mv",
                "lpg_peak_res_mv", "ch4_peak_sigma", "lpg_peak_sigma"]
        cols += [c for c in ("mems_a_peak_sigma", "mems_b_peak_sigma") if c in evs.columns]
        cols += ["ratio", "lead_s", "thermal", "gps_speed_kmh_report_only"]
        lines += ["## Event fingerprints\n", evs[cols].to_markdown(index=False, floatfmt=".2f"), ""]
    if not args.skip_synth:
        syn = cmd_synth(args)
        plot_synth(syn, REPORT_DIR / "synthetic.png")
        piv = syn.pivot_table(index=["exposure_s", "x"], columns="a_mv", values="detected")
        pis = syn.pivot_table(index=["exposure_s", "x"], columns="a_mv", values="subtraction_detected")
        lines += ["## Synthetic plumes: independent detection\n", piv.to_markdown(floatfmt=".2f"), "",
                  "## Synthetic plumes: subtraction reference\n", pis.to_markdown(floatfmt=".2f"), ""]
    (REPORT_DIR / "metrics.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_DIR.relative_to(REPO)}")


# ---- C versus Python parity ----------------------------------------------------------------

HOST_DIR = TOOLS / "anomaly_host"
LIB_DIR = REPO / "firmware" / "phone_board" / "lib" / "anomaly"


def build_host(build: Path, name: str, defines: dict) -> Path:
    """Compile tools/anomaly_host/replay_host.c with the firmware core, using zig cc
    (pip install ziglang): no other compiler is needed on Windows."""
    exe = build / (name + (".exe" if sys.platform == "win32" else ""))
    cmd = [sys.executable, "-m", "ziglang", "cc", "-std=c99", "-O2", "-Wall", "-Wextra",
           "-I", str(LIB_DIR), str(HOST_DIR / "replay_host.c"), str(LIB_DIR / "anomaly.c"),
           "-o", str(exe)]
    cmd += [f"-D{k}={v}" if v is not None else f"-D{k}" for k, v in defines.items()]
    subprocess.run(cmd, check=True)
    return exe


def write_host_input(path: Path, inp: dict) -> None:
    n = len(inp["t_ms"])
    cols = {
        "t_ms": inp["t_ms"], "ch4_mv": inp["ch4_mv"], "lpg_mv": inp["lpg_mv"],
        "temp_c": inp["temp_c"], "rh_pct": inp["rh_pct"], "valid": inp["valid"].astype(int),
        "airflow_index": inp.get("airflow_index", np.zeros(n)),
        "airflow_ok": np.asarray(inp.get("airflow_ok", np.zeros(n)), int),
        "co_ppm": inp.get("co_ppm", np.zeros(n)), "co_ok": np.asarray(inp.get("co_ok", np.zeros(n)), int),
    }
    for ch in core.CHANNEL_NAMES[2:core.nch_of(inp)]:
        cols[f"{ch}_mv"] = inp[f"{ch}_mv"]
        cols[f"{ch}_ok"] = np.asarray(inp[f"{ch}_ok"], int)
    pd.DataFrame(cols).to_csv(path, index=False, float_format="%.17g")


def synthetic_hooks(inp: dict) -> dict:
    """Made-up airflow and CO channels, only to exercise those code paths in the
    parity test (no survey has them yet)."""
    t = (inp["t_ms"] - inp["t_ms"][0]) / 1000.0
    out = dict(inp)
    out["airflow_index"] = 0.6 + 0.5 * np.sin(t / 47.0) + 0.1 * np.sin(t / 3.1)
    out["airflow_ok"] = np.ones(len(t), bool)
    co = 0.4 + 0.05 * np.sin(t / 11.0)
    for t0 in np.arange(400.0, t[-1], 700.0):
        co += 6.0 * np.exp(-np.clip(t - t0, 0, None) / 40.0) * (t >= t0)
    out["co_ppm"] = co
    out["co_ok"] = np.ones(len(t), bool)
    return out


def synthetic_mems(inp: dict, seed: int = 1) -> dict:
    """Made-up MEMS channels, only to exercise the 4-channel code paths in the
    parity test (no rev F survey exists yet). They are NOT a model of the MEMS
    sensors: scaled, lagged copies of the Figaro readings plus noise and a drift,
    a few bumps of their own, and validity that starts after a warm-up and drops
    out now and then, both briefly and for longer than the gap reset."""
    rng = np.random.default_rng(seed)
    t_ms = inp["t_ms"]
    t = (t_ms - t_ms[0]) / 1000.0
    n = len(t)
    out = dict(inp)
    lag_a = np.searchsorted(t, t - 3.0)
    lag_b = np.searchsorted(t, t - 1.0)
    a = 300.0 + 0.6 * inp["ch4_mv"][lag_a] + rng.normal(0.0, 0.8, n) + 5.0 * np.sin(t / 900.0)
    b = 150.0 + 1.5 * inp["lpg_mv"][lag_b] + rng.normal(0.0, 1.2, n)
    for t0 in np.arange(900.0, t[-1], 1300.0):
        a += 40.0 * np.exp(-np.clip(t - t0, 0, None) / 12.0) * (t >= t0)
    ok_a = np.asarray(inp["valid"], bool) & (t > 150.0)
    ok_b = ok_a.copy()
    for t0 in np.arange(1100.0, t[-1], 1700.0):
        ok_a &= ~((t >= t0) & (t < t0 + 5.0))          # shorter than the gap reset
        ok_b &= ~((t >= t0 + 400) & (t < t0 + 430.0))  # longer: the channel restarts
    out.update(mems_a_mv=a, mems_a_ok=ok_a, mems_b_mv=b, mems_b_ok=ok_b)
    return out


def compare(py_o: dict, py_ev, c_out: pd.DataFrame, c_ev: pd.DataFrame) -> dict:
    v = py_o["valid"]
    nch = py_o["res"].shape[1]
    names = core.CHANNEL_NAMES[:nch]
    d = {}
    for name, col in (("res", "res"), ("sigma", "sigma"), ("pred", "pred")):
        for k, ch in enumerate(names):
            a = np.nan_to_num(py_o[name][:, k])[v]
            b = c_out[f"{ch}_{col}"].to_numpy()[v]
            d[f"{ch}_{name}_max_abs_diff_mv"] = float(np.max(np.abs(a - b))) if v.any() else 0.0
    d["anomaly_flag_mismatches"] = int(sum(np.sum(py_o["anomaly"][:, k] != c_out[f"{ch}_anom"].to_numpy().astype(bool))
                                           for k, ch in enumerate(names)))
    # Every channel's event peaks (for MEMS channels these are recorded inside the
    # Figaro-opened events).
    if len(py_ev) != len(c_ev):
        d["event_peak_max_abs_diff_mv"] = float("inf")
    elif len(py_ev):
        d["event_peak_max_abs_diff_mv"] = float(max(
            np.max(np.abs(np.array([e.peak_res_mv[k] for e in py_ev]) - c_ev[f"{ch}_peak_res_mv"].to_numpy()))
            for k, ch in enumerate(names)))
    else:
        d["event_peak_max_abs_diff_mv"] = 0.0
    d["events_python"] = len(py_ev)
    d["events_c"] = len(c_ev)
    py_cls = [e.class_name for e in py_ev]
    c_cls = list(c_ev["class"]) if len(c_ev) else []
    d["event_class_mismatches"] = sum(a != b for a, b in zip(py_cls, c_cls)) + abs(len(py_cls) - len(c_cls))
    if len(py_ev) and len(c_ev) == len(py_ev):
        d["event_ratio_max_abs_diff"] = float(np.max(np.abs(np.array([e.ratio for e in py_ev]) - c_ev["ratio"].to_numpy())))
    return d


def cmd_parity(args) -> pd.DataFrame:
    build = Path(args.build) if args.build else TOOLS / "anomaly_host" / "build"
    build.mkdir(parents=True, exist_ok=True)
    surveys = load_manifest(args.surveys)
    # 2-channel builds (rev B/E) and 4-channel builds (rev F, on synthetic MEMS
    # inputs). The Python twin takes its channel count from the inputs.
    hooks = {"ANOM_USE_AIRFLOW": 1, "ANOM_USE_CO": 1, "ANOM_USE_RLS": 1}
    variants = [
        ("default", 2, {}),
        ("hp30", 2, {"ANOM_RES_HP_TAU_S": 30.0}),
        ("airflow_co_rls", 2, hooks),
        ("nch4", 4, {}),
        ("nch4_airflow_co_rls_hp30", 4, {**hooks, "ANOM_RES_HP_TAU_S": 30.0}),
    ]
    rows = []
    for vname, nch, pyover in variants:
        cdefs = {"ANOM_NCH": str(nch), **{k: str(v) for k, v in pyover.items()}}
        exe_d = build_host(build, f"replay_host_{vname}_double",
                           {**cdefs, "ANOM_REAL": "double", "ANOM_REAL_IS_DOUBLE": None})
        exe_f = build_host(build, f"replay_host_{vname}_float", cdefs)
        cfg = config(**pyover)
        for s in surveys:
            inp = synthetic_hooks(s.inputs) if "airflow" in vname else s.inputs
            if nch == 4 and core.nch_of(inp) == 2:
                inp = synthetic_mems(inp)
            fin = build / f"{s.id}_{vname}_in.csv"
            write_host_input(fin, inp)
            py_o, py_ev = core.replay(inp, cfg)
            for prec, exe in (("double", exe_d), ("float", exe_f)):
                fo, fe = build / f"{s.id}_{vname}_{prec}_out.csv", build / f"{s.id}_{vname}_{prec}_ev.csv"
                subprocess.run([str(exe), str(fin), str(fo), str(fe)], check=True)
                row = {"variant": vname, "survey": s.id, "c_precision": prec}
                row.update(compare(py_o, py_ev, pd.read_csv(fo), pd.read_csv(fe)))
                rows.append(row)
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(df.to_string(index=False, float_format=lambda v: f"{v:.3g}"))
    dbl = df[df.c_precision == "double"]
    # fillna: the MEMS columns are empty on 2-channel rows.
    ok = ((dbl.filter(like="max_abs_diff_mv").fillna(0.0) < 1e-6).all(axis=None)
          and (dbl.anomaly_flag_mismatches == 0).all() and (dbl.event_class_mismatches == 0).all())
    print("\nDouble-precision C matches Python:", "YES" if ok else "NO")
    print("Variants (channels):", ", ".join(f"{v} ({n})" for v, n, _ in variants))
    flt = df[df.c_precision == "float"]
    print(f"Single-precision C (as on the device): worst residual difference "
          f"{flt.filter(like='res_max').max().max():.4f} mV, flag mismatches {int(flt.anomaly_flag_mismatches.sum())}, "
          f"event class mismatches {int(flt.event_class_mismatches.sum())}")
    if not ok:
        sys.exit(1)
    return df


# ---- CLI ----------------------------------------------------------------------------------

def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("file")
    p.add_argument("--out")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("fit")
    p.add_argument("--write-config", action="store_true")
    p.add_argument("--surveys", nargs="*")
    p.set_defaults(func=cmd_fit)
    p = sub.add_parser("tune")
    p.add_argument("--write-config", action="store_true")
    p.add_argument("--surveys", nargs="*")
    p.set_defaults(func=cmd_tune)
    p = sub.add_parser("synth")
    p.add_argument("--surveys", nargs="*")
    p.set_defaults(func=cmd_synth)
    p = sub.add_parser("report")
    p.add_argument("--surveys", nargs="*")
    p.add_argument("--skip-synth", action="store_true")
    p.set_defaults(func=cmd_report)
    p = sub.add_parser("parity")
    p.add_argument("--surveys", nargs="*")
    p.add_argument("--build")
    p.set_defaults(func=cmd_parity)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
