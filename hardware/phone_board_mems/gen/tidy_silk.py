"""Move reference designators so no silkscreen text overlaps another label, a
part outline, a pad or the board edge. Runs on the routed board (copper is not
touched). A reference that finds no free spot is hidden; it stays on F.Fab.

  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/tidy_silk.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcbnew  # noqa: E402

import build_pcb  # noqa: E402
import design  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

mm, T = pcbnew.FromMM, pcbnew.ToMM
GAP = 0.15  # mm between a label and anything else

# Labels that the board-level silkscreen text replaces (e.g. "RST", "BOOT").
HIDE_REFS = getattr(design, "SILK_HIDE_REFS", set())


def rect(bb, grow=0.0):
    return (T(bb.GetLeft()) - grow, T(bb.GetTop()) - grow, T(bb.GetRight()) + grow, T(bb.GetBottom()) + grow)


def hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def main():
    pcb = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb")
    board = pcbnew.LoadBoard(pcb)
    build_pcb.add_silk(board)  # board-level labels from design.SILK_TEXT
    x0, y0, x1, y1 = design.OUTLINE
    inner = (x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5)

    fps = list(board.GetFootprints())
    pads = [rect(p.GetBoundingBox(), GAP) for fp in fps for p in fp.Pads()]
    outlines = {fp.GetReference(): [rect(g.GetBoundingBox(), GAP) for g in fp.GraphicalItems()
                                    if g.GetLayer() == pcbnew.F_SilkS and g.GetClass() != "PCB_TEXT"]
                for fp in fps}
    courtyards = {fp.GetReference(): rect(fp.GetCourtyard(pcbnew.F_CrtYd).BBox())
                  for fp in fps if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount()}
    placed = [rect(t.GetBoundingBox(), GAP) for t in board.GetDrawings()
              if t.GetClass() == "PCB_TEXT" and t.GetLayer() == pcbnew.F_SilkS]
    edge_cuts = [rect(d.GetBoundingBox(), 0.3) for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts
                 and T(d.GetBoundingBox().GetWidth()) < 20 and T(d.GetBoundingBox().GetHeight()) < 20]

    def clear(ref, r, strict):
        if not (inner[0] <= r[0] and r[2] <= inner[2] and inner[1] <= r[1] and r[3] <= inner[3]):
            return False
        if any(hit(r, o) for o in pads + placed + edge_cuts):
            return False
        if any(hit(r, o) for k, os_ in outlines.items() if k != ref for o in os_):
            return False
        if strict and any(hit(r, c) for k, c in courtyards.items() if k != ref):
            return False
        return True

    # Big parts first: they have the fewest good spots.
    order = sorted((fp for fp in fps if fp.Reference().IsVisible()),
                   key=lambda f: -T(f.GetBoundingBox(False).GetWidth() * f.GetBoundingBox(False).GetHeight()))
    moved = hidden = kept = 0
    for fp in order:
        ref = fp.GetReference()
        field = fp.Reference()
        if ref in HIDE_REFS:
            field.SetVisible(False)
            hidden += 1
            continue
        cx0, cy0, cx1, cy1 = courtyards.get(ref, rect(fp.GetBoundingBox(False)))
        cx, cy = (cx0 + cx1) / 2, (cy0 + cy1) / 2
        cur = rect(field.GetBoundingBox(), GAP)
        if clear(ref, cur, True):
            placed.append(cur)
            kept += 1
            continue
        found = None
        for strict in (True, False):
            for size in (0.6, 0.5):
                field.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
                field.SetTextThickness(mm(size * 0.16))
                for angle in (0, 90):
                    field.SetTextAngleDegrees(angle)
                    for d in (0.0, 0.3, 0.7):
                        cands = [(cx, cy0 - d), (cx, cy1 + d), (cx0 - d, cy), (cx1 + d, cy),
                                 (cx0 - d, cy0 - d), (cx1 + d, cy0 - d), (cx0 - d, cy1 + d), (cx1 + d, cy1 + d)]
                        for px, py in cands:
                            field.SetPosition(pcbnew.VECTOR2I(mm(px), mm(py)))
                            # nudge the label fully outside the courtyard edge it sits on
                            r = rect(field.GetBoundingBox(), GAP)
                            w, h = r[2] - r[0], r[3] - r[1]
                            if py <= cy0:
                                py -= h / 2
                            elif py >= cy1:
                                py += h / 2
                            if px <= cx0:
                                px -= w / 2
                            elif px >= cx1:
                                px += w / 2
                            field.SetPosition(pcbnew.VECTOR2I(mm(px), mm(py)))
                            r = rect(field.GetBoundingBox(), GAP)
                            if clear(ref, r, strict):
                                found = r
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if found:
            placed.append(found)
            moved += 1
        else:
            field.SetVisible(False)
            hidden += 1
    board.Save(pcb)
    build_pcb.write_project()  # Save rewrites the .kicad_pro with defaults
    print(f"references: {kept} kept, {moved} moved, {hidden} hidden")


if __name__ == "__main__":
    main()
