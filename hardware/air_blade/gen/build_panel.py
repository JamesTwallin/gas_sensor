"""Panelize the blade for JLCPCB assembly ("Panel by Customer").

The blade (5.7 x 14.9 mm) is below JLC's minimum assembly size, and JLC's own
panel option only offers V-cut, which cannot follow the forked tip or the
shoulders. So this script builds a 3 x 2 panel with KiKit: a 5 mm frame with
tooling holes and fiducials, and mouse-bite tabs only on the straight body
sides (between the fork and the shoulders). The tips, the slot and the foot
stay clean, because a tab stub there would catch in the case slot or stop the
shoulders sitting flat on rev E.

Run with KiCad's python (needs `python -m pip install kikit` there), after
gen/export.py:

  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/build_panel.py

Writes production/panel/: gerbers.zip, bom.csv, cpl.csv and a render.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import zipfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import design  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

CLI = os.environ.get("KICAD_CLI", r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe")
PCB = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb")
OUT = os.path.join(PROJECT_DIR, "production", "panel")
PANEL = os.path.join(PROJECT_DIR, "build", "panel", design.PROJECT + "_panel.kicad_pcb")

COLS, ROWS = 3, 2
SPACE = 2.0       # mm between blades (and between blades and the frame)
FRAME = 5.0       # mm frame width: JLC's minimum rail for assembly
# One tab per long side, centred in the straight stretch of body side between
# the bottom of the fork (y = 5.8) and the shoulders (y = 11.2). KiKit's
# "fixed" tabs are centred on the board's bounding box (y = 7.45), which is
# inside that stretch.
TAB_W = 1.5
# The SDA and GND tracks run 0.2-0.35 mm inside the body sides, so the mouse-bite
# holes sit wholly outside the blade (offset = -radius): holes cutting into the
# board would sever them. That leaves a ~0.25 mm nub per tab to file flush.

PRESET = {
    "layout": {"type": "grid", "rows": ROWS, "cols": COLS, "space": f"{SPACE}mm",
               "renameref": "{orig}_{n}"},
    "tabs": {"type": "fixed", "hcount": 1, "vcount": 0, "hwidth": f"{TAB_W}mm"},
    "cuts": {"type": "mousebites", "drill": "0.5mm", "spacing": "0.8mm", "offset": "-0.25mm",
             "prolong": "0.5mm"},
    "framing": {"type": "frame", "width": f"{FRAME}mm", "space": f"{SPACE}mm", "cuts": "none"},
    "tooling": {"type": "3hole", "hoffset": "2.5mm", "voffset": "2.5mm", "size": "1.152mm"},
    "fiducials": {"type": "3fid", "hoffset": "5mm", "voffset": "2.5mm",
                  "coppersize": "1mm", "opening": "2mm"},
    "text": {"type": "simple", "text": "AIR BLADE A  3x2", "anchor": "mt",
             "voffset": "2.5mm", "hjustify": "center", "vjustify": "center", "width": "1mm",
             "height": "1mm", "thickness": "0.15mm"},
    "post": {"millradius": "0.5mm"},
}


def run(*args):
    print("kicad-cli", " ".join(args[:3]), "...")
    subprocess.run([CLI, *args], check=True, stdout=subprocess.DEVNULL)


def main():
    os.makedirs(os.path.dirname(PANEL), exist_ok=True)
    preset = os.path.join(os.path.dirname(PANEL), "preset.json")
    with open(preset, "w") as f:
        json.dump(PRESET, f, indent=1)
    subprocess.run([sys.executable, "-m", "kikit.ui", "panelize", "-p", preset, PCB, PANEL], check=True)

    shutil.rmtree(OUT, ignore_errors=True)
    gdir = os.path.join(OUT, "gerbers")
    os.makedirs(gdir)
    layers = ["F.Cu", "B.Cu", "F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen",
              "F.Mask", "B.Mask", "Edge.Cuts"]
    run("pcb", "export", "gerbers", "--layers", ",".join(layers), "--subtract-soldermask",
        "--no-protel-ext", "-o", gdir + os.sep, PANEL)
    run("pcb", "export", "drill", "--format", "excellon", "--drill-origin", "absolute",
        "--excellon-units", "mm", "-o", gdir + os.sep, PANEL)
    with zipfile.ZipFile(os.path.join(OUT, "gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gdir)):
            z.write(os.path.join(gdir, f), f)

    # Placement: each blade copy is the single board shifted (never rotated), so
    # apply the single board's KiCad->LCSC origin correction (gen/jlc_placement.json)
    # to every copy. JLC's Y axis points up, so KiCad's Y is negated.
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "jlc_placement.json")) as f:
        placement = json.load(f)
    parts = {p.ref: p for p in design.PARTS
             if not (p.virtual or p.dnp or getattr(p, "no_assembly", False))}
    board = pcbnew.LoadBoard(PANEL)
    rows, groups = [], {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        orig = ref.rsplit("_", 1)[0]
        if orig not in parts:
            continue  # fiducials, tooling holes
        r = placement[orig]
        pos = fp.GetPosition()
        x = pcbnew.ToMM(pos.x) + r["x"] - r["kicad_x"]
        y = pcbnew.ToMM(pos.y) + r["y"] - r["kicad_y"]
        rows.append([ref, f"{x:.4f}mm", f"{-y:.4f}mm", "Top", f"{r['rot'] % 360:g}"])
        p = parts[orig]
        groups.setdefault((p.value, p.footprint.split(":")[-1], p.lcsc or ""), []).append(ref)
    expected = len(parts) * COLS * ROWS
    if len(rows) != expected:
        raise SystemExit(f"found {len(rows)} placed parts in the panel, expected {expected}")
    rows.sort(key=lambda row: (row[0].rsplit("_", 1)[0], int(row[0].rsplit("_", 1)[1])))
    with open(os.path.join(OUT, "cpl.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(rows)
    with open(os.path.join(OUT, "bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, fp, lcsc), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            w.writerow([value, ",".join(sorted(refs)), fp, lcsc])

    bb = board.GetBoardEdgesBoundingBox()
    print(f"panel {pcbnew.ToMM(bb.GetWidth()):.1f} x {pcbnew.ToMM(bb.GetHeight()):.1f} mm, "
          f"{COLS * ROWS} blades, {len(rows)} placements")
    for side in ("top", "bottom"):
        run("pcb", "render", "--side", side, "--quality", "high", "--width", "1600", "--height", "1600",
            "--background", "opaque", "-o", os.path.join(OUT, f"render_{side}.png"), PANEL)
    print("done:", OUT)


if __name__ == "__main__":
    main()
