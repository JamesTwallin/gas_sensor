"""Rev D phone-companion board with MEMS gas sensors: the single source of truth
for schematic and PCB.

Rev D is rev C (hardware/phone_board) with the two Figaro TO-5 cans replaced by
Winsen GM-402B MEMS sensors and the 5 V heater boost replaced by a 2.8 V LDO.
Everything else (ESP32-S3-MINI-1, charger, USB, ADS1115, SHT40 tongue) is the
rev C circuit. Spec: docs/phone_board.md plus the rev D notes in README.md.
Coordinates are mm, KiCad convention (x right, y down), origin top-left.
"""

from parts import C, Part, R

PROJECT = "phone_board_mems"
TITLE = "Methane detector - phone companion board, MEMS sensors"
REV = "D"
BLOCKS = ["usb_power", "regulators", "mcu", "sensors", "adc_env"]
LIB = "phone_board_mems"

# ---- LCSC part numbers (JLCPCB parts API, checked 2026-09-17; C99754 and C53099 2026-09-28) ----
R10K, R5K1, R100K, R4K7, R1K, R20K, R1K5, R1K8 = "C25744", "C25905", "C25741", "C25900", "C11702", "C25765", "C25867", "C25871"
R1M = "C26083"
C100N, C1U, C10U_0603 = "C1525", "C52923", "C19702"
F0603 = "Capacitor_SMD:C_0603_1608Metric"
F0805 = "Capacitor_SMD:C_0805_2012Metric"


def Cap10u(ref, a, b, block):
    return C(ref, "10uF", a, b, block, lcsc=C10U_0603, fp=F0603)


def Cap100n(ref, a, b, block):
    return C(ref, "100nF", a, b, block, lcsc=C100N)


def TP(ref, net, block):
    p = Part(ref, "Connector:TestPoint", "TestPoint:TestPoint_Pad_D1.0mm", net, {"1": net}, block)
    p.no_assembly = p.not_in_bom = True
    return p


def Hole(ref):
    p = Part(ref, "Mechanical:MountingHole", "MountingHole:MountingHole_2.2mm_M2", "M2", {}, "mcu")
    p.no_assembly = p.not_in_bom = True
    return p


def sensor_channel(n, s_ref, name, block):
    """GM-402B: heater RH1-RH2 across +2V8_HTR/GND (~35 mA). Electrode loop from +3V3
    through the element into a 10k+10k load; the ADC reads the midpoint tap = VRL/2
    (<= 1.65 V). Same topology as rev B/C with VC = 3.3 V and RL = 20k."""
    rl, tap = f"{name}_RL", f"{name}_TAP"
    s = Part(s_ref, f"{LIB}:GM-402B", f"{LIB}:GM-402B", "GM-402B",
             {"1": "+2V8_HTR", "3": "GND", "5": "+3V3", "7": rl}, block, lcsc="C99754", mpn="GM-402B",
             description="Winsen MEMS CH4/C3H8 sensor, SMD 5x5 mm, heater 2.8 V ~35 mA")
    return [
        s,
        R(f"R{n}", "10k", rl, tap, block, lcsc=R10K),
        R(f"R{n + 1}", "10k", tap, "GND", block, lcsc=R10K),
        C(f"C{n}", "100nF", tap, "GND", block, lcsc=C100N),
        # ESP32 fallback ADC link, not fitted by default (see rev C notes).
        R(f"R{n + 2}", "1k", tap, f"{name}_FB", block, lcsc=R1K, dnp=True),
    ]


