#!/usr/bin/env python3
"""Render gas-sensor survey logs (the firmware's CSVs) into videos.

The video plays back in real time (the data is resampled onto a uniform 1/FPS
grid, so it matches the survey second-for-second even if the firmware's sample
spacing jittered). Each frame is a scrolling area chart of how much gas is in
the air -- each sensor's rise above its own rolling background, with methane and
LPG summed into one signal -- over the last `--window` seconds. Styled for a popsci
audience: bold Noto Sans Display headline, qualitative "none -> a lot" y-axis
(the voltage doesn't map to a known concentration), despined axes.

It takes no arguments: it renders EVERY *.csv in tools/data/ to its own
<name>.mp4 in tools/videos/. Tweak FPS / WINDOW_S / STRIDE below if you need
to. Frames are streamed straight to ffmpeg, so no intermediate image files are
ever written to disk -- nothing to clean up.

The CSV is the one written by src/main.cpp, columns:
  millis_since_boot,state,ch4_vout_mv,ch4_baseline_mv,ch4_dev_mv,
  lpg_vout_mv,lpg_baseline_mv,lpg_dev_mv,temp_c,humidity_pct,pressure_hpa,
  utc_iso8601,lat,lon,alt_m,sats,fix

Usage:
  pip install -r tools/requirements.txt   # once, in your env
  python tools/plot_survey.py             # every tools/data/*.csv -> tools/videos/*.mp4

ffmpeg comes from the imageio-ffmpeg pip package, so nothing system-wide is needed.
"""

import glob
import os
import sys

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # no display needed; we only save files
import matplotlib.pyplot as plt
import matplotlib.font_manager as font_manager
from matplotlib.animation import FuncAnimation, FFMpegWriter

# Point matplotlib at the ffmpeg binary bundled with imageio-ffmpeg, so the user
# does not have to install ffmpeg separately.
try:
    import imageio_ffmpeg
    plt.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # noqa: BLE001 - fall back to a system ffmpeg if present
    pass

# --- popsci house style -----------------------------------------------------
# Big bold Noto Sans Display headlines, despined axes, dashed grid, punchy
# colours. The two .ttf files sit alongside this script so the look travels with it.
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

GAS_COLOR = "#2ECC71"   # vivid green  -- combined methane + LPG signal
INK = "#222222"         # near-black for text
MUTED = "#666666"       # grey for subtitles

REQUIRED = ["millis_since_boot", "ch4_vout_mv", "ch4_baseline_mv",
            "lpg_vout_mv", "lpg_baseline_mv", "ch4_dev_mv"]

