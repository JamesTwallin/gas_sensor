"""List pads, vias and track segments within a box (mm), to plan hand routes.

  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/near.py X0 Y0 X1 Y1 [LAYER]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402

import design  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

x0, y0, x1, y1 = (float(v) for v in sys.argv[1:5])
only = sys.argv[5] if len(sys.argv) > 5 else None
b = pcbnew.LoadBoard(os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb"))
mm = pcbnew.ToMM


def inside(bb):
    return not (mm(bb.GetRight()) < x0 or mm(bb.GetLeft()) > x1 or mm(bb.GetBottom()) < y0 or mm(bb.GetTop()) > y1)


for fp in b.GetFootprints():
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        if inside(bb) and (only is None or p.IsOnLayer(b.GetLayerID(only))):
            print(f"pad {fp.GetReference()}.{p.GetNumber():3s} {p.GetNetname():14s} "
                  f"x {mm(bb.GetLeft()):.2f}..{mm(bb.GetRight()):.2f} y {mm(bb.GetTop()):.2f}..{mm(bb.GetBottom()):.2f}")
for t in b.GetTracks():
    bb = t.GetBoundingBox()
    if not inside(bb):
        continue
    if t.GetClass() == "PCB_VIA":
        print(f"via {t.GetNetname():14s} at ({mm(t.GetPosition().x):.2f}, {mm(t.GetPosition().y):.2f}) d {mm(t.GetWidth()):.2f}")
    elif only is None or t.GetLayerName() == only:
        print(f"trk {t.GetNetname():14s} {t.GetLayerName():6s} ({mm(t.GetStart().x):.2f},{mm(t.GetStart().y):.2f})"
              f"-({mm(t.GetEnd().x):.2f},{mm(t.GetEnd().y):.2f}) w {mm(t.GetWidth()):.2f}")
