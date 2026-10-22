"""Prototype of the platform side: pool many surveys and rank places to check.

Each survey is replayed through the shared detector (tools/anomaly_core.py, the
firmware's twin, with the coefficients in anomaly_config.h). Samples and events
are then binned by location cell. Position is only a tag here: the model never
sees it, and a cell is never judged against its own history or average. What a
cell's history *is* used for is persistence -- does the anomaly come back on
different passes, at different times of day, travelling in different directions,
at different airflow?

  python tools/aggregate.py                       # surveys in tools/surveys.json
  python tools/aggregate.py a.csv b.csv           # or app survey CSVs directly
  python tools/aggregate.py --labels labels.csv   # merge checked outcomes

Writes, to tools/data/aggregate/ (or --out):
  candidates.csv / candidates.json   ranked cells with any flagged pass, with
                                     every event's fingerprint (UNRESOLVED and
                                     both-channel events included, never dropped)
  passes.csv                         one row per pass through a cell
  labels_template.csv                one row per candidate, label = unchecked
  fingerprint_library.jsonl          events from labelled candidates, one JSON
                                     object per line, for retraining and for the
                                     class fingerprint library

Labels: unchecked, confirmed_leak, rejected, other_source. A label is set after a
candidate has been checked with a proper instrument; edit labels_template.csv
(or keep your own labels.csv in the same format) and pass it with --labels.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anomaly_core as core  # noqa: E402
import replay as rp  # noqa: E402

LABELS = ("unchecked", "confirmed_leak", "rejected", "other_source")
LABEL_COLUMNS = ("cell_id", "label", "checked_utc", "instrument", "measured_ppm", "notes")

CELL_M = 30.0            # cell size, metres
PASS_GAP_S = 600.0       # re-entering a cell within 10 min is the same pass: a U-turn
                          # inside one event is not independent evidence
TOD_BINS = ((0, 6, "night"), (6, 12, "morning"), (12, 18, "afternoon"), (18, 24, "evening"))
AIRFLOW_BINS = (0.15, 0.5)   # index: low / medium / high (only with a thermistor)


def cell_ids(lat: np.ndarray, lon: np.ndarray, cell_m: float = CELL_M) -> np.ndarray:
    """Square-ish cells: rows of fixed latitude height, columns scaled by the
    cosine of the row's latitude so they stay about cell_m wide everywhere."""
    dlat = cell_m / 111_320.0
    row = np.floor(lat / dlat)
    row_lat = (row + 0.5) * dlat
    dlon = cell_m / (111_320.0 * np.cos(np.radians(row_lat)))
    col = np.floor(lon / dlon)
    out = np.array([f"{int(r)}:{int(c)}" if np.isfinite(r) and np.isfinite(c) else ""
                    for r, c in zip(row, col)], dtype=object)
    return out


def cell_centre(cell: str, cell_m: float = CELL_M) -> tuple[float, float]:
    r, c = (int(x) for x in cell.split(":"))
    dlat = cell_m / 111_320.0
    lat = (r + 0.5) * dlat
    dlon = cell_m / (111_320.0 * math.cos(math.radians(lat)))
    return lat, (c + 0.5) * dlon


def heading_deg(df: pd.DataFrame, window_s: float = 10.0) -> np.ndarray:
    """Direction of travel over a trailing window (tag only), NaN when slow."""
    t = df["millis_since_boot"].to_numpy(float) / 1000.0
    lat = df["lat"].to_numpy(float)
    lon = df["lon"].to_numpy(float)
    j = np.searchsorted(t, t - window_s)
    dy = (lat - lat[j]) * 111_320.0
    dx = (lon - lon[j]) * 111_320.0 * np.cos(np.radians(lat))
    h = (np.degrees(np.arctan2(dx, dy)) + 360.0) % 360.0
    return np.where(np.hypot(dx, dy) > 5.0, h, np.nan)


def tod_bin(hour: float) -> str:
    for a, b, name in TOD_BINS:
        if a <= hour < b:
            return name
    return ""


def airflow_bin(x: float) -> str:
    if not np.isfinite(x):
        return "unknown"
    return "low" if x < AIRFLOW_BINS[0] else ("medium" if x < AIRFLOW_BINS[1] else "high")


