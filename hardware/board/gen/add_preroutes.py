"""Add PREROUTE tracks / vias from design.py that the routed board does not have yet,
then refill zones, anchor orphan GND fill and save. For hand-routed links added
after routing (so a full re-route is not needed).

  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/add_preroutes.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402

import design  # noqa: E402
import route  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

mm = pcbnew.FromMM
pcb = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb")
b = pcbnew.LoadBoard(pcb)


def key(net, layer, a, c):
    a, c = sorted([(round(a[0], 3), round(a[1], 3)), (round(c[0], 3), round(c[1], 3))])
    return (net, layer, a, c)


have_t, have_v = set(), set()
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    if t.GetClass() == "PCB_VIA":
        have_v.add((t.GetNetname(), round(pcbnew.ToMM(s.x), 3), round(pcbnew.ToMM(s.y), 3)))
    else:
        have_t.add(key(t.GetNetname(), t.GetLayerName(), (pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)),
                       (pcbnew.ToMM(e.x), pcbnew.ToMM(e.y))))
added = 0
for tr in design.PREROUTE:
    for a, c in zip(tr["pts"], tr["pts"][1:]):
        if key("/" + tr["net"], tr["layer"], a, c) in have_t:
            continue
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
        t.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1])))
        t.SetWidth(mm(tr["width"]))
        t.SetLayer(b.GetLayerID(tr["layer"]))
        t.SetNet(b.FindNet("/" + tr["net"]))
        t.SetLocked(True)
        b.Add(t)
        added += 1
for v in design.PREROUTE_VIAS:
    if ("/" + v["net"], round(v["at"][0], 3), round(v["at"][1], 3)) in have_v:
        continue
    via = pcbnew.PCB_VIA(b)
    via.SetPosition(pcbnew.VECTOR2I(mm(v["at"][0]), mm(v["at"][1])))
    via.SetWidth(mm(v.get("d", design.RULES["via_d"])))
    via.SetDrill(mm(v.get("drill", design.RULES["via_drill"])))
    via.SetNet(b.FindNet("/" + v["net"]))
    via.SetLocked(True)
    b.Add(via)
    added += 1
for _ in range(3):
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    if not route.anchor_orphan_fills(b):
        break
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(pcb)
print(f"added {added} prerouted items; open connections: {route.open_connections(b)}")
