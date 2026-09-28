"""Rev B phone-companion board: the single source of truth for schematic and PCB.

Spec: docs/phone_board.md. Nets are named here; build_sch.py draws them and
build_pcb.py lays them out, so the two cannot drift apart. Coordinates are mm,
KiCad convention (x right, y down), board origin at the top-left corner.
"""

from parts import C, Part, R

PROJECT = "phone_board"
TITLE = "Methane detector - phone companion board"
REV = "C"
BLOCKS = ["usb_power", "regulators", "mcu", "sensors", "adc_env"]

# ---- LCSC part numbers (JLCPCB parts API, checked 2026-09-17) ---------------
R10K, R5K1, R100K, R4K7, R1K, R20K, R1K5, R1K8 = "C25744", "C25905", "C25741", "C25900", "C11702", "C25765", "C25867", "C25871"
R732K = "C27016"
R1M = "C26083"
C100N, C1U, C10U_0603, C22U_0805 = "C1525", "C52923", "C19702", "C45783"
F0603 = "Capacitor_SMD:C_0603_1608Metric"
F0805 = "Capacitor_SMD:C_0805_2012Metric"


def Cap10u(ref, a, b, block):
    return C(ref, "10uF", a, b, block, lcsc=C10U_0603, fp=F0603)


def Cap22u(ref, a, b, block):
    return C(ref, "22uF", a, b, block, lcsc=C22U_0805, fp=F0805)


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


def sensor_channel(n, s_ref, name, mpn, block):
    """Bare TGS26xx: heater 1-4 on +5V_HTR, electrodes 3(+) to VC=+5V_HTR and
    2(-) into a 20k+20k load. The ADC reads the midpoint tap = VRL/2 (<= 2.5 V)."""
    rl, tap = f"{name}_RL", f"{name}_TAP"
    s = Part(s_ref, "phone_board:TGS26xx", "Package_TO_SOT_THT:TO-5-4", mpn,
             {"1": "+5V_HTR", "4": "GND", "3": "+5V_HTR", "2": rl}, block, mpn=mpn,
             description=f"Figaro {mpn}, hand-soldered (not stocked at LCSC)")
    s.no_assembly = True
    return [
        s,
        R(f"R{n}", "20k", rl, tap, block, lcsc=R20K),
        R(f"R{n + 1}", "20k", tap, "GND", block, lcsc=R20K),
        C(f"C{n}", "100nF", tap, "GND", block, lcsc=C100N),
        # ESP32 fallback ADC link: not fitted by default (its 50 mm trace passes USB/I2C and would
        # couple noise into the tap). Hand-fit a 1k if the ADS1115 ever needs bypassing.
        R(f"R{n + 2}", "1k", tap, f"{name}_FB", block, lcsc=R1K, dnp=True),
    ]


