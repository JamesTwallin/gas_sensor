"""Rev E phone-companion board: the single source of truth for schematic and PCB.

Rev E is rev C's circuit on rev B's 66 x 36 mm outline (so it fits the printed
enclosure, hardware/enclosure/case.scad), plus what the gas anomaly
detector needs (docs/REPORT.md, docs/HARDWARE.md):
  - airflow thermistor pads (heated bead + unheated reference) at the gas inlet,
    read by the ADS1115 on AIN2/AIN3 instead of VBAT and the heater rail, which
    move to ESP32 ADC pins GPIO1/GPIO2 (the old fallback-ADC links are gone);
  - a 0.5 ohm shunt in each sensor heater's return and a second ADS1115 (0x49)
    to read heater current, plus the 3V3 rail for the thermistor dividers;
  - wire pads for a CO module (UART) and a sampling fan, on the 5 V heater rail;
  - more VSYS bulk capacitance for USB-only start-up.

Spec: docs/phone_board.md (rev B/C) and hardware/board/README.md (what
rev E changes). Nets are named here; build_sch.py draws them and build_pcb.py
lays them out, so the two cannot drift apart. Coordinates are mm, KiCad
convention (x right, y down), board origin at the top-left corner.
"""

from parts import C, Part, R

PROJECT = "board"
TITLE = "Methane detector - phone companion board"
REV = "E"
BLOCKS = ["usb_power", "regulators", "mcu", "sensors", "adc_env"]

# ---- LCSC part numbers (JLCPCB parts API, checked 2026-09-17) ---------------
R10K, R5K1, R100K, R4K7, R1K, R20K, R1K5, R1K8 = "C25744", "C25905", "C25741", "C25900", "C11702", "C25765", "C25867", "C25871"
R732K = "C27016"
R3K9, R220K, R0R5_0603 = "C51721", "C25767", "C2934253"  # jlcsearch, checked 2026-10-10
F0603R = "Resistor_SMD:R_0603_1608Metric"
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


def Pads(ref, fp, value, nets, block, description):
    """Plated wire pads (hand-soldered wires, nothing to assemble or buy)."""
    n = len(nets)
    p = Part(ref, f"Connector_Generic:Conn_01x{n:02d}", fp, value, nets, block, description=description)
    p.no_assembly = p.not_in_bom = True
    p.no_3d = True  # the footprint is a pin header's; drop its 3D model so renders show bare pads
    return p


def Hole(ref):
    p = Part(ref, "Mechanical:MountingHole", "MountingHole:MountingHole_2.2mm_M2", "M2", {}, "mcu")
    p.no_assembly = p.not_in_bom = True
    return p


