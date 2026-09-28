"""Export JLCPCB fabrication + assembly files and preview renders.

  python export.py

Writes hardware/phone_board/production/:
  gerbers.zip        upload as the PCB
  bom.csv            JLC BOM (Comment, Designator, Footprint, LCSC Part #)
  cpl.csv            JLC pick-and-place (Designator, Mid X, Mid Y, Layer, Rotation)
and hardware/phone_board/preview/: schematic PDF, per-layer PDF, 3D renders.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import design  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

CLI = os.environ.get("KICAD_CLI", r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe")
PCB = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb")
SCH = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_sch")
PROD = os.path.join(PROJECT_DIR, "production")
PREV = os.path.join(PROJECT_DIR, "preview")



def run(*args):
    print("kicad-cli", " ".join(args[:3]), "...")
    subprocess.run([CLI, *args], check=True, stdout=subprocess.DEVNULL)


def main():
    for d in (PROD, PREV):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    gdir = os.path.join(PROD, "gerbers")
    os.makedirs(gdir)
    cu = ["F.Cu"] + [f"In{i}.Cu" for i in range(1, design.COPPER_LAYERS - 1)] + ["B.Cu"]
    layers = cu + ["F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen", "F.Mask", "B.Mask", "Edge.Cuts"]
    run("pcb", "export", "gerbers", "--layers", ",".join(layers), "--subtract-soldermask",
        "--no-protel-ext", "-o", gdir + os.sep, PCB)
    run("pcb", "export", "drill", "--format", "excellon", "--drill-origin", "absolute",
        "--excellon-units", "mm", "-o", gdir + os.sep, PCB)
    with zipfile.ZipFile(os.path.join(PROD, "gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gdir)):
            z.write(os.path.join(gdir, f), f)

    # BOM straight from design.py, grouped by value + footprint + LCSC part.
    groups = {}
    for p in design.PARTS:
        if p.virtual or p.dnp or getattr(p, "no_assembly", False):
            continue
        key = (p.value, p.footprint.split(":")[-1], p.lcsc or "")
        groups.setdefault(key, []).append(p.ref)
    with open(os.path.join(PROD, "bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, fp, lcsc), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            w.writerow([value, ",".join(sorted(refs)), fp, lcsc])

    # CPL from gen/jlc_placement.json (LCSC footprint origin + rotation, see
    # jlc_align.py). JLC's Y axis points up, so KiCad's Y is negated.
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "jlc_placement.json")) as f:
        placement = json.load(f)
    missing = []
    with open(os.path.join(PROD, "cpl.csv"), "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in design.PARTS:
            if p.virtual or p.dnp or getattr(p, "no_assembly", False):
                continue
            r = placement.get(p.ref)
            if r is None:
                missing.append(p.ref)
                continue
            w.writerow([p.ref, f"{r['x']:.4f}mm", f"{-r['y']:.4f}mm", "Top", f"{r['rot'] % 360:g}"])
    if missing:
        raise SystemExit(f"no JLC placement for {missing}: run gen/jlc_align.py")

    run("sch", "export", "pdf", "-o", os.path.join(PREV, "schematic.pdf"), SCH)
    run("pcb", "export", "pdf", "--mode-separate", "--include-border-title",
        "--layers", ",".join(cu + ["F.Silkscreen", "B.Silkscreen", "Edge.Cuts"]),
        "--common-layers", "Edge.Cuts", "-o", PREV + os.sep, PCB)
    for side in ("top", "bottom"):
        run("pcb", "render", "--side", side, "--quality", "high", "--width", "1600", "--height", "1200",
            "--background", "opaque", "-o", os.path.join(PREV, f"render_{side}.png"), PCB)
    run("pcb", "render", "--side", "top", "--rotate", "320,0,25", "--perspective", "--quality", "high", "--width", "1600",
        "--height", "1200", "--background", "opaque", "-o", os.path.join(PREV, "render_iso.png"), PCB)
    print("done:", PROD, PREV)


if __name__ == "__main__":
    main()
