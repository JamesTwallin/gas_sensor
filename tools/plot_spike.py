"""Bench-log plot: ppm estimate with and without temperature/humidity correction,
overlaid, plus the first time-derivative of the corrected estimate on a twin axis
with spikes flagged. The derivative is the plume indicator: a plume arrives as a
step, so d(ppm)/dt spikes, while slow drift (warm-up, weather) stays near zero.

Usage:
    python tools/plot_spike.py LOG [--gas ch4|lpg] [--ro OHM] [--out PNG]
                                   [--smooth S] [--sigma K]

LOG is either the firmware's bench CSV (rows "ms,seq,adc,ch4_tap_mv,...") or
the bridge watch log ("HH:MM:SS ms=.. seq=.. ch4_vrl=.. lpg_vrl=.. T=.. RH=..").
The ppm maths mirrors app/src/core/ppm.ts (Figaro datasheet curves, Table 1
temperature/humidity factors normalised to 20 C / 65 %RH).
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---- Figaro curves, as in app/src/core/ppm.ts ---------------------------------
TEMPS = [-10, 0, 10, 20, 30, 40]
RHS = [35, 50, 65, 95]


@dataclass
class Curve:
    gas: str
    ref_ppm: float
    exponent: float
    ro_typical: float
    rows: list[list[float | None]]


TGS2611 = Curve("CH4", 5000, -0.47, 2150, [
    [None, None, None, 1.51], [None, None, 1.45, 1.25], [None, 1.33, 1.19, 1.02],
    [1.25, 1.11, 1.0, 0.87], [1.05, 0.94, 0.86, 0.77], [0.92, 0.82, 0.76, 0.69]])
TGS2610 = Curve("LPG", 1800, -0.53, 2150, [
    [None, None, None, 1.6], [None, None, 1.5, 1.35], [None, 1.5, 1.23, 1.08],
    [1.52, 1.19, 1.0, 0.85], [1.23, 0.94, 0.79, 0.68], [0.98, 0.75, 0.61, 0.53]])

RL_OHM, VC_MV = 40000.0, 5000.0   # rev B load circuit (Info JSON rl_ohm / vc_mv)


def _interp(pts: list[tuple[float, float]], x: float) -> float:
    if len(pts) == 1 or x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        if x <= bx:
            return ay + (x - ax) / (bx - ax) * (by - ay)
    return pts[-1][1]


def env_factor(curve: Curve, temp_c: float, rh: float) -> float:
    t = min(max(temp_c, TEMPS[0]), TEMPS[-1])
    h = min(max(rh, RHS[0]), RHS[-1])
    pts = []
    for ti, temp in enumerate(TEMPS):
        row = [(RHS[ri], v) for ri, v in enumerate(curve.rows[ti]) if v is not None]
        if row:
            pts.append((temp, _interp(row, h)))
    return _interp(pts, t) if pts else 1.0


def estimate_ppm(rs: np.ndarray, ro: float, curve: Curve, temp=None, rh=None) -> np.ndarray:
    factor = np.ones_like(rs)
    if temp is not None and rh is not None:
        factor = np.array([env_factor(curve, t, h) if np.isfinite(t) and np.isfinite(h) else 1.0
                           for t, h in zip(temp, rh)])
    ratio = rs / ro / factor
    with np.errstate(invalid="ignore", divide="ignore"):
        return curve.ref_ppm * np.power(ratio, 1.0 / curve.exponent)


# ---- log parsing ----------------------------------------------------------------
WATCH = re.compile(r"ms=(\d+) seq=(\d+) ch4_vrl=(\d+) lpg_vrl=(\d+) T=([\d.-]+|) RH=([\d.-]+|)")


def load(path: str):
    ms, ch4, lpg, temp, rh = [], [], [], [], []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = WATCH.search(line)
        if m:
            ms.append(int(m[1])); ch4.append(float(m[3])); lpg.append(float(m[4]))
            temp.append(float(m[5]) if m[5] else np.nan); rh.append(float(m[6]) if m[6] else np.nan)
            continue
        f = line.strip().split(",")
        if len(f) >= 12 and f[0].isdigit() and f[2] in ("ads", "esp"):
            ms.append(int(f[0])); ch4.append(float(f[5])); lpg.append(float(f[6]))
            temp.append(float(f[9]) if f[9] else np.nan); rh.append(float(f[10]) if f[10] else np.nan)
    if not ms:
        sys.exit(f"no sample rows found in {path}")
    return (np.array(ms, float), np.array(ch4), np.array(lpg), np.array(temp), np.array(rh))


def rs_from_vrl(vrl_mv: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore"):
        return np.where(vrl_mv > 1, RL_OHM * (VC_MV - vrl_mv) / vrl_mv, np.nan)


# ---- plot -------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log")
    ap.add_argument("--gas", choices=["ch4", "lpg"], default="ch4")
    ap.add_argument("--ro", type=float, help="Ro in ohms (default: datasheet typical)")
    ap.add_argument("--smooth", type=float, default=1.0, help="derivative window, seconds")
    ap.add_argument("--sigma", type=float, default=4.0, help="spike threshold in robust sigmas")
    ap.add_argument("--out", help="PNG path (default: next to the log)")
    a = ap.parse_args()

    ms, ch4, lpg, temp, rh = load(a.log)
    curve = TGS2611 if a.gas == "ch4" else TGS2610
    vrl = ch4 if a.gas == "ch4" else lpg
    ro = a.ro or curve.ro_typical
    t = (ms - ms[0]) / 1000.0
    rs = rs_from_vrl(vrl)
    ppm_raw = estimate_ppm(rs, ro, curve)
    ppm_cor = estimate_ppm(rs, ro, curve, temp, rh)

    # first derivative of the corrected estimate, over a --smooth second window
    dt = np.median(np.diff(t)) if len(t) > 1 else 0.25
    win = max(1, int(round(a.smooth / dt)))
    d = np.full_like(ppm_cor, np.nan)
    d[win:] = (ppm_cor[win:] - ppm_cor[:-win]) / (t[win:] - t[:-win])
    # Threshold: k robust sigmas of the derivative, but never below 5 % of the
    # signal's own span per second, so a flat trace does not flag its own noise.
    good = np.isfinite(d)
    mad = np.nanmedian(np.abs(d[good] - np.nanmedian(d[good]))) if good.any() else 0
    span = np.nanpercentile(ppm_cor, 95) - np.nanpercentile(ppm_cor, 5)
    thresh = max(a.sigma * 1.4826 * mad, 0.05 * span) if good.any() else np.inf
    spikes = np.where(good & (d > thresh))[0]

    # palette: reference categorical slots 1/2 for the two ppm lines, slot 3 for the derivative
    c_cor, c_raw, c_der, c_flag = "#2a78d6", "#eb6834", "#1baf7a", "#d03b3b"
    ink, ink2, grid = "#0b0b0b", "#52514e", "#e6e5e1"

    fig, ax = plt.subplots(figsize=(12, 5.2), dpi=150)
    fig.patch.set_facecolor("#fcfcfb"); ax.set_facecolor("#fcfcfb")
    ax.plot(t, ppm_cor, color=c_cor, lw=2, label="ppm, T/RH corrected")
    ax.plot(t, ppm_raw, color=c_raw, lw=2, ls=(0, (4, 2)), label="ppm, uncorrected (20 °C / 65 %RH)")
    ax.set_ylabel(f"{curve.gas} estimate (ppm, Ro = {ro:.0f} Ω)", color=ink)
    ax.set_xlabel("time (s)", color=ink)
    ax.grid(True, color=grid, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(grid)
    ax.tick_params(colors=ink2)

    ax2 = ax.twinx()
    ax2.fill_between(t, 0, np.nan_to_num(d), color=c_der, alpha=0.18, lw=0)
    ax2.plot(t, d, color=c_der, lw=1.4, label=f"d(ppm)/dt, {a.smooth:g} s window")
    if np.isfinite(thresh):
        ax2.axhline(thresh, color=c_flag, lw=1, ls=":", label=f"spike threshold ({a.sigma:g}σ robust)")
    if len(spikes):
        ax2.scatter(t[spikes], d[spikes], s=36, color=c_flag, zorder=5, label=f"spike ({len(spikes)} samples)")
        # annotate the start of each burst (bursts closer than 5 s count as one)
        gap = int(round(5.0 / dt))
        starts = [i for k, i in enumerate(spikes) if k == 0 or spikes[k] - spikes[k - 1] > gap]
        for i in starts:
            ax2.annotate("spike", (t[i], d[i]), textcoords="offset points", xytext=(6, 8),
                         color=c_flag, fontsize=9, fontweight="bold")
    ax2.set_ylabel("first derivative (ppm / s)", color=ink)
    ax2.spines["top"].set_visible(False); ax2.spines["right"].set_color(grid)
    ax2.tick_params(colors=ink2)
    lo, hi = np.nanmin(d), np.nanmax(d)
    pad = 0.15 * (hi - lo if hi > lo else 1)
    ax2.set_ylim(lo - pad, hi + pad)

    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", frameon=False, fontsize=9, labelcolor=ink2)
    tmean = np.nanmean(temp); rhmean = np.nanmean(rh)
    ax.set_title(f"{curve.gas}: corrected vs uncorrected estimate, with first derivative as the spike indicator"
                 f"   (mean {tmean:.1f} °C, {rhmean:.0f} %RH)", color=ink, fontsize=11, loc="left")
    fig.tight_layout()
    out = a.out or re.sub(r"\.[^.]+$", "", a.log) + f"_{a.gas}_spike.png"
    fig.savefig(out)
    print(f"wrote {out}: {len(t)} samples, {len(spikes)} spike samples above {thresh:.1f} ppm/s")


if __name__ == "__main__":
    main()
