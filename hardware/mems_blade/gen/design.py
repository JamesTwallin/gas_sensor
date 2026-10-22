"""MEMS blade: a plug-in board for the rev F phone-companion board.

A test rig for choosing a cheaper gas sensor than the Figaro pair (docs/mems_rig.md). It
stands upright in a second notch in rev F's sensor-end edge, between the LPG can and
the H1 hole, and pokes out through a slot in the case face, so both sensors sit in the
outside air level with the Figaro caps and the air blade. It carries:
  - U1, a Saiya SY-CH4-37BPM MEMS methane sensor (heater ~3.6 V / 60 mW through R1 =
    82 ohm from 5 V, as its datasheet's circuit; RL = R3 + R4 = 20k, read at the tap);
  - U2, an SGX MiCS-5524 MEMS sensor for CO, H2 and other reducing gases, weak on
    methane (heater ~2.4 V / 76 mW through R2 = 82 ohm; RL = R5 + R6 = 200k, because its
    clean-air resistance is 100k-1.5M);
  - C1 and C2, decoupling for the switched 5 V heater feed and the 3V3 electrode supply.
The heaters are fed from rev F's switched +5V_MEMS; both electrode loops run from +3V3.
Five plated holes in the foot take short 0.5 mm wire legs, which bend down onto rev F's
J5 pads. (First drawn with flat pads meant to meet J5 at a right angle; the same joint
on the air blade could not be soldered: the pads missed by about 0.3 mm each way.)

Coordinates (mm, KiCad: x right, y down) are the blade's own: x across the blade, y along
it from the tip (y = 0) to the bottom of the tab (y = 18.4). On rev F, board y = 36.2 -
blade x, and blade y = 16.8 - height above the board's top. (The first drawing assumed
board y = 24.8 + blade x, the view from behind, which mirrored the whole blade: the same
mistake that made air blade rev A unusable. Someone looking at the parts from the case's
end wall sees blade x growing towards decreasing board y.) The blade's front (F.Cu, with
the parts) faces the case's sensor-end wall, away from the middle of the board: facing
the middle, the sensors would sweep through the case's H1 screw boss on the way into the
shell. The foot pads are on the back (B.Cu), facing J5.
"""

from parts import C, Part, R

PROJECT = "mems_blade"
TITLE = "MEMS blade - SY-CH4-37BPM + MiCS-5524 test rig for the rev F board"
REV = "A"
BLOCKS = ["blade"]

LIB = "mems_blade"
R0402 = "Resistor_SMD:R_0402_1005Metric"

PARTS = [
    # ---- U1: Saiya SY-CH4-37BPM (methane), LCSC C22363924 -----------------------------
    # Pads 1/5 heater, 3/7 sensing electrodes, the rest not connected; non-polar.
    Part("U1", f"{LIB}:SY-CH4-37BPM", f"{LIB}:SY-CH4-37BPM", "SY-CH4-37BPM",
         {"1": "U1_HTR", "5": "GND", "7": "+3V3", "3": "A_RL"}, "blade",
         lcsc="C22363924", mpn="SY-CH4-37BPM",
         description="Saiya MEMS CH4 sensor, 3.8 x 3.8 mm; heater 200-240 ohm, ~3.6 V / 60 mW"),
    R("R1", "82", "+5V_MEMS", "U1_HTR", "blade", lcsc="C23255", fp="Resistor_SMD:R_0603_1608Metric"),
    R("R3", "10k", "A_RL", "MEMS_A_TAP", "blade", lcsc="C25744"),
    R("R4", "10k", "MEMS_A_TAP", "GND", "blade", lcsc="C25744"),

    # ---- U2: SGX MiCS-5524 (CO / H2 / reducing gases), LCSC C3659348 -------------------
    # C/F heater, D/G sensing electrodes (datasheet pin table); the 82 ohm sits in the
    # heater's low side, as in SGX's recommended circuit. R2 drops ~84 mW: 0805 (125 mW).
    Part("U2", f"{LIB}:MICS-5524", f"{LIB}:MICS-5524", "MiCS-5524",
         {"F": "+5V_MEMS", "C": "U2_HTR", "G": "+3V3", "D": "B_RL"}, "blade",
         lcsc="C3659348", mpn="MICS-5524",
         description="SGX MEMS reducing-gas sensor, 5 x 7 mm; heater 74 ohm, ~2.4 V / 76 mW"),
    R("R2", "82", "U2_HTR", "GND", "blade", lcsc="C17841", fp="Resistor_SMD:R_0805_2012Metric"),
    R("R5", "100k", "B_RL", "MEMS_B_TAP", "blade", lcsc="C25741"),
    R("R6", "100k", "MEMS_B_TAP", "GND", "blade", lcsc="C25741"),

    C("C1", "1uF", "+5V_MEMS", "GND", "blade", lcsc="C52923"),
    C("C2", "100nF", "+3V3", "GND", "blade", lcsc="C1525"),
    Part("J1", "Connector_Generic:Conn_01x05", f"{LIB}:BladeFoot_1x05_Legs_P0.95mm", "FOOT",
         {"1": "MEMS_A_TAP", "2": "GND", "3": "+3V3", "4": "+5V_MEMS", "5": "MEMS_B_TAP"}, "blade",
         description="Wire legs to rev F J5: 1 sensor A tap, 2 GND, 3 3V3, 4 5V heaters, 5 sensor B tap"),
]
for _p in PARTS:
    if _p.ref == "J1":
        _p.no_assembly = _p.not_in_bom = True

