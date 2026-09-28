"""Generate phone_board.kicad_sch from design.py.

Every connected pin gets a net label at its connection point; unused pins get a
no-connect flag. Parts are laid out block by block, left to right. It is a
"label-style" schematic: the connectivity is exact, the drawing is tidy but not
hand-drafted. Run with any Python 3:  python build_sch.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import design  # noqa: E402
from kicad_lib import PROJECT_DIR, load_symbol, stable_uuid, symbol_pins  # noqa: E402
from sexpr import QStr, dumps  # noqa: E402

GRID = 2.54
PAGE = "A2"
PAGE_W, PAGE_H = 594.0, 420.0
ROOT_UUID = stable_uuid("root-sheet")


def snap(v):
    return round(v / GRID) * GRID


def font(size=1.27, justify=None, hide=False):
    eff = ["effects", ["font", ["size", size, size]]]
    if justify:
        eff.append(["justify"] + justify)
    if hide:
        eff.append(["hide", "yes"])
    return eff


def prop(name, value, x, y, hide=False, angle=0):
    return ["property", QStr(name), QStr(value), ["at", x, y, angle], font(hide=hide)]


def label_node(net, x, y, pin_angle):
    # Pin angle is the direction from the connection point into the body, so the
    # label text runs the opposite way.
    ang = {0: 180, 180: 0, 90: 270, 270: 90}[int(pin_angle) % 360]
    just = ["left", "bottom"] if ang in (0, 90) else ["right", "bottom"]
    return ["label", QStr(net), ["at", x, y, ang], ["fields_autoplaced", "yes"],
            font(justify=just), ["uuid", QStr(stable_uuid("label", net, x, y))]]


def symbol_extent(pins, part):
    xs = [p.x for p in pins] or [0]
    ys = [p.y for p in pins] or [0]
    # room for the labels hanging off each side
    lab = max((len(n) for n in part.nets.values()), default=4) * 1.1 + 4
    return (min(xs) - lab, max(xs) + lab, min(ys) - 6, max(ys) + 6)


def main():
    lib_symbols = {}
    body = []
    pwr_flag_nets = set()
    net_pin_types = {}

    cursor_y = 30.0
    for block in design.BLOCKS:
        parts = [p for p in design.PARTS if p.block == block]
        cursor_x = 30.0
        row_h = 0.0
        for part in parts:
            sym = lib_symbols.setdefault(part.symbol, load_symbol(part.symbol))
            pins = symbol_pins(sym)
            units = sorted({p.unit for p in pins if p.unit > 0} or {1})
            for unit in units:
                upins = [p for p in pins if p.unit in (0, unit)]
                x0, x1, y0, y1 = symbol_extent(upins, part)
                w, h = x1 - x0, y1 - y0
                if cursor_x + w > PAGE_W - 20:
                    cursor_x = 30.0
                    cursor_y += row_h + 10
                    row_h = 0.0
                sx, sy = snap(cursor_x - x0), snap(cursor_y + y1)
                cursor_x += w + 8
                row_h = max(row_h, h)

                sym_uuid = stable_uuid("sym", part.ref, unit)
                node = ["symbol", ["lib_id", QStr(part.symbol)], ["at", sx, sy, 0],
                        ["unit", unit], ["exclude_from_sim", "no"],
                        ["in_bom", "no" if part.virtual or getattr(part, "not_in_bom", False) else "yes"],
                        ["on_board", "no" if part.virtual else "yes"],
                        ["dnp", "yes" if part.dnp else "no"],
                        ["fields_autoplaced", "yes"], ["uuid", QStr(sym_uuid)],
                        prop("Reference", part.ref, sx, sy + y0 - 2.54 * 0 - 1.27, angle=0),
                        prop("Value", part.value, sx, sy - y0 + 1.27),
                        prop("Footprint", part.footprint or "", sx, sy, hide=True),
                        prop("Datasheet", part.datasheet or "~", sx, sy, hide=True),
                        prop("Description", part.description or "", sx, sy, hide=True)]
                if part.lcsc:
                    node.append(prop("LCSC", part.lcsc, sx, sy, hide=True))
                if part.mpn:
                    node.append(prop("MPN", part.mpn, sx, sy, hide=True))
                for p in pins:
                    if p.unit in (0, unit):
                        node.append(["pin", QStr(p.number), ["uuid", QStr(stable_uuid("pin", part.ref, p.number))]])
                node.append(["instances", ["project", QStr(design.PROJECT),
                             ["path", QStr("/" + ROOT_UUID), ["reference", QStr(part.ref)], ["unit", unit]]]])
                body.append(node)

                for p in upins:
                    px, py = sx + p.x, sy - p.y
                    net = part.net_for(p)
                    if net is None:
                        if p.etype != "no_connect" and not (p.hidden and p.etype == "power_in"):
                            body.append(["no_connect", ["at", px, py],
                                         ["uuid", QStr(stable_uuid("nc", part.ref, p.number))]])
                        continue
                    body.append(label_node(net, px, py, p.angle))
                    net_pin_types.setdefault(net, set()).add(p.etype)
        cursor_y += row_h + 25

    # PWR_FLAG on nets that have power inputs but nothing that drives them.
    flag = load_symbol("power:PWR_FLAG")
    fx = 30.0
    for net, types in sorted(net_pin_types.items()):
        if "power_in" in types and "power_out" not in types:
            lib_symbols.setdefault("power:PWR_FLAG", flag)
            fu = stable_uuid("pwrflag", net)
            fy = snap(PAGE_H - 25)
            body.append(["symbol", ["lib_id", QStr("power:PWR_FLAG")], ["at", snap(fx), fy, 0],
                         ["unit", 1], ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
                         ["dnp", "no"], ["uuid", QStr(fu)],
                         prop("Reference", "#FLG0" + str(len(pwr_flag_nets) + 1).zfill(2), snap(fx), fy - 5, hide=True),
                         prop("Value", "PWR_FLAG", snap(fx), fy - 4),
                         prop("Footprint", "", snap(fx), fy, hide=True),
                         prop("Datasheet", "~", snap(fx), fy, hide=True),
                         prop("Description", "", snap(fx), fy, hide=True),
                         ["pin", QStr("1"), ["uuid", QStr(stable_uuid("pwrflagpin", net))]],
                         ["instances", ["project", QStr(design.PROJECT),
                          ["path", QStr("/" + ROOT_UUID),
                           ["reference", QStr("#FLG0" + str(len(pwr_flag_nets) + 1).zfill(2))], ["unit", 1]]]]])
            body.append(label_node(net, snap(fx), fy, 90))
            pwr_flag_nets.add(net)
            fx += 25

    title = ["title_block", ["title", QStr(design.TITLE)], ["rev", QStr(design.REV)],
             ["comment", 1, QStr("Generated by hardware/phone_board/gen/build_sch.py from design.py - do not hand-edit")],
             ["comment", 2, QStr("Spec: docs/phone_board.md")]]
    tree = ["kicad_sch", ["version", "20250114"], ["generator", QStr("eeschema")],
            ["generator_version", QStr("9.0")], ["uuid", QStr(ROOT_UUID)], ["paper", QStr(PAGE)], title,
            ["lib_symbols"] + list(lib_symbols.values())]
    tree += body
    tree += [["sheet_instances", ["path", QStr("/"), ["page", QStr("1")]]], ["embedded_fonts", "no"]]

    out = os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_sch")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(tree) + "\n")
    print(f"wrote {out}: {len(design.PARTS)} parts, flags on {sorted(pwr_flag_nets)}")


if __name__ == "__main__":
    main()