def survey_passes(sv: rp.Survey, cfg: dict, cell_m: float):
    """Replay one survey; return (passes, events) tagged with cells."""
    o, events = core.replay(sv.inputs, cfg)
    df = sv.df
    ok = o["ready"] & (df["fix"].to_numpy() == 1)
    cells = cell_ids(df["lat"].to_numpy(float), df["lon"].to_numpy(float), cell_m)
    cells = np.where(ok, cells, "")
    t = sv.inputs["t_ms"]
    utc = pd.to_datetime(df["utc_iso8601"], errors="coerce")
    hdg = heading_deg(df)
    air = df["airflow_index"].to_numpy(float) if "airflow_index" in df.columns else np.full(len(df), np.nan)
    z = np.where(o["sigma"] > 0, o["res"] / np.where(o["sigma"] > 0, o["sigma"], 1.0), np.nan)
    anom = o["anomaly"].any(axis=1)

    # Events: tag each with the cell at its peak (the larger channel's peak).
    ev_rows = []
    for e in events:
        d = e.as_dict()
        k = 0 if e.peak_sigma[0] >= e.peak_sigma[1] else 1
        i = int(np.clip(np.searchsorted(t, e.t_peak_ms[k]), 0, len(t) - 1))
        d.update(survey=sv.id, mode=sv.mode, cell_id=cells[i] or cell_ids(
            np.array([df["lat"].iloc[i]]), np.array([df["lon"].iloc[i]]), cell_m)[0],
            utc_peak=str(utc.iloc[i]), lat=float(df["lat"].iloc[i]), lon=float(df["lon"].iloc[i]),
            heading_deg=None if not np.isfinite(hdg[i]) else float(hdg[i]))
        ev_rows.append(d)

    # Passes: runs of samples in one cell; re-entry after PASS_GAP_S is a new pass.
    rows = []
    open_by_cell: dict = {}
    for i in np.flatnonzero(cells != ""):
        c = cells[i]
        cur = open_by_cell.get(c)
        if cur is None or t[i] - cur["_t_last"] > PASS_GAP_S * 1000:
            if cur is not None:
                rows.append(cur)
            cur = open_by_cell[c] = {"cell_id": c, "survey": sv.id, "mode": sv.mode,
                                     "_t_first": t[i], "_t_last": t[i], "_idx": []}
        cur["_t_last"] = t[i]
        cur["_idx"].append(i)
    rows += open_by_cell.values()
    passes = []
    ev_spans = [(e.t_start_ms, e.t_end_ms, e.id) for e in events]
    for p in rows:
        idx = np.array(p["_idx"])
        t0, t1 = p["_t_first"], p["_t_last"]
        zc = z[idx]
        hd = hdg[idx]
        u = utc.iloc[idx[len(idx) // 2]]
        ev_ids = [eid for a, b, eid in ev_spans if a <= t1 and b >= t0]
        passes.append({
            "cell_id": p["cell_id"], "survey": p["survey"], "mode": p["mode"],
            "utc_mid": str(u), "time_of_day": tod_bin(u.hour + u.minute / 60) if pd.notna(u) else "",
            "span_s": (t1 - t0) / 1000.0, "samples": len(idx),
            "ch4_peak_z": float(np.nanmax(zc[:, 0])), "lpg_peak_z": float(np.nanmax(zc[:, 1])),
            "ch4_mean_z": float(np.nanmean(zc[:, 0])), "lpg_mean_z": float(np.nanmean(zc[:, 1])),
            # Flagged only if a channel was raised while in this cell: a long event
            # driven through many cells does not flag the ones it merely spans.
            "flagged": bool(anom[idx].any()),
            "event_ids": ";".join(f"{p['survey']}#{e}" for e in ev_ids),
            "heading_octant": "" if np.all(np.isnan(hd)) else
                              "N NE E SE S SW W NW".split()[int(((np.nanmedian(hd) + 22.5) % 360) // 45)],
            "airflow": airflow_bin(float(np.nanmean(air[idx])) if np.isfinite(air[idx]).any() else np.nan),
            "wind_dir": "",  # no wind source yet
        })
    return passes, ev_rows


def score_cells(passes: pd.DataFrame, events: pd.DataFrame, k_on: float) -> pd.DataFrame:
    """Persistence score per cell. Prototype weights, documented in REPORT.md."""
    out = []
    for cell, g in passes.groupby("cell_id"):
        n = len(g)
        fl = g[g.flagged]
        nf = len(fl)
        if nf == 0:
            continue
        peak = np.maximum(g.ch4_peak_z, g.lpg_peak_z)
        weakest = float(peak.min())             # weakest residual over all passes
        weakest_flagged = float(np.maximum(fl.ch4_peak_z, fl.lpg_peak_z).min())
        tods = sorted(set(fl.time_of_day) - {""})
        dirs = sorted(set(fl.heading_octant) - {""})
        airs = sorted(set(fl.airflow) - {"unknown"})
        surveys = sorted(set(fl.survey))
        frac = nf / n
        # Shrink towards 0 for few passes, reward recurrence across conditions.
        diversity = 1.0 + 0.25 * (max(len(tods), 1) - 1) + 0.25 * (max(len(dirs), 1) - 1) \
            + 0.25 * (max(len(airs), 1) - 1) + 0.25 * (len(surveys) - 1)
        score = nf / (n + 1.0) * diversity * (1.0 + max(weakest, 0.0) / k_on)
        lat, lon = cell_centre(cell)
        ev = events[events.cell_id == cell] if len(events) else events
        out.append({
            "cell_id": cell, "lat": round(lat, 6), "lon": round(lon, 6), "score": round(score, 4),
            "passes": n, "flagged_passes": nf, "fraction_flagged": round(frac, 3),
            "surveys_flagged": ";".join(surveys),
            "weakest_peak_z_all_passes": round(weakest, 2),
            "weakest_peak_z_flagged_passes": round(weakest_flagged, 2),
            "times_of_day_flagged": ";".join(tods), "directions_flagged": ";".join(dirs),
            "airflow_flagged": ";".join(airs) or "unknown", "wind_dir": "",
            "events": len(ev),
            "event_classes": ";".join(f"{c}x{m}" for c, m in ev["class"].value_counts().items()) if len(ev) else "",
            "label": "unchecked",
        })
    df = pd.DataFrame(out)
    if len(df):
        df = df.sort_values(["score", "flagged_passes"], ascending=False).reset_index(drop=True)
        df.insert(0, "rank", np.arange(1, len(df) + 1))
    return df


def merge_labels(cands: pd.DataFrame, labels_path: Path | None) -> pd.DataFrame:
    if labels_path is None or not labels_path.exists() or not len(cands):
        return cands
    lab = pd.read_csv(labels_path, dtype=str).fillna("")
    bad = set(lab["label"]) - set(LABELS)
    if bad:
        raise ValueError(f"unknown labels {sorted(bad)}; use one of {LABELS}")
    lab = lab.drop_duplicates("cell_id", keep="last").set_index("cell_id")
    cands = cands.copy()
    for col in LABEL_COLUMNS[1:]:
        cands[col] = cands["cell_id"].map(lab[col]) if col in lab.columns else ""
    cands["label"] = cands["label"].replace("", "unchecked").fillna("unchecked")
    return cands.fillna("")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="app survey CSVs (default: tools/surveys.json)")
    ap.add_argument("--labels", type=Path, help="labels CSV: " + ",".join(LABEL_COLUMNS))
    ap.add_argument("--out", type=Path, default=rp.TOOLS / "data" / "aggregate")
    ap.add_argument("--cell-m", type=float, default=CELL_M)
    args = ap.parse_args(argv)

    cfg = rp.config()
    if args.files:
        surveys = []
        for f in args.files:
            path = rp.find_file(f)
            df = pd.read_csv(path)
            surveys.append(rp.Survey(id=path.stem, file=str(path), mode="", df=df, inputs=rp.to_inputs(df)))
    else:
        surveys = rp.load_manifest()

    all_p, all_e = [], []
    for sv in surveys:
        p, e = survey_passes(sv, cfg, args.cell_m)
        all_p += p
        all_e += e
    passes = pd.DataFrame(all_p)
    events = pd.DataFrame(all_e)
    cands = merge_labels(score_cells(passes, events, cfg["ANOM_K_ON"]), args.labels)

    args.out.mkdir(parents=True, exist_ok=True)
    passes.to_csv(args.out / "passes.csv", index=False)
    cands.to_csv(args.out / "candidates.csv", index=False)
    blob = []
    for _, c in cands.iterrows():
        evs = events[events.cell_id == c.cell_id] if len(events) else events
        blob.append({**{k: (v.item() if hasattr(v, "item") else v) for k, v in c.items()},
                     "fingerprints": json.loads(evs.to_json(orient="records")) if len(evs) else []})
    (args.out / "candidates.json").write_text(json.dumps(blob, indent=1, default=str), encoding="utf-8")
    tmpl = pd.DataFrame({"cell_id": cands["cell_id"] if len(cands) else [], "label": "unchecked",
                         "checked_utc": "", "instrument": "", "measured_ppm": "", "notes": ""})
    tmpl.to_csv(args.out / "labels_template.csv", index=False)

    # Fingerprint library: every event in a labelled (checked) cell, with its label.
    with open(args.out / "fingerprint_library.jsonl", "w", encoding="utf-8") as fh:
        if len(cands) and len(events):
            for _, c in cands[cands.label != "unchecked"].iterrows():
                for _, e in events[events.cell_id == c.cell_id].iterrows():
                    rec = json.loads(e.to_json())
                    rec.update(label=c.label, instrument=c.get("instrument", ""),
                               measured_ppm=c.get("measured_ppm", ""), notes=c.get("notes", ""))
                    fh.write(json.dumps(rec) + "\n")

    nflag = int(passes.flagged.sum()) if len(passes) else 0
    print(f"{len(surveys)} surveys, {len(passes)} passes through {passes.cell_id.nunique() if len(passes) else 0} "
          f"cells ({args.cell_m:.0f} m), {nflag} flagged passes, {len(events)} events, "
          f"{len(cands)} candidate cells -> {args.out}")
    if len(cands):
        cols = ["rank", "cell_id", "score", "passes", "flagged_passes", "weakest_peak_z_flagged_passes",
                "times_of_day_flagged", "directions_flagged", "event_classes", "label"]
        print(cands[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
