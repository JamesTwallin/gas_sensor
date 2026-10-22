"""One-figure walk-through of how the detector works (REPORT.md section 2), drawn
on one survey replayed with a model fitted without it (default D4, the drive past
the known leak). "Confirmed" is the survey's logged leak window (leak_utc in
surveys.json), or failing that an event the full detector raised; "candidate" is
any other time the leftover went above k, with no hold time.

By default the leftover also has its 15 s average taken off and uses the detector's
own noise level, as the firmware does. --no-highpass leaves the 15 s average in and
works out a noise level for it the same way (5 minutes, excursions above 3 sigma
kept out).

Same popsci house style as plot_vehicular.py.

  python tools/plot_method.py [--survey D4] [--no-highpass] [--out docs/report/method.png]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as font_manager  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anomaly_core as core  # noqa: E402
import replay as rp  # noqa: E402

# --- popsci house style (as plot_vehicular.py) -------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
for _f in ("NotoSansDisplay-Regular.ttf", "NotoSansDisplay-Bold.ttf"):
    _p = os.path.join(_HERE, _f)
    if os.path.exists(_p):
        font_manager.fontManager.addfont(_p)
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Noto Sans Display", "Noto Sans", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.facecolor"] = "white"
plt.rcParams["savefig.facecolor"] = "white"

INK = "#222222"
MUTED = "#666666"
WARN = "#c0392b"
C_CH4 = "#2a6fc4"       # the app's CH4 blue
C_LPG = "#b8621f"       # the app's LPG orange
C_TEMP = "#8e3b3b"
C_AH = "#3a8f8a"
EVENT = "#f6dccb"       # detected event
DPI = 150
CH = (("CH4", "methane sensor", C_CH4), ("LPG", "LPG sensor", C_LPG))
CLASS_WORDS = {"HEAVY_HC": "LPG-led: heavier hydrocarbon", "NATURAL_GAS": "natural gas",
               "THERMAL": "temperature step", "UNRESOLVED": "both sensors, unresolved",
               "UNCLASSIFIED": "methane only", "LOW_AIRFLOW": "low airflow", "EXHAUST": "exhaust"}
# how each survey's confirmed gas was checked on the day
CONFIRMED_BY = {"D4": "confirmed leak\nthree drive-bys", "D5": "confirmed by smell"}


def robust_sigma(t_ms: np.ndarray, x: np.ndarray, iters: int = 3) -> np.ndarray:
    """Trailing 5-minute robust SD (1.4826 x MAD), never below 1 mV; samples more
    than 3 sigmas up are kept out of it, as the detector keeps anomalies out."""
    idx = pd.to_datetime(t_ms, unit="ms")
    keep = np.ones(len(x), bool)
    for _ in range(iters + 1):
        y = pd.Series(np.where(keep, x, np.nan), index=idx)
        med = y.rolling("300s", min_periods=200).median()
        mad = (y - med).abs().rolling("300s", min_periods=200).median()
        sig = np.maximum((1.4826 * mad).shift(1).to_numpy(), 1.0)
        with np.errstate(invalid="ignore"):
            keep = ~(x / sig > 3)
    return sig


def load(sid: str, highpass: bool):
    surveys = rp.load_manifest()
    cfg = rp.config()
    coefs = rp.loso_coefs(surveys, cfg)  # scored by a model that never saw this survey
    s = next(x for x in surveys if x.id == sid)
    c = rp.cfg_with(cfg, coefs[sid])
    o, events = core.replay(s.inputs, c)
    inp = s.inputs
    t0 = inp["t_ms"][0]
    v, ready = inp["valid"], o["ready"]
    nan = lambda a, m: np.where(m[:, None] if a.ndim == 2 else m, a, np.nan)  # noqa: E731
    mv = np.column_stack([inp["ch4_mv"], inp["lpg_mv"]])
    if highpass:
        res, sigma = o["res"][:, :2], o["sigma"][:, :2]
    else:
        res = np.where(ready[:, None], o["model_res"][:, :2], np.nan)
        sigma = np.column_stack([robust_sigma(inp["t_ms"], res[:, j]) for j in range(2)])
    with np.errstate(invalid="ignore", divide="ignore"):
        z = res / np.where(sigma > 0, sigma, np.nan)
    d = {
        "tm": (inp["t_ms"] - t0) / 60000.0,
        "mv": nan(mv, v),
        "base": nan(mv - o["target"][:, :2], v),
        "temp": nan(inp["temp_c"], v),
        "ah": nan(np.array([core.abs_humidity(a, b) for a, b in zip(inp["temp_c"], inp["rh_pct"])]), v),
        "target": nan(o["target"][:, :2], v),
        "pred": nan(o["pred"][:, :2], v),
        "res": nan(res, ready),
        "z": nan(z, ready),
        "sigma": np.nanmedian(nan(sigma, ready), axis=0),
        "highpass": highpass,
        "events": ([((a - t0) / 60000.0, (b - t0) / 60000.0, None) for a, b in s.leak_ms] if s.leak_ms else
                   [((e.t_start_ms - t0) / 60000.0, (e.t_end_ms - t0) / 60000.0, e.class_name) for e in events]),
    }
    return s, c, d


def _despine(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.tick_params(colors=INK)


def _step(ax, n: int, head: str, sub: str) -> None:
    ax.set_title(f"{n}  {head}", loc="left", fontsize=12.5, fontweight="bold", color=INK, pad=19)
    ax.text(0, 1.035, sub, transform=ax.transAxes, fontsize=9.5, color=MUTED, va="bottom")


def _tag(ax, text: str, color: str) -> None:
    ax.text(0.22, 0.95, text, transform=ax.transAxes, ha="left", va="top", fontsize=9, color=color)


def candidates(d, k: float, min_gap_min: float = 1.0) -> list[tuple[float, float]]:
    """Peaks above k outside any confirmed event, one per cluster."""
    with np.errstate(invalid="ignore"):
        zmax = np.fmax(d["z"][:, 0], d["z"][:, 1])
    inside = np.zeros(len(zmax), bool)
    for a, b, _ in d["events"]:
        inside |= (d["tm"] >= a - 0.2) & (d["tm"] <= b + 0.2)
    idx = np.flatnonzero((zmax > k) & ~inside)
    out: list[tuple[float, float]] = []
    for i in idx:
        if out and d["tm"][i] - out[-1][0] < min_gap_min:
            if zmax[i] > out[-1][1]:
                out[-1] = (d["tm"][i], zmax[i])
            continue
        out.append((d["tm"][i], zmax[i]))
    return out


def draw(fig, axes, d, cfg, confirmed: str) -> None:
    tm = d["tm"]
    a1, a2t, a2h, a3c, a3l, a4, a5 = axes
    k, k_off = cfg["ANOM_K_ON"], cfg["ANOM_K_OFF"]

    for j, (_, name, col) in enumerate(CH):
        a1.plot(tm, d["mv"][:, j], color=col, lw=1.4, label=name)
        a1.plot(tm, d["base"][:, j], color=INK, lw=1.0, ls="--",
                label="each one's slow 5-minute average" if j else None)
    a1.set_ylabel("mV", color=INK)
    a1.legend(loc="upper left", bbox_to_anchor=(0.05, 1.0), frameon=False, fontsize=9, ncol=3)
    _step(a1, 1, "Take away the slow drift",
          "Each sensor's voltage wanders slowly. Subtract its own 5-minute moving average.")

    a2t.plot(tm, d["temp"], color=C_TEMP, lw=1.4)
    a2t.set_ylabel("°C", color=INK)
    _tag(a2t, "air temperature", C_TEMP)
    _step(a2t, 2, "Watch the air",
          "Temperature and humidity are logged alongside the gas, by a separate sensor.")
    a2h.plot(tm, d["ah"], color=C_AH, lw=1.4)
    a2h.set_ylabel("g/m³", color=INK)
    _tag(a2h, "humidity (grams of water per m³ of air)", C_AH)

    for j, ax in enumerate((a3c, a3l)):
        _, name, col = CH[j]
        ax.plot(tm, d["target"][:, j], color=col, lw=1.4, label=f"{name}, after step 1")
        ax.plot(tm, d["pred"][:, j], color=INK, lw=1.0, alpha=0.85,
                label="predicted from temperature and humidity alone")
        ax.axhline(0, color=MUTED, lw=0.6)
        ax.set_ylabel("mV", color=INK)
        ax.legend(loc="upper left", bbox_to_anchor=(0.05, 1.0), frameon=False, fontsize=9, ncol=2)
    _step(a3c, 3, "Predict the wiggles from the air",
          "Gas sensors also react to heat and damp. A fitted formula predicts that part "
          "(it never uses the gas readings).")

    for j, (_, name, col) in enumerate(CH):
        a4.plot(tm, d["res"][:, j], color=col, lw=1.2, label=name)
    a4.axhline(0, color=MUTED, lw=0.6)
    a4.set_ylabel("mV", color=INK)
    if d["highpass"]:
        _step(a4, 4, "Keep what the formula can't explain, and only the quick part",
              "Actual minus predicted, minus its own 15-second average. Slow misses (airflow, stops) "
              "drop out; a gas plume is quick.")
    else:
        _step(a4, 4, "Keep what the formula can't explain",
              "Actual minus predicted: whatever the air alone does not account for.")

    a5.axhspan(-k_off, k_off, color="#dddddd", lw=0, zorder=1)
    for j, (_, name, col) in enumerate(CH):
        a5.plot(tm, d["z"][:, j], color=col, lw=1.2, label=name, zorder=3)
    a5.axhline(k, color=WARN, lw=1.3, ls="--", zorder=2)
    a5.text(tm[0] + 0.45 * (tm[-1] - tm[0]), k + 0.5, f"flag: above {k:g}×", ha="center", va="bottom",
            fontsize=9.5, color=WARN)
    a5.text(tm[0] + 0.01 * (tm[-1] - tm[0]), k_off + 0.5, "everyday noise", ha="left",
            va="bottom", fontsize=9, color=MUTED, zorder=4)
    top = max(k + 8, float(np.nanmax(d["z"])) * 1.25)
    a5.set_ylim(-8, top)
    groups: list[list[tuple[float, float]]] = []
    for c in candidates(d, k):  # peaks a few minutes apart share one label
        if groups and c[0] - groups[-1][-1][0] < 4.0:
            groups[-1].append(c)
        else:
            groups.append([c])
    for g in groups:
        for tx, zx in g:
            a5.scatter([tx], [zx], s=60, facecolors="none", edgecolors=INK, linewidths=1.1, zorder=5)
        tx, zx = max(g, key=lambda c: c[1])
        a5.annotate("candidates" if len(g) > 1 else "candidate", (tx, zx), xytext=(0, 9),
                    textcoords="offset points", ha="center", va="bottom", fontsize=9, fontweight="bold",
                    color=INK)
    a5.set_ylabel("× typical noise", color=INK)
    a5.legend(loc="upper left", bbox_to_anchor=(0.0, 0.88), frameon=False, fontsize=9)
    sig = ", ".join(f"{n} {s_:.0f} mV" for (n, _, _), s_ in zip(CH, d["sigma"]))
    _step(a5, 5, "Flag anything far above the usual noise",
          f"Divide by the typical size of the last 5 minutes' wobble (here about {sig}).")
    a5.set_xlabel("minutes into the drive", color=INK)

    for ax in axes:
        for a, b, _ in d["events"]:
            ax.axvspan(a, b, color=EVENT, lw=0, zorder=0)
        _despine(ax)
    for ax in axes[:-1]:
        ax.tick_params(labelbottom=False)
    for a, b, cls in d["events"]:
        label = confirmed if cls is None else f"{confirmed}\n{CLASS_WORDS.get(cls, cls)}"
        right = b < tm[0] + 0.7 * (tm[-1] - tm[0])  # label beside the band, on the side with room
        a5.text(b + 0.4 if right else a - 0.4, top * 0.97, label, ha="left" if right else "right", va="top",
                fontsize=9.5, fontweight="bold", color=WARN, linespacing=1.15)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--survey", default="D4")
    ap.add_argument("--no-highpass", dest="highpass", action="store_false",
                    help="leave the 15 s average in (the firmware takes it off)")
    ap.add_argument("--out", type=Path, default=rp.REPORT_DIR / "method.png")
    args = ap.parse_args()
    s, cfg, d = load(args.survey, args.highpass)

    fig = plt.figure(figsize=(9.5, 13.6))
    # One block per step; panels within a step sit close together.
    outer = fig.add_gridspec(5, 1, height_ratios=[1.2, 1.05, 1.95, 1.1, 1.5],
                             hspace=0.36, left=0.09, right=0.985, top=0.905, bottom=0.04)
    a1 = fig.add_subplot(outer[0])
    axes = [a1]
    for i, n in ((1, 2), (2, 2), (3, 1), (4, 1)):
        sub = outer[i].subgridspec(n, 1, hspace=0.08)
        axes += [fig.add_subplot(sub[j], sharex=a1) for j in range(n)]
    draw(fig, axes, d, cfg, CONFIRMED_BY.get(s.id, "confirmed"))

    fig.suptitle("A suggested model for anomaly detection".upper(), fontsize=26, fontweight="bold",
                 color=INK, x=0.015, ha="left", y=0.995, va="top")
    fig.text(0.015, 0.962, "How low-cost sensors can punch above their weight",
             fontsize=15, color=MUTED, ha="left", va="top")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=DPI, bbox_inches="tight")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