PARTS = [
    # ---- USB-C, ESD, charger / power path, battery, power switch (rev C) -----
    Part("J1", "Connector:USB_C_Receptacle_USB2.0_16P", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         "TYPE-C-31-M-12", {"VBUS": "VBUS", "GND": "GND", "SHIELD": "GND", "CC1": "CC1", "CC2": "CC2",
                            "D+": "USB_DP", "D-": "USB_DN"}, "usb_power", lcsc="C165948"),
    R("R1", "5.1k", "CC1", "GND", "usb_power", lcsc=R5K1),
    R("R2", "5.1k", "CC2", "GND", "usb_power", lcsc=R5K1),
    Part("U1", "Power_Protection:USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", "USBLC6-2SC6",
         {"1": "USB_DN", "6": "USB_DN", "3": "USB_DP", "4": "USB_DP", "2": "GND", "5": "VBUS"},
         "usb_power", lcsc="C7519"),
    Part("U2", "Battery_Management:BQ24073RGT", "Package_DFN_QFN:VQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm",
         "BQ24073RGTR", {"13": "VBUS", "10": "VSYS", "11": "VSYS", "2": "VBAT", "3": "VBAT",
                         "1": "BQ_TS", "4": "GND", "5": "GND", "6": "BQ_EN1", "7": "PGOOD_N",
                         "8": "GND", "17": "GND", "9": "CHG_N", "12": "BQ_ILIM", "15": "GND",
                         "16": "BQ_ISET"},  # 14 TMR open = default safety timers
         "usb_power", lcsc="C15220",
         description="EN2=0 EN1=1: USB500 input limit; ISET 1.8k = ~500 mA charge; TS fixed 10k (no NTC)"),
    C("C1", "10uF", "VBUS", "GND", "usb_power", lcsc="C15850", fp=F0805),  # 25 V: VBUS can ring on hot-plug
    Cap10u("C2", "VSYS", "GND", "usb_power"),
    Cap10u("C3", "VBAT", "GND", "usb_power"),
    R("R3", "10k", "BQ_TS", "GND", "usb_power", lcsc=R10K),
    R("R4", "1.5k", "BQ_ILIM", "GND", "usb_power", lcsc=R1K5),
    R("R5", "1.8k", "BQ_ISET", "GND", "usb_power", lcsc=R1K8),
    R("R6", "10k", "+3V3", "CHG_N", "usb_power", lcsc=R10K),
    R("R7", "10k", "+3V3", "PGOOD_N", "usb_power", lcsc=R10K),
    R("R26", "100k", "VBUS", "BQ_EN1", "usb_power", lcsc=R100K),  # EN1 high with EN2 low = USB500
    Part("J2", "Connector_Generic:Conn_01x02", "Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",
         "LiPo 1S", {"1": "GND", "2": "BAT_CELL"}, "usb_power", lcsc="C295747",
         description="JST-PH battery: pin 1 = -, pin 2 = + (Adafruit/SparkFun convention) - CHECK YOUR CELL"),
    Part("Q1", "Transistor_FET:AO3401A", "Package_TO_SOT_SMD:SOT-23", "AO3401A",
         {"G": "GND", "D": "BAT_CELL", "S": "VBAT"}, "usb_power", lcsc="C15127"),  # reverse-cell protection
    Part("SW1", "Switch:SW_SPDT", "Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02", "POWER",
         {"1": "VSYS", "2": "PWR_EN"}, "usb_power", lcsc="C431540",
         description="Logic-level power switch: drives the regulator enables, not the battery current"),
    R("R27", "1M", "PWR_EN", "GND", "usb_power", lcsc=R1M),  # holds regulators off when SW1 is open

    # ---- 3.3 V LDO and 2.8 V heater LDO -------------------------------------
    Part("U3", "Regulator_Linear:AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5", "AP2112K-3.3",
         {"VIN": "VSYS", "EN": "PWR_EN", "GND": "GND", "VOUT": "+3V3"}, "regulators", lcsc="C51118"),
    Cap10u("C4", "+3V3", "GND", "regulators"),
    C("C16", "1uF", "VSYS", "GND", "regulators", lcsc=C1U),  # LDO input cap, at U3 VIN
    # Heater rail: 2.8 V +/-0.1 V per the GM-402B spec, ~35 mA per sensor. An LDO replaces
    # rev C's 5 V boost, inductor and feedback network. EN is driven by HTR_EN exactly as the
    # boost's was, so the firmware's heater control is unchanged.
    Part("U4", f"{LIB}:ME6211C28", "Package_TO_SOT_SMD:SOT-23-5", "ME6211C28",
         {"VIN": "VSYS", "EN": "HTR_EN", "GND": "GND", "VOUT": "+2V8_HTR"}, "regulators",
         lcsc="C53099", mpn="ME6211C28M5G-N",
         description="2.8 V heater LDO; dissipates < 0.1 W at 4.2 V VSYS with both heaters on"),
    C("C5", "1uF", "VSYS", "GND", "regulators", lcsc=C1U),
    Cap10u("C6", "+2V8_HTR", "GND", "regulators"),
    R("R10", "100k", "HTR_EN", "GND", "regulators", lcsc=R100K),  # heaters off until firmware drives HTR_EN

    # ---- ESP32-S3-MINI-1, reset/boot, LED, test points (rev C) --------------
    Part("U5", "RF_Module:ESP32-S3-MINI-1", "RF_Module:ESP32-S2-MINI-1", "ESP32-S3-MINI-1-N8",
         {"GND": "GND", "3": "+3V3", "45": "ESP_EN", "4": "BOOT", "5": "CH4_FB", "6": "LPG_FB",
          "9": "CHG_N", "10": "PGOOD_N", "11": "HTR_EN", "12": "I2C_SDA", "13": "I2C_SCL",
          "14": "ADS_RDY", "23": "USB_DN", "24": "USB_DP", "34": "LED_DIN", "39": "TXD0", "40": "RXD0"},
         "mcu", lcsc="C2913206",
         description="S2-MINI-1 land pattern is the S3-MINI-1 pattern (same pads 1-65)"),
    Cap10u("C8", "+3V3", "GND", "mcu"),
    Cap100n("C9", "+3V3", "GND", "mcu"),
    R("R11", "10k", "+3V3", "ESP_EN", "mcu", lcsc=R10K),
    C("C10", "1uF", "ESP_EN", "GND", "mcu", lcsc=C1U),
    R("R12", "10k", "+3V3", "BOOT", "mcu", lcsc=R10K),
    Part("SW2", "Switch:SW_Push", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", "RESET",
         {"1": "ESP_EN", "2": "GND"}, "mcu", lcsc="C318884"),
    Part("SW3", "Switch:SW_Push", "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", "BOOT",
         {"1": "BOOT", "2": "GND"}, "mcu", lcsc="C318884"),
    Part("D1", "LED:WS2812B-2020", "LED_SMD:LED_WS2812B-2020_PLCC4_2.0x2.0mm", "WS2812B-2020",
         {"DIN": "LED_DIN", "VDD": "+3V3", "VSS": "GND"}, "mcu", lcsc="C52917434"),
    Cap100n("C11", "+3V3", "GND", "mcu"),
    TP("TP1", "TXD0", "mcu"), TP("TP2", "RXD0", "mcu"), TP("TP3", "GND", "mcu"),
    TP("TP4", "+3V3", "mcu"), TP("TP5", "VBAT", "mcu"), TP("TP6", "+2V8_HTR", "mcu"),
    Hole("H1"), Hole("H2"),

    # ---- Gas sensors: two GM-402B sockets (channel names kept for the firmware/app) ----
    *sensor_channel(20, "S1", "CH4", "sensors"),
    *sensor_channel(23, "S2", "LPG", "sensors"),

    # ---- ADS1115 + monitors, SHT40 (rev C) -----------------------------------
    Part("U6", "Analog_ADC:ADS1115IDGS", "Package_SO:MSOP-10_3x3mm_P0.5mm", "ADS1115IDGSR",
         {"1": "GND", "2": "ADS_RDY", "3": "GND", "4": "CH4_TAP", "5": "LPG_TAP", "6": "VBAT_SENSE",
          "7": "HTR_SENSE", "8": "+3V3", "9": "I2C_SDA", "10": "I2C_SCL"}, "adc_env", lcsc="C37593"),
    Cap100n("C12", "+3V3", "GND", "adc_env"),
    R("R13", "1M", "VBAT", "VBAT_SENSE", "adc_env", lcsc=R1M),
    R("R14", "1M", "VBAT_SENSE", "GND", "adc_env", lcsc=R1M),
    Cap100n("C13", "VBAT_SENSE", "GND", "adc_env"),
    # Heater rail monitor: 1.4 V at the tap when the rail is at 2.8 V.
    R("R15", "100k", "+2V8_HTR", "HTR_SENSE", "adc_env", lcsc=R100K),
    R("R16", "100k", "HTR_SENSE", "GND", "adc_env", lcsc=R100K),
    Cap100n("C14", "HTR_SENSE", "GND", "adc_env"),
    R("R17", "4.7k", "+3V3", "I2C_SDA", "adc_env", lcsc=R4K7),
    R("R18", "4.7k", "+3V3", "I2C_SCL", "adc_env", lcsc=R4K7),
    R("R19", "10k", "+3V3", "ADS_RDY", "adc_env", lcsc=R10K),
    Part("U7", "Sensor_Humidity:SHT4x", "Sensor_Humidity:Sensirion_DFN-4_1.5x1.5mm_P0.8mm_SHT4x_NoCentralPad",
         "SHT40-AD1B", {"1": "I2C_SDA", "2": "I2C_SCL", "3": "+3V3", "4": "GND"}, "adc_env",
         lcsc="C2909890", mpn="SHT40-AD1B-R2", description="I2C 0x44, +/-1.8 %RH"),
    Cap100n("C15", "+3V3", "GND", "adc_env"),
]

