"""Print each footprint's courtyard bounding box (mm), to check placement by hand.

  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/courtyards.py [REF ...]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402

import design  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

board = pcbnew.LoadBoard(os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb"))
want = set(sys.argv[1:])
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if want and ref not in want:
        continue
    fp.BuildCourtyardCaches()
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    if cy.OutlineCount() == 0:
        print(f"{ref:5s} no courtyard")
        continue
    bb = cy.BBox()
    print(f"{ref:5s} x {pcbnew.ToMM(bb.GetLeft()):6.2f}..{pcbnew.ToMM(bb.GetRight()):6.2f}  "
          f"y {pcbnew.ToMM(bb.GetTop()):6.2f}..{pcbnew.ToMM(bb.GetBottom()):6.2f}")