PARTS = [
    # ---- USB-C, ESD, charger / power path, battery, power switch -------------
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
    # EN1 high (with EN2 low) selects USB500. Fed from VBUS (not VSYS) so it draws nothing from
    # the battery and is already high when USB arrives with no/flat battery. 100k vs the 285k
    # internal pull-down gives ~3.7 V at 5 V VBUS and stays < 7 V abs max up to the 6.6 V OVP.
    R("R26", "100k", "VBUS", "BQ_EN1", "usb_power", lcsc=R100K),
    Part("J2", "Connector_Generic:Conn_01x02", "Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",
         "LiPo 1S", {"1": "GND", "2": "BAT_CELL"}, "usb_power", lcsc="C295747",
         description="JST-PH battery: pin 1 = -, pin 2 = + (Adafruit/SparkFun convention) - CHECK YOUR CELL"),
    # Reverse-battery protection: P-FET with gate to GND. Correct cell -> body diode then channel
    # conduct (both directions, so charging works); reversed cell -> FET off, body diode blocks.
    Part("Q1", "Transistor_FET:AO3401A", "Package_TO_SOT_SMD:SOT-23", "AO3401A",
         {"G": "GND", "D": "BAT_CELL", "S": "VBAT"}, "usb_power", lcsc="C15127"),
    Part("SW1", "Switch:SW_SPDT", "Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02", "POWER",
         {"1": "VSYS", "2": "PWR_EN"}, "usb_power", lcsc="C431540",
         description="Logic-level power switch: drives the regulator enables, not the battery current. "
                     "Throw C is left open so a make-before-break transition can never short VSYS to GND"),
    R("R27", "1M", "PWR_EN", "GND", "usb_power", lcsc=R1M),  # holds regulators off when SW1 is open

    # ---- 3.3 V LDO and 5 V heater boost --------------------------------------
    Part("U3", "Regulator_Linear:AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5", "AP2112K-3.3",
         {"VIN": "VSYS", "EN": "PWR_EN", "GND": "GND", "VOUT": "+3V3"}, "regulators", lcsc="C51118"),
    Cap10u("C4", "+3V3", "GND", "regulators"),
    Part("U4", "phone_board:TPS61023", "Package_TO_SOT_SMD:SOT-563", "TPS61023DRLR",
         {"VIN": "VSYS", "EN": "HTR_EN", "GND": "GND", "SW": "BOOST_SW", "VOUT": "+5V_HTR", "FB": "BOOST_FB"},
         "regulators", lcsc="C919459"),
    Part("L1", "Device:L", "Inductor_SMD:L_Sunlord_SWPA4030S", "1uH", {"1": "VSYS", "2": "BOOST_SW"},
         "regulators", lcsc="C42193", mpn="SWPA4030S1R0NT"),
    Cap10u("C5", "VSYS", "GND", "regulators"),
    Cap22u("C6", "+5V_HTR", "GND", "regulators"),
    Cap22u("C7", "+5V_HTR", "GND", "regulators"),
    R("R8", "732k", "+5V_HTR", "BOOST_FB", "regulators", lcsc=R732K),
    R("R9", "100k", "BOOST_FB", "GND", "regulators", lcsc=R100K),
    # Heaters are OFF until the firmware drives HTR_EN (GPIO7) high: no inrush before boot,
    # and a firmware crash fails safe. The GPIO actively drives the line, so switching noise
    # from the nearby boost SW node can't toggle it.
    R("R10", "100k", "HTR_EN", "GND", "regulators", lcsc=R100K),
    C("C16", "1uF", "VSYS", "GND", "regulators", lcsc=C1U),  # LDO input cap, at U3 VIN

    # ---- ESP32-S3-MINI-1, reset/boot, LED, test points -----------------------
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
    TP("TP4", "+3V3", "mcu"), TP("TP5", "VBAT", "mcu"), TP("TP6", "+5V_HTR", "mcu"),
    Hole("H1"), Hole("H2"),

    # ---- Gas sensors ----------------------------------------------------------
    *sensor_channel(20, "S1", "CH4", "TGS2611-E00", "sensors"),
    *sensor_channel(23, "S2", "LPG", "TGS2610-D00", "sensors"),

    # ---- ADS1115 + monitors, SHT40 ------------------------------------------
    Part("U6", "Analog_ADC:ADS1115IDGS", "Package_SO:MSOP-10_3x3mm_P0.5mm", "ADS1115IDGSR",
         {"1": "GND", "2": "ADS_RDY", "3": "GND", "4": "CH4_TAP", "5": "LPG_TAP", "6": "VBAT_SENSE",
          "7": "HTR_SENSE", "8": "+3V3", "9": "I2C_SDA", "10": "I2C_SCL"}, "adc_env", lcsc="C37593"),
    Cap100n("C12", "+3V3", "GND", "adc_env"),
    # 1M/1M: ~2 uA drain and ~2 uA into the unpowered ADS1115 input when switched off. Reads a
    # few % low against the ADC input impedance -> calibrate in firmware.
    R("R13", "1M", "VBAT", "VBAT_SENSE", "adc_env", lcsc=R1M),
    R("R14", "1M", "VBAT_SENSE", "GND", "adc_env", lcsc=R1M),
    Cap100n("C13", "VBAT_SENSE", "GND", "adc_env"),
    R("R15", "100k", "+5V_HTR", "HTR_SENSE", "adc_env", lcsc=R100K),
    R("R16", "100k", "HTR_SENSE", "GND", "adc_env", lcsc=R100K),
    Cap100n("C14", "HTR_SENSE", "GND", "adc_env"),
    R("R17", "4.7k", "+3V3", "I2C_SDA", "adc_env", lcsc=R4K7),
    R("R18", "4.7k", "+3V3", "I2C_SCL", "adc_env", lcsc=R4K7),
    R("R19", "10k", "+3V3", "ADS_RDY", "adc_env", lcsc=R10K),
    # Temperature + humidity (humidity is the main MOX false-positive source; the
    # phone's barometer covers pressure, so no BME280). I2C 0x44.
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
    "Power": dict(track=0.5, clearance=0.15, nets=["VSYS", "VBAT", "+5V_HTR", "BAT_CELL"]),
    "Vbus": dict(track=0.4, clearance=0.15, nets=["VBUS"]),
    "Supply3V3": dict(track=0.3, nets=["+3V3"]),
    "BoostSW": dict(track=0.35, clearance=0.15, nets=["BOOST_SW"]),
}