def sensor_channel(n, s_ref, name, mpn, block, shunt_ref):
    """Bare TGS26xx: heater 1-4 on +5V_HTR, electrodes 3(+) to VC=+5V_HTR and
    2(-) into a 20k+20k load. The ADC reads the midpoint tap = VRL/2 (<= 2.5 V).
    Rev E: the heater returns to GND through a 0.5 ohm shunt (about 40 mV at the
    heater's ~85 mA), read by the second ADS1115. Moving air cools the heater; if
    its resistance follows its temperature, the current shows the cooling the gas
    sensor itself feels. Fit a 0 ohm link instead to disable."""
    rl, tap, ret = f"{name}_RL", f"{name}_TAP", f"{name}_HTR_I"
    s = Part(s_ref, "phone_board:TGS26xx", "Package_TO_SOT_THT:TO-5-4", mpn,
             {"1": "+5V_HTR", "4": ret, "3": "+5V_HTR", "2": rl}, block, mpn=mpn,
             description=f"Figaro {mpn}, hand-soldered (not stocked at LCSC)")
    s.no_assembly = True
    return [
        s,
        R(f"R{n}", "20k", rl, tap, block, lcsc=R20K),
        R(f"R{n + 1}", "20k", tap, "GND", block, lcsc=R20K),
        C(f"C{n}", "100nF", tap, "GND", block, lcsc=C100N),
        R(shunt_ref, "0.5", ret, "GND", block, lcsc=R0R5_0603, fp=F0603R),
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
         {"GND": "GND", "3": "+3V3", "45": "ESP_EN", "4": "BOOT", "5": "VBAT_SENSE", "6": "HTR_SENSE",
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
    TP("TP4", "+3V3", "mcu"), TP("TP5", "VBAT", "mcu"),
    Hole("H1"), Hole("H2"),

    # ---- Gas sensors ----------------------------------------------------------
    *sensor_channel(20, "S1", "CH4", "TGS2611-E00", "sensors", "R22"),
    *sensor_channel(23, "S2", "LPG", "TGS2610-D00", "sensors", "R25"),

    # ---- ADS1115 + monitors, SHT40 ------------------------------------------
    Part("U6", "Analog_ADC:ADS1115IDGS", "Package_SO:MSOP-10_3x3mm_P0.5mm", "ADS1115IDGSR",
         {"1": "GND", "2": "ADS_RDY", "3": "GND", "4": "CH4_TAP", "5": "LPG_TAP", "6": "TH_HOT",
          "8": "+3V3", "9": "I2C_SDA", "10": "I2C_SCL"}, "adc_env", lcsc="C37593"),
    Cap100n("C12", "+3V3", "GND", "adc_env"),
    # 1M/1M: ~2 uA drain. Rev E reads it on ESP32 GPIO1 (was ADS1115 AIN2); C13 is the
    # charge reservoir for the ADC's sampling capacitor. Calibrate in firmware.
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

    # ---- Rev E: air blade (hardware/air_blade, docs/HARDWARE.md) ------------------
    # J3 is the socket for the air blade: a small plug-in board that stands in a notch
    # in the sensor-end edge, between the cans, and pokes out through the case face. It
    # carries the heated airflow thermistor (1k NTC, fed through R28 = 1k: 2.7 mW,
    # about 1 K above the air) and an outside-air SHT40 at I2C 0x45 (the on-board U7 is
    # 0x44 and reads the case air). Five pads soldered to the blade's foot.
    Pads("J3", "phone_board:BladeSocket_1x05_P1.0mm",
         "AIR BLADE", {"1": "TH_HOT", "2": "GND", "3": "+3V3", "4": "I2C_SCL", "5": "I2C_SDA"}, "adc_env",
         description="Air blade socket: 1 heated thermistor, 2 GND, 3 3V3, 4 SCL, 5 SDA"),
    R("R28", "1k", "+3V3", "TH_HOT", "adc_env", lcsc=R1K),
    Cap100n("C24", "TH_HOT", "GND", "adc_env"),

    # ---- Rev E: second ADS1115 (0x49): heater currents and the 3V3 rail --------
    # ADDR to VDD = 0x49. ALERT/RDY unused (polled over I2C). AIN3 spare.
    Part("U8", "Analog_ADC:ADS1115IDGS", "Package_SO:MSOP-10_3x3mm_P0.5mm", "ADS1115IDGSR",
         {"1": "+3V3", "3": "GND", "4": "CH4_HTR_I", "5": "LPG_HTR_I", "6": "V3V3_HALF",
          "8": "+3V3", "9": "I2C_SDA", "10": "I2C_SCL"}, "adc_env", lcsc="C37593"),
    Cap100n("C26", "+3V3", "GND", "adc_env"),
    # The thermistor dividers hang off +3V3, which the ADS1115 does not use as its
    # reference: measure the rail so their readings can be corrected for it.
    R("R33", "100k", "+3V3", "V3V3_HALF", "adc_env", lcsc=R100K),
    R("R34", "100k", "V3V3_HALF", "GND", "adc_env", lcsc=R100K),
    Cap100n("C27", "V3V3_HALF", "GND", "adc_env"),

    # ---- Rev E: CO module and sampling fan --------------------------------------
    # J4 is six plated pads along the top edge. The CO module (Winsen ZE15-CO /
    # ZE07-CO) needs 5-12 V: it runs from the heater rail, as does an optional
    # 5 V fan; both are off with the heaters. Module TX -> RXD0 (GPIO44); RXD0's
    # 3.0 V-max input is driven through 1k. Pin 1 doubles as the +5V_HTR test point.
    Pads("J4", "Connector_PinHeader_1.27mm:PinHeader_1x06_P1.27mm_Vertical",
         "AUX", {"1": "+5V_HTR", "2": "GND", "3": "RXD0", "4": "CO_RX", "5": "+5V_HTR", "6": "GND"},
         "mcu", description="Wire pads: 1 +5V (CO), 2 GND, 3 CO TX in, 4 CO RX out, 5 +5V (fan), 6 GND"),
    R("R30", "1k", "TXD0", "CO_RX", "mcu", lcsc=R1K),

    # ---- Rev E: VSYS bulk (USB-only heater start-up, see README) ----------------
    Cap22u("C28", "VSYS", "GND", "regulators"),
    Cap22u("C29", "VSYS", "GND", "regulators"),
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
# rev E: notch in the sensor-end edge, between the cans, for the air blade's tab
NOTCHES = [dict(x0=64.8, y0=13.4, y1=17.6)]


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
    # rev E: RST stacked right above BOOT (as rev D); BOOT stays on rev B's spot, and
    # the serial/supply test pads take RST's old place, in a row
    "TP1": (27.0, 19.3, 0, "F"), "TP2": (29.3, 19.3, 0, "F"),
    "TP3": (31.6, 19.3, 0, "F"), "TP4": (33.9, 19.3, 0, "F"),
    "SW2": (22.6, 24.7, 0, "F"), "SW3": (22.6, 31.4, 0, "F"), "R12": (18.0, 27.4, 90, "F"),
    "U7": (8.5, 30.0, 0, "F"), "C15": (10.6, 30.0, 90, "F"),
    "SW1": (33.0, 1.8, 180, "F"),  # lever overhangs the top edge; pins face inboard
    "U3": (29.5, 10.5, 0, "F"), "C4": (29.5, 14.0, 0, "F"), "C16": (28.4, 7.6, 0, "F"),
    "J1": (33.0, 32.3, 0, "F"), "U1": (33.0, 24.2, 0, "F"),
    "R1": (29.5, 25.5, 90, "F"), "R2": (37.6, 24.6, 90, "F"),
    "U2": (42.5, 23.5, 0, "F"), "C1": (38.2, 22.0, 0, "F"), "C2": (40.0, 19.3, 0, "F"),
    "C3": (46.5, 23.5, 90, "F"),
    "R3": (40.6, 29.0, 0, "F"), "R4": (40.6, 30.6, 0, "F"), "R5": (40.6, 32.2, 0, "F"),
    "R6": (36.0, 19.0, 0, "F"), "R7": (36.0, 17.6, 0, "F"), "R26": (43.5, 27.2, 0, "F"), "Q1": (43.6, 30.3, 90, "F"), "R27": (26.9, 5.8, 90, "F"),
    "J2": (50.0, 30.0, 0, "F"), "TP5": (43.5, 34.0, 0, "F"),
    "U4": (44.5, 8.0, 180, "F"), "L1": (40.8, 8.0, 0, "F"), "C5": (37.0, 8.0, 90, "F"),
    "C6": (45.0, 11.0, 0, "F"), "C7": (40.8, 11.5, 180, "F"),
    "R8": (47.5, 7.1, 0, "F"), "R9": (47.5, 8.5, 0, "F"), "R10": (34.5, 11.0, 90, "F"),
    # J4 (CO/fan pads) takes TP6's place on the top edge; pins run +x from pin 1
    "J4": (49.6, 1.9, 90, "F"), "R30": (47.4, 2.4, 0, "F"),
    "U6": (47.5, 15.5, 90, "F"), "C12": (44.5, 15.5, 90, "F"),
    # rev E: VBAT and heater-rail dividers side by side (VBAT feed from the charger,
    # +5V from the boost output next door); their filter caps sit at the ESP32's
    # ADC pins (GPIO1/GPIO2), which they feed
    "R14": (39.6, 15.0, 90, "F"), "R13": (40.8, 15.0, 90, "F"),
    "R15": (42.0, 15.0, 90, "F"), "R16": (43.2, 15.0, 90, "F"),
    "C14": (12.6, 19.7, 270, "F"), "C13": (13.8, 19.7, 270, "F"),
    "R17": (44.0, 18.6, 0, "F"), "R18": (47.5, 19.8, 0, "F"), "R19": (45.0, 20.4, 0, "F"),
    "S1": _to5(60.5, 9.0), "R20": (51.5, 6.5, 90, "F"), "R21": (53.0, 6.5, 90, "F"),
    "C20": (54.5, 6.5, 90, "F"),
    "S2": _to5(60.5, 22.0), "R23": (50.5, 23.0, 90, "F"), "R24": (52.0, 23.0, 90, "F"),
    "C23": (53.5, 23.0, 90, "F"),
    # rev E: heater shunts beside each can's heater-return pin (CH4 in the free top-right
    # corner, LPG in the 3 mm gap between the cans), with the thermistor pads in that
    # gap too (pads run +x from pin 1, at the gas inlet); the thermistor dividers in a
    # row above the two ADCs, between J3 and their inputs
    "R22": (59.0, 2.0, 0, "F"),
    "R28": (51.0, 11.0, 90, "F"), "C24": (52.2, 11.0, 90, "F"),
    "R25": (57.0, 15.5, 0, "F"),
    # rev E: the air blade's socket pads, beside the notch in the sensor-end edge
    "J3": (64.025, 15.5, 0, "F"),
    # rev E: ADS1115 #2 and its 3V3 divider, where the old fallback links were
    "U8": (52.6, 16.0, 90, "F"), "C26": (55.0, 15.5, 90, "F"),
    "R33": (50.8, 20.3, 90, "F"), "R34": (52.2, 20.3, 270, "F"), "C27": (53.6, 20.3, 270, "F"),
    # rev E: extra VSYS bulk at the boost converter's input, beside C5
    "C28": (34.9, 7.5, 90, "F"), "C29": (32.8, 7.7, 90, "F"),
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
# rev E: no B.Cu fill between J4's pads and its +5V detour (it leaves a sliver)
J4_NOFILL = dict(layers=["B.Cu"], rule_area=("fills",), name="J4 no fill",
                 pts=[(49.0, 0.6), (57.0, 0.6), (57.0, 3.0), (49.0, 3.0)])
ZONES.append(J4_NOFILL)
# Layers Freerouting may not route signals on (kept as solid planes).
PLANE_LAYERS = ["In1.Cu"]
# Poured after routing so Freerouting can use F/In2/B for signals.
POST_ROUTE_ZONES = [dict(net="GND", layers=["F.Cu", "In2.Cu", "B.Cu"], name="GND fill")]
# 1 mm L-shaped slot that cuts the SHT40 tongue free on two sides (closed polygon).
SLOTS = [[(1.0, 24.0), (16.0, 24.0), (16.0, 31.0), (15.0, 31.0), (15.0, 25.0), (1.0, 25.0)]]
# Switch labels replace their reference designators on the silkscreen.
SILK_HIDE_REFS = {"SW2", "SW3"}
SILK_TEXT = [
    dict(text="CH4", at=(64.9, 12.5), size=0.6), dict(text="LPG", at=(56.0, 28.2), size=1.0),
    dict(text="BLADE", at=(61.4, 15.5), size=0.5),
    dict(text="5V G TX RX 5V G", at=(52.8, 3.7), size=0.5),
    # serial / supply test pads (as rev C labels them)
    dict(text="TX", at=(27.0, 17.7), size=0.6), dict(text="RX", at=(29.3, 17.7), size=0.6),
    dict(text="GND", at=(31.6, 17.7), size=0.6), dict(text="3V3", at=(33.9, 17.7), size=0.6),
    dict(text="-", at=(48.0, 24.6), size=1.0), dict(text="+", at=(53.0, 24.6), size=1.0), dict(text="ON", at=(38.8, 2.4), size=0.8),
    dict(text="RST", at=(27.6, 24.7), size=0.8), dict(text="BOOT", at=(18.0, 34.5), size=0.8),
    dict(text="CH4 detector rev E", at=(33.0, 33.0), size=1.0, side="B"),
]

# Hand-routed boost power loop (locked; Freerouting routes around it).
# U4 is rotated 180 deg: SW / VOUT / GND pads face the inductor on the left.
PREROUTE = [
    # rev E: 3V3 divider node R33-R34-C27 in a straight line (pads face each other)
    dict(net="V3V3_HALF", layer="F.Cu", width=0.25, pts=[(50.8, 19.79), (53.6, 19.79)]),
    # rev E: GPIO2 (heater rail) and GPIO1 (VBAT, under it on B.Cu) to their filter caps
    dict(net="HTR_SENSE", layer="F.Cu", width=0.2, pts=[(10.65, 17.5), (10.65, 18.3), (12.6, 18.3), (12.6, 19.22)]),
    dict(net="VBAT_SENSE", layer="F.Cu", width=0.2, pts=[(9.8, 17.5), (9.8, 18.6)]),
    dict(net="VBAT_SENSE", layer="B.Cu", width=0.2, pts=[(9.8, 18.6), (13.8, 18.6)]),
    dict(net="VBAT_SENSE", layer="F.Cu", width=0.2, pts=[(13.8, 18.6), (13.8, 19.22)]),
    # rev E: charger VBAT pins (2, 3) out to a via, so VBAT can leave on an inner layer
    dict(net="VBAT", layer="F.Cu", width=0.4, pts=[(41.0625, 23.25), (40.6, 23.25), (40.25, 23.6), (40.25, 24.6)]),
    dict(net="VBAT", layer="F.Cu", width=0.3, pts=[(41.0625, 23.75), (40.25, 23.75)]),
    # rev E: TXD0 from the module's top row to R30 (CO module), on In2 along the top strip
    dict(net="TXD0", layer="F.Cu", width=0.2, pts=[(11.5, 3.5), (11.5, 2.4)]),
    dict(net="TXD0", layer="In2.Cu", width=0.2, pts=[(11.5, 2.4), (12.0, 2.9), (45.9, 2.9)]),
    dict(net="TXD0", layer="F.Cu", width=0.2, pts=[(45.9, 2.9), (46.4, 2.4), (46.89, 2.4)]),
    # ...and off that, down B.Cu between D1 and the power switch to the TX test pad
    dict(net="TXD0", layer="B.Cu", width=0.2, pts=[(27.3, 2.9), (27.3, 4.0), (26.5, 4.8), (26.5, 18.8), (26.0, 19.3)]),
    dict(net="TXD0", layer="F.Cu", width=0.2, pts=[(26.0, 19.3), (27.0, 19.3)]),
    # rev E: charger VSYS pins (10, 11) escape: right to a via, then on In2 to a via at
    # VSYS cap C2's pad (otherwise the autorouter boxes them in with ILIM/VBUS/CHG_N)
    dict(net="VSYS", layer="F.Cu", width=0.3, pts=[(43.94, 23.25), (43.94, 23.75)]),
    dict(net="VSYS", layer="F.Cu", width=0.3, pts=[(43.94, 23.5), (44.95, 23.5)]),
    dict(net="VSYS", layer="In2.Cu", width=0.5, pts=[(44.95, 23.5), (44.95, 21.3), (40.2, 21.3), (39.225, 20.3)]),
    dict(net="VSYS", layer="F.Cu", width=0.4, pts=[(39.225, 19.3), (39.225, 20.3)]),
    # ...and from there up to the boost input on B.Cu (the charger-to-boost VSYS trunk)
    dict(net="VSYS", layer="B.Cu", width=0.5, pts=[(39.225, 20.3), (38.7, 19.8), (38.7, 6.7), (38.3, 6.1)]),
    # rev E: SCL trunk alongside the SDA one: In2 from the module side, a hop on B.Cu
    # across the SDA branch, and a via under ADS1115 #1 to its SCL pin
    dict(net="I2C_SCL", layer="In2.Cu", width=0.2, pts=[(16.6, 19.9), (16.6, 15.85), (42.6, 15.85), (42.6, 16.4)]),
    dict(net="I2C_SCL", layer="B.Cu", width=0.2, pts=[(42.6, 16.4), (45.8, 16.4), (46.2, 16.0)]),
    dict(net="I2C_SCL", layer="F.Cu", width=0.2, pts=[(46.5, 13.3875), (46.5, 15.7), (46.2, 16.0)]),
    # rev E: ADS1115 #1 GND pins (1, 3) to a plane via left of the package
    dict(net="GND", layer="F.Cu", width=0.25, pts=[(47.5, 17.613), (47.5, 18.8), (46.5, 18.8)]),
    dict(net="GND", layer="F.Cu", width=0.25, pts=[(46.5, 17.613), (46.5, 18.8), (45.9, 18.8), (46.0, 19.7)]),
    # rev E: ADS1115 #2 centre GND pin to a via under the package body
    dict(net="GND", layer="F.Cu", width=0.2, pts=[(52.6, 18.113), (52.6, 16.0)]),
    # rev E: SDA trunk from the module side to the ADCs' pull-up on In2 (as rev C needed;
    # the middle is too dense for the autorouter), clear of the H2 hole
    dict(net="I2C_SDA", layer="In2.Cu", width=0.2, pts=[(15.75, 18.7), (15.75, 15.2), (43.2, 15.2),
                                                        (44.51, 16.5), (44.51, 19.45)]),
    dict(net="I2C_SDA", layer="F.Cu", width=0.2, pts=[(44.51, 18.6), (44.51, 19.45)]),
    # ...and on to ADS1115 #1's SDA pin, through a via under its body
    dict(net="I2C_SDA", layer="In2.Cu", width=0.2, pts=[(43.2, 15.2), (46.7, 15.2), (47.0, 15.5)]),
    dict(net="I2C_SDA", layer="F.Cu", width=0.2, pts=[(47.0, 13.3875), (47.0, 15.5)]),
    # rev E: R14's GND pad straight to a plane via
    dict(net="GND", layer="F.Cu", width=0.25, pts=[(39.6, 14.49), (39.6, 13.55)]),
    # rev E: GND of the LPG shunt R25 and C26 (between the cans) and of the monitor
    # caps C13/C14 (by the ESP32) to plane vias: the fills there are cut off
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(57.825, 15.5), (58.7, 15.5)]),
    dict(net="GND", layer="F.Cu", width=0.25, pts=[(12.6, 20.18), (13.8, 20.18)]),
    dict(net="GND", layer="F.Cu", width=0.25, pts=[(13.2, 20.18), (13.2, 20.95)]),
    # rev E: air blade socket GND pad to a plane via (too near the edge for the fill)
    dict(net="GND", layer="F.Cu", width=0.3, pts=[(64.025, 14.5), (62.9, 14.5)]),
    # rev E: heater-rail divider feed (R15) from the boost output's via by C6, under the ADC row
    dict(net="+5V_HTR", layer="B.Cu", width=0.5, pts=[(44.05, 12.3), (44.05, 13.46), (41.098, 16.412)]),
    dict(net="+5V_HTR", layer="F.Cu", width=0.5, pts=[(41.098, 16.412), (42.0, 15.51)]),
    # rev E: J4's +5V pads to the boost output's B.Cu feed (R8 sense line)
    dict(net="+5V_HTR", layer="B.Cu", width=0.4, pts=[(49.6, 3.2), (47.8, 5.0), (46.99, 5.0)]),
    # rev E: J4's two +5V pads, joined under pins 2-4 on B.Cu
    dict(net="+5V_HTR", layer="B.Cu", width=0.4, pts=[(49.6, 1.9), (49.6, 3.2), (54.68, 3.2), (54.68, 1.9)]),
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
    dict(net="GND", at=(58.7, 15.5)), dict(net="GND", at=(13.2, 20.95)),  # rev E: cut-off GND
    dict(net="GND", at=(62.9, 14.5)),  # rev E: air blade socket GND
    dict(net="TXD0", at=(27.3, 2.9)), dict(net="TXD0", at=(26.0, 19.3)),  # rev E: TX test pad
    dict(net="+5V_HTR", at=(41.098, 16.412)),  # rev E: R15 feed
    dict(net="GND", at=(45.9, 18.8)), dict(net="GND", at=(46.0, 19.7)),  # rev E: ADS1115 #1 GND
    dict(net="GND", at=(39.6, 13.55)),  # rev E: R14 GND
    dict(net="I2C_SDA", at=(44.51, 19.45)),  # rev E: SDA trunk, ADC end
    dict(net="I2C_SDA", at=(47.0, 15.5), d=0.5, drill=0.2),  # rev E: under ADS1115 #1
    dict(net="TXD0", at=(11.5, 2.4)), dict(net="TXD0", at=(45.9, 2.9)),  # rev E: TXD0 to R30
    dict(net="VBAT", at=(40.25, 24.6)),  # rev E: charger VBAT escape
    dict(net="VSYS", at=(44.95, 23.5), d=0.5, drill=0.2), dict(net="VSYS", at=(39.225, 20.3)),  # rev E
    dict(net="I2C_SCL", at=(42.6, 16.4)), dict(net="I2C_SCL", at=(46.2, 16.0), d=0.5, drill=0.2),  # rev E
    dict(net="VBAT_SENSE", at=(9.8, 18.6)), dict(net="VBAT_SENSE", at=(13.8, 18.6)),  # rev E
    dict(net="GND", at=(52.6, 16.0), d=0.5, drill=0.2),  # rev E: ADS1115 #2 GND, under its body
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
