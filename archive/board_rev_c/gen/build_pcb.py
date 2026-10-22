"""Generate phone_board.kicad_pcb (unrouted) from design.py.

Loads every footprint, assigns pad nets from the same pin->net map the
schematic uses, links each footprint to its schematic symbol UUID, places it
per design.PLACEMENT, and adds the outline, planes and keepouts.

Run with KiCad's bundled Python:
  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" build_pcb.py
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcbnew  # noqa: E402

try:  # KiCad's release build still pops wx assert dialogs from geometry code; silence them
    import wx
    wx.DisableAsserts()
except Exception:
    pass

import design  # noqa: E402
from kicad_lib import PROJECT_DIR, fp_lib_path, load_symbol, stable_uuid, symbol_pins  # noqa: E402

mm = pcbnew.FromMM


def V(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def write_project():
    """Net classes and board rules live in the .kicad_pro."""
    rules = design.RULES
    classes = [dict(name="Default", clearance=rules["clearance"], track_width=rules["track"],
                    via_diameter=rules["via_d"], via_drill=rules["via_drill"],
                    microvia_diameter=0.3, microvia_drill=0.1, diff_pair_width=0.2,
                    diff_pair_gap=0.2, diff_pair_via_gap=0.25, bus_width=12, wire_width=6,
                    line_style=0, pcb_color="rgba(0, 0, 0, 0.000)",
                    schematic_color="rgba(0, 0, 0, 0.000)", priority=2147483647)]
    patterns = []
    for i, (name, nc) in enumerate(design.NETCLASSES.items()):
        c = dict(classes[0])
        c.update(name=name, priority=i, clearance=nc.get("clearance", rules["clearance"]),
                 track_width=nc["track"], via_diameter=nc.get("via_d", rules["via_d"]),
                 via_drill=nc.get("via_drill", rules["via_drill"]))
        classes.append(c)
        patterns += [{"netclass": name, "pattern": "/" + n} for n in nc["nets"]]
    pro = {
        "board": {"design_settings": {
            "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2,
                         "copper_text_size_h": 1.5, "copper_text_size_v": 1.5,
                         "copper_text_thickness": 0.3, "silk_line_width": 0.12,
                         "silk_text_size_h": 0.8, "silk_text_size_v": 0.8,
                         "silk_text_thickness": 0.12},
            "rules": {"min_clearance": rules["min_clearance"], "min_track_width": rules["min_track"],
                      "min_via_diameter": rules["min_via_d"], "min_through_hole_diameter": rules["min_drill"],
                      "min_via_annular_width": rules["min_annular"], "min_copper_edge_clearance": 0.3,
                      "min_hole_clearance": 0.2, "min_hole_to_hole": 0.25,
                      "min_silk_clearance": 0.0, "min_text_height": 0.6, "min_text_thickness": 0.08,
                      "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1,
                      "min_connection": 0.0, "min_groove_width": 0.0, "max_error": 0.005,
                      "min_resolved_spokes": 1, "solder_mask_to_copper_clearance": 0.005,
                      "use_height_for_length_calcs": True},
            "rule_severities": {"lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore",
                                "silk_overlap": "ignore", "silk_over_copper": "ignore",
                                "silk_edge_clearance": "ignore", "text_height": "ignore",
                                "text_thickness": "ignore"},
            "track_widths": [], "via_dimensions": [], "diff_pair_dimensions": []}},
        "meta": {"filename": design.PROJECT + ".kicad_pro", "version": 3},
        "net_settings": {"classes": classes, "meta": {"version": 4}, "net_colors": None,
                         "netclass_assignments": None, "netclass_patterns": patterns},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[stable_uuid("root-sheet"), "Root"]],
        "text_variables": {},
    }
    with open(os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pro"), "w") as f:
        json.dump(pro, f, indent=2)


def rounded_rect(board, x0, y0, x1, y1, r, layer, notches=()):
    """Outline with rounded corners. `notches` are rectangular cut-ins from the
    right edge: dict(x0=inner end, y0, y1). The right edge is split around them."""
    w = mm(0.1)
    right = []
    y = y0 + r
    for n in sorted(notches, key=lambda n: n["y0"]):
        right += [((x1, y), (x1, n["y0"])), ((x1, n["y0"]), (n["x0"], n["y0"])),
                  ((n["x0"], n["y0"]), (n["x0"], n["y1"])), ((n["x0"], n["y1"]), (x1, n["y1"]))]
        y = n["y1"]
    right.append(((x1, y), (x1, y1 - r)))
    segs = [((x0 + r, y0), (x1 - r, y0)), *right,
            ((x1 - r, y1), (x0 + r, y1)), ((x0, y1 - r), (x0, y0 + r))]
    for a, b in segs:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*a))
        s.SetEnd(V(*b))
        s.SetLayer(layer)
        s.SetWidth(w)
        board.Add(s)
    for cx, cy, start in ((x1 - r, y0 + r, 270), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetCenter(V(cx, cy))
        a = math.radians(start)
        s.SetStart(V(cx + r * math.cos(a), cy + r * math.sin(a)))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True)
        s.SetLayer(layer)
        s.SetWidth(w)
        board.Add(s)


def poly_zone(board, pts, layers, net=None, rule_area=None, name="", priority=0):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    for layer in layers:
        ls.AddLayer(board.GetLayerID(layer) if isinstance(layer, str) else layer)
    z.SetLayerSet(ls)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(x), mm(y))
    if name:
        z.SetZoneName(name)
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks("tracks" in rule_area)
        z.SetDoNotAllowVias("vias" in rule_area)
        z.SetDoNotAllowCopperPour("fills" in rule_area)
        z.SetDoNotAllowPads("pads" in rule_area)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetNet(net)
        z.SetAssignedPriority(priority)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetMinThickness(mm(0.2))
        z.SetLocalClearance(mm(0.25))
        z.SetThermalReliefGap(mm(0.3))
        z.SetThermalReliefSpokeWidth(mm(0.35))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


def main():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(design.COPPER_LAYERS)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(1.6))

    nets = {}

    def net(name, raw=False):
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name if raw else "/" + name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    for part in design.PARTS:
        if part.virtual:
            continue
        lib, name = part.footprint.split(":", 1)
        fp = pcbnew.FootprintLoad(fp_lib_path(lib), name)
        if fp is None:
            raise RuntimeError(f"footprint {part.footprint} not found for {part.ref}")
        fp.SetFPIDAsString(part.footprint)
        fp.SetReference(part.ref)
        fp.SetValue(part.value)
        fp.SetPath(pcbnew.KIID_PATH("/" + stable_uuid("sym", part.ref, 1)))
        fp.SetSheetname("Root")
        fp.SetSheetfile(design.PROJECT + ".kicad_sch")
        for key, val in (("LCSC", part.lcsc), ("MPN", part.mpn)):
            if val:
                field = pcbnew.PCB_FIELD(fp, fp.GetNextFieldId(), key)
                field.SetText(val)
                field.SetVisible(False)
                field.SetLayer(pcbnew.F_Fab)
                fp.AddField(field)
        if part.dnp:
            fp.SetDNP(True)
        board.Add(fp)

        pins = symbol_pins(load_symbol(part.symbol))
        pad_nets = part.pad_nets(pins)
        pin_names = {p.number: p.name for p in pins}
        for pad in fp.Pads():
            n = pad_nets.get(pad.GetNumber())
            if n:
                pad.SetNet(net(n))
            elif pad.GetNumber() in pin_names:
                # match eeschema's name for a no-connect pin so parity checks pass
                pname = pin_names[pad.GetNumber()]
                label = f"{part.ref}-{pname}-Pad{pad.GetNumber()}" if pname not in ("", "~")                     else f"{part.ref}-Pad{pad.GetNumber()}"
                pad.SetNet(net(f"unconnected-({label})", raw=True))

        x, y, rot, side = design.PLACEMENT.get(part.ref, (0, 0, 0, "F"))
        fp.SetPosition(V(x, y))
        if side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        fp.SetOrientationDegrees(rot)
        if part.ref.startswith(("TP", "H")):
            fp.Reference().SetVisible(False)
        fp.Reference().SetTextSize(V(0.6, 0.6))
        fp.Reference().SetTextThickness(mm(0.1))

    # Pads with no net that the symbol also didn't list (thermal/mounting pads of
    # modules often share a number with a GND pin, which the loop above covers).
    unassigned = [f"{fp.GetReference()}.{p.GetNumber()}" for fp in board.GetFootprints()
                  for p in fp.Pads() if not p.GetNetname() and p.GetNumber() and p.IsOnCopperLayer()
                  and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
    if unassigned:
        print("pads without a net:", ", ".join(unassigned))

    x0, y0, x1, y1 = design.OUTLINE
    rounded_rect(board, x0, y0, x1, y1, design.CORNER_R, pcbnew.Edge_Cuts, getattr(design, "NOTCHES", ()))
    for cut in getattr(design, "SLOTS", []):
        # thermal isolation slot: a closed polygon on Edge.Cuts (the mill rounds inner corners)
        for a, c in zip(cut, cut[1:] + cut[:1]):
            s = pcbnew.PCB_SHAPE(board)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(V(*a))
            s.SetEnd(V(*c))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(mm(0.1))
            board.Add(s)

    for z in design.ZONES:
        poly_zone(board, z.get("pts") or [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                  z["layers"], net=net(z["net"]) if z.get("net") else None,
                  rule_area=z.get("rule_area"), name=z.get("name", ""), priority=z.get("priority", 0))

    for tr in getattr(design, "PREROUTE", []):
        for a, c in zip(tr["pts"], tr["pts"][1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(V(*a))
            t.SetEnd(V(*c))
            t.SetWidth(mm(tr["width"]))
            t.SetLayer(board.GetLayerID(tr["layer"]))
            t.SetNet(net(tr["net"]))
            t.SetLocked(True)
            board.Add(t)
    for v in getattr(design, "PREROUTE_VIAS", []):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(V(*v["at"]))
        via.SetWidth(mm(v.get("d", design.RULES["via_d"])))
        via.SetDrill(mm(v.get("drill", design.RULES["via_drill"])))
        via.SetNet(net(v["net"]))
        via.SetLocked(True)
        board.Add(via)

    add_silk(board)

    out = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb")
    board.Save(out)
    write_project()  # after Save, which rewrites the .kicad_pro with defaults
    print(f"wrote {out}: {len(board.GetFootprints())} footprints, {len(nets)} nets")


_removed = []


def add_silk(board):
    """Board-level silkscreen labels from design.SILK_TEXT (replacing any already there)."""
    for item in list(board.GetDrawings()):
        if item.GetClass() == "PCB_TEXT" and item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            board.Remove(item)
            _removed.append(item)  # keep Python from freeing it while KiCad still points at it
    for t in getattr(design, "SILK_TEXT", []):
        txt = pcbnew.PCB_TEXT(board)
        txt.SetText(t["text"])
        txt.SetPosition(V(*t["at"]))
        txt.SetLayer(pcbnew.B_SilkS if t.get("side") == "B" else pcbnew.F_SilkS)
        txt.SetTextSize(V(t.get("size", 1.0), t.get("size", 1.0)))
        txt.SetTextThickness(mm(t.get("size", 1.0) * 0.15))
        if t.get("side") == "B":
            txt.SetMirrored(True)
        board.Add(txt)


if __name__ == "__main__":
    if "--silk-only" in sys.argv:  # relabel a routed board without rebuilding it
        pcb = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb")
        b = pcbnew.LoadBoard(pcb)
        add_silk(b)
        b.Save(pcb)
        write_project()
        print("updated silkscreen text in", pcb)
    else:
        main()
