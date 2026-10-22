"""Air blade: a small plug-in board for the rev E phone-companion board.

It stands upright in a notch in rev E's sensor-end edge, between the two gas
sensor cans, and pokes out through a slot in the case face, so its tip sits in the
outside air level with the sensor caps. It carries:
  - RT1, the heated airflow thermistor (1k NTC, fed 2.7 mW through rev E's R28),
    on its own prong so its warmth does not reach the SHT40;
  - U1, an SHT40 at I2C 0x46 (the -CD1B variant; a -BD1B at 0x45 also works, an -AD1B
    at 0x44 does not): the outside air's temperature and
    humidity (rev E's on-board SHT40 at 0x44 reads the case air), and the ambient
    temperature the airflow calculation needs;
  - C1, U1's decoupling capacitor.
Rev B: five plated holes in its foot take short 0.5 mm wire legs, which bend down
onto rev E's J3 pads. (Rev A had flat pads meant to meet J3 at a right angle: they
missed J3 by about 0.3 mm each way, and levering the blade tore its 0.15 mm tracks.
Rev A's files are in ../rev_a.) Rev A was also drawn mirror-image: its foot
pads met J3 in reverse order (its GND on rev E's SCL, its SDA on the thermistor
feed), which clamped rev E's I2C bus when soldered. Rev B swaps the prongs and the
foot order.

Coordinates (mm, KiCad: x right, y down) are the blade's own: x across the blade,
y along it from the tip (y = 0) to the bottom of the tab (y = 14.9). On rev E,
board y = 12.65 + blade x, and blade y = 13.3 - height above the board's top.
(Rev A assumed board y = 18.35 - blade x: that is the view from behind the blade.)
The blade's front (F.Cu, with the parts) faces the middle of rev E, so someone
looking at the parts from the middle of rev E sees blade x growing towards
increasing board y; J3 pad 1 (board y 13.5) meets foot hole 1 at blade x 0.85.
"""

from parts import C, Part

PROJECT = "air_blade"
TITLE = "Air blade - airflow thermistor + outside-air SHT40 for the rev E board"
REV = "B"
BLOCKS = ["blade"]

PARTS = [
    Part("U1", "Sensor_Humidity:SHT4x", "Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",
         "SHT40-CD1B", {"1": "SDA", "2": "SCL", "3": "+3V3", "4": "GND"}, "blade",
         lcsc="C7461852", mpn="SHT40-CD1B-R3", description="I2C 0x46 (rev E's on-board SHT40 is 0x44)"),
    C("C1", "100nF", "+3V3", "GND", "blade", lcsc="C1525"),
    Part("RT1", "Device:Thermistor_NTC", "Resistor_SMD:R_0603_1608Metric", "1k NTC",
         {"1": "TH_HOT", "2": "GND"}, "blade", lcsc="C152577", mpn="NCP18XQ102J03RB",
         description="Murata 1k at 25 degC, B25/50 3650 K, 1 mW/K; self-heated through rev E's R28"),
    Part("J1", "Connector_Generic:Conn_01x05", "air_blade:BladeFoot_1x05_Legs", "FOOT",
         {"1": "TH_HOT", "2": "GND", "3": "+3V3", "4": "SCL", "5": "SDA"}, "blade",
         description="Wire legs to rev E J3: 1 heated thermistor, 2 GND, 3 3V3, 4 SCL, 5 SDA"),
]
for _p in PARTS:
    if _p.ref == "J1":
        _p.no_assembly = _p.not_in_bom = True

# ---- Board ------------------------------------------------------------------
COPPER_LAYERS = 2
BOARD_THICKNESS = 1.6  # rev A was drawn at 1.0; JLC made it at 1.6, and the case now expects 1.6
RULES = dict(clearance=0.15, track=0.15, via_d=0.45, via_drill=0.2, min_clearance=0.127, min_track=0.127,
             min_via_d=0.45, min_drill=0.2, min_annular=0.125)
NETCLASSES = {}

# Prong A (heated thermistor) x 0.5-2.1, prong B (SHT40) x 3.1-5.2, a 1.0 mm gap
# between them down to y 5.8 (below the case face, so the prongs are separate where
# the air is). Rev A had them the other way round, which put each part over the wrong
# pocket in the case. The body widens to the foot at y 11.2 (rev A: 11.8; the
# shoulders rest on the board); the tab (x 0.85-4.85) goes down into rev E's notch.
OUTLINE_POLY = [(0.5, 0.0), (2.1, 0.0), (2.1, 5.8), (3.1, 5.8), (3.1, 0.0), (5.2, 0.0), (5.2, 11.2),
                (5.7, 11.2), (5.7, 13.3), (4.85, 13.3), (4.85, 14.9), (0.85, 14.9), (0.85, 13.3),
                (0.0, 13.3), (0.0, 11.2), (0.5, 11.2)]
