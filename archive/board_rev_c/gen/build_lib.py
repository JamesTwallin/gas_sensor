"""Write lib/phone_board.kicad_sym: symbols the stock KiCad library lacks.

  TPS61023  TI boost converter, SOT-563 (datasheet SLVSF14B pinout)
  TGS26xx   Figaro TGS2611 / TGS2610 bare MOX sensor, TO-5 4-pin
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kicad_lib import PROJECT_DIR  # noqa: E402
from sexpr import QStr, dumps  # noqa: E402


def eff(hide=False, justify=None):
    e = ["effects", ["font", ["size", 1.27, 1.27]]]
    if justify:
        e.append(["justify", justify])
    if hide:
        e.append(["hide", "yes"])
    return e


def prop(k, v, x=0, y=0, hide=False):
    return ["property", QStr(k), QStr(v), ["at", x, y, 0], eff(hide)]


def pin(etype, x, y, angle, name, number):
    return ["pin", etype, "line", ["at", x, y, angle], ["length", 2.54],
            ["name", QStr(name), eff()], ["number", QStr(number), eff()]]


def symbol(name, ref, value, fp, desc, datasheet, w, h, pins):
    return ["symbol", QStr(name), ["pin_names", ["offset", 1.016]],
            ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            prop("Reference", ref, -w, h + 1.27), prop("Value", value, -w, -h - 1.27),
            prop("Footprint", fp, 0, 0, True), prop("Datasheet", datasheet, 0, 0, True),
            prop("Description", desc, 0, 0, True),
            ["symbol", QStr(name + "_0_1"),
             ["rectangle", ["start", -w, h], ["end", w, -h],
              ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]]],
            ["symbol", QStr(name + "_1_1")] + pins,
            ["embedded_fonts", "no"]]


def main():
    tps = symbol("TPS61023", "U", "TPS61023", "Package_TO_SOT_SMD:SOT-563",
                 "3.7 A synchronous boost converter, 0.5-5.5 V in, true load disconnect",
                 "https://www.ti.com/lit/ds/symlink/tps61023.pdf", 7.62, 5.08, [
                     pin("power_in", -10.16, 2.54, 0, "VIN", "3"),
                     pin("input", -10.16, -2.54, 0, "EN", "2"),
                     pin("power_in", 0, -7.62, 90, "GND", "4"),
                     pin("passive", 10.16, 2.54, 180, "SW", "5"),
                     pin("power_out", 10.16, 0, 180, "VOUT", "6"),
                     pin("input", 10.16, -2.54, 180, "FB", "1"),
                 ])
    tgs = symbol("TGS26xx", "S", "TGS26xx", "Package_TO_SOT_THT:TO-5-4",
                 "Figaro TGS2610/TGS2611 MOX gas sensor: heater 1-4, electrodes 2(-) 3(+)",
                 "https://www.figarosensor.com/product/docs/tgs2611-e00_product%20infomation(fusa)_rev01.pdf",
                 7.62, 5.08, [
                     pin("passive", -10.16, 2.54, 0, "H1", "1"),
                     pin("passive", -10.16, -2.54, 0, "H4", "4"),
                     pin("passive", 10.16, 2.54, 180, "S+", "3"),
                     pin("passive", 10.16, -2.54, 180, "S-", "2"),
                 ])
    lib = ["kicad_symbol_lib", ["version", "20241209"], ["generator", QStr("kicad_symbol_editor")],
           ["generator_version", QStr("9.0")], tps, tgs]
    os.makedirs(os.path.join(PROJECT_DIR, "lib"), exist_ok=True)
    with open(os.path.join(PROJECT_DIR, "lib", "phone_board.kicad_sym"), "w", newline="\n") as f:
        f.write(dumps(lib) + "\n")
    with open(os.path.join(PROJECT_DIR, "sym-lib-table"), "w", newline="\n") as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "phone_board")(type "KiCad")'
                '(uri "${KIPRJMOD}/lib/phone_board.kicad_sym")(options "")(descr "rev B custom symbols"))\n)\n')
    print("wrote lib/phone_board.kicad_sym")


if __name__ == "__main__":
    main()
