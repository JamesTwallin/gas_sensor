"""Load symbols from KiCad libraries and expose their pins.

Shared by the schematic builder (plain Python) and the PCB builder (KiCad's
bundled Python), so it must not import anything outside the stdlib.
"""

import copy
import os
import uuid

from sexpr import QStr, find, find_all, parse

KICAD_SHARE = os.environ.get("KICAD9_SHARE", r"C:\Program Files\KiCad\9.0\share\kicad")
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(HERE)
PROJECT_LIB = "phone_board_mems"  # project-local symbol + footprint library nickname

# Deterministic UUIDs so regenerating the schematic and the board keeps the
# symbol<->footprint links (and KiCad's schematic-parity check) stable.
_NS = uuid.UUID("0b6f3c1e-7a52-4c55-9d0e-6a8f1c2b3d4e")


def stable_uuid(*parts):
    return str(uuid.uuid5(_NS, "/".join(str(p) for p in parts)))


def sym_lib_path(lib):
    if lib == PROJECT_LIB:
        return os.path.join(PROJECT_DIR, "lib", PROJECT_LIB + ".kicad_sym")
    return os.path.join(KICAD_SHARE, "symbols", lib + ".kicad_sym")


def fp_lib_path(lib):
    if lib == PROJECT_LIB:
        return os.path.join(PROJECT_DIR, "lib", PROJECT_LIB + ".pretty")
    return os.path.join(KICAD_SHARE, "footprints", lib + ".pretty")


_lib_cache = {}


def _lib(lib):
    if lib not in _lib_cache:
        with open(sym_lib_path(lib), encoding="utf-8") as f:
            tree = parse(f.read())
        _lib_cache[lib] = {s[1]: s for s in find_all(tree, "symbol")}
    return _lib_cache[lib]


def load_symbol(lib_id):
    """Return a flattened copy of the symbol, named 'Lib:Name' for lib_symbols."""
    lib, name = lib_id.split(":", 1)
    syms = _lib(lib)
    if name not in syms:
        raise KeyError(f"symbol {lib_id} not found")
    sym = copy.deepcopy(syms[name])
    ext = find(sym, "extends")
    if ext:
        parent = load_symbol(f"{lib}:{ext[1]}")
        pname = ext[1]
        child_props = {p[1]: p for p in find_all(sym, "property")}
        flat = [parent[0], QStr(name)]
        for c in parent[2:]:
            if isinstance(c, list) and c[0] == "property" and c[1] in child_props:
                flat.append(child_props.pop(c[1]))
            elif isinstance(c, list) and c[0] == "symbol":
                sub = copy.deepcopy(c)
                sub[1] = QStr(str(sub[1]).replace(pname.split(":")[-1], name, 1))
                flat.append(sub)
            else:
                flat.append(c)
        flat.extend(child_props.values())
        sym = flat
    sym[1] = QStr(lib_id)
    return sym


class Pin:
    def __init__(self, number, name, etype, x, y, angle, unit, hidden):
        self.number, self.name, self.etype = number, name, etype
        self.x, self.y, self.angle, self.unit, self.hidden = x, y, angle, unit, hidden

    def __repr__(self):
        return f"Pin({self.number} {self.name} {self.etype} u{self.unit})"


def symbol_pins(sym):
    pins = []
    base = str(sym[1]).split(":")[-1]
    for sub in find_all(sym, "symbol"):
        suffix = str(sub[1])[len(base) + 1:]
        unit, style = (int(v) for v in suffix.split("_"))
        if style == 2:  # De Morgan alternate body
            continue
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            hidden = "hide" in p or (find(p, "hide") or [None, "no"])[1] == "yes"
            pins.append(Pin(str(find(p, "number")[1]), str(find(p, "name")[1]), p[1],
                            float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0,
                            unit, hidden))
    return pins


def unit_count(sym):
    units = {int(str(s[1]).rsplit("_", 2)[-2]) for s in find_all(sym, "symbol")}
    return max(units) if units else 1