# ---- Board ------------------------------------------------------------------
COPPER_LAYERS = 4
RULES = dict(clearance=0.15, track=0.2, via_d=0.6, via_drill=0.3, min_clearance=0.127, min_track=0.127,
             min_via_d=0.45, min_drill=0.2, min_annular=0.13)
NETCLASSES = {
    "Power": dict(track=0.5, clearance=0.15, nets=["VSYS", "VBAT", "+2V8_HTR", "BAT_CELL"]),
    "Vbus": dict(track=0.4, clearance=0.15, nets=["VBUS"]),
    "Supply3V3": dict(track=0.3, nets=["+3V3"]),
}

OUTLINE = (0, 0, 55, 31)
CORNER_R = 2.0

# (x, y, rotation, side). Rev C's MCU column and power/USB column are kept
# (the MCU column verbatim, the USB/charger column moved up 2 mm into the room
# the boost converter left). The sensors are SMD now, so the right end is a
# plain column: two GM-402B rotated 180 deg so their electrode pads face the
# ADC, the battery connector under them leaving through the right edge.
PLACEMENT = {
    "U5": (9.8, 8.5, 90, "F"),
    "C8": (8.0, 18.6, 0, "F"), "C9": (11.0, 18.6, 0, "F"),
    "R11": (22.5, 10.0, 90, "F"), "C10": (24.0, 10.0, 90, "F"),
    "D1": (22.2, 7.0, 0, "F"), "C11": (24.7, 7.0, 90, "F"),
    "TP1": (22.3, 13.4, 0, "F"), "TP2": (24.6, 13.4, 0, "F"),
    "TP3": (22.3, 15.9, 0, "F"), "TP4": (24.6, 15.9, 0, "F"),
    "SW2": (21.8, 19.9, 0, "F"), "SW3": (21.8, 27.0, 0, "F"), "R12": (17.6, 23.6, 0, "F"),
    "U7": (8.5, 26.0, 0, "F"), "C15": (10.6, 26.0, 90, "F"),
    "SW1": (31.0, 1.8, 180, "F"),  # lever overhangs the top edge; pins face inboard
    "U3": (27.5, 10.5, 0, "F"), "C4": (27.5, 14.0, 0, "F"), "C16": (26.4, 7.6, 0, "F"),
    "R27": (29.5, 6.2, 0, "F"), "R10": (32.5, 11.0, 90, "F"),
    "U4": (38.5, 8.0, 0, "F"), "C5": (35.3, 8.0, 90, "F"), "C6": (41.3, 8.0, 90, "F"),
    "J1": (31.0, 27.3, 0, "F"), "U1": (31.0, 19.2, 0, "F"),
    "R1": (27.5, 20.5, 90, "F"), "R2": (37.0, 23.5, 90, "F"),
    "U2": (40.5, 21.5, 0, "F"), "C1": (36.2, 20.0, 0, "F"), "C2": (38.0, 17.3, 0, "F"),
    "C3": (45.0, 19.1, 0, "F"),
    "R3": (38.6, 24.6, 0, "F"), "R4": (38.6, 26.2, 0, "F"), "R5": (38.6, 27.8, 0, "F"),
    "R6": (34.4, 17.0, 0, "F"), "R7": (34.4, 15.6, 0, "F"), "R26": (38.6, 29.6, 0, "F"),
    "Q1": (41.6, 27.8, 90, "F"), "TP5": (43.5, 24.75, 0, "F"),
    "J2": (49.6, 26.1, 90, "F"),  # cable leaves through the right edge
    "U6": (44.0, 9.5, 90, "F"), "C12": (47.0, 9.5, 90, "F"),
    "R13": (39.0, 15.0, 90, "F"), "R14": (37.6, 15.0, 90, "F"), "C13": (36.2, 15.0, 90, "F"),
    "R17": (41.6, 17.75, 0, "F"), "R19": (43.7, 17.75, 0, "F"), "R18": (45.8, 17.75, 0, "F"),
    "R15": (50.0, 18.0, 90, "F"), "R16": (51.5, 18.0, 90, "F"), "C14": (53.0, 18.0, 90, "F"),
    "TP6": (46.5, 4.9, 0, "F"),
    "S1": (51.5, 6.5, 180, "F"), "R20": (49.7, 2.5, 90, "F"), "R21": (51.2, 2.5, 90, "F"),
    "C20": (52.7, 2.5, 90, "F"), "R22": (50.5, 20.5, 0, "F"),
    # S2's load resistor sits just below its electrode pad so the RL track has a straight run
    "S2": (51.5, 13.5, 180, "F"), "R23": (47.7, 15.8, 90, "F"), "R24": (46.5, 15.8, 90, "F"),
    "C23": (46.5, 13.9, 90, "F"), "R25": (52.5, 20.5, 0, "F"),
    "H1": (38.5, 2.9, 0, "F"), "H2": (23.0, 2.6, 0, "F"),
}

