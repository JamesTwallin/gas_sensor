"""Rev B phone-companion board: the single source of truth for schematic and PCB.

Spec: docs/phone_board.md. Nets are named here; build_sch.py draws them and
build_pcb.py lays them out, so the two cannot drift apart. Coordinates are mm,
KiCad convention (x right, y down), board origin at the top-left corner.
"""

from parts import C, Part, R

PROJECT = "phone_board"
TITLE = "Methane detector - phone companion board"
REV = "B"
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

OUTLINE = (0, 0, 66, 36)
CORNER_R = 2.0


def _to5(cx, cy):
    """TO-5-4 origin is pin 1; rotate 45 deg and put the can centre at (cx, cy)."""
    return (round(cx - 1.796, 3), round(cy + 1.796, 3), 45, "F")


# (x, y, rotation, side). ESP32 antenna faces the left edge (its footprint
# carries the antenna keepout). Heaters at the right end, SHT40 on the
# slotted tongue at the bottom-left, as far from them as the board allows.
PLACEMENT = {
    "U5": (9.8, 10.5, 90, "F"),
    "C8": (8.0, 20.6, 0, "F"), "C9": (11.0, 20.6, 0, "F"),
    "R11": (22.5, 6.0, 90, "F"), "C10": (24.0, 6.0, 90, "F"),
    "D1": (25.0, 2.6, 0, "F"), "C11": (22.0, 2.6, 0, "F"),
    "TP1": (20.5, 23.0, 0, "F"), "TP2": (22.8, 23.0, 0, "F"),
    "TP3": (25.1, 23.0, 0, "F"), "TP4": (22.8, 25.6, 0, "F"),
    "SW2": (29.6, 18.6, 0, "F"), "SW3": (22.6, 31.4, 0, "F"), "R12": (18.0, 27.4, 90, "F"),
    "U7": (8.5, 30.0, 0, "F"), "C15": (10.6, 30.0, 90, "F"),
    "SW1": (33.0, 1.8, 180, "F"),  # lever overhangs the top edge; pins face inboard
    "U3": (29.5, 10.5, 0, "F"), "C4": (29.5, 14.0, 0, "F"), "C16": (28.4, 7.6, 0, "F"),
    "J1": (33.0, 32.3, 0, "F"), "U1": (33.0, 24.2, 0, "F"),
    "R1": (29.5, 25.5, 90, "F"), "R2": (37.6, 24.6, 90, "F"),
    "U2": (42.5, 23.5, 0, "F"), "C1": (38.2, 22.0, 0, "F"), "C2": (40.0, 19.3, 0, "F"),
    "C3": (46.5, 23.5, 90, "F"),
    "R3": (40.6, 29.0, 0, "F"), "R4": (40.6, 30.6, 0, "F"), "R5": (40.6, 32.2, 0, "F"),
    "R6": (36.0, 19.0, 0, "F"), "R7": (36.0, 17.6, 0, "F"), "R26": (43.5, 27.2, 0, "F"), "Q1": (43.6, 30.3, 90, "F"), "R27": (31.5, 6.2, 0, "F"),
    "J2": (50.0, 30.0, 0, "F"), "TP5": (43.5, 34.0, 0, "F"),
    "U4": (44.5, 8.0, 180, "F"), "L1": (40.8, 8.0, 0, "F"), "C5": (37.0, 8.0, 90, "F"),
    "C6": (45.0, 11.0, 0, "F"), "C7": (40.8, 11.5, 180, "F"),
    "R8": (47.5, 7.1, 0, "F"), "R9": (47.5, 8.5, 0, "F"), "R10": (34.5, 11.0, 90, "F"),
    "TP6": (51.0, 2.2, 0, "F"),
    "U6": (47.5, 15.5, 90, "F"), "C12": (44.5, 15.5, 90, "F"),
    "R13": (41.0, 15.0, 90, "F"), "R14": (39.6, 15.0, 90, "F"), "C13": (38.2, 15.0, 90, "F"),
    "R15": (51.8, 11.0, 90, "F"), "R16": (53.2, 11.0, 90, "F"), "C14": (54.6, 11.0, 90, "F"),
    "R17": (44.0, 18.6, 0, "F"), "R18": (47.5, 19.8, 0, "F"), "R19": (45.0, 20.4, 0, "F"),
    "S1": _to5(60.5, 9.0), "R20": (51.5, 6.5, 90, "F"), "R21": (53.0, 6.5, 90, "F"),
    "C20": (54.5, 6.5, 90, "F"), "R22": (51.5, 15.0, 0, "F"),
    "S2": _to5(60.5, 22.0), "R23": (50.5, 23.0, 90, "F"), "R24": (52.0, 23.0, 90, "F"),
    "C23": (53.5, 23.0, 90, "F"), "R25": (52.0, 20.2, 0, "F"),
    "H1": (62.0, 32.5, 0, "F"), "H2": (24.2, 12.9, 0, "F"),
}

