"""Autoroute phone_board.kicad_pcb with Freerouting, stitch GND, fill zones, save.

  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" route.py [passes]

Needs Java 25+ and freerouting.jar: set the JAVA and FREEROUTING env vars (see
hardware/phone_board/README.md). Locked tracks from design.PREROUTE are
exported as fixed wires. Freerouting is re-run on the result (up to ROUNDS
times) while connections remain open, since a single run occasionally leaves
one or two behind.
"""

import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcbnew  # noqa: E402

try:  # KiCad's release build pops wx assert dialogs from geometry code; silence them
    import wx
    wx.DisableAsserts()
except Exception:
    pass

import build_pcb  # noqa: E402
import design  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

JAVA = os.environ.get("JAVA", "java")
JAR = os.environ.get("FREEROUTING", "freerouting.jar")
ROUNDS = 3
mm = pcbnew.FromMM


def freeroute(board, work, passes):
    dsn, ses = os.path.join(work, "route.dsn"), os.path.join(work, "route.ses")
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        raise RuntimeError("DSN export failed")
    # Mark plane layers as "power" so Freerouting keeps signals off them.
    with open(dsn, encoding="utf-8") as f:
        text = f.read()
    for layer in getattr(design, "PLANE_LAYERS", []):
        text = re.sub(r"(\(layer " + re.escape(layer) + r"\s+\(type )signal\)", r"\1power)", text)
    with open(dsn, "w", encoding="utf-8") as f:
        f.write(text)
    if os.path.exists(ses):
        os.remove(ses)
    t0 = time.time()
    subprocess.run([JAVA, "-jar", JAR, "-de", dsn, "-do", ses, "-mp", str(passes), "--gui.enabled=false"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise RuntimeError("SES import failed")
    print(f"  freerouting pass done in {time.time() - t0:.0f}s")


def via_at(board, p, net):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(p)
    via.SetWidth(mm(design.RULES["via_d"]))
    via.SetDrill(mm(design.RULES["via_drill"]))
    via.SetNet(net)
    board.Add(via)
    return via


class Clearance:
    """Answers 'can a GND via go here?' against copper, courtyards and keepouts."""

    def __init__(self, board, use_courtyards=True):
        self.board = board
        self.r = mm(design.RULES["via_d"]) // 2
        self.cu = [board.GetLayerID(n) for n in ("F.Cu", "In2.Cu", "B.Cu")]
        self.items = list(board.GetTracks()) + [p for fp in board.GetFootprints() for p in fp.Pads()]
        self.courtyards = [fp.GetCourtyard(pcbnew.F_CrtYd) for fp in board.GetFootprints()
                           if use_courtyards and fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount()]
        self.keepouts = [z for z in board.Zones() if z.GetIsRuleArea()]

    def ok(self, p):
        if any(c.Contains(p) or c.Collide(p, mm(0.3)) for c in self.courtyards):
            return False
        if any(z.Outline().Collide(p, mm(0.8)) for z in self.keepouts):
            return False
        circle = pcbnew.SHAPE_CIRCLE(p, self.r)
        return not any(it.IsOnLayer(layer) and it.GetEffectiveShape(layer).Collide(circle, mm(0.25))
                       for it in self.items for layer in self.cu)

    def add(self, item):
        self.items.append(item)


def stitch(board):
    """GND vias on a grid wherever they clear everything else."""
    pitch = getattr(design, "STITCH_PITCH", 0)
    if not pitch:
        return
    gnd = board.FindNet("/GND")
    cl = Clearance(board)
    x0, y0, x1, y1 = design.OUTLINE
    added = 0
    y = y0 + 1.5
    while y < y1 - 1.2:
        x = x0 + 1.5
        while x < x1 - 1.2:
            p = pcbnew.VECTOR2I(mm(x), mm(y))
            if cl.ok(p):
                cl.add(via_at(board, p, gnd))
                added += 1
            x += pitch
        y += pitch
    print(f"  added {added} GND stitching vias")


def anchor_orphan_fills(board):
    """A GND fill piece with no via only reaches the plane through whatever pad it
    touches, which may be nothing. Give each such piece its own via."""
    gnd = board.FindNet("/GND")
    anchors = [v.GetPosition() for v in board.GetTracks()
               if v.GetClass() == "PCB_VIA" and v.GetNetCode() == gnd.GetNetCode()]
    anchors += [p.GetPosition() for fp in board.GetFootprints() for p in fp.Pads()
                if p.GetNetCode() == gnd.GetNetCode() and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
    cl = Clearance(board, use_courtyards=False)
    r = mm(design.RULES["via_d"]) // 2 + mm(0.05)
    added = 0
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() != gnd.GetNetCode():
            continue
        for layer in z.GetLayerSet().Seq():
            polys = z.GetFilledPolysList(layer)
            for i in range(polys.OutlineCount()):
                outline = polys.Outline(i)
                if any(outline.PointInside(a) for a in anchors):
                    continue
                bb = outline.BBox()
                step = mm(0.25)
                found = None
                yy = bb.GetTop() + r
                while yy < bb.GetBottom() - r and not found:
                    xx = bb.GetLeft() + r
                    while xx < bb.GetRight() - r:
                        p = pcbnew.VECTOR2I(xx, yy)
                        ring = [pcbnew.VECTOR2I(int(xx + dx * r), int(yy + dy * r))
                                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0.7, 0.7), (-0.7, 0.7),
                                               (0.7, -0.7), (-0.7, -0.7))]
                        if outline.PointInside(p) and all(outline.PointInside(q) for q in ring) and cl.ok(p):
                            found = p
                            break
                        xx += step
                    yy += step
                if found:
                    v = via_at(board, found, gnd)
                    cl.add(v)
                    anchors.append(found)
                    added += 1
    return added


def open_connections(board):
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    conn.RecalculateRatsnest()
    return conn.GetUnconnectedCount(False)


def main():
    passes = sys.argv[1] if len(sys.argv) > 1 else "100"
    pcb = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb")
    work = os.path.join(PROJECT_DIR, "build")
    os.makedirs(work, exist_ok=True)
    board = pcbnew.LoadBoard(pcb)

    x0, y0, x1, y1 = design.OUTLINE
    for rnd in range(1, ROUNDS + 1):
        print(f"round {rnd}")
        freeroute(board, work, passes)
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
        left = open_connections(board)
        print(f"  {left} connections open")
        if left == 0:
            break

    have = {z.GetZoneName() for z in board.Zones()}
    for z in getattr(design, "POST_ROUTE_ZONES", []):
        if z["name"] not in have:
            build_pcb.poly_zone(board, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z["layers"],
                                net=board.FindNet("/" + z["net"]), name=z["name"])
    # Freerouting occasionally leaves sub-minimum-width slivers on pour nets; drop them.
    min_w = mm(design.RULES["min_track"])
    for t in list(board.GetTracks()):
        if t.GetClass() == "PCB_TRACK" and t.GetWidth() < min_w and not t.IsLocked():
            board.Remove(t)
    stitch(board)
    for _ in range(3):
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        n = anchor_orphan_fills(board)
        print(f"  anchored {n} orphan GND fill pieces")
        if not n:
            break
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(pcb)
    print("saved", pcb, "- open connections:", open_connections(board))


if __name__ == "__main__":
    main()