ZONES = [
    dict(net="GND", layers=["In1.Cu"], name="GND plane"),
    # keep routing 0.35 mm off the SHT40 tongue slot (Freerouting ignores inner cutouts)
    dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("tracks", "vias"), name="slot keepout h",
         pts=[(0.65, 21.15), (16.35, 21.15), (16.35, 22.85), (0.65, 22.85)]),
    dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("tracks", "vias"), name="slot keepout v",
         pts=[(14.65, 21.15), (16.35, 21.15), (16.35, 27.85), (14.65, 27.85)]),
    dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("fills",), name="SHT40 no-copper",
         pts=[(7.2, 24.7), (9.8, 24.7), (9.8, 27.3), (7.2, 27.3)]),  # Sensirion: no copper under the sensor
]
PLANE_LAYERS = ["In1.Cu"]
POST_ROUTE_ZONES = [dict(net="GND", layers=["F.Cu", "In2.Cu", "B.Cu"], name="GND fill")]
# 1 mm L-shaped slot that cuts the SHT40 tongue free on two sides (closed polygon).
# The heaters are now ~40 mW each, so the tongue mainly isolates the SHT40 from
# the ESP32 and charger; it is shorter than rev C's to suit the 31 mm board.
SLOTS = [[(1.0, 21.5), (16.0, 21.5), (16.0, 27.5), (15.0, 27.5), (15.0, 22.5), (1.0, 22.5)]]
SILK_HIDE_REFS = {"SW2", "SW3"}
SILK_TEXT = [
    dict(text="+", at=(45.4, 25.1), size=1.0), dict(text="-", at=(45.4, 27.1), size=1.0),
    dict(text="ON", at=(36.6, 5.1), size=0.8),
    dict(text="RST", at=(21.8, 23.5), size=0.8), dict(text="BOOT", at=(21.8, 30.4), size=0.8),
    dict(text="TX", at=(22.3, 12.0), size=0.6), dict(text="RX", at=(24.6, 12.0), size=0.6),
    dict(text="GND", at=(22.3, 17.3), size=0.6), dict(text="3V3", at=(24.6, 17.3), size=0.6),
    dict(text="CH4 detector rev D MEMS", at=(31.0, 14.5), size=1.0, side="B"),
]