# Tweakables (no command-line args, by request).
FPS = 4          # video frames per second; 4 matches the firmware's log rate
WINDOW_S = 12.0  # seconds of history in the scrolling time-series panel
STRIDE = 1       # render every Nth row (>1 to shorten a long render)
# The element keeps settling for a while after the firmware reaches RUNNING (its
# on-device warm-up/baseline windows are deliberately short), so early readings
# drift high as it finishes heating. Discard this much of the survey, measured
# from the first RUNNING sample. Set to 0 to keep everything. (Matches plot_map.py.)
WARMUP_DROP_S = 120  # seconds of survey dropped as sensor warm-up
# Logs live in tools/data/, resolved relative to this script so it works from any
# working directory. Each .mp4 is written alongside its CSV.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def load_log(path):
    """Read the firmware CSV into a DataFrame, tolerating blank GPS fields."""
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns {missing} (got {list(df.columns)})")
    for c in ["ch4_vout_mv", "ch4_baseline_mv", "ch4_dev_mv", "lpg_vout_mv",
              "lpg_baseline_mv", "lpg_dev_mv", "lat", "lon", "alt_m", "sats", "fix"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "fix" not in df.columns:
        df["fix"] = 0
    df["elapsed_s"] = (df["millis_since_boot"] - df["millis_since_boot"].iloc[0]) / 1000.0
    return df


def render(csv_path, out_path, fps, window, stride):
    """Render one CSV log to one video file. Returns True on success."""
    df = load_log(csv_path)
    if df.empty:
        print(f"  skip {csv_path}: no rows")
        return False

    fig, ax_ts = plt.subplots(figsize=(5, 5))
    fig.subplots_adjust(top=0.80, bottom=0.12, left=0.10, right=0.96)

    # Only the RUNNING portion of the survey is interesting -- drop warm-up/idle
    # rows and stitch the surviving segments into one continuous timeline, so the
    # video has no flat interpolated gaps where non-running time was cut out.
    state = df.get("state")
    if state is not None:
        df = df[state.astype(str).str.strip().str.upper() == "RUNNING"]
        df = df.reset_index(drop=True)

    # Drop the warm-up tail: the first WARMUP_DROP_S of the survey, timed from the
    # earliest RUNNING sample, where the element is still heating and reads high.
    if WARMUP_DROP_S > 0 and "millis_since_boot" in df.columns and not df.empty:
        ms = pd.to_numeric(df["millis_since_boot"], errors="coerce")
        if ms.notna().any():
            before = len(df)
            df = df[ms - ms.min() >= WARMUP_DROP_S * 1000.0].reset_index(drop=True)
            dropped = before - len(df)
            if dropped:
                print(f"  dropped {dropped} row(s) in first {WARMUP_DROP_S:g}s "
                      f"(sensor warm-up)")

    if len(df) < 2:
        print(f"  skip {csv_path}: fewer than 2 RUNNING samples")
        plt.close(fig)
        return False
    raw_t = df["elapsed_s"].to_numpy()
    dt = np.diff(raw_t)
    good = dt[dt > 0]
    nominal = float(np.median(good)) if len(good) else 1.0 / fps
    # Collapse the jumps left behind by removed (non-running) stretches to one
    # nominal sample step; keep genuine sample spacing everywhere else.
    dt = np.where(dt > 5 * nominal, nominal, np.maximum(dt, 0.0))
    src_t = np.concatenate(([0.0], np.cumsum(dt)))

    # Resample onto a uniform real-time grid so each frame is exactly 1/fps of
    # real elapsed time -- the video then matches the survey second-for-second,
    # even if the firmware's sample spacing jittered or dropped samples. Numeric
    # series are linearly interpolated; per-frame title metadata uses the nearest
    # original row (so text fields like state/utc_iso8601 stay intact).
    duration = float(src_t[-1])
    if duration <= 0:
        print(f"  skip {csv_path}: zero-duration RUNNING segment")
        plt.close(fig)
        return False
    elapsed = np.arange(0.0, duration + 0.5 / fps, 1.0 / fps)
    ch4_v = np.interp(elapsed, src_t, df["ch4_vout_mv"].to_numpy())
    ch4_b = np.interp(elapsed, src_t, df["ch4_baseline_mv"].to_numpy())
    lpg_v = np.interp(elapsed, src_t, df["lpg_vout_mv"].to_numpy())
    lpg_b = np.interp(elapsed, src_t, df["lpg_baseline_mv"].to_numpy())
    # We don't know what the voltage means in real units, and we don't care which
    # gas is which -- the story is just "how much gas is in the air". So take each
    # sensor's rise above its own rolling background (clipped at zero) and SUM
    # them into a single "how much gas" signal.
    ch4_d = np.clip(ch4_v - ch4_b, 0, None)
    lpg_d = np.clip(lpg_v - lpg_b, 0, None)
    total = ch4_d + lpg_d
    ymax = max(float(np.nanmax(total)) * 1.15, 150.0)  # floor so a calm log isn't all noise
    # nearest original row index for each grid time (for the subtitle text)
    right = np.searchsorted(src_t, elapsed).clip(1, len(src_t) - 1)
    nearest = np.where(elapsed - src_t[right - 1] <= src_t[right] - elapsed,
                       right - 1, right)
    frames = range(0, len(elapsed), max(1, stride))
    name = os.path.basename(csv_path)

    # Fixed popsci headline (drawn once; it survives the per-frame ax.clear()).
    fig.suptitle("GAS SENSOR READOUT", x=0.10, y=0.95,
                 ha="left", va="top", fontsize=22, fontweight="bold", color=INK)
    fig.text(0.10, 0.885, "Combustible gas the sensor detected during the survey",
             ha="left", va="top", fontsize=12, color=MUTED)

    def update(i):
        t_now = elapsed[i]

        ax_ts.clear()
        m = (elapsed >= t_now - window) & (elapsed <= t_now)
        # x is seconds relative to "now" (0 at the right edge, -window at left).
        x = elapsed[m] - t_now
        # Methane + LPG combined into one "how much gas" signal -- a single area.
        ax_ts.fill_between(x, total[m], color=GAS_COLOR, alpha=0.9)
        # Crisp line riding the top of the area for a bit of punch.
        ax_ts.plot(x, total[m], color=GAS_COLOR, lw=1.8)
        ax_ts.set_xlim(-window, 0)
        ax_ts.set_ylim(0, ymax)
        # Voltage doesn't map to a known concentration -> qualitative y-axis.
        ax_ts.set_yticks([0, ymax])
        ax_ts.set_yticklabels(["none", "a lot"], fontsize=12, color=INK)
        ax_ts.tick_params(axis="x", labelsize=10, colors=MUTED)
        ax_ts.tick_params(axis="y", length=0)
        for side in ("top", "right"):
            ax_ts.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax_ts.spines[side].set_color(MUTED)
        ax_ts.grid(axis="y", linestyle="--", alpha=0.35)
        ax_ts.set_axisbelow(True)

        # Live timestamp / state readout, tucked into the plot's top-right so it
        # never collides with the headline/subtitle above.
        row = df.iloc[nearest[i]]
        ts = row.get("utc_iso8601")
        ts = "" if (pd.isna(ts) or ts == "") else f"{ts}   "
        state = str(row.get("state", "")).strip()
        ax_ts.text(0.99, 0.96, f"{ts}{state}", transform=ax_ts.transAxes,
                   ha="right", va="top", fontsize=10, color=MUTED)
        if i % 50 == 0:
            print(f"  {name}: frame {i}/{len(elapsed)}", end="\r", flush=True)
        return []

    # FFMpegWriter pipes frames directly to ffmpeg -- no per-frame image files are
    # written to disk, so there is nothing to delete afterwards.
    ani = FuncAnimation(fig, update, frames=frames, blit=False)
    ani.save(out_path, writer=FFMpegWriter(fps=fps, bitrate=2400))
    plt.close(fig)
    print(f"  wrote {out_path}                       ")
    return True


def main():
    # No arguments: render every *.csv in tools/data/ to tools/videos/<name>.mp4.
    csvs = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
    if not csvs:
        sys.exit(f"No *.csv files in {DATA_DIR}")

    video_dir = os.path.join(os.path.dirname(DATA_DIR), "videos")
    os.makedirs(video_dir, exist_ok=True)

    print(f"Rendering {len(csvs)} log(s) at {FPS} fps:")
    ok = 0
    for csv_path in csvs:
        name = os.path.splitext(os.path.basename(csv_path))[0]
        out_path = os.path.join(video_dir, name + ".mp4")
        try:
            if render(csv_path, out_path, FPS, WINDOW_S, STRIDE):
                ok += 1
        except Exception as e:  # noqa: BLE001 - one bad log should not stop the batch
            print(f"  skip {csv_path}: {e}")
    print(f"Done: {ok}/{len(csvs)} rendered.")


if __name__ == "__main__":
    main()
