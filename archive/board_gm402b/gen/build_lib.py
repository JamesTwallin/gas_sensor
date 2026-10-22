"""Write lib/phone_board_mems.kicad_sym: symbols the stock KiCad library lacks.

  GM-402B    Winsen MEMS combustible-gas sensor, SMD-8 5x5 mm (LCSC C99754). Pin
             names/numbers follow LCSC's own symbol: 1 RH1, 3 RH2 (heater), 5 RS1,
             7 RS2 (sensing electrode), 2/4/6/8 NC.
  ME6211C28  Microne 2.8 V 450 mA LDO with CE, SOT-23-5 (LCSC C53099):
             1 VIN, 2 VSS, 3 CE, 4 NC, 5 VOUT (same order as the AP2112K).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kicad_lib import PROJECT_DIR, PROJECT_LIB  # noqa: E402
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
    gm = symbol("GM-402B", "S", "GM-402B", f"{PROJECT_LIB}:GM-402B",
                "Winsen GM-402B MEMS CH4/C3H8 sensor: heater RH1-RH2 (2.8 V, ~35 mA), electrode RS1-RS2",
                "https://www.winsen-sensor.com/sensors/mems-gas-sensor/gm402b.html", 7.62, 5.08, [
                    pin("passive", -10.16, 2.54, 0, "RH1", "1"),
                    pin("passive", -10.16, -2.54, 0, "RH2", "3"),
                    pin("passive", 10.16, 2.54, 180, "RS1", "5"),
                    pin("passive", 10.16, -2.54, 180, "RS2", "7"),
                    pin("no_connect", -5.08, -7.62, 90, "NC", "2"),
                    pin("no_connect", -2.54, -7.62, 90, "NC", "4"),
                    pin("no_connect", 2.54, -7.62, 90, "NC", "6"),
                    pin("no_connect", 5.08, -7.62, 90, "NC", "8"),
                ])
    ldo = symbol("ME6211C28", "U", "ME6211C28", "Package_TO_SOT_SMD:SOT-23-5",
                 "Microne ME6211C28M5G 2.8 V 450 mA LDO with chip enable, 220 mV dropout at 200 mA",
                 "https://jlcpcb.com/partdetail/54115-ME6211C28M5GN/C53099", 7.62, 5.08, [
                     pin("power_in", -10.16, 2.54, 0, "VIN", "1"),
                     pin("input", -10.16, -2.54, 0, "EN", "3"),
                     pin("power_in", 0, -7.62, 90, "GND", "2"),
                     pin("power_out", 10.16, 2.54, 180, "VOUT", "5"),
                     pin("no_connect", 10.16, -2.54, 180, "NC", "4"),
                 ])
    lib = ["kicad_symbol_lib", ["version", "20241209"], ["generator", QStr("kicad_symbol_editor")],
           ["generator_version", QStr("9.0")], gm, ldo]
    os.makedirs(os.path.join(PROJECT_DIR, "lib"), exist_ok=True)
    with open(os.path.join(PROJECT_DIR, "lib", PROJECT_LIB + ".kicad_sym"), "w", newline="\n") as f:
        f.write(dumps(lib) + "\n")
    with open(os.path.join(PROJECT_DIR, "sym-lib-table"), "w", newline="\n") as f:
        f.write(f'(sym_lib_table\n  (version 7)\n  (lib (name "{PROJECT_LIB}")(type "KiCad")'
                f'(uri "${{KIPRJMOD}}/lib/{PROJECT_LIB}.kicad_sym")(options "")(descr "rev D custom symbols"))\n)\n')
    print(f"wrote lib/{PROJECT_LIB}.kicad_sym")


if __name__ == "__main__":
    main()
