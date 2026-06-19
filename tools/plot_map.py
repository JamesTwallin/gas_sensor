#!/usr/bin/env python3
"""Render gas-sensor survey logs as a single map: the GPS track coloured by gas.

Unlike plot_survey.py (which makes a scrolling video), this draws static PNGs
per log -- an x/y scatter of the survey's lat/lon positions over a satellite
basemap, with each point coloured by the mapped signal at that spot. Good for
seeing *where* on the ground the readings spiked.

It takes no arguments: it renders EVERY *.csv in tools/data/ into tools/maps/.
Each log is mapped twice (see SIGNALS): <name>.png is the raw conditioned VOUT as
logged, and <name>_above_baseline.png is the rise above the rolling baseline (the
anomaly). Tweak the knobs below if you need to.

Alongside each map it also writes a matching <name>..._env.png, a cross-check that
scatters that signal against the logged temperature and humidity. MOX sensors are
confounded by the weather (humidity especially -- see docs/sensors.md), so a
hotspot that merely tracks the environment is a classic false positive; a high
Pearson correlation there flags the log for a human to eyeball before the map is
trusted.

Each SIGNALS entry sums one or more mV columns into the value it maps; edit the
list to add LPG (e.g. lpg_vout_mv) or to change which signals are drawn.

The basemap is Esri World Imagery (free satellite/aerial tiles, no API key)
served via contextily, and the tiles are cached locally under your contextily
cache dir -- so only the first render of a given area needs the network;
re-renders of the same patch are offline.

The CSV is the one written by src/main.cpp, columns:
  millis_since_boot,state,ch4_vout_mv,ch4_baseline_mv,ch4_dev_mv,
  lpg_vout_mv,lpg_baseline_mv,lpg_dev_mv,temp_c,humidity_pct,pressure_hpa,
  utc_iso8601,lat,lon,alt_m,sats,fix

Usage:
  pip install matplotlib pandas numpy contextily   # once, in your env
  python tools/plot_map.py                          # every tools/data/*.csv -> tools/maps/*.png
  python tools/plot_map.py --combine                # merge ALL tools/data/*.csv into one map
  python tools/plot_map.py --combine a.csv b.csv    # merge just these logs into one map
  python tools/plot_map.py --diff                   # CH4/LPG differential map (fossil vs biogenic)
  python tools/plot_map.py --diff a.csv b.csv       # differential over just these logs
  python tools/plot_map.py --diff --zoom            # differential cropped to the leak hotspot

With --combine the named logs (or every *.csv in tools/data/ if none are named)
are loaded individually -- so each log's own warm-up drop, jitter filter and GPS
smoothing still apply -- then their readings are pooled and rendered as a single
combined<suffix>.png (plus its _env.png) per signal. The route line is broken between logs so
no straight jump is drawn from the end of one survey to the start of the next;
the heatmap simply averages every reading that fell in each ground cell, across
all the pooled logs.

With --diff the same pooled logs are rendered as one differential.png. The CH4
and LPG channels are near-collinear in practice (they rise together with sensor
drift / weather), so instead of either channel this maps the COMMON-MODE-REJECTED
residual -- where the two channels disagree -- which is what carries source info:
red = LPG-rich (heavier-HC / fossil-leaning), blue = CH4-rich (biogenic-leaning).
Cells are shown only where the rig made several separate passes (so one-off
traffic puffs drop out) and where there's a real signal to type. A side panel
shows the (ch4, lpg) scatter with the fitted common-mode line. See docs/sensors.md.
"""

import glob
import math
import os
import sys

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # no display needed; we only save files
import matplotlib.pyplot as plt
import matplotlib.font_manager as font_manager
import contextily as ctx

# --- popsci house style -----------------------------------------------------
# Same Noto Sans Display look as plot_survey.py; the .ttf files sit alongside
# this script so the typography travels with it.
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
WARN = "#c0392b"        # red for the contamination flag
GAS_CMAP = "inferno"    # dark = little gas, bright = a lot

# Each log is mapped twice: once for the raw conditioned VOUT as logged, and once
# for the rise above the rolling baseline (the anomaly). Each SIGNALS entry is one
# heatmap -- its "cols" are summed into the mapped value, "label" titles it, and
# "suffix" is appended to the output filename ("" for the primary map). To map a
# combined CH4+LPG signal, add the matching lpg column to an entry's "cols".
SIGNALS = (
    {"cols": ("ch4_vout_mv",), "label": "CH4 raw VOUT", "suffix": ""},
    {"cols": ("ch4_dev_mv",), "label": "CH4 above baseline", "suffix": "_above_baseline"},
)

# Tweakables (no command-line args, by request).
# The element keeps settling for a while after the firmware reaches RUNNING (its
# on-device warm-up/baseline windows are deliberately short), so early readings
# drift high as it finishes heating. Discard this much of the survey, measured
# from the first RUNNING sample. Set to 0 to keep everything.
WARMUP_DROP_S = 120  # seconds of survey dropped as sensor warm-up
MARGIN_FRAC = 0.15   # padding around the track, as a fraction of its span
MIN_SPAN_M = 60.0    # minimum half-width of the map (m) so a tiny/parked track
                     # still gets a sensible amount of street context
