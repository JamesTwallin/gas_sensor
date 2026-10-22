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
Five pads on its foot solder to rev E's J3 at a right angle.

Coordinates (mm, KiCad: x right, y down) are the blade's own: x across the blade,
y along it from the tip (y = 0) to the bottom of the tab (y = 14.9). On rev E,
blade x = 18.35 - board y, and blade y = 13.3 - height above the board's top.
The blade's front (F.Cu, with the parts) faces the middle of rev E.
"""

from parts import C, Part

PROJECT = "air_blade"
TITLE = "Air blade - airflow thermistor + outside-air SHT40 for the rev E board"
REV = "A"
BLOCKS = ["blade"]

PARTS = [
    Part("U1", "Sensor_Humidity:SHT4x", "Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",
         "SHT40-CD1B", {"1": "SDA", "2": "SCL", "3": "+3V3", "4": "GND"}, "blade",
         lcsc="C7461852", mpn="SHT40-CD1B-R3", description="I2C 0x46 (rev E's on-board SHT40 is 0x44)"),
    C("C1", "100nF", "+3V3", "GND", "blade", lcsc="C1525"),
    Part("RT1", "Device:Thermistor_NTC", "Resistor_SMD:R_0603_1608Metric", "1k NTC",
         {"1": "TH_HOT", "2": "GND"}, "blade", lcsc="C152577", mpn="NCP18XQ102J03RB",
         description="Murata 1k at 25 degC, B25/50 3650 K, 1 mW/K; self-heated through rev E's R28"),
    Part("J1", "Connector_Generic:Conn_01x05", "air_blade:BladeFoot_1x05_P1.0mm", "FOOT",
         {"1": "TH_HOT", "2": "GND", "3": "+3V3", "4": "SCL", "5": "SDA"}, "blade",
         description="Solders to rev E J3: 1 heated thermistor, 2 GND, 3 3V3, 4 SCL, 5 SDA"),
]
for _p in PARTS:
    if _p.ref == "J1":
        _p.no_assembly = _p.not_in_bom = True

# ---- Board ------------------------------------------------------------------
COPPER_LAYERS = 2
BOARD_THICKNESS = 1.0
RULES = dict(clearance=0.15, track=0.15, via_d=0.45, via_drill=0.2, min_clearance=0.127, min_track=0.127,
             min_via_d=0.45, min_drill=0.2, min_annular=0.125)
NETCLASSES = {}

# Prong A (SHT40) x 0.5-2.6, prong B (heated thermistor) x 3.6-5.2, a 1.0 mm gap
# between them down to y 5.8 (below the case face, so the prongs are separate where
# the air is). The body widens to the foot at y 11.8 (the shoulders rest on the
# board); the tab (x 0.85-4.85) goes down into rev E's notch.
OUTLINE_POLY = [(0.5, 0.0), (2.6, 0.0), (2.6, 5.8), (3.6, 5.8), (3.6, 0.0), (5.2, 0.0), (5.2, 11.8),
                (5.7, 11.8), (5.7, 13.3), (4.85, 13.3), (4.85, 14.9), (0.85, 14.9), (0.85, 13.3),
                (0.0, 13.3), (0.0, 11.8), (0.5, 11.8)]
OUTLINE = (0.0, 0.0, 5.7, 14.9)  # bounding box
CORNER_R = 0.0
HIDE_REFS = True  # no room for reference designators

PLACEMENT = {
    "U1": (1.55, 1.75, 90, "F"),
    "C1": (1.55, 3.9, 90, "F"),
    "RT1": (4.4, 1.6, 90, "F"),
    "J1": (2.85, 12.55, 0, "F"),
}
ZONES = []  # no copper pours: copper would carry the thermistor's heat away
PLANE_LAYERS = []
POST_ROUTE_ZONES = []
SLOTS = []
SILK_HIDE_REFS = set()
SILK_TEXT = [
    dict(text="AIR", at=(2.85, 8.0), size=0.7, side="B"),
    dict(text="BLADE A", at=(2.85, 9.3), size=0.5, side="B"),
]
# Hand-routed: 0.15 mm tracks, no pours. The SHT40's footprint keeps tracks and vias
# off its body (Sensirion), so its supply pads link up to vias just above it and SDA /
# SCL leave from the pads' outer ends; C1's pads drop to B.Cu through vias in the
# pads (filled, as on rev E).
W = 0.15
PREROUTE = [
    # prong A (SHT40)
    dict(net="GND", layer="F.Cu", width=W, pts=[(1.15, 1.05), (1.15, 0.55)]),
    dict(net="+3V3", layer="F.Cu", width=W, pts=[(1.95, 1.05), (1.95, 0.55)]),
    dict(net="SDA", layer="F.Cu", width=W, pts=[(1.15, 2.6), (0.9, 2.85), (0.9, 12.1), (0.85, 12.15)]),
    dict(net="SCL", layer="F.Cu", width=W, pts=[(1.95, 2.6), (2.2, 2.85), (2.2, 10.9), (1.85, 11.25), (1.85, 12.1)]),
    dict(net="GND", layer="B.Cu", width=W, pts=[(1.15, 0.55), (0.95, 0.75), (0.95, 6.6), (3.85, 9.5), (3.85, 11.55)]),
    dict(net="GND", layer="B.Cu", width=W, pts=[(1.55, 3.42), (0.95, 3.42)]),
    dict(net="+3V3", layer="B.Cu", width=W, pts=[(1.95, 0.55), (2.15, 0.75), (2.15, 6.15), (2.85, 6.85)]),
    dict(net="+3V3", layer="B.Cu", width=W, pts=[(1.55, 4.38), (2.15, 4.38)]),
    dict(net="+3V3", layer="F.Cu", width=W, pts=[(2.85, 6.85), (2.85, 12.1)]),
    # prong B (heated thermistor)
    dict(net="TH_HOT", layer="F.Cu", width=W, pts=[(4.4, 2.425), (4.4, 11.5), (4.85, 11.95), (4.85, 12.1)]),
    dict(net="GND", layer="B.Cu", width=W, pts=[(4.4, 0.775), (4.4, 10.0), (3.85, 10.55)]),
    dict(net="GND", layer="F.Cu", width=W, pts=[(3.85, 11.55), (3.85, 12.1)]),
]
PREROUTE_VIAS = [dict(net="GND", at=(1.15, 0.55)), dict(net="+3V3", at=(1.95, 0.55)),
                 dict(net="GND", at=(1.55, 3.42)), dict(net="+3V3", at=(1.55, 4.38)),
                 dict(net="+3V3", at=(2.85, 6.85)), dict(net="GND", at=(3.85, 11.55)),
                 dict(net="GND", at=(4.4, 0.775))]