ZONES = [
    dict(net="GND", layers=["In1.Cu"], name="GND plane"),
    # keep routing 0.35 mm off the SHT40 tongue slot (Freerouting ignores inner cutouts)
    dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("tracks", "vias"), name="slot keepout h",
         pts=[(0.65, 23.65), (16.35, 23.65), (16.35, 25.35), (0.65, 25.35)]),
    dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("tracks", "vias"), name="slot keepout v",
         pts=[(14.65, 23.65), (16.35, 23.65), (16.35, 31.35), (14.65, 31.35)]),
]
ZONES.append(dict(layers=["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], rule_area=("fills",), name="SHT40 no-copper",
                  pts=[(7.2, 28.7), (9.8, 28.7), (9.8, 31.3), (7.2, 31.3)]))  # Sensirion: no copper under the sensor
# Layers Freerouting may not route signals on (kept as solid planes).
PLANE_LAYERS = ["In1.Cu"]
# Poured after routing so Freerouting can use F/In2/B for signals.
POST_ROUTE_ZONES = [dict(net="GND", layers=["F.Cu", "In2.Cu", "B.Cu"], name="GND fill")]
# 1 mm L-shaped slot that cuts the SHT40 tongue free on two sides (closed polygon).
SLOTS = [[(1.0, 24.0), (16.0, 24.0), (16.0, 31.0), (15.0, 31.0), (15.0, 25.0), (1.0, 25.0)]]
# Switch labels replace their reference designators on the silkscreen.
SILK_HIDE_REFS = {"SW2", "SW3"}
SILK_TEXT = [
    dict(text="CH4", at=(60.5, 15.2), size=1.0), dict(text="LPG", at=(56.0, 28.2), size=1.0),
    dict(text="-", at=(48.0, 24.6), size=1.0), dict(text="+", at=(53.0, 24.6), size=1.0), dict(text="ON", at=(38.8, 2.4), size=0.8),
    dict(text="RST", at=(24.3, 18.6), size=0.8), dict(text="BOOT", at=(18.0, 34.5), size=0.8),
    dict(text="CH4 detector rev B", at=(33.0, 33.0), size=1.0, side="B"),
]

# Hand-routed boost power loop (locked; Freerouting routes around it).
# U4 is rotated 180 deg: SW / VOUT / GND pads face the inductor on the left.
PREROUTE = [
    dict(net="BOOST_SW", layer="F.Cu", width=0.8, pts=[(42.3, 8.0), (42.9, 8.0)]),
    dict(net="BOOST_SW", layer="F.Cu", width=0.35, pts=[(42.9, 8.0), (43.788, 8.0)]),
    dict(net="+5V_HTR", layer="F.Cu", width=0.35, pts=[(43.788, 8.5), (43.788, 9.2)]),
    dict(net="+5V_HTR", layer="F.Cu", width=0.6, pts=[(43.788, 9.2), (44.05, 9.8), (44.05, 11.0)]),
    dict(net="GND", layer="F.Cu", width=0.35, pts=[(43.788, 7.5), (43.788, 6.5)]),
    dict(net="VSYS", layer="F.Cu", width=0.8, pts=[(37.0, 8.775), (39.3, 8.775)]),
    dict(net="VSYS", layer="F.Cu", width=0.3, pts=[(45.212, 7.5), (45.9, 7.5), (45.9, 6.1)]),
    dict(net="BOOST_FB", layer="F.Cu", width=0.2, pts=[(45.212, 8.5), (46.99, 8.5)]),
    dict(net="GND", layer="F.Cu", width=0.4, pts=[(45.95, 11.0), (47.0, 11.0)]),
    dict(net="GND", layer="F.Cu", width=0.4, pts=[(37.0, 7.225), (36.0, 7.225)]),
    dict(net="GND", layer="F.Cu", width=0.4, pts=[(39.85, 11.5), (39.85, 12.6)]),
    # Boost feedback top (R8) sensed at output cap C6, on B.Cu
    dict(net="+5V_HTR", layer="F.Cu", width=0.25, pts=[(46.99, 7.1), (46.99, 5.0)]),
    dict(net="+5V_HTR", layer="F.Cu", width=0.4, pts=[(44.05, 11.0), (44.05, 12.3)]),
    dict(net="+5V_HTR", layer="B.Cu", width=0.25, pts=[(44.05, 12.3), (44.05, 10.0), (46.99, 7.06), (46.99, 5.0)]),
    # SHT40 on the slotted tongue: decoupling, I2C out through the neck on B.Cu,
    # +3V3 in through the neck on F.Cu (the autorouter can't thread the neck).
    dict(net="+3V3", layer="F.Cu", width=0.25, pts=[(9.2, 30.4), (10.1, 30.4), (10.6, 30.48)]),
    dict(net="GND", layer="F.Cu", width=0.25, pts=[(9.2, 29.6), (10.1, 29.6), (10.6, 29.52)]),
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(10.6, 29.52), (10.6, 28.5)]),
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(10.6, 30.48), (12.0, 30.48), (13.5, 34.4), (16.8, 34.4),
                                                   (16.8, 28.6), (18.0, 27.91)]),
    dict(net="+3V3", layer="B.Cu", width=0.3, pts=[(16.8, 28.6), (16.8, 22.5), (10.52, 22.5)]),
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(10.52, 22.5), (10.52, 20.6)]),
    dict(net="I2C_SDA", layer="F.Cu", width=0.2, pts=[(7.8, 29.6), (6.4, 29.6)]),
    dict(net="I2C_SCL", layer="F.Cu", width=0.2, pts=[(7.8, 30.4), (7.2, 30.4), (7.2, 33.6)]),
    dict(net="I2C_SDA", layer="B.Cu", width=0.2, pts=[(6.4, 29.6), (6.4, 32.2), (17.6, 32.2), (17.6, 21.5),
                                                      (15.75, 21.5), (15.75, 18.7)]),
    dict(net="I2C_SCL", layer="B.Cu", width=0.2, pts=[(7.2, 33.6), (18.6, 33.6), (18.6, 19.9), (16.6, 19.9)]),
    dict(net="I2C_SDA", layer="F.Cu", width=0.2, pts=[(15.75, 17.5), (15.75, 18.7)]),
    dict(net="I2C_SCL", layer="F.Cu", width=0.2, pts=[(16.6, 17.5), (16.6, 19.9)]),
    # VSYS: inductor input -> via -> B.Cu -> via at the boost VIN stub
    dict(net="VSYS", layer="F.Cu", width=0.4, pts=[(38.3, 6.1), (39.3, 6.6)]),
    dict(net="VSYS", layer="B.Cu", width=0.4, pts=[(38.3, 6.1), (38.9, 5.3), (45.3, 5.3), (45.9, 6.1)]),
    # Battery: J2 + -> Q1 drain, wide and on one layer (all charge/discharge current)
    dict(net="BAT_CELL", layer="F.Cu", width=0.6, pts=[(51.0, 27.15), (51.0, 29.5), (43.6, 29.5), (43.6, 29.363)]),
    # ESP32 3V3 pin -> C8 -> C9 decoupling chain (joins the tongue feed at C9)
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(8.1, 17.5), (8.1, 19.2), (7.225, 20.1), (7.225, 20.6)]),
    dict(net="+3V3", layer="F.Cu", width=0.3, pts=[(7.225, 20.6), (7.225, 21.9), (9.9, 21.9), (10.52, 22.5)]),
    # AP2112K GND pin straight to the plane
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(28.3625, 10.5), (27.2, 10.5)]),
    # ESP32 corner GND pad 63 straight to a via
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(19.35, 17.5), (20.7, 17.5)]),
    dict(net="+5V_HTR", layer="F.Cu", width=0.6, pts=[(44.05, 11.0), (42.5, 11.5), (41.75, 11.5)]),
]
PREROUTE_VIAS = [
    dict(net="GND", at=(43.788, 6.5)), dict(net="VSYS", at=(45.9, 6.1)), dict(net="GND", at=(47.0, 11.0)),
    dict(net="GND", at=(36.0, 7.225)), dict(net="GND", at=(39.85, 12.6)), dict(net="GND", at=(20.7, 17.5)), dict(net="+5V_HTR", at=(46.99, 5.0)), dict(net="+5V_HTR", at=(44.05, 12.3)),
    # SHT40 tongue: GND, I2C escape vias, and pickup vias just past the neck
    dict(net="GND", at=(10.6, 28.5)), dict(net="GND", at=(6.2, 34.2)),
    dict(net="I2C_SDA", at=(6.4, 29.6)), dict(net="I2C_SCL", at=(7.2, 33.6)),
    dict(net="I2C_SDA", at=(15.75, 18.7)), dict(net="I2C_SCL", at=(16.6, 19.9)),
    dict(net="+3V3", at=(16.8, 28.6)), dict(net="+3V3", at=(10.52, 22.5)),
    dict(net="GND", at=(27.2, 10.5)),
    dict(net="GND", at=(23.6, 4.0)),  # F.Cu pour between C11 and D1 has no other via
    # VSYS feed for the boost VIN pin, dropped next to the inductor input
    dict(net="VSYS", at=(38.3, 6.1)),
    # ESP32 module centre GND pads (the fill can't reach inside the pad ring)
    *[dict(net="GND", at=(x, y), d=0.5, drill=0.2) for x in (11.525, 13.175) for y in (9.675, 11.325)],
    # BQ24073 exposed pad thermal vias
    dict(net="GND", at=(42.1, 23.1), d=0.5, drill=0.2), dict(net="GND", at=(42.9, 23.9), d=0.5, drill=0.2),
]
# GND stitching vias: grid pitch (mm), kept clear of copper, courtyards and keepouts.
STITCH_PITCH = 2.54