OUTLINE = (0, 0, 60, 33)
CORNER_R = 2.0
# Notches milled in from the right edge (x0 = inner end, y0..y1 = width): one between
# the two sensor cans so each stands in air on three sides.
NOTCHES = [dict(x0=53.0, y0=11.9, y1=13.1)]


def _to5(cx, cy):
    """TO-5-4 origin is pin 1; rotate 45 deg and put the can centre at (cx, cy)."""
    return (round(cx - 1.796, 3), round(cy + 1.796, 3), 45, "F")


# (x, y, rotation, side). The board has a business end: the ESP32 (antenna over
# the left edge) and both power connectors are at the rear, the two Figaro cans
# stand at the front edge, overhanging it by ~1 mm with a notch between them.
#   Rear:   USB-C on the bottom edge and the JST-PH on the top edge, both right
#           beside the module, with the reverse-cell FET next to the JST so the
#           battery lead and its protection stay together.
#   Middle: LDO, boost loop (hand-routed, moved rigidly), charger, ADC, buttons.
#   Front:  cans, their load networks, heater-rail monitor.
#   SHT40:  on the slotted tongue at the rear-left, copper-free on all layers.
PLACEMENT = {
    "U5": (9.8, 8.5, 90, "F"),
    "C8": (8.0, 18.6, 0, "F"), "C9": (11.0, 18.6, 0, "F"),
    "R11": (22.0, 18.4, 0, "F"), "C10": (24.3, 18.4, 0, "F"),
    "TP1": (22.0, 13.4, 0, "F"), "TP2": (24.3, 13.4, 0, "F"),
    "TP3": (22.0, 15.9, 0, "F"), "TP4": (24.3, 15.9, 0, "F"),
    "U7": (6.0, 29.0, 0, "F"), "C15": (8.2, 29.0, 90, "F"), "R12": (17.0, 23.0, 90, "F"),
    # rear power connectors and the battery FET
    "J1": (24.0, 29.3, 0, "F"), "U1": (23.3, 21.2, 0, "F"),
    "R1": (20.3, 22.5, 90, "F"), "R2": (30.0, 25.5, 90, "F"),
    "J2": (25.3, 4.9, 180, "F"),  # cable leaves through the top edge
    "Q1": (31.7, 10.6, 270, "F"), "TP5": (34.1, 6.4, 0, "F"),
    "D1": (31.8, 2.3, 0, "F"), "C11": (30.6, 5.2, 90, "F"), "R27": (32.1, 5.0, 0, "F"),
    "SW1": (38.0, 1.8, 180, "F"),  # lever overhangs the top edge; pins face inboard
    "U3": (27.5, 14.0, 0, "F"), "C4": (27.5, 17.4, 0, "F"), "C16": (30.7, 14.4, 0, "F"),
    "R10": (34.6, 12.5, 0, "F"), "H2": (28.0, 20.6, 0, "F"),
    "SW2": (34.4, 21.9, 0, "F"), "SW3": (34.4, 29.0, 0, "F"),
    # boost loop: rev C block moved 1 mm right
    "U4": (43.5, 8.0, 180, "F"), "L1": (39.8, 8.0, 0, "F"), "C5": (36.0, 8.0, 90, "F"),
    "C6": (44.0, 11.0, 0, "F"), "C7": (39.8, 11.5, 180, "F"),
    "R8": (46.5, 7.1, 0, "F"), "R9": (46.5, 8.5, 0, "F"),
    # charger
    "U2": (45.5, 23.5, 0, "F"), "C1": (41.2, 22.0, 0, "F"), "C2": (43.6, 19.6, 0, "F"),
    "C3": (41.2, 24.2, 0, "F"),  # VBAT cap on the VBAT-pin side (left) of U2
    "R3": (43.6, 26.6, 0, "F"), "R4": (43.6, 28.2, 0, "F"), "R5": (43.6, 29.8, 0, "F"),
    "R6": (40.8, 19.0, 0, "F"), "R7": (40.8, 17.6, 0, "F"), "R26": (43.6, 31.4, 0, "F"),
    # ADC, monitors, pull-ups
    "U6": (45.5, 15.5, 90, "F"), "C12": (48.0, 15.5, 90, "F"),
    "R13": (39.0, 15.0, 90, "F"), "R14": (37.6, 15.0, 90, "F"), "C13": (36.2, 15.0, 90, "F"),
    "R15": (43.6, 4.2, 0, "F"), "R16": (45.7, 4.2, 0, "F"), "C14": (47.8, 4.2, 0, "F"),
    "R17": (46.2, 19.9, 0, "F"), "R19": (48.3, 19.9, 0, "F"), "R18": (40.4, 20.2, 0, "F"),
    "TP6": (48.6, 9.0, 0, "F"),
    # sensors at the front edge, load networks just inboard of them
    "S1": _to5(56.5, 6.5), "R20": (49.6, 11.5, 0, "F"), "R21": (49.6, 13.0, 0, "F"),
    "C20": (49.6, 14.5, 0, "F"), "R22": (49.4, 4.4, 90, "F"),
    "S2": _to5(56.5, 18.5), "R23": (53.5, 25.0, 0, "F"), "R24": (55.6, 25.0, 0, "F"),
    "C23": (57.7, 25.0, 0, "F"), "R25": (52.0, 26.6, 0, "F"),
    "H1": (56.5, 30.0, 0, "F"),
}

