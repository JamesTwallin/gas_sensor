# Air blade (rev A)

A tiny plug-in board for the [rev E phone-companion board](../phone_board_reve/).
It stands upright in a notch in rev E's sensor end, between the two gas sensor
cans, and pokes 4.5 mm out through a slot in the case face, so its tip sits in the
outside air level with the gas sensors' caps. It carries:

- **an outside-air temperature/humidity sensor** (SHT40-CD1B, I²C address 0x46;
  an SHT40-BD1B at 0x45 works too, but never an -AD1B, which clashes with rev E's own).
  Rev E's own SHT40 (0x44) sits inside the case and reads the case air, warmed by
  the gas sensors' heaters; this one reads the street;
- **the heated airflow thermistor** (a 1 kΩ NTC). Moving air cools it; the
  firmware turns that into an airflow index for the gas detector
  ([docs/HARDWARE.md](../../docs/HARDWARE.md) section 1). The SHT40 beside it gives
  it the air temperature it needs.

![top](preview/render_top.png)

**Status: designed, not built.** The board passes KiCad's checks (no design-rule
errors, nothing unconnected, schematic and board in agreement).

## Shape

5.7 × 14.9 mm, 2 layers, **1.0 mm thick**.

- **Tip: two prongs, 1 mm apart.** The SHT40 and its capacitor are on one, the
  heated thermistor on the other, so the thermistor's warmth (2.7 mW) does not
  reach the SHT40. The gap runs down to just below the case face.
- **Foot:** five pads on the front face, just above two small shoulders. The
  shoulders rest on rev E's top surface; below them a tab drops into rev E's notch.
- **No copper pours,** and thin (0.15 mm) tracks: copper would carry the
  thermistor's heat away and blunt the airflow signal.

| Foot pad | Net | Rev E J3 pad |
|---|---|---|
| 1 | heated thermistor | 1 |
| 2 | GND | 2 |
| 3 | 3.3 V | 3 |
| 4 | SCL | 4 |
| 5 | SDA | 5 |

## Parts

All three are assembled by JLC (LCSC numbers in `production/bom.csv`):

| Ref | Part | LCSC | What it does |
|---|---|---|---|
| U1 | Sensirion SHT40-CD1B-R3 | C7461852 | outside-air temperature and humidity, I²C 0x46 |
| C1 | 100 nF 0402 | C1525 | U1's supply decoupling |
| RT1 | Murata NCP18XQ102J03RB, 1 kΩ NTC, 0603, B 3650 K | C152577 | heated airflow thermistor, fed 2.7 mW through rev E's R28 (1 kΩ) |

## Ordering from JLCPCB

The blade is too small for JLC to assemble on its own, and JLC's own panel
option ("Panel by JLCPCB") only does V-cut, which can't follow the forked tip
or the shoulders. So order the ready-made panel in **`production/panel/`**: 6
blades in a 35 × 46 mm frame, with tooling holes and alignment marks for the
assembly machine.

![panel](production/panel/render_top.png)

1. **PCB:** upload `production/panel/gerbers.zip`. 2 layers, **1.0 mm** thick.
   Leave **Delivery Format at "Single PCB"**: the file already is the panel, so
   the quantity counts panels (minimum 5 = 30 blades of bare board). 0.15 mm
   track and clearance, 0.45 mm vias with a 0.2 mm drill. Two of the vias sit in
   C1's pads: choose JLC's filled and capped via-in-pad option, as for rev E.
2. **Assembly:** top side only, `production/panel/bom.csv` and
   `production/panel/cpl.csv`. Assemble **2 panels** (JLC's minimum) = 12 blades.
   Look over JLC's placement preview, especially each U1's pin-1 corner
   (positions matched to LCSC's footprints by `gen/jlc_align.py`).
3. **Breaking out:** each blade hangs on two small tabs of drilled holes on its
   long sides, below the fork. Bend each blade out with pliers, then file the
   two nubs flush so the blade slides through the case slot. The tips, the
   slot and the foot have no tabs, so they need no filing.

`production/gerbers.zip`, `bom.csv` and `cpl.csv` (one blade) are kept for reference.

## Fitting it to rev E

1. Tin rev E's J3 pads (the five pads beside the notch between the cans, labelled
   BLADE) and the blade's five foot pads.
2. Put the blade's tab into the notch, **parts facing the middle of rev E** (the
   foot pads facing J3), with the shoulders flat on the board.
3. Check it stands square, then solder each foot pad to its J3 pad with a fillet
   of solder across the corner. Pad 1 is the one nearest the CH4 can.
4. Fit the board into the rev E front shell
   ([hardware/enclosure](../enclosure/), `stl/reve_v2_front.stl`) straight down,
   not tilted: the blade slides into a guide on the inside of the face and out
   through the slot between the sensor collars. The guide holds it over 5.8 mm, so
   knocks on the tip go into the case, not the solder joint.

## Firmware

Nothing to set: the rev E firmware (`pio run -d firmware/phone_board -e
phone_board_reve`) looks for an SHT40 at 0x45, then 0x46, at start-up. When it finds one, that
supplies the temperature and humidity (to the phone and to the gas detector), the
on-board SHT40 is logged as `case_temp_c` / `case_rh_pct` on USB serial, and the
Info JSON says `"t_src":2`. Then run the still-air calibration
([docs/HARDWARE.md](../../docs/HARDWARE.md) section 1.6).

## The design is generated

As for rev E: edit `gen/design.py`, then

| Step | Command |
|---|---|
| schematic | `python gen/build_sch.py` |
| board (placed and routed: every track is in `design.py`) | `"C:\Program Files\KiCad\9.0\bin\python.exe" gen/build_pcb.py` |
| JLC placement | `...\python.exe gen/jlc_align.py` |
| fab files + renders | `python gen/export.py` |
| 6-up panel for ordering (needs `pip install kikit` in KiCad's python) | `...\python.exe gen/build_panel.py` |

Checks: `kicad-cli pcb drc --schematic-parity air_blade.kicad_pcb` and `kicad-cli sch
erc air_blade.kicad_sch`. Last run (2026-10-10): 0 violations, 0 unconnected, 0
parity issues; ERC 0 errors, 0 warnings.

## Not known yet

- How much the thermistor self-heats on the blade (an estimate is about 1 °C:
  some of its heat goes into the blade, not the air), and how strongly its
  reading follows airflow. The still-air calibration and the airflow survey in
  [docs/PROTOCOL.md](../../docs/PROTOCOL.md) measure both.
- Whether the right-angle solder joint is strong enough for a fleet (the case
  guide takes side loads; a dab of epoxy along the shoulders would add more).