POINT_SIZE = 22      # scatter marker area
# This is a *walking* survey, so a fix that implies moving faster than a brisk
# walk is GPS jitter (a position jump), not real travel -- discard it. We also
# require a minimum satellite count so weak fixes don't pollute the heatmap.
MAX_WALK_SPEED_MPS = 3.5  # ~12 km/h; faster apparent motion == bad fix, dropped
MIN_SATS = 5              # rows with fewer locked satellites are dropped
# After the jitter filter, the surviving track still wobbles sample-to-sample
# (consumer GPS is good to a few metres, not centimetres). Smooth lat/lon with a
# centred rolling mean over this many samples so the route reads as a clean line
# rather than a zigzag. The window is in samples (~1/s logging), so 5 averages
# roughly +-2 s of fixes. Set to 1 to disable smoothing.
GPS_SMOOTH_WINDOW = 17
BIN_SIZE_M =2     # heatmap cell size on the ground (m). Each cell shows the
                     # MEAN total gas of every reading that fell inside it, so
                     # passing the same spot twice averages rather than overplots.
HEATMAP_ALPHA = 0.75 # heatmap opacity so the basemap streets show through
# Above this |Pearson r| between total gas and an environment channel, the gas
# signal tracks temperature/humidity closely enough that hotspots are suspect --
# not proof of contamination, but a reason to eyeball the scatter before trusting
# the map. MOX sensors are confounded by humidity especially (see docs/sensors.md).
CONTAM_R = 0.5

# --- --diff mode (two-channel differential) ---------------------------------
# The CH4 and LPG channels are near-collinear in practice (r ~ 0.95): both rise
# together with whatever common driver dominates (sensor drift, board temp, and
# humidity when it varies). That shared "common-mode" component carries no source
# information. We fit it (lpg ~ a + b*ch4) and map the RESIDUAL -- where the two
# channels DISagree -- which does carry information (see docs/sensors.md):
#   residual > 0  ->  LPG richer than CH4 predicts  ->  heavier-HC / fossil-leaning
#   residual < 0  ->  CH4 richer than LPG predicts   ->  methane-selective / biogenic-leaning
# Common-mode rises (both together) cancel to ~0 residual and are NOT flagged --
# which also rejects a humidity step that lifts both channels at once.
DIFF_CH4_COL = "ch4_dev_mv"   # the two channels the differential is built from
DIFF_LPG_COL = "lpg_dev_mv"
# A passing vehicle is a one-time puff at a place-and-time; a real source is
# anchored and re-encountered on a return pass or a second survey. So only show a
# cell that was visited on at least this many separate passes -- which drops
# transient traffic spikes. A "visit" ends when the track leaves the cell for
# longer than VISIT_GAP_S (or crosses into another log). If the data has no
# revisits at all (a single straight pass), the filter is auto-disabled with a
# warning rather than blanking the map.
DIFF_MIN_VISITS = 2
VISIT_GAP_S = 30.0
# Residual is meaningless on near-baseline noise, so only colour cells whose mean
# magnitude (|ch4| + |lpg|) is above this percentile of all populated cells --
# i.e. show the differential only where there is actually a signal to type.
DIFF_MAG_PCT = 70
DIFF_CMAP = "RdBu_r"   # diverging: red = fossil-leaning (+), blue = biogenic-leaning (-)
# The single global fit removes the INSTANTANEOUS common mode but not a slowly
# CHANGING offset: over a long walk the two channels' adaptive baselines wander
# apart, leaving a residual that drifts monotonically with time (observed: several
# mV across a survey, larger than the real spatial spread). Mapped raw, that
# paints a fake time-gradient. So subtract each log's own linear-in-time trend
# from its residual, leaving only departures relative to that log's drift -- i.e.
# genuine spatial features. Set False to see the raw (drift-contaminated) residual.
DIFF_DETREND = True
# --diff --zoom crops the map to the leak instead of the whole survey. The centre
# is the magnitude-weighted centroid of the most fossil-leaning kept cells (the
# top ZOOM_TOPFRAC by residual), so a single noisy pixel can't yank the view; the
# crop is a fixed half-width so the leak fills the frame and the basemap pulls
# correspondingly deeper tiles. The scatter panel is unchanged (it's the whole
# survey's composition).
ZOOM_TOPFRAC = 0.2   # fraction of kept cells (highest residual) defining the hotspot
ZOOM_RADIUS_M = 80   # half-width of the zoomed view (m)

DPI = 150
# Esri World Imagery: free, no-token satellite/aerial tiles -- the closest legit
# stand-in for Google's satellite layer (Google's own tiles need an API key and
# their ToS forbids this use, so they aren't shipped with contextily). Swap to
# ctx.providers.OpenStreetMap.Mapnik for a plain street map if you prefer.
BASEMAP = ctx.providers.Esri.WorldImagery
MAX_ZOOM = 19        # provider's deepest tile level; a tiny track would otherwise
                     # make contextily ask for an invalid zoom 20+
# Logs live in tools/data/, resolved relative to this script so it works from any
# working directory. Each .png is written to tools/maps/.
DATA_DIR = os.path.join(_HERE, "data")

# Earth radius used by the Web Mercator (EPSG:3857) projection that web tiles use.
_R_MERC = 6378137.0