ZONES = [
    dict(net="GND", layers=["In1.Cu"], name="GND plane"),
    # keep routing 0.35 mm off the SHT40 tongue slot and the sensor notch (Freerouting ignores cutouts)
    dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("tracks", "vias"), name="slot keepout h",
         pts=[(0.65, 23.65), (13.35, 23.65), (13.35, 25.35), (0.65, 25.35)]),
    dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("tracks", "vias"), name="slot keepout v",
         pts=[(11.65, 23.65), (13.35, 23.65), (13.35, 30.85), (11.65, 30.85)]),
    dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("tracks", "vias"), name="notch keepout",
         pts=[(52.65, 11.55), (60.0, 11.55), (60.0, 13.45), (52.65, 13.45)]),
    # The whole tongue and its neck carry no copper pour on any layer: copper is
    # what conducts board heat into the SHT40. Only its four tracks cross the neck.
    dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("fills",), name="SHT40 tongue no-copper",
         pts=[(0.0, 23.65), (13.35, 23.65), (13.35, 33.0), (0.0, 33.0)]),
]
PLANE_LAYERS = ["In1.Cu"]
POST_ROUTE_ZONES = [dict(net="GND", layers=["F.Cu", "In2.Cu", "B.Cu"], name="GND fill")]
# 1 mm L-shaped slot: the tongue (x 0-12, y 25-33) hangs off a 2.5 mm neck at its bottom-right.
SLOTS = [[(1.0, 24.0), (13.0, 24.0), (13.0, 30.5), (12.0, 30.5), (12.0, 25.0), (1.0, 25.0)]]
SILK_HIDE_REFS = {"SW2", "SW3"}
SILK_TEXT = [
    dict(text="CH4", at=(56.5, 6.5), size=1.0, side="B"), dict(text="LPG", at=(56.5, 18.5), size=1.0, side="B"),
    dict(text="+", at=(23.2, 8.9), size=1.0), dict(text="-", at=(27.4, 8.9), size=1.0),
    dict(text="ON", at=(41.8, 5.1), size=0.8),
    dict(text="RST", at=(34.4, 25.45), size=0.8), dict(text="BOOT", at=(34.4, 32.35), size=0.8),
    dict(text="TX", at=(22.0, 12.0), size=0.6), dict(text="RX", at=(24.3, 12.0), size=0.6),
    dict(text="GND", at=(22.0, 17.2), size=0.6), dict(text="3V3", at=(24.3, 17.2), size=0.6),
    dict(text="CH4 detector rev C", at=(33.0, 14.5), size=1.0, side="B"),
]

# Battery pin 2 (+) of the top-edge J2 down past its pads to the FET drain (Q1 pad 3).
BAT_CELL_PTS = [(24.3, 7.75), (24.3, 10.6), (28.4, 10.6), (29.34, 11.54), (31.7, 11.54)]

