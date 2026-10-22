"""Plots for docs/board.md (the rev E design note).

  python hardware/board/gen/note_plots.py

The numbers are copied from docs/REPORT.md (held-out results on the four
October 2026 surveys); regenerate them with `python tools/replay.py report`.
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
from matplotlib import patheffects  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(BOARD))
OUT = os.path.join(REPO, "docs", "rev_e")
os.makedirs(OUT, exist_ok=True)

INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GREY = "#a9a8a2"


def style(ax):
    ax.grid(True, axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.yaxis.label.set_color(INK2)
    ax.xaxis.label.set_color(INK2)


# ---- 1. Annotated board ---------------------------------------------------------
img = mpimg.imread(os.path.join(BOARD, "preview", "render_top.png"))
# Find the board in the render: olive solder mask (green above blue) against the
# lavender background (blue above green).
dark = (img[:, :, 1] - img[:, :, 2]) > 0.04
cols = np.flatnonzero(dark.mean(axis=0) > 0.3)
rows_ = np.flatnonzero(dark.mean(axis=1) > 0.3)
X0, X1, Y0, Y1 = cols[0], cols[-1], rows_[0], rows_[-1]


def px(x, y):
    return X0 + x / 66.0 * (X1 - X0), Y0 + y / 36.0 * (Y1 - Y0)


pad = 260
fig, ax = plt.subplots(figsize=(12, 7.2))
ax.imshow(img, extent=(0, img.shape[1], img.shape[0], 0))
ax.set_axis_off()
notes = [
    ((64.0, 15.5), (80.0, 10.0), "J3 + edge notch: socket for the\nair blade (heated thermistor +\noutside-air SHT40)"),
    ((52.8, 1.9), (47.0, -10.0), "J4: CO module + fan pads\n(5 V, GND, TX, RX, 5 V, GND)"),
    ((59.0, 2.0), (80.0, -4.0), "R22: CH4 heater shunt"),
    ((51.6, 11.0), (66.0, -10.0), "R28/C24: heated\nthermistor feed"),
    ((57.0, 15.5), (80.0, 22.0), "R25: LPG heater shunt"),
    ((52.6, 16.0), (58.0, 47.0), "U8: 2nd ADS1115 -\nheater currents + 3V3 rail"),
    ((47.5, 15.5), (36.0, 47.0), "U6: AIN2 now reads the\nheated thermistor"),
    ((33.9, 7.6), (24.0, -10.0), "C28/C29: more VSYS bulk\nat the boost input"),
    ((8.5, 30.0), (4.0, 47.0), "on-board SHT40:\nnow the case reading"),
    ((22.6, 24.7), (20.0, 47.0), "RST: now right\nabove BOOT"),
]
halo = [patheffects.withStroke(linewidth=3.2, foreground=INK)]
for (bx, by), (tx, ty), text in notes:
    an = ax.annotate(text, xy=px(bx, by), xytext=px(tx, ty), fontsize=9, color=INK, ha="center", va="center",
                     bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GREY, lw=0.8),
                     arrowprops=dict(arrowstyle="-", color="white", lw=1.4, shrinkA=0, shrinkB=6))
    an.arrow_patch.set_path_effects(halo)
    # a ring on the part itself: white with a dark edge, visible on the dark board
    ax.plot(*px(bx, by), "o", ms=11, mfc="none", mec="white", mew=1.8, path_effects=halo)
ax.set_xlim(X0 - 40, X1 + pad)
ax.set_ylim(Y1 + 190, Y0 - 190)
ax.set_title("Rev E: what is new (same outline, holes and connectors as rev B; RST now stacked above BOOT)",
             loc="left", fontsize=10, color=INK)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "board_annotated.png"), dpi=110)
plt.close(fig)

# ---- 1a. Rev B and rev E side by side ----------------------------------------------
# Rev B's render comes from the rev-b git tag; both renders use the same camera, so
# the same board-finding works on both. Boxes are rev E courtyards (gen/courtyards.py).
import io  # noqa: E402
import subprocess  # noqa: E402

revb_png = subprocess.run(["git", "-C", REPO, "show", "rev-b:hardware/phone_board/preview/render_top.png"],
                          capture_output=True, check=True).stdout
img_b = mpimg.imread(io.BytesIO(revb_png), format="png")
new_parts = [
    ((63.5, 66.0, 13.15, 17.85), "J3"), ((48.4, 57.1, 0.3, 3.5), "J4"),
    ((57.5, 60.5, 1.2, 2.8), "R22"), ((55.5, 58.5, 14.7, 16.3), "R25"), ((50.8, 55.5, 12.8, 19.2), "U8"),
    ((50.5, 52.7, 10.0, 12.0), "R28 C24"), ((50.3, 54.1, 19.3, 21.3), "R33 R34 C27"),
    ((31.8, 35.9, 5.8, 9.5), "C28 C29"),((12.1, 14.3, 18.7, 20.7), "C13 C14"),
    ((46.4, 48.4, 1.9, 2.9), "R30"),
    ((18.8, 26.4, 21.85, 27.55), "SW2 (RST, moved)"), ((25.95, 34.95, 18.25, 20.35), "TP1-TP4 (moved)"),
]
fig, axs = plt.subplots(2, 1, figsize=(10, 11.5))
for ax, im, title in ((axs[0], img_b, "Rev B (built, tested 2026-09-28)"),
                      (axs[1], img, "Rev E (designed): new and moved parts boxed in yellow")):
    d = (im[:, :, 1] - im[:, :, 2]) > 0.04
    cx = np.flatnonzero(d.mean(axis=0) > 0.3)
    cy = np.flatnonzero(d.mean(axis=1) > 0.3)
    bx0, bx1, by0, by1 = cx[0], cx[-1], cy[0], cy[-1]
    ax.imshow(im, extent=(0, im.shape[1], im.shape[0], 0))
    ax.set_xlim(bx0 - 15, bx1 + 15)
    ax.set_ylim(by1 + 15, by0 - 15)
    ax.set_axis_off()
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    if im is img:
        sx, sy = (bx1 - bx0) / 66.0, (by1 - by0) / 36.0
        for (x0, x1, y0, y1), label in new_parts:
            ax.add_patch(plt.Rectangle((bx0 + x0 * sx - 3, by0 + y0 * sy - 3), (x1 - x0) * sx + 6,
                                       (y1 - y0) * sy + 6, fill=False, ec=YELLOW, lw=2.2,
                                       path_effects=[patheffects.withStroke(linewidth=4, foreground=INK)]))
fig.text(0.02, 0.012, "Same outline, holes, cans, USB-C, switch, BOOT button and SHT40 tongue as rev B. RST now "
         "sits above BOOT, so rev E\ntakes the rev E front shell (RST pen hole moved). The rest is rev C's circuit "
         "re-packed into the same space.",
         fontsize=9, color=INK2)
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(os.path.join(OUT, "previous_vs_current.png"), dpi=110)
plt.close(fig)

# ---- 1b. The on-board SHT40 reads case air ---------------------------------------
# Survey analysis (2026-10-10): SHT40 temperature minus its own 10-minute median,
# by GPS speed band, on the three drives. Warmer when slow = case air heated by the
# sensor heaters and cooled by airflow, not the outside air.
bands = ["< 3", "3-15", "15-40", "40-70", "> 70"]
drives = {"D1 drive": [0.26, 0.29, 0.31, -0.11, 0.00], "D2 drive": [0.65, 0.60, 0.59, -0.08, -0.20],
          "D3 drive": [0.24, 0.22, 0.40, -0.13, -0.16]}
fig, ax = plt.subplots(figsize=(8.5, 4.0))
x = np.arange(len(bands))
for i, ((name, v), c) in enumerate(zip(drives.items(), [BLUE, ORANGE, YELLOW])):
    ax.bar(x + (i - 1) * 0.26, v, 0.24, color=c, label=name)
ax.axhline(0, color=INK2, lw=0.8)
ax.set_xticks(x, [b + " km/h" for b in bands])
ax.set_ylabel("SHT40 reading vs its 10-min median, degC")
ax.set_title("The on-board SHT40 runs warm when the device is slow and cools at speed:\n"
             "it is reading air inside the case, warmed by the sensor heaters.", loc="left", fontsize=10, color=INK)
ax.legend(frameon=False, fontsize=8, loc="upper right")
style(ax)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "sht40_case_air.png"), dpi=110)
plt.close(fig)

# ---- 2. Where the detector's error is: residual spread vs timescale --------------
# REPORT.md section 3: residual SD left after removing a centred rolling mean of W s.
W = ["5 s", "15 s", "30 s", "60 s", "120 s", "all"]
rows = {
    "D1 drive": [1.4, 3.0, 4.7, 7.3, 10.8, 14.0],
    "D2 drive": [1.0, 1.9, 4.0, 8.4, 13.9, 16.1],
    "W1 walk": [1.8, 3.0, 4.3, 6.5, 7.9, 8.6],
    "D3 drive": [1.0, 2.1, 3.7, 5.8, 8.4, 11.3],
}
fig, ax = plt.subplots(figsize=(8.5, 4.2))
xs = np.arange(len(W))
cols = [BLUE, ORANGE, AQUA, YELLOW]
for (name, v), c in zip(rows.items(), cols):
    ax.plot(xs, v, color=c, lw=2, marker="o", ms=5, label=name)
ax.axhspan(0.3, 0.5, color=GREY, alpha=0.35, lw=0)
ax.text(0.05, 0.62, "electronic noise 0.3-0.5 mV", fontsize=8, color=INK2)
ax.set_xticks(xs, W)
ax.set_xlabel("events shorter than this are kept (timescale)")
ax.set_ylabel("unexplained CH4 signal, mV (SD)")
ax.set_title("What the temperature/humidity model cannot explain is slow: tens of seconds to minutes.\n"
             "That is the timescale of stops, starts and speed changes - airflow over the sensors.",
             loc="left", fontsize=10, color=INK)
ax.legend(frameon=False, fontsize=8, loc="upper left")
style(ax)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "error_timescale.png"), dpi=110)
plt.close(fig)

# ---- 3. What an airflow input buys (GPS speed as an offline stand-in) -------------
labels = ["D1 drive", "D2 drive", "D3 drive", "W1 walk"]
before = [11.4, 12.4, 6.9, 8.9]
after = [7.2, 6.5, 5.7, 10.1]
fig, ax = plt.subplots(figsize=(8.5, 4.0))
x = np.arange(len(labels))
ax.bar(x - 0.19, before, 0.36, color=GREY, label="temperature + humidity only (rev B/C today)")
ax.bar(x + 0.19, after, 0.36, color=BLUE, label="+ an airflow input (GPS speed as stand-in)")
for i in range(len(labels)):
    ax.text(x[i] - 0.19, before[i] + 0.2, f"{before[i]:.1f}", ha="center", fontsize=8, color=INK2)
    ax.text(x[i] + 0.19, after[i] + 0.2, f"{after[i]:.1f}", ha="center", fontsize=8, color=INK2)
ax.set_xticks(x, labels)
ax.set_ylabel("unexplained CH4 signal, mV (robust SD)")
ax.set_title("An airflow measurement nearly halves the CH4 error on drives.\n"
             "GPS speed only stands in for it offline; rev E measures the air over the sensors directly.",
             loc="left", fontsize=10, color=INK)
ax.legend(frameon=False, fontsize=8, loc="upper right")
ax.set_ylim(0, 15)
style(ax)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "airflow_gain.png"), dpi=110)
plt.close(fig)

# ---- 4. Old spike detector vs the new detector (same data, same false-alarm rate) --
sizes = [45, 90, 135]
old = [0.00, 0.05, 1.00]          # app slope detector, 10 s plume (0.8 false alarms / h)
new = [0.18, 0.77, 0.95]          # anomaly detector, 10 s plume (0.85 false alarms / h)
fig, ax = plt.subplots(figsize=(8.5, 4.0))
x = np.arange(len(sizes))
ax.bar(x - 0.19, [100 * v for v in old], 0.36, color=GREY, label="old: slope > 25 mV/s (app)")
ax.bar(x + 0.19, [100 * v for v in new], 0.36, color=BLUE, label="new: conditions model + robust threshold")
for i in range(len(sizes)):
    ax.text(x[i] - 0.19, 100 * old[i] + 2, f"{100 * old[i]:.0f}%", ha="center", fontsize=8, color=INK2)
    ax.text(x[i] + 0.19, 100 * new[i] + 2, f"{100 * new[i]:.0f}%", ha="center", fontsize=8, color=INK2)
ax.set_xticks(x, [f"{s} mV" for s in sizes])
ax.set_xlabel("synthetic plume on the CH4 sensor (assumed 10 s shape)")
ax.set_ylabel("plumes detected, %")
ax.set_ylim(0, 112)
ax.set_title("At the same false-alarm rate (about 0.8 per hour), the new detector catches mid-sized\n"
             "plumes the old one misses. Rev E's airflow input is aimed at the small ones.",
             loc="left", fontsize=10, color=INK)
ax.legend(frameon=False, fontsize=8, loc="upper left")
style(ax)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "old_vs_new.png"), dpi=110)
plt.close(fig)

# ---- 5. Expected thermistor response (datasheet-based estimate) ------------------
v = np.linspace(0, 3, 61)
g = 0.12 + 0.094 * np.sqrt(v)       # HARDWARE.md 1.4, BR16 estimate (King's law)
idx = g / 0.12 - 1
fig, ax = plt.subplots(figsize=(8.5, 3.8))
ax.plot(v * 3.6, idx, color=BLUE, lw=2)
for kmh, lab in ((0, "stopped"), (4.5, "walking"), (10.8, "slow traffic")):
    i = np.argmin(abs(v * 3.6 - kmh))
    ax.plot(v[i] * 3.6, idx[i], "o", color=BLUE, ms=6, mec="white", mew=1.5)
    ax.text(v[i] * 3.6 + 0.2, idx[i] - 0.12, lab, fontsize=8, color=INK2)
ax.set_xlabel("air speed over the bead, km/h")
ax.set_ylabel("airflow index (0 = still air)")
ax.set_title("Estimated thermistor response (to be calibrated): steepest at low air speeds,\n"
             "exactly where stops and stop-start traffic upset the gas sensors.",
             loc="left", fontsize=10, color=INK)
style(ax)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "thermistor_response.png"), dpi=110)
plt.close(fig)
print("wrote plots to", OUT)