# ---- Board ------------------------------------------------------------------
COPPER_LAYERS = 2
BOARD_THICKNESS = 1.6  # stiffer than the air blade's 1.0 for an 11.4 mm wide, 8 mm proud blade
RULES = dict(clearance=0.15, track=0.15, via_d=0.45, via_drill=0.2, min_clearance=0.127, min_track=0.127,
             min_via_d=0.45, min_drill=0.2, min_annular=0.125)
NETCLASSES = {
    "Heater": dict(track=0.3, clearance=0.15, nets=["+5V_MEMS", "U1_HTR", "U2_HTR"]),
}

# The blade is 11.4 mm wide (rev F board y 24.8-36.2: clear of the LPG can's cap hole on
# one side and the case's corner screw block on the other). Its tip stands 8.0 mm proud of
# the case face; the face's outer surface is at y 8.0, its inner surface at 9.8, and the
# board's top at 16.8 (the shoulders). The tab (x 5.65-10.05, board y 26.15-30.55) goes
# down into rev F's notch.
OUTLINE_POLY = [(0.0, 0.0), (11.4, 0.0), (11.4, 16.8), (10.05, 16.8), (10.05, 18.4), (5.65, 18.4),
                (5.65, 16.8), (0.0, 16.8)]
OUTLINE = (0.0, 0.0, 11.4, 18.4)  # bounding box
CORNER_R = 0.0
HIDE_REFS = True  # no room for reference designators

PLACEMENT = {
    # sensors at the tip, the methane sensor at the end farther from the LPG can
    # (board y 33.6; the MiCS-5524 at board y 27.8)
    "U2": (8.4, 4.0, 90, "F"),
    "U1": (2.6, 2.85, 0, "F"),
    # everything else below the face, inside the case
    "R2": (8.4, 11.3, 0, "F"), "C1": (5.4, 11.3, 0, "F"), "R1": (2.6, 11.3, 0, "F"),
    "R5": (9.5, 13.5, 0, "F"), "R6": (7.3, 13.5, 0, "F"), "C2": (5.4, 13.5, 0, "F"),
    "R3": (3.5, 13.5, 0, "F"), "R4": (1.4, 13.5, 0, "F"),
    # holes 1, 3, 5 (x 9.75, 7.85, 5.95: J5 pads 1, 3, 5) at y 15.9; holes 2, 4 at y 14.9
    "J1": (7.85, 15.9, 0, "F"),
}
ZONES = []
PLANE_LAYERS = []
POST_ROUTE_ZONES = []
SLOTS = []
SILK_HIDE_REFS = set()
SILK_TEXT = [
    dict(text="MEMS BLADE A", at=(3.0, 12.0), size=0.6, side="B"),
    dict(text="37BPM", at=(2.6, 6.0), size=0.6), dict(text="5524", at=(8.4, 8.5), size=0.5),
]
PREROUTE = []
PREROUTE_VIAS = []
STITCH_PITCH = 0  # no GND stitching on the blade