# Hand-routed tracks (locked; Freerouting routes around them).
PREROUTE = [
    # Boost power loop (U4 rotated 180: SW / VOUT / GND pads face the inductor on the left)
    dict(net="BOOST_SW", layer="F.Cu", width=0.8, pts=[(41.3, 8.0), (41.9, 8.0)]),
    dict(net="BOOST_SW", layer="F.Cu", width=0.35, pts=[(41.9, 8.0), (42.788, 8.0)]),
    dict(net="+5V_HTR", layer="F.Cu", width=0.35, pts=[(42.788, 8.5), (42.788, 9.2)]),
    dict(net="+5V_HTR", layer="F.Cu", width=0.6, pts=[(42.788, 9.2), (43.05, 9.8), (43.05, 11.0)]),
    dict(net="GND", layer="F.Cu", width=0.35, pts=[(42.788, 7.5), (42.788, 6.5)]),
    dict(net="VSYS", layer="F.Cu", width=0.8, pts=[(36.0, 8.775), (38.3, 8.775)]),
    dict(net="VSYS", layer="F.Cu", width=0.3, pts=[(44.212, 7.5), (44.9, 7.5), (44.9, 6.1)]),
    dict(net="BOOST_FB", layer="F.Cu", width=0.2, pts=[(44.212, 8.5), (45.99, 8.5)]),
    dict(net="GND", layer="F.Cu", width=0.4, pts=[(44.95, 11.0), (46.0, 11.0)]),
    dict(net="GND", layer="F.Cu", width=0.4, pts=[(36.0, 7.225), (35.0, 7.225)]),
    dict(net="GND", layer="F.Cu", width=0.4, pts=[(38.85, 11.5), (38.85, 12.6)]),
    # Boost feedback top (R8) sensed at output cap C6, on B.Cu
    dict(net="+5V_HTR", layer="F.Cu", width=0.25, pts=[(45.99, 7.1), (45.99, 5.0)]),
    dict(net="+5V_HTR", layer="F.Cu", width=0.4, pts=[(43.05, 11.0), (43.05, 12.3)]),
    dict(net="+5V_HTR", layer="B.Cu", width=0.25, pts=[(43.05, 12.3), (43.05, 10.0), (45.99, 7.06), (45.99, 5.0)]),
    # VSYS: inductor input -> via -> B.Cu -> via at the boost VIN stub
    dict(net="VSYS", layer="F.Cu", width=0.4, pts=[(37.3, 6.1), (38.3, 6.6)]),
    dict(net="VSYS", layer="B.Cu", width=0.4, pts=[(37.3, 6.1), (37.9, 5.3), (44.3, 5.3), (44.9, 6.1)]),
    dict(net="+5V_HTR", layer="F.Cu", width=0.6, pts=[(43.05, 11.0), (41.5, 11.5), (40.75, 11.5)]),
    # Boost EN pad is boxed in by the VIN and FB tracks: escape under the SOT-563 body to a
    # via between the pad rows (the route rev B/C's autorouter found; locked so it is kept)
    dict(net="HTR_EN", layer="F.Cu", width=0.2, pts=[(44.212, 8.0), (43.845, 8.0), (43.523, 7.678), (43.523, 7.083)]),
    # SDA trunk from the module to the ADS1115 on In2 (the middle is too dense for the
    # autorouter to find this 30 mm path by itself)
    dict(net="I2C_SDA", layer="F.Cu", width=0.2, pts=[(45.0, 13.3875), (45.0, 12.2), (47.2, 12.2)]),
    dict(net="I2C_SDA", layer="In2.Cu", width=0.2, pts=[(47.2, 12.2), (47.2, 16.7), (15.75, 16.7)]),
    # SHT40 tongue: decoupling, then GND and +3V3 through the neck on F.Cu, I2C on B.Cu.
    # No pour reaches the tongue, so GND is a track like the others.
    dict(net="+3V3", layer="F.Cu", width=0.25, pts=[(6.7, 29.4), (7.7, 29.4), (8.2, 29.48)]),
    dict(net="GND", layer="F.Cu", width=0.25, pts=[(6.7, 28.6), (7.7, 28.6), (8.2, 28.52)]),
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(8.2, 29.48), (9.4, 29.48), (10.3, 32.1), (16.8, 32.1),
                                                   (16.8, 25.0), (17.0, 23.51)]),
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(8.2, 28.52), (11.0, 28.52), (11.0, 31.3), (13.6, 31.3),
                                                  (14.2, 30.7), (14.2, 29.8)]),
    dict(net="+3V3", layer="B.Cu", width=0.3, pts=[(16.8, 25.0), (16.8, 20.5), (10.52, 20.5)]),
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(10.52, 20.5), (10.52, 18.6)]),
    # leave the SHT40 pads straight outward (its footprint keepout only opens at the pads)
    dict(net="I2C_SDA", layer="F.Cu", width=0.2, pts=[(5.3, 28.6), (4.9, 28.6), (4.9, 27.4)]),
    dict(net="I2C_SCL", layer="F.Cu", width=0.2, pts=[(5.3, 29.4), (4.9, 29.4), (4.9, 31.6)]),
    dict(net="I2C_SDA", layer="B.Cu", width=0.2, pts=[(4.9, 27.4), (4.9, 30.4), (5.8, 31.3), (17.6, 31.3),
                                                      (17.6, 19.5), (15.75, 19.5), (15.75, 16.7)]),
    dict(net="I2C_SCL", layer="B.Cu", width=0.2, pts=[(4.9, 31.6), (5.4, 32.1), (18.6, 32.1), (18.6, 17.9),
                                                      (16.6, 17.9)]),
    dict(net="I2C_SDA", layer="F.Cu", width=0.2, pts=[(15.75, 15.5), (15.75, 16.7)]),
    dict(net="I2C_SCL", layer="F.Cu", width=0.2, pts=[(16.6, 15.5), (16.6, 17.9)]),
    # Battery: J2 + -> Q1 drain, wide and on one layer (all charge/discharge current)
    dict(net="BAT_CELL", layer="F.Cu", width=0.6, pts=BAT_CELL_PTS),
    # ESP32 3V3 pin -> C8 -> C9 decoupling chain (joins the tongue feed at C9)
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(8.1, 15.5), (8.1, 17.2), (7.225, 18.1), (7.225, 18.6)]),
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(7.225, 18.6), (7.225, 19.9), (9.9, 19.9), (10.52, 20.5)]),
    # AP2112K and USB ESD diode GND pins straight to the plane
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(26.363, 14.0), (25.5, 14.0)]),
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(22.1625, 21.2), (21.3, 21.2)]),
    # ESP32 corner GND pad 63 straight to a via
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(19.35, 15.5), (20.7, 15.5)]),
    # GND pads the pours tend to fence off: charger pin 8, VSYS cap C2, EN cap C10
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(46.25, 24.938), (46.25, 26.0)]),
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(44.375, 19.6), (44.375, 20.6)]),
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(24.81, 18.4), (25.6, 18.4)]),
]
PREROUTE_VIAS = [
    dict(net="GND", at=(46.25, 26.0)), dict(net="GND", at=(44.375, 20.6)), dict(net="GND", at=(25.6, 18.4)),
    dict(net="GND", at=(42.788, 6.5)), dict(net="VSYS", at=(44.9, 6.1)), dict(net="GND", at=(46.0, 11.0)),
    dict(net="GND", at=(35.0, 7.225)), dict(net="GND", at=(38.85, 12.6)), dict(net="GND", at=(20.7, 15.5)),
    dict(net="+5V_HTR", at=(45.99, 5.0)), dict(net="+5V_HTR", at=(43.05, 12.3)), dict(net="VSYS", at=(37.3, 6.1)),
    dict(net="HTR_EN", at=(43.523, 7.083)), dict(net="I2C_SDA", at=(47.2, 12.2)),
    # SHT40 tongue: I2C escape vias on the tongue, GND and +3V3 pickup vias just past the neck
    dict(net="I2C_SDA", at=(4.9, 27.4)), dict(net="I2C_SCL", at=(4.9, 31.6)),
    dict(net="GND", at=(14.2, 29.8)), dict(net="+3V3", at=(16.8, 25.0)), dict(net="+3V3", at=(10.52, 20.5)),
    dict(net="I2C_SDA", at=(15.75, 16.7)), dict(net="I2C_SCL", at=(16.6, 17.9)),
    dict(net="GND", at=(25.5, 14.0)), dict(net="GND", at=(21.3, 21.2)),
    # ESP32 module centre GND pads (the fill can't reach inside the pad ring)
    *[dict(net="GND", at=(x, y), d=0.5, drill=0.2) for x in (11.525, 13.175) for y in (7.675, 9.325)],
    # BQ24073 exposed pad thermal vias
    dict(net="GND", at=(45.1, 23.1), d=0.5, drill=0.2), dict(net="GND", at=(45.9, 23.9), d=0.5, drill=0.2),
]
# GND stitching vias: grid pitch (mm), kept clear of copper, courtyards and keepouts.
STITCH_PITCH = 2.54
