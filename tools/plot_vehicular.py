"""One-figure summary of a vehicular leak detection: the 11 October 2026 positive
control (survey D4), replayed with a model fitted without D4.

Drawn in the repo's popsci house style (as plot_map.py / plot_survey.py: Noto
Sans Display, despined axes, dashed grid, inferno for gas) over Esri World
Imagery satellite tiles.

  python tools/plot_vehicular.py [--out docs/report/vehicular_detection.png]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import contextily as ctx  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.font_manager as font_manager  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anomaly_core as core  # noqa: E402
import replay as rp  # noqa: E402

# --- popsci house style (as plot_map.py) -------------------------------------
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

INK = "#222222"         # near-black for text
MUTED = "#666666"       # grey for subtitles
WARN = "#c0392b"        # red: the leak marker
GAS_CMAP = "inferno"    # dark = little gas, bright = a lot
C_CH4 = "#2a6fc4"       # the app's CH4 blue (app/src/ui/theme.ts, light)
C_LPG = "#b8621f"       # the app's LPG orange
SHADE = "#eeeeee"
BASEMAP = ctx.providers.Esri.WorldImagery
DPI = 150

# The leak's position is survey data, so it lives in the (git-ignored) survey index.
LEAK = tuple(next(e for e in json.loads(rp.MANIFEST.read_text())["surveys"] if "leak_latlon" in e)["leak_latlon"])
WINDOW = ("2026-10-11 12:16:30", "2026-10-11 12:24:30")
PASSES = (("12:17:40", "12:18:10", "pass 1\n65 km/h"),
          ("12:18:40", "12:19:10", "pass 2\n43 km/h"),
          ("12:20:40", "12:21:30", "pass 3\nstopped"))
MAP_HALF_M = 140        # half-height of the map view, metres
BIN_SIZE_M = 5          # heatmap cell, as plot_map.py
HEATMAP_ALPHA = 0.75
_R_MERC = 6378137.0


def lonlat_to_mercator(lon, lat):
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    return np.radians(lon) * _R_MERC, np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * _R_MERC


def load():
    surveys = rp.load_manifest()
    cfg = rp.config()
    coefs = rp.loso_coefs(surveys, cfg)  # D4 is scored by a model that never saw it
    s = next(x for x in surveys if x.id == "D4")
    o, events = core.replay(s.inputs, rp.cfg_with(cfg, coefs["D4"]))
    df = s.df.copy()
    # GPS updates about once a second (15-20 m at driving speed) while gas is
    # logged at 4 Hz: place each sample between the fixes either side of it, so
    # the 5 m cells form a continuous track instead of a chequerboard.
    t = df["millis_since_boot"].to_numpy(float)
    la, lo = df["lat"].to_numpy(float), df["lon"].to_numpy(float)
    new_fix = np.r_[True, (np.diff(la) != 0) | (np.diff(lo) != 0)]
    for c in ("lat", "lon"):
        v = df[c].to_numpy(float)
        ok = new_fix & np.isfinite(v)
        df[c] = np.interp(t, t[ok], v[ok])
    res = pd.DataFrame({"utc": pd.to_datetime(df["utc_iso8601"]),
                        "ch4": o["res"][:, 0], "lpg": o["res"][:, 1], "sig_ch4": o["sigma"][:, 0],
                        "lat": df["lat"], "lon": df["lon"], "ready": o["ready"],
                        "speed": rp.gps_speed_kmh(df)})
    w = res[(res.utc >= WINDOW[0]) & (res.utc <= WINDOW[1]) & res.ready]
    n_leak = sum(1 for e in events if any(e.t_start_ms < b and e.t_end_ms >= a for a, b in s.leak_ms))
    return w, n_leak


def draw_map(fig, ax, cax, w: pd.DataFrame, n_leak: int) -> None:
    x, y = lonlat_to_mercator(w.lon, w.lat)
    lx, ly = lonlat_to_mercator(LEAK[1], LEAK[0])
    bb = ax.get_position()
    aspect = (bb.width * fig.get_figwidth()) / (bb.height * fig.get_figheight())
    x0, x1 = lx - MAP_HALF_M * aspect, lx + MAP_HALF_M * aspect
    y0, y1 = ly - MAP_HALF_M, ly + MAP_HALF_M
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)

    # As plot_map.py: bin onto a ground grid, mean per cell, so the three passes
    # average rather than overplot; white route line underneath.
    xe = np.arange(x0, x1 + BIN_SIZE_M, BIN_SIZE_M)
    ye = np.arange(y0, y1 + BIN_SIZE_M, BIN_SIZE_M)
    lpg = w.lpg.to_numpy()
    tot, _, _ = np.histogram2d(x, y, bins=[xe, ye], weights=lpg)
    cnt, _, _ = np.histogram2d(x, y, bins=[xe, ye])
    with np.errstate(invalid="ignore"):
        mean = np.ma.masked_invalid(tot / cnt)
    ax.plot(x, y, color="white", lw=0.8, alpha=0.6, zorder=2)
    mesh = ax.pcolormesh(xe, ye, mean.T, cmap=GAS_CMAP, vmin=0, vmax=300,
                         alpha=HEATMAP_ALPHA, zorder=3, shading="flat")
    ax.scatter([lx], [ly], marker="*", s=700, color=WARN, edgecolors="white", linewidths=1.2, zorder=4)
    ax.annotate("hotspot", (lx, ly), xytext=(-17, -1), textcoords="offset points", ha="right",
                fontsize=12, fontweight="bold", color="white")
    try:
        ctx.add_basemap(ax, source=BASEMAP, crs="EPSG:3857", zoom=18, attribution_size=6)
    except Exception as e:  # noqa: BLE001 - still emit the track if tiles fail
        print(f"  (no basemap -- {e})")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title(f"Rural methane plume found by a low-cost, home-made sensor ",
                 fontsize=16, color=MUTED, loc="left")

    cb = fig.colorbar(mesh, cax=cax)
    cb.set_label("gas reading above normal (mV)", color=INK)
    cb.outline.set_visible(False)
    cb.solids.set_alpha(1)


def _despine(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.tick_params(colors=INK)


def draw_series(ax_gas, ax_spd, w: pd.DataFrame) -> None:
    day = WINDOW[0][:10]
    for a, b, label in PASSES:
        t0, t1 = pd.Timestamp(f"{day} {a}"), pd.Timestamp(f"{day} {b}")
        for ax in (ax_gas, ax_spd):
            ax.axvspan(t0, t1, color=SHADE, zorder=0, lw=0)
        ax_gas.text(t0 + (t1 - t0) / 2, 575, label, ha="center", va="top", fontsize=9, color=MUTED,
                    linespacing=1.15)
    noise = float(np.median(w.sig_ch4))
    ax_gas.axhspan(-3 * noise, 3 * noise, color="#dddddd", zorder=1, lw=0)
    ax_gas.text(w.utc.iloc[-1], 3 * noise + 8, "everyday noise", ha="right", va="bottom", fontsize=10, color=MUTED)
    ax_gas.plot(w.utc, w.lpg, color=C_LPG, lw=2, label="LPG sensor (TGS2610)", zorder=3)
    ax_gas.plot(w.utc, w.ch4, color=C_CH4, lw=2, label="CH4 sensor (TGS2611)", zorder=3)
    ax_gas.set_ylim(-40, 580)
    ax_gas.set_yticks([0, 100, 200, 300, 400, 500])
    ax_gas.set_title("The two gas sensors as the car went by (drive-bys shaded)",
                     fontsize=9, color=MUTED, loc="left")
    ax_gas.set_ylabel("above normal (mV)", color=INK)
    ax_gas.legend(loc="upper right", bbox_to_anchor=(1.0, 0.86), frameon=False)
    ax_gas.tick_params(labelbottom=False)

    ax_spd.plot(w.utc, w.speed, color=INK, lw=1.5)
    ax_spd.set_ylim(0, 100)
    ax_spd.set_yticks([0, 50, 100])
    ax_spd.set_ylabel("km/h", color=INK)
    ax_spd.set_xlabel(f"UTC, {day}", color=INK)
    ax_spd.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    for ax in (ax_gas, ax_spd):
        _despine(ax)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=rp.REPORT_DIR / "vehicular_detection.png")
    args = ap.parse_args()
    w, n_leak = load()

    # Layout in inches so the map, the colour bar and the two charts share edges.
    fw, fh = 7.5, 9.6
    left, width = 0.75, 5.6                # map and charts share these
    cb_gap, cb_w = 0.15, 0.22
    top_title, map_h = 0.74, 4.1
    map_left = 0.12                        # map runs out to the figure's left text edge
    gap1, gas_h, gap2, spd_h = 0.42, 2.4, 0.12, 0.85

    def box(x, y_top, w_in, h_in):
        return [x / fw, 1 - (y_top + h_in) / fh, w_in / fw, h_in / fh]

    fh += map_h - 3.7
    fig = plt.figure(figsize=(fw, fh))
    y = top_title
    ax_map = fig.add_axes(box(map_left, y, left + width - map_left, map_h))
    cax = fig.add_axes(box(left + width + cb_gap, y, cb_w, map_h))
    y += map_h + gap1
    ax_gas = fig.add_axes(box(left, y, width, gas_h))
    y += gas_h + gap2
    ax_spd = fig.add_axes(box(left, y, width, spd_h), sharex=ax_gas)

    draw_map(fig, ax_map, cax, w, n_leak)
    draw_series(ax_gas, ax_spd, w)
    # Title flush with the map's left edge, the figure's leftmost element.
    x_text = map_left / fw
    fig.suptitle("Gas leak spotted on a drive-by".upper(), fontsize=28, fontweight="bold", color=INK,
                 x=x_text, ha="left", y=1 - 0.08 / fh, va="top")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=DPI, bbox_inches="tight")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
