"""Add design.ZONES rule areas missing from the routed board, then refill zones.

For keepouts added after routing (so a ~5 minute re-route is not needed):
  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/add_keepouts.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402

import design  # noqa: E402
from build_pcb import poly_zone  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

pcb = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb")
b = pcbnew.LoadBoard(pcb)
have = {z.GetZoneName() for z in b.Zones()}
added = 0
for z in design.ZONES:
    if z.get("rule_area") and z.get("name") and z["name"] not in have:
        poly_zone(b, z["pts"], z["layers"], rule_area=z["rule_area"], name=z["name"])
        added += 1
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(pcb)
print(f"added {added} keepout(s), refilled zones, saved {pcb}")