def lonlat_to_mercator(lon, lat):
    """Project lon/lat degrees to EPSG:3857 metres (what contextily tiles use).

    Done inline with the standard spherical formula so we don't need pyproj just
    to place a handful of points.
    """
    x = np.radians(lon) * _R_MERC
    y = np.log(np.tan(np.pi / 4.0 + np.radians(lat) / 2.0)) * _R_MERC
    return x, y


def haversine_m(lon1, lat1, lon2, lat2):
    """Great-circle distance in metres between two lon/lat points (degrees).

    Used for the walking-speed filter, where we need true ground distance --
    Web Mercator metres are stretched by ~1/cos(lat) and would inflate speeds.
    """
    r = 6371000.0  # mean Earth radius (m)
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.sqrt(a))


def drop_gps_jitter(gps):
    """Keep only fixes consistent with a walking pace; drop position jumps.

    Walks in time order, holding the last *accepted* point. A point implying a
    speed above MAX_WALK_SPEED_MPS from that anchor is treated as jitter and
    discarded (the anchor is not advanced, so the next point is still compared
    to the last good one -- a single bad jump doesn't strand the rest). dt comes
    from millis_since_boot, which is monotonic within a log; if it's missing or
    non-increasing we keep the point rather than guess.
    """
    if len(gps) < 2 or "millis_since_boot" not in gps.columns:
        return gps

    g = gps.sort_values("millis_since_boot")
    t = pd.to_numeric(g["millis_since_boot"], errors="coerce").to_numpy() / 1000.0
    lon = g["lon"].to_numpy()
    lat = g["lat"].to_numpy()

    keep = np.zeros(len(g), dtype=bool)
    keep[0] = True
    anchor = 0
    for i in range(1, len(g)):
        dt = t[i] - t[anchor]
        if not np.isfinite(dt) or dt <= 0:
            keep[i] = True          # can't judge speed -> don't drop
            anchor = i
            continue
        dist = haversine_m(lon[anchor], lat[anchor], lon[i], lat[i])
        if dist / dt <= MAX_WALK_SPEED_MPS:
            keep[i] = True
            anchor = i
        # else: jitter jump -- drop point i, keep anchor where it is
    return g[keep]


def smooth_gps(gps):
    """Smooth the lat/lon track with a centred rolling mean to kill the wobble.

    Run *after* drop_gps_jitter, so the big jumps are already gone and we're only
    averaging out the few-metre sample-to-sample noise of a consumer fix. Points
    are taken in time order (millis_since_boot) and each lat/lon is replaced by
    the mean of its GPS_SMOOTH_WINDOW-sample neighbourhood (min_periods=1 keeps
    the ends from going NaN). Only the positions move; gas/time columns are
    untouched, so a reading still carries its own value -- just snapped onto the
    de-jittered route. No-op if the window is < 2 or the track is too short.
    """
    if GPS_SMOOTH_WINDOW < 2 or len(gps) < 2:
        return gps
    g = (gps.sort_values("millis_since_boot")
         if "millis_since_boot" in gps.columns else gps).copy()
    for c in ("lat", "lon"):
        g[c] = g[c].rolling(GPS_SMOOTH_WINDOW, center=True, min_periods=1).mean()
    return g


def lonlat_bounds(ax):
    """Return (west, south, east, north) in lon/lat for the axis Mercator limits.

    The inverse of lonlat_to_mercator, used to ask contextily for an appropriate
    tile zoom level (it wants geographic bounds).
    """
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    west, east = (np.degrees(x / _R_MERC) for x in (x0, x1))
    south, north = (np.degrees(2.0 * np.arctan(np.exp(y / _R_MERC)) - np.pi / 2.0)
                    for y in (y0, y1))
    return west, south, east, north