# Battery pin 2 (+) of the edge-rotated J2 to the reverse-protection FET drain (Q1 pad 3).
BAT_CELL_PTS = [(46.75, 25.1), (45.5, 25.1), (43.737, 26.863), (41.6, 26.863)]

# Hand-routed tracks (locked; Freerouting routes around them). No boost loop any
# more: what remains is the SHT40 tongue, the ESP32 3V3 chain and GND stubs.
PREROUTE = [
    # SHT40 on the slotted tongue: decoupling, I2C out through the neck on B.Cu,
    # +3V3 in through the neck on F.Cu (the autorouter can't thread the neck).
    dict(net="+3V3", layer="F.Cu", width=0.25, pts=[(9.2, 26.4), (10.1, 26.4), (10.6, 26.48)]),
    dict(net="GND", layer="F.Cu", width=0.25, pts=[(9.2, 25.6), (10.1, 25.6), (10.6, 25.52)]),
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(10.6, 25.52), (10.6, 24.5)]),
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(10.6, 26.48), (12.0, 26.48), (13.5, 30.2), (16.8, 30.2),
                                                   (16.8, 24.6), (17.09, 23.6)]),
    dict(net="+3V3", layer="B.Cu", width=0.3, pts=[(16.8, 24.6), (16.8, 20.5), (10.52, 20.5)]),
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(10.52, 20.5), (10.52, 18.6)]),
    dict(net="I2C_SDA", layer="F.Cu", width=0.2, pts=[(7.8, 25.6), (6.4, 25.6)]),
    dict(net="I2C_SCL", layer="F.Cu", width=0.2, pts=[(7.8, 26.4), (7.2, 26.4), (7.2, 29.4)]),
    dict(net="I2C_SDA", layer="B.Cu", width=0.2, pts=[(6.4, 25.6), (6.4, 28.2), (17.6, 28.2), (17.6, 19.5),
                                                      (15.75, 19.5), (15.75, 16.7)]),
    dict(net="I2C_SCL", layer="B.Cu", width=0.2, pts=[(7.2, 29.4), (18.6, 29.4), (18.6, 17.9), (16.6, 17.9)]),
    dict(net="I2C_SDA", layer="F.Cu", width=0.2, pts=[(15.75, 15.5), (15.75, 16.7)]),
    dict(net="I2C_SCL", layer="F.Cu", width=0.2, pts=[(16.6, 15.5), (16.6, 17.9)]),
    # Battery: J2 + -> Q1 drain, wide and on one layer (all charge/discharge current)
    dict(net="BAT_CELL", layer="F.Cu", width=0.6, pts=BAT_CELL_PTS),
    # ESP32 3V3 pin -> C8 -> C9 decoupling chain (joins the tongue feed at C9)
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(8.1, 15.5), (8.1, 17.2), (7.225, 18.1), (7.225, 18.6)]),
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(7.225, 18.6), (7.225, 19.9), (9.9, 19.9), (10.52, 20.5)]),
    # LDO GND pins straight to the plane (AP2112K and the heater LDO)
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(26.363, 10.5), (25.2, 10.5)]),
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(37.363, 8.0), (36.3, 8.0)]),
    # USB ESD diode GND pin likewise
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(29.8625, 19.2), (28.8, 19.2)]),
    # ESP32 corner GND pad 63 straight to a via
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(19.35, 15.5), (20.7, 15.5)]),
    # EN capacitor C10 GND pad: its pour island between D1, C11 and the test pads had no via
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(24.0, 9.52), (24.0, 8.6)]),
    # ADS1115 decoupling C12 GND pad likewise (hemmed in by U6 and the S1 pads)
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(47.0, 9.02), (47.0, 8.1)]),
    # Charger pin 8 (GND, bottom row) and the VSYS cap C2's GND pad: both were left on
    # pour islands the autorouter fenced off from the thermal vias.
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(41.25, 22.938), (41.25, 24.0)]),
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(38.775, 17.3), (39.7, 17.3)]),
]
PREROUTE_VIAS = [
    dict(net="GND", at=(20.7, 15.5)), dict(net="GND", at=(24.0, 8.6)), dict(net="GND", at=(47.0, 8.1)),
    dict(net="GND", at=(41.25, 24.0)), dict(net="GND", at=(39.7, 17.3)),
    # SHT40 tongue: GND, I2C escape vias, and pickup vias just past the neck
    dict(net="GND", at=(10.6, 24.5)), dict(net="GND", at=(6.2, 30.0)),
    dict(net="I2C_SDA", at=(6.4, 25.6)), dict(net="I2C_SCL", at=(7.2, 29.4)),
    dict(net="I2C_SDA", at=(15.75, 16.7)), dict(net="I2C_SCL", at=(16.6, 17.9)),
    dict(net="+3V3", at=(16.8, 24.6)), dict(net="+3V3", at=(10.52, 20.5)),
    dict(net="GND", at=(25.2, 10.5)), dict(net="GND", at=(36.3, 8.0)), dict(net="GND", at=(28.8, 19.2)),
    # ESP32 module centre GND pads (the fill can't reach inside the pad ring)
    *[dict(net="GND", at=(x, y), d=0.5, drill=0.2) for x in (11.525, 13.175) for y in (7.675, 9.325)],
    # BQ24073 exposed pad thermal vias
    dict(net="GND", at=(40.1, 21.1), d=0.5, drill=0.2), dict(net="GND", at=(40.9, 21.9), d=0.5, drill=0.2),
]
STITCH_PITCH = 2.54
