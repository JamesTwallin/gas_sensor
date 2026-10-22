"""Print the end points of every open connection (ratsnest line) on the board.

  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/ratsnest.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402

import design  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

b = pcbnew.LoadBoard(os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb"))
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.BuildConnectivity()
conn = b.GetConnectivity()
for code, net in b.GetNetsByNetcode().items():
    if code == 0:
        continue
    rn = conn.GetRatsnestForNet(code)
    if rn is None:
        continue
    for e in rn.GetEdges():
        a, c = e.GetSourcePos(), e.GetTargetPos()
        print(f"{net.GetNetname()}: ({pcbnew.ToMM(a.x):.2f}, {pcbnew.ToMM(a.y):.2f}) -> "
              f"({pcbnew.ToMM(c.x):.2f}, {pcbnew.ToMM(c.y):.2f})")
