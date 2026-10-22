"""List GND fill islands that touch no GND pad or via (DRC reports them only as
"Zone 'GND fill' unconnected" with no position).

  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/islands.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402

import design  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

b = pcbnew.LoadBoard(os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb"))
GND = "/GND"
anchors = [(t.GetPosition(), t) for t in b.GetTracks() if t.GetNetname() == GND]
anchors += [(p.GetPosition(), p) for f in b.GetFootprints() for p in f.Pads() if p.GetNetname() == GND]
for z in b.Zones():
    if z.GetIsRuleArea() or z.GetNetname() != GND:
        continue
    for layer in z.GetLayerSet().Seq():
        polys = z.GetFilledPolysList(layer)
        for i in range(polys.OutlineCount()):
            outline = polys.Outline(i)
            if any(item.IsOnLayer(layer) and outline.PointInside(pos) for pos, item in anchors):
                continue
            bb = outline.BBox()
            print(f"{b.GetLayerName(layer)} island x {pcbnew.ToMM(bb.GetLeft()):.2f}..{pcbnew.ToMM(bb.GetRight()):.2f} "
                  f"y {pcbnew.ToMM(bb.GetTop()):.2f}..{pcbnew.ToMM(bb.GetBottom()):.2f} "
                  f"area {outline.Area() / 1e12:.3f} mm2")