def load_track(path):
    """Read the firmware CSV, keep only rows with a real GPS fix and position."""
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    for c in ["ch4_vout_mv", "lpg_vout_mv", "ch4_dev_mv", "lpg_dev_mv",
              "lat", "lon", "fix", "sats"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for need in ("lat", "lon"):
        if need not in df.columns:
            raise ValueError(f"missing column {need!r} (got {list(df.columns)})")

    # Only the 'running' state -- drop any rows logged in other states.
    if "state" in df.columns:
        df = df[df["state"].astype(str).str.strip().str.upper() == "RUNNING"]

    # Drop the warm-up tail: the first WARMUP_DROP_S of the survey, timed from the
    # earliest RUNNING sample, where the element is still heating and reads high.
    if WARMUP_DROP_S > 0 and "millis_since_boot" in df.columns:
        ms = pd.to_numeric(df["millis_since_boot"], errors="coerce")
        if ms.notna().any():
            before = len(df)
            df = df[ms - ms.min() >= WARMUP_DROP_S * 1000.0]
            dropped = before - len(df)
            if dropped:
                print(f"  dropped {dropped} row(s) in first {WARMUP_DROP_S:g}s "
                      f"(sensor warm-up)")

    # A GPS fix plus a non-zero, finite position. 0,0 is the null-island default
    # the firmware writes before it has a lock.
    gps = df[df.get("fix", 0) == 1].copy()
    gps = gps.dropna(subset=["lat", "lon"])
    gps = gps[(gps["lat"] != 0) | (gps["lon"] != 0)]

    # Require a decent satellite count -- weak fixes are the noisy ones.
    if "sats" in gps.columns:
        before = len(gps)
        gps = gps[gps["sats"] >= MIN_SATS]
        dropped = before - len(gps)
        if dropped:
            print(f"  dropped {dropped} row(s) with < {MIN_SATS} sats")

    # Drop fixes that imply faster-than-walking motion (GPS jitter/jumps).
    before = len(gps)
    gps = drop_gps_jitter(gps)
    dropped = before - len(gps)
    if dropped:
        print(f"  dropped {dropped} row(s) faster than "
              f"{MAX_WALK_SPEED_MPS:g} m/s (GPS jitter)")

    # Smooth the de-jittered track so the route reads as a line, not a zigzag.
    if GPS_SMOOTH_WINDOW >= 2 and len(gps) >= 2:
        gps = smooth_gps(gps)
        print(f"  smoothed GPS track (rolling mean, window {GPS_SMOOTH_WINDOW})")

    return gps


def pearson(a, b):
    """Pearson r between two arrays, ignoring pairs where either value is missing.

    Returns (r, n_used). r is nan if fewer than 3 valid pairs survive or either
    column is constant (no variance -> correlation undefined), which keeps the
    contamination check from firing on degenerate data.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    n = int(m.sum())
    if n < 3:
        return float("nan"), n
    a, b = a[m], b[m]
    if a.std() == 0 or b.std() == 0:
        return float("nan"), n
    return float(np.corrcoef(a, b)[0, 1]), n


def signal_total(df, cols):
    """Sum the given mV column(s) row-wise into one mapped signal (missing -> 0)."""
    total = pd.Series(0.0, index=df.index)
    for col in cols:
        total = total + pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0)
    return total.to_numpy()


def render_env(df, name, out_path, cols, signal_label):
    """Cross-check the mapped signal against the logged environment.

    Scatters the signal against temperature and humidity (one panel each) and
    annotates the Pearson correlation. A hotspot that merely tracks the weather
    is the classic MOX false positive; a high |r| flags the log for a human to
    eyeball before trusting its map. Returns True if a figure was written (i.e.
    at least one of temp/humidity was actually logged).
    """
    gas = signal_total(df, cols).astype(float)
    panels = []
    for col, label, unit in (("temp_c", "temperature", "°C"),
                             ("humidity_pct", "humidity", "%RH")):
        if col in df.columns:
            env = pd.to_numeric(df[col], errors="coerce").to_numpy()
            if np.isfinite(env).sum() >= 3:
                panels.append((label, unit, env))
    if not panels:
        print(f"  ({name}: no temp/humidity logged -- skipping env cross-check)")
        return False

    fig, axes = plt.subplots(1, len(panels), figsize=(5.5 * len(panels), 5),
                             squeeze=False)
    flagged = []
    for ax, (label, unit, env) in zip(axes[0], panels):
        r, n = pearson(env, gas)
        suspect = np.isfinite(r) and abs(r) >= CONTAM_R
        if suspect:
            flagged.append(label)

        ax.scatter(env, gas, c=gas, cmap=GAS_CMAP, s=POINT_SIZE,
                   edgecolors="none", alpha=0.85)
        if np.isfinite(r):  # least-squares trend line over the valid pairs
            m = np.isfinite(env) & np.isfinite(gas)
            slope, intercept = np.polyfit(env[m], gas[m], 1)
            xs = np.array([env[m].min(), env[m].max()])
            ax.plot(xs, intercept + slope * xs, color=INK, lw=1.2,
                    ls="--", alpha=0.7)

        rtxt = "n/a" if not np.isfinite(r) else f"{r:+.2f}"
        ax.set_title(f"vs {label}:  r = {rtxt}  (n={n})"
                     + ("   (!) tracks env" if suspect else ""),
                     fontsize=10, color=(WARN if suspect else MUTED), loc="left")
        ax.set_xlabel(f"{label} ({unit})", color=INK)
        ax.set_ylabel(f"{signal_label} (mV)", color=INK)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        print(f"  {name}: gas vs {label} r={rtxt} (n={n})"
              + ("  <-- possible contamination" if suspect else ""))

    verdict = ("possible contamination -- gas tracks " + " & ".join(flagged)
               if flagged else "no strong gas/environment correlation")
    fig.subplots_adjust(top=0.80)
    fig.suptitle(f"{name} {signal_label} environment cross-check", fontsize=15,
                 fontweight="bold", color=INK)
    fig.text(0.5, 0.88, verdict, fontsize=10, ha="center",
             color=(WARN if flagged else MUTED))
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out_path}")
    return True


def render(df, name, out_path, cols, label):
    """Render one loaded track to one map PNG. Returns True on success."""
    x, y = lonlat_to_mercator(df["lon"].to_numpy(), df["lat"].to_numpy())

    # Square the view around the track's centre, with padding, so the basemap
    # aspect ratio stays true (1 m east == 1 m north on screen).
    cx, cy = (x.min() + x.max()) / 2.0, (y.min() + y.max()) / 2.0
    half = max(x.max() - cx, y.max() - cy, MIN_SPAN_M)
    half *= 1.0 + MARGIN_FRAC

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(cx - half, cx + half)
    ax.set_ylim(cy - half, cy + half)
    ax.set_aspect("equal")

    # Bin the readings onto a regular ground grid and take the MEAN gas per cell,
    # so revisiting a spot averages its readings instead of overplotting points.
    # Edges are built outward from the view centre in BIN_SIZE_M steps so the grid
    # always covers the (square, padded) extent.
    gas = signal_total(df, cols)
    n_half = int(math.ceil(half / BIN_SIZE_M))
    x_edges = cx + np.arange(-n_half, n_half + 1) * BIN_SIZE_M
    y_edges = cy + np.arange(-n_half, n_half + 1) * BIN_SIZE_M
    gas_sum, _, _ = np.histogram2d(x, y, bins=[x_edges, y_edges], weights=gas)
    counts, _, _ = np.histogram2d(x, y, bins=[x_edges, y_edges])
    with np.errstate(invalid="ignore"):
        mean = gas_sum / counts          # empty cells -> 0/0 = nan
    mean = np.ma.masked_invalid(mean)    # masked cells render transparent

    # Faint line for the survey route, heatmap of binned-mean gas on top. White,
    # not ink, so the route + markers stay visible over dark satellite imagery.
    # When several logs are pooled (--combine), draw each one's route separately
    # so no straight jump is drawn between the end of one survey and the next.
    if "_seg" in df.columns:
        seg = df["_seg"].to_numpy()
        for s in np.unique(seg):
            m = seg == s
            ax.plot(x[m], y[m], color="white", lw=0.8, alpha=0.6, zorder=2)
    else:
        ax.plot(x, y, color="white", lw=0.8, alpha=0.6, zorder=2)
    # pcolormesh wants C shaped (ny, nx); histogram2d gives (nx, ny) -> transpose.
    sc = ax.pcolormesh(x_edges, y_edges, mean.T, cmap=GAS_CMAP,
                       alpha=HEATMAP_ALPHA, zorder=3, shading="flat")

    # contextily picks a zoom from the extent; cap it so a small (e.g. parked)
    # track does not request a level deeper than the provider serves.
    zoom = min(ctx.tile._calculate_zoom(*lonlat_bounds(ax)), MAX_ZOOM)
    try:
        ctx.add_basemap(ax, source=BASEMAP,
                        crs="EPSG:3857", zoom=zoom, attribution_size=6)
    except Exception as e:  # noqa: BLE001 - still emit the track if tiles fail
        print(f"  ({name}: no basemap -- {e})")

    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label(f"mean {label} (mV)", color=INK)
    cb.outline.set_visible(False)

    fig.suptitle(f"{name} {label} heatmap", fontsize=18,
                 fontweight="bold", color=INK, x=0.12, ha="left", y=0.92)
    ax.set_title(f"{label} (mV), averaged over all "
                 f"GPS readings in each {BIN_SIZE_M:g} m cell along the route",
                 fontsize=9, color=MUTED, loc="left")

    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out_path}")
    return True


def resolve_csvs(names):
    """Turn the names given after --combine into paths under tools/data/.

    A bare name is looked up in DATA_DIR (with .csv appended if missing); a path
    that already exists is used as-is. With no names, every *.csv in DATA_DIR is
    returned. Exits with a clear message if a named log can't be found.
    """
    if not names:
        return sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
    paths = []
    for n in names:
        for cand in (n, n + ".csv", os.path.join(DATA_DIR, n),
                     os.path.join(DATA_DIR, n + ".csv")):
            if os.path.exists(cand):
                paths.append(cand)
                break
        else:
            sys.exit(f"can't find log {n!r} (looked in {DATA_DIR} too)")
    return paths


def map_each(map_dir):
    """Default mode: map every *.csv in tools/data/, one PNG per SIGNALS entry.

    Each log yields, per signal, a <name><suffix>.png heatmap and a
    <name><suffix>_env.png environment cross-check.
    """
    csvs = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
    if not csvs:
        sys.exit(f"No *.csv files in {DATA_DIR}")

    print(f"Mapping {len(csvs)} log(s):")
    ok = 0
    for csv_path in csvs:
        name = os.path.basename(csv_path)
        stem = os.path.splitext(name)[0]
        try:
            df = load_track(csv_path)
            if len(df) < 1:
                print(f"  skip {name}: no GPS-fixed rows")
                continue
            for sig in SIGNALS:
                out_path = os.path.join(map_dir, stem + sig["suffix"] + ".png")
                env_path = os.path.join(map_dir, stem + sig["suffix"] + "_env.png")
                render(df, name, out_path, sig["cols"], sig["label"])
                render_env(df, name, env_path, sig["cols"], sig["label"])
            ok += 1
        except Exception as e:  # noqa: BLE001 - one bad log should not stop the batch
            print(f"  skip {csv_path}: {e}")
    print(f"Done: {ok}/{len(csvs)} mapped.")


def load_pool(names):
    """Load the chosen logs and concatenate them into one pooled frame.

    Each log is loaded (and filtered/smoothed) independently, then concatenated
    with a per-log _seg id (0,1,2,...) so downstream code can tell the surveys
    apart -- to break the route line between them, and to treat a different log as
    a different "visit" to a place. Returns (pooled_df, n_logs); exits if nothing
    usable was found.
    """
    csvs = resolve_csvs(names)
    if not csvs:
        sys.exit(f"No *.csv files in {DATA_DIR}")

    parts = []
    for seg, csv_path in enumerate(csvs):
        name = os.path.basename(csv_path)
        try:
            df = load_track(csv_path)
        except Exception as e:  # noqa: BLE001 - one bad log should not stop the batch
            print(f"  skip {csv_path}: {e}")
            continue
        if len(df) < 1:
            print(f"  skip {name}: no GPS-fixed rows")
            continue
        df = df.copy()
        df["_seg"] = seg
        parts.append(df)
        print(f"  + {name}: {len(df)} reading(s)")

    if not parts:
        sys.exit("Nothing to pool: no GPS-fixed rows in the chosen logs.")
    return pd.concat(parts, ignore_index=True), len(parts)


def map_combined(names, map_dir):
    """--combine mode: pool the chosen logs and render one combined map per signal.

    The pooled frame goes through the same render/render_env as a single log; the
    per-log _seg id keeps render() from drawing a jump between separate surveys.
    """
    print("Combining logs:")
    combined, n = load_pool(names)
    name = f"combined ({n} logs)"
    for sig in SIGNALS:
        render(combined, name, os.path.join(map_dir, "combined" + sig["suffix"] + ".png"),
               sig["cols"], sig["label"])
        render_env(combined, name, os.path.join(map_dir, "combined" + sig["suffix"] + "_env.png"),
                   sig["cols"], sig["label"])
    print(f"Done: combined {n} log(s), {len(combined)} reading(s).")


def assign_visits(df):
    """Tag each reading with a _visit id: a separate pass through its location.

    Readings are ordered by (log, time). A new visit starts whenever the log
    changes or the gap since the previous reading exceeds VISIT_GAP_S -- i.e. the
    track left and came back later, or it's a different survey. Within one
    continuous pass the id is constant. Per cell, the count of DISTINCT visit ids
    is how many separate times the rig was there, which is what the persistence
    filter thresholds on. Returns the frame ordered, with an int _visit column.
    """
    g = df.sort_values(["_seg", "millis_since_boot"]).copy()
    seg = g["_seg"].to_numpy()
    t = pd.to_numeric(g["millis_since_boot"], errors="coerce").to_numpy() / 1000.0
    vid = np.zeros(len(g), dtype=int)
    cur = 0
    for i in range(1, len(g)):
        gap = t[i] - t[i - 1]
        if seg[i] != seg[i - 1] or not np.isfinite(gap) or gap > VISIT_GAP_S:
            cur += 1
        vid[i] = cur
    g["_visit"] = vid
    return g


def render_diff(df, name, out_path, n_logs, zoom=False):
    """Render the two-channel differential map + a composition scatter panel.

    Left: a ground heatmap of the common-mode-rejected residual (red = LPG-rich /
    fossil-leaning, blue = CH4-rich / biogenic-leaning), shown only for cells that
    both clear the persistence filter (>= DIFF_MIN_VISITS separate passes, so
    transient traffic puffs drop out) and carry a real signal (mean magnitude
    above the DIFF_MAG_PCT percentile). Right: the (ch4, lpg) scatter with the
    fitted common-mode line, points coloured by the same residual. With zoom=True
    the map is cropped to the fossil-leaning hotspot (the leak) instead of the
    whole survey. Returns True on success.
    """
    for c in (DIFF_CH4_COL, DIFF_LPG_COL):
        if c not in df.columns:
            print(f"  skip diff: missing column {c!r}")
            return False
    ch4 = pd.to_numeric(df[DIFF_CH4_COL], errors="coerce").to_numpy()
    lpg = pd.to_numeric(df[DIFF_LPG_COL], errors="coerce").to_numpy()
    ok = np.isfinite(ch4) & np.isfinite(lpg)
    if ok.sum() < 10 or np.nanstd(ch4[ok]) == 0:
        print("  skip diff: not enough varied CH4/LPG data for a common-mode fit")
        return False

    # Common-mode fit lpg ~ a + b*ch4, then the residual each reading carries.
    b, a = np.polyfit(ch4[ok], lpg[ok], 1)
    resid = lpg - (a + b * ch4)
    mag = np.abs(ch4) + np.abs(lpg)

    g = df.copy()
    g["_resid"] = resid
    g["_mag"] = mag
    g = g[np.isfinite(g["_resid"]) & np.isfinite(g["_mag"])]

    # Strip each log's slow baseline drift (see DIFF_DETREND): subtract the
    # linear-in-time trend of the residual within each log so the map shows
    # spatial departures, not the time-gradient of two diverging baselines.
    if DIFF_DETREND:
        t_all = pd.to_numeric(g["millis_since_boot"], errors="coerce").to_numpy() / 1000.0
        r_all = g["_resid"].to_numpy().astype(float)
        seg_all = g["_seg"].to_numpy()
        for sv in np.unique(seg_all):
            sel = seg_all == sv
            t, r = t_all[sel], r_all[sel]
            m = np.isfinite(t) & np.isfinite(r)
            if m.sum() >= 3 and np.ptp(t[m]) > 0:
                slope, intercept = np.polyfit(t[m], r[m], 1)
                r_all[sel] = r - (intercept + slope * t)
        g = g.copy()
        g["_resid"] = r_all

    g = assign_visits(g)

    x, y = lonlat_to_mercator(g["lon"].to_numpy(), g["lat"].to_numpy())

    # Square, padded view (same framing as render()).
    cx, cy = (x.min() + x.max()) / 2.0, (y.min() + y.max()) / 2.0
    half = max(x.max() - cx, y.max() - cy, MIN_SPAN_M) * (1.0 + MARGIN_FRAC)
    n_half = int(math.ceil(half / BIN_SIZE_M))
    x_edges = cx + np.arange(-n_half, n_half + 1) * BIN_SIZE_M
    y_edges = cy + np.arange(-n_half, n_half + 1) * BIN_SIZE_M

    # Per-cell aggregate: mean residual, mean magnitude, distinct-visit count.
    ix = np.floor((x - x_edges[0]) / BIN_SIZE_M).astype(int)
    iy = np.floor((y - y_edges[0]) / BIN_SIZE_M).astype(int)
    cells = pd.DataFrame({"ix": ix, "iy": iy, "resid": g["_resid"].to_numpy(),
                          "mag": g["_mag"].to_numpy(), "visit": g["_visit"].to_numpy()})
    agg = cells.groupby(["ix", "iy"]).agg(
        resid=("resid", "mean"), mag=("mag", "mean"),
        visits=("visit", "nunique")).reset_index()

    # Magnitude gate: only type cells where there is actually a signal.
    mag_gate = float(np.percentile(agg["mag"], DIFF_MAG_PCT)) if len(agg) else 0.0
    gated = agg[agg["mag"] >= mag_gate]
    # Persistence filter: of those, keep only cells seen on enough separate passes
    # (drops one-off traffic puffs). If nothing is revisited, disable rather than
    # blank the map. The persistence filter is the survey-wide traffic guard; in
    # --zoom we're already on a confirmed hotspot, so we skip it and show every
    # signal-bearing cell -- otherwise a real single-pass leak (whose revisits
    # scatter across adjacent fine cells) would be filtered right out.
    max_visits = int(agg["visits"].max())
    min_visits = DIFF_MIN_VISITS
    if max_visits < DIFF_MIN_VISITS:
        print(f"  (diff: no cell was revisited {DIFF_MIN_VISITS}x "
              f"(max {max_visits}) -- persistence filter disabled)")
        min_visits = 1
    kept = gated if zoom else gated[gated["visits"] >= min_visits]
    note = "mag-gated only (zoom)" if zoom else f">= {min_visits} visit(s)"
    print(f"  diff: fit lpg = {a:.1f} + {b:.2f}*ch4; "
          f"{len(kept)}/{len(agg)} cells kept ({note}, mag >= {mag_gate:.1f} mV)")
    if kept.empty:
        print("  skip diff: no cells survived the persistence + magnitude filter")
        return False

    nx, ny = len(x_edges) - 1, len(y_edges) - 1
    grid = np.full((nx, ny), np.nan)
    for _, r in kept.iterrows():
        if 0 <= int(r.ix) < nx and 0 <= int(r.iy) < ny:
            grid[int(r.ix), int(r.iy)] = r.resid
    grid = np.ma.masked_invalid(grid)
    # The map shows the (detrended) per-cell residual; the scatter shows the raw
    # residual (distance off the common-mode line). They answer different
    # questions, so each gets its own symmetric diverging scale.
    vmax = float(np.nanmax(np.abs(kept["resid"]))) or 1.0
    vmax_sc = float(np.nanmax(np.abs(resid[ok]))) or 1.0

    # View extent: the whole survey, or cropped to the leak if zoom was asked for.
    view_cx, view_cy, view_half = cx, cy, half
    if zoom:
        kx = x_edges[0] + (kept["ix"].to_numpy() + 0.5) * BIN_SIZE_M
        ky = y_edges[0] + (kept["iy"].to_numpy() + 0.5) * BIN_SIZE_M
        kr = kept["resid"].to_numpy()
        # The leak is the most fossil-leaning cells: take the top fraction by
        # residual and use their residual-weighted centroid, so one stray pixel
        # can't drag the crop off the actual hotspot.
        ntop = max(1, int(round(len(kr) * ZOOM_TOPFRAC)))
        sel = np.argsort(kr)[::-1][:ntop]
        w = np.clip(kr[sel], 0, None)
        if w.sum() <= 0:
            w = np.ones(len(sel))
        view_cx = float(np.average(kx[sel], weights=w))
        view_cy = float(np.average(ky[sel], weights=w))
        view_half = ZOOM_RADIUS_M
        lon_c = math.degrees(view_cx / _R_MERC)
        lat_c = math.degrees(2.0 * math.atan(math.exp(view_cy / _R_MERC)) - math.pi / 2.0)
        print(f"  diff zoom: hotspot at {lat_c:.5f}, {lon_c:.5f} "
              f"(top {ntop} cell(s), peak residual {float(kr[sel].max()):+.1f} mV); "
              f"crop +/-{ZOOM_RADIUS_M:g} m")

    fig, (axm, axs) = plt.subplots(1, 2, figsize=(15, 8),
                                   gridspec_kw={"width_ratios": [1.25, 1]})

    # --- left: the differential map ---
    axm.set_xlim(view_cx - view_half, view_cx + view_half)
    axm.set_ylim(view_cy - view_half, view_cy + view_half)
    axm.set_aspect("equal")
    if "_seg" in g.columns:
        seg = g["_seg"].to_numpy()
        for s in np.unique(seg):
            m = seg == s
            axm.plot(x[m], y[m], color="white", lw=0.8, alpha=0.6, zorder=2)
    else:
        axm.plot(x, y, color="white", lw=0.8, alpha=0.6, zorder=2)
    mesh = axm.pcolormesh(x_edges, y_edges, grid.T, cmap=DIFF_CMAP,
                          vmin=-vmax, vmax=vmax, alpha=HEATMAP_ALPHA,
                          zorder=3, shading="flat")
    zoom_level = min(ctx.tile._calculate_zoom(*lonlat_bounds(axm)), MAX_ZOOM)
    try:
        ctx.add_basemap(axm, source=BASEMAP, crs="EPSG:3857", zoom=zoom_level,
                        attribution_size=6)
    except Exception as e:  # noqa: BLE001 - still emit the map if tiles fail
        print(f"  ({name}: no basemap -- {e})")
    axm.set_xticks([]); axm.set_yticks([])
    for sp in axm.spines.values():
        sp.set_visible(False)
    cb = fig.colorbar(mesh, ax=axm, fraction=0.046, pad=0.02)
    cb.set_label("LPG/CH4 differential (mV): + fossil-leaning / - biogenic-leaning",
                 color=INK)
    cb.outline.set_visible(False)

    # --- right: the composition scatter with the common-mode line ---
    sc = axs.scatter(ch4[ok], lpg[ok], c=resid[ok], cmap=DIFF_CMAP,
                     vmin=-vmax_sc, vmax=vmax_sc, s=12, edgecolors="none", alpha=0.7)
    xs = np.array([np.nanmin(ch4[ok]), np.nanmax(ch4[ok])])
    axs.plot(xs, a + b * xs, color=INK, lw=1.3, ls="--", alpha=0.8,
             label=f"common mode: lpg = {a:.1f} + {b:.2f}·ch4")
    axs.set_xlabel("CH4 above baseline (mV)", color=INK)
    axs.set_ylabel("LPG above baseline (mV)", color=INK)
    axs.legend(loc="upper left", fontsize=8, frameon=False)
    for sp in ("top", "right"):
        axs.spines[sp].set_visible(False)
    axs.set_title("each reading; distance off the line = differential",
                  fontsize=9, color=MUTED, loc="left")

    fig.suptitle(f"{name} CH4/LPG differential (common-mode rejected)"
                 + ("  -- zoomed to leak" if zoom else ""),
                 fontsize=16, fontweight="bold", color=INK, x=0.12, ha="left",
                 y=0.96)
    _persist = ("signal-bearing cells (persistence off for zoom)" if zoom
                else f"shown only where revisited >= {min_visits}x and signal is real")
    axm.set_title(f"{'drift-corrected ' if DIFF_DETREND else ''}residual per "
                  f"{BIN_SIZE_M:g} m cell, {_persist}",
                  fontsize=9, color=MUTED, loc="left")

    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out_path}")
    return True


def map_diff(names, map_dir, zoom=False):
    """--diff mode: pool the chosen logs and render one differential map.

    With zoom=True the map is cropped to the fossil-leaning hotspot (the leak) and
    written to differential_zoom.png; otherwise the full survey -> differential.png.
    """
    print("Differential map:")
    pooled, n = load_pool(names)
    label = f"combined ({n} logs)" if n > 1 else os.path.basename(resolve_csvs(names)[0])
    out = "differential_zoom.png" if zoom else "differential.png"
    render_diff(pooled, label, os.path.join(map_dir, out), n, zoom=zoom)
    print(f"Done: differential over {n} log(s), {len(pooled)} reading(s).")


def main():
    map_dir = os.path.join(_HERE, "maps")
    os.makedirs(map_dir, exist_ok=True)

    args = sys.argv[1:]
    if args and args[0] == "--combine":
        # --combine [name ...]: pool the named logs (or every tools/data/*.csv if
        # none are named) into a single combined.png + combined_env.png.
        map_combined(args[1:], map_dir)
    elif args and args[0] == "--diff":
        # --diff [--zoom] [name ...]: pool the named logs (or all) and render one
        # differential.png -- the common-mode-rejected CH4/LPG residual, with a
        # persistence filter that drops transient (traffic) spikes. --zoom anywhere
        # in the args crops the map to the leak hotspot (-> differential_zoom.png).
        rest = args[1:]
        zoom = "--zoom" in rest
        names = [a for a in rest if a != "--zoom"]
        map_diff(names, map_dir, zoom=zoom)
    else:
        # No arguments: render every *.csv in tools/data/ to tools/maps/. Each log
        # yields <name>.png (the gas map) and <name>_env.png (the env cross-check).
        map_each(map_dir)


if __name__ == "__main__":
    main()
