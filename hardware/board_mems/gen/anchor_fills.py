"""Re-run route.py's orphan-GND-fill anchoring on the routed board (after edits
that refill zones, such as gen/add_keepouts.py), then refill and save.

  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/anchor_fills.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402

import design  # noqa: E402
import route  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

pcb = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb")
b = pcbnew.LoadBoard(pcb)
total = 0
for _ in range(3):
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    n = route.anchor_orphan_fills(b)
    total += n
    if n == 0:
        break
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(pcb)
print(f"anchored {total} orphan GND fill pieces; open connections: {route.open_connections(b)}")