OUTLINE = (0.0, 0.0, 5.7, 14.9)  # bounding box
CORNER_R = 0.0
HIDE_REFS = True  # no room for reference designators

PLACEMENT = {
    "U1": (4.15, 1.75, 90, "F"),
    "C1": (4.15, 3.9, 90, "F"),
    "RT1": (1.3, 1.6, 90, "F"),  # board y 13.95, over the case's thermistor pocket
    # holes 1, 3, 5 (x 0.85, 2.85, 4.85) at y 12.4; holes 2, 4 (x 1.85, 3.85) at y 11.4
    "J1": (2.85, 12.4, 0, "F"),
}
ZONES = []  # no copper pours: copper would carry the thermistor's heat away
PLANE_LAYERS = []
POST_ROUTE_ZONES = []
SLOTS = []
SILK_HIDE_REFS = set()
SILK_TEXT = [
    dict(text="AIR", at=(2.85, 8.0), size=0.7, side="B"),
    dict(text="BLADE B", at=(2.85, 9.3), size=0.5, side="B"),
]
# Hand-routed, no pours. Thin (0.15 mm) tracks on the prongs, where copper would carry
# the thermistor's heat away; 0.25 mm below y 6.6, inside the case, on the way to the
# foot's holes. The SHT40's footprint keeps tracks and vias off its body (Sensirion),
# so its supply pads link up to vias just above it and SDA / SCL leave from the pads'
# outer ends; C1's pads drop to B.Cu through vias in the pads (filled, as on rev E).
# The foot's holes are plated, so they join F.Cu and B.Cu themselves. The foot order
# (TH_HOT, GND, 3V3, SCL, SDA from x 0.85) puts SCL left of SDA, the reverse of the
# SHT40's pads, so SCL crosses under SDA through one via at (4.6, 7.5).
W = 0.15
T = 0.25
PREROUTE = [
    # prong B (SHT40): supply up to vias, signals down the prong's edges
    dict(net="GND", layer="F.Cu", width=W, pts=[(3.75, 1.05), (3.75, 0.55)]),
    dict(net="+3V3", layer="F.Cu", width=W, pts=[(4.55, 1.05), (4.55, 0.55)]),
    dict(net="SDA", layer="F.Cu", width=W, pts=[(3.75, 2.6), (3.5, 2.85), (3.5, 6.6)]),
    dict(net="SDA", layer="F.Cu", width=T, pts=[(3.5, 6.6), (3.5, 8.0), (4.7, 9.2), (4.7, 11.75), (4.85, 12.4)]),
    dict(net="SCL", layer="F.Cu", width=W, pts=[(4.55, 2.6), (4.8, 2.85), (4.8, 6.6), (4.6, 6.8), (4.6, 7.5)]),
    dict(net="SCL", layer="B.Cu", width=T, pts=[(4.6, 7.5), (3.85, 8.25), (3.85, 11.4)]),
    dict(net="GND", layer="B.Cu", width=W, pts=[(3.75, 0.55), (3.55, 0.75), (3.55, 6.6)]),
    dict(net="GND", layer="B.Cu", width=T, pts=[(3.55, 6.6), (1.85, 8.3), (1.85, 11.4)]),
    dict(net="GND", layer="B.Cu", width=W, pts=[(4.15, 3.42), (3.55, 3.42)]),
    dict(net="+3V3", layer="B.Cu", width=W, pts=[(4.55, 0.55), (4.75, 0.75), (4.75, 6.15)]),
    dict(net="+3V3", layer="B.Cu", width=T, pts=[(4.75, 6.15), (2.85, 8.05), (2.85, 12.4)]),
    dict(net="+3V3", layer="B.Cu", width=W, pts=[(4.15, 4.38), (4.75, 4.38)]),
    # prong A (heated thermistor)
    dict(net="TH_HOT", layer="F.Cu", width=W, pts=[(1.3, 2.425), (1.3, 6.6)]),
    dict(net="TH_HOT", layer="F.Cu", width=T, pts=[(1.3, 6.6), (1.3, 10.3), (0.95, 10.65), (0.95, 11.8), (0.85, 12.4)]),
    dict(net="GND", layer="B.Cu", width=W, pts=[(1.3, 0.775), (1.3, 6.6)]),
    dict(net="GND", layer="B.Cu", width=T, pts=[(1.3, 6.6), (1.3, 10.0), (1.85, 10.55)]),
]
PREROUTE_VIAS = [dict(net="GND", at=(3.75, 0.55)), dict(net="+3V3", at=(4.55, 0.55)),
                 dict(net="GND", at=(4.15, 3.42)), dict(net="+3V3", at=(4.15, 4.38)),
                 dict(net="SCL", at=(4.6, 7.5)), dict(net="GND", at=(1.3, 0.775))]
