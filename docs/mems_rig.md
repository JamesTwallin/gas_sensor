# The MEMS rig: a test rig for a cheaper gas sensor

The MEMS rig is the board with one addition: a socket for a second plug-in board,
the **MEMS blade**, which carries two small, cheap MEMS gas sensors. They sit in the
same inlet air as the two Figaro sensors and the air blade, so every plume is seen
by all four gas sensors at once. The rig exists to answer one question: **can a
sensor costing a pound or two find real leaks as well as the Figaros, which cost
about £23 each?** Production units will carry only the sensor that wins.

The rig's board files are in [hardware/board_mems](../hardware/board_mems/),
the blade's in [hardware/mems_blade](../hardware/mems_blade/), the survey that
decides it is section 4 of [PROTOCOL.md](PROTOCOL.md), and the analysis tool is
`tools/compare_sensors.py`.

## The short version

- **Why:** a board unit costs about £110 at five units, and half of that is the two
  Figaro sensors. The target for a vehicle unit is about £40.
- **What is new:** a socket (J5) and a notch in the board's sensor end, beside the
  LPG sensor, for the MEMS blade. The blade stands up through a slot in the case
  face, with its two sensors 0.5 to 8 mm out in the air.
- **The sensors:** a **Saiya SY-CH4-37BPM**, a methane sensor (about $1.90 at
  100), and an **SGX MiCS-5524**, which responds strongly to CO and hydrogen and only
  weakly to methane (about $4.70 at 100). Both are stocked at LCSC and placed by
  JLC. The Winsen GM-402B used in an earlier draft is discontinued.
- **Everything else is the same as the board.** Same outline, holes, Figaro
  positions, air blade socket, CO and fan pads. With the socket empty, the rig
  behaves exactly like the board.
- **It fits the board's case**, with a new front shell that has the second slot.
- **Software:** the firmware, the app and the analysis tools now handle four gas
  channels. Logs from the first board and from the board replay exactly as before.
- **Nothing has been built.** Both the rig's board and the blade pass KiCad's checks:
  no design-rule errors, no unconnected nets, schematic and board in agreement, and a
  clean electrical rules check. The MEMS blade was first drawn mirror-image and has
  been redrawn; the air blade can't be fitted to the board yet and is being
  redesigned (see "What is not proven yet").

## Why: cost, and what the survey data says

At five units the board costs about £110 (see the cost table below), and the two
Figaro sensors are about £56 of that with VAT. Bought by the hundred, MEMS gas
sensors cost one or two pounds and JLC places them like any other part.

But no MEMS sensor has a field record on this project. The one real leak surveyed
so far (11 October, [REPORT.md](REPORT.md)) gives the bar a replacement has to
clear. After the conditions model, the leak stood out by:

| Pass | TGS2611 (CH4) | TGS2610 (LPG) |
|---|---|---|
| ~65 km/h | 5 SD | 18 SD |
| ~43 km/h | 16 SD | 40 SD |
| stopped | 37 SD | 66 SD |

(SD here is the robust spread of the leftover signal, so 5 SD is a clear but
small event.) The TGS2610 was the stronger grid-gas channel. A MEMS sensor is
worth switching to only if it gets comparable numbers at 43 to 65 km/h, at the
same false-alarm rate. A datasheet cannot tell us that: it has to be measured on
the same plumes, which is what the rig does.

## The two sensors

Chosen from what LCSC stocks and JLC can place (checked 19 October 2026). The
other candidates are listed at the end.

| | **SY-CH4-37BPM** (sensor A) | **MiCS-5524** (sensor B) |
|---|---|---|
| Maker | Saiya Sensor (China) | SGX Sensortech (Amphenol) |
| LCSC / stock | C22363924 / 71 | C3659348 / 893 |
| Price at 1 / 100 / 1000 | $2.88 / $1.88 / $1.69 | $6.44 / $4.68 / n.a. |
| Target gas | methane, 50-15000 ppm | CO, H2, ethanol; methane above ~1000 ppm |
| Package | 3.8 x 3.8 x 1.5 mm, 8 pads | 5 x 7 x 1.55 mm, 10 pads |
| Heater | 200-240 ohm, ~3.6 V, ~60 mW | 66-82 ohm, ~2.4 V, ~76 mW |
| How we power it | 5 V through 82 ohm (the datasheet's circuit) | 5 V through 82 ohm (the datasheet's circuit) |
| Clean-air resistance | 10-1000 kohm | 100-1500 kohm |
| Load resistor on the blade | 20 kohm (datasheet: 10-50 k) | 200 kohm (chosen near its clean-air range) |
| Methane response | resistance falls to ~0.17 of clean air at 500 ppm (read off its curve) | weak: ~0.6-0.8 at 1000-10000 ppm (read off its curve) |
| Response / recovery | < 20 s / < 60 s (to 70 %) | not stated |
| Temperature and humidity | large: clean-air resistance ~2.4 times at -10 °C, ~0.6 times at 40 °C, falls with humidity | not stated |
| Warm-up | 60 minutes after every power-up; 4 hours powered after soldering | not stated |

Sources: the [SY-CH4-37BPM datasheet](https://www.lcsc.com/datasheet/lcsc_datasheet_2403281610_Saiya-Sensor-SYMM-CH4-4_C22363924.pdf)
and [MiCS-5524 datasheet](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2310271531_Amphenol-ICC-MICS-5524_C3659348.pdf)
on LCSC, and LCSC's product pages for stock and prices.

Why these two: the 37BPM is the only stocked MEMS part made for methane with a
steady heater and a steady reading, so it is the real candidate. The MiCS-5524 is
from a different maker and a different chemistry. It is unlikely to beat the
Figaros on methane, but it reacts strongly to CO and hydrogen, which are in
exhaust and not in mains gas. So it plays roughly the part the TGS2610 plays next
to the TGS2611, and may help tell exhaust from a leak. The rig records both and
lets the survey decide.

## What is new on the board

![The MEMS rig board](../hardware/board_mems/preview/render_top.png)

| | Part | What it does |
|---|---|---|
| **J5** + a second notch | 5 solder pads, 0.95 mm apart, between the LPG can and the H1 hole | the socket for the MEMS blade: 1 sensor A output, 2 GND, 3 3.3 V, 4 switched 5 V for the heaters, 5 sensor B output |
| **Q2, Q3, R37, R38** | P-MOSFET switch with a small N-MOSFET to drive it | switch 5 V from the Figaro heater rail to the blade's heaters, on GPIO12, so the firmware can turn them on after the Figaros |
| **C32** | 1 uF | decoupling for the blade's heater feed |
| **U6 AIN3, U8 AIN3** | the two ADCs' spare inputs | read sensor A and sensor B with 16-bit precision |
| **R35, R36** | 1 Mohm pull-ups on the two inputs | an empty socket reads full scale, so the firmware knows the blade is missing |
| **C30, C31** | 100 nF | filter the two inputs |

The blade itself carries the two sensors, their load resistors (each a pair, with
the ADC reading the middle, as on the Figaro channels) and their 82 ohm heater
resistors, which sit low on the blade inside the case, away from the sensors.

Why the heaters run from 5 V and not from their own regulator, as an earlier draft
had it: the two sensors want different heater voltages (3.6 V and 2.4 V), and both
datasheets give the same circuit, 5 V through 82 ohm. The 5 V rail is already
there for the Figaros, so one switch and two resistors do the job.

### Where the blade goes, and why there

The only free stretch of the sensor end wide enough for two sensors side by side
is the corner beside the LPG can, above the H1 mounting hole. The blade stands
there, 11.4 mm wide, with its back (the foot pads) facing the middle of the
board and its parts facing the case's end wall. Facing the other way, the sensors
would hit the case's H1 screw boss on the way into the shell.

Two consequences:
- **The battery lead now goes past the other corner.** On the board it comes up
  past the board's end next to the USB-C side; that is where the blade stands now.
  On the rig, bring the lead up past the board's end at the power-switch side and
  over the top of the board to the battery plug.
- **The blade is in the LPG can's heat** when the case stands on its switch edge
  on a car mirror (see "Heat" below).

### The case

Print `hardware/enclosure/stl/front_mems.stl` (`mems = true` in
`hardware/enclosure/case.scad`). It is the board's front shell with a second slot,
3.55 x 11.7 mm, beside the LPG cap. The back tray (`back.stl`) and the car adapter
(`car_adapter.stl`) are the same as for the board. In the model, the blade and its
parts clear the shell, the H1 boss, the end wall and the tray.

## Power

Worst case with everything fitted and on. Figures are typical datasheet values;
the CO module's and the fan's are assumptions (marked).

| Load | Rail | Current on that rail |
|---|---|---|
| TGS2611 heater | 5 V | 56 mA |
| TGS2610 heater | 5 V | 56 mA |
| SY-CH4-37BPM heater + 82 ohm | 5 V | 17 mA |
| MiCS-5524 heater + 82 ohm | 5 V | 32 mA |
| CO module (ZE15-CO) | 5 V | ~40 mA (assumed) |
| 5 V fan | 5 V | ~80 mA (assumed) |
| ESP32 (Bluetooth peaks), ADCs, SHT40s, air blade, LED | 3.3 V | ~155 mA peak |

| Case | Drawn from VSYS at 4.4 V (USB) | Within the USB 500 mA limit? |
|---|---|---|
| Board, Figaros only | ~305 mA | yes |
| MEMS rig, Figaros + MEMS blade | ~370 mA | yes |
| MEMS rig + CO module | ~425 mA | yes, with less margin |
| MEMS rig + CO module + fan | ~530 mA | **no** |

(5 V loads converted through the boost at about 85 % efficiency; the 3.3 V
regulator passes its current straight through.)

What this means:
- **The MEMS blade fits the budget.** It adds about 65 mA at the USB input.
- **Turn-on is staggered.** The first board browned out on USB alone when the cold
  Figaro heaters switched on. The MEMS heaters have their own switch, and the
  firmware turns them on 5 seconds after the Figaro heaters, so their start does not
  add to the Figaros' inrush. No extra capacitance is needed beyond the board's.
- **The fan is the problem, not the MEMS blade.** With a fan as well, USB alone is
  over budget. The fan sits straight on the 5 V rail with no switch, so the
  firmware cannot stagger it. Run a fan only with a battery fitted, which covers
  the difference. A later version could give J4's fan pad its own switch.
- **Battery life:** the rig with the blade draws about 1.1 W against the board's
  0.9 W, so about 6 hours on the 2000 mAh cell against about 7.5 (both estimates).

## Heat

The MEMS sensors stand 0.5 to 8 mm out of the face; the LPG can's cap stands about
4 mm out, 9 mm (MiCS-5524) and 13 mm (37BPM) away, centre to centre. Estimates, not
measurements:
- **Moving:** the cans' warm air is carried downstream. A rough estimate, taking
  about a third of the can's 0.28 W out through its cap into a plume about a
  centimetre across at 2 m/s, warms that plume by about 0.4 °C, and only if the
  blade is directly downstream. Usually less.
- **Stopped, case on a car mirror:** this is the bad case. The case stands on its
  switch edge with the USB-C side up, so warm air from the LPG can rises straight
  past the MEMS blade. In still air that could be a few degrees. The 37BPM's
  clean-air resistance changes by roughly 1.5 % per degree, so this would show as a
  slow drift at stops.
- **The other way round:** the MEMS heaters (about 0.14 W together) are above the
  air blade in that position, so their warm air rises away from it.

There was no better place: the blade has to fit beside the cans, inside the board's
outline and case. The comparison measures the effect directly (each channel's
temperature sensitivity, and its residual at stops).

## Firmware, app and tools

- **Firmware:** build target `board_mems` (the `HW_MEMS` flag). It detects the
  blade at start-up and every sample, turns the MEMS heaters on 5 seconds after the
  Figaros, waits 60 minutes before using the MEMS readings, and counts burn-in hours
  in flash. The info JSON says `"proto":2`, `"mems":0/1` and `"mems_burnin_h"`.
- **Bluetooth:** the existing packets are unchanged, so older apps keep working.
  The MEMS data comes on a new characteristic (Gas2, `6d1a0007-...`), one 20-byte
  packet per sample, matched to its sample by sequence number.
- **App:** records 11 new columns at the end of the CSV (blank for older boards) and
  shows the two MEMS channels on the live screen when a blade is fitted.
- **Detector:** runs on all four channels independently, each with its own
  conditions model and thresholds (`anomaly_config.h`). No gas channel is used to
  predict another, and nothing derived from GPS is a model input. The CH4/LPG
  ratio, classification and lead time stay on the two Figaros. The MEMS
  coefficient rows start empty: the rig's first surveys fill them.
- **Tools:** `replay.py` (run, fit, tune, synth, parity, report) and
  `anomaly_core.py` handle two or four channels. Logs from the first board and from
  the board replay byte-for-byte as before, and the C/Python parity test passes for
  both. The new `tools/compare_sensors.py` produces the comparison in
  [PROTOCOL.md](PROTOCOL.md) section 4.

## The comparison plan

Section 4 of [PROTOCOL.md](PROTOCOL.md). In short: a confirmed leak, 10 passes at
each of 30, 50 and 65 km/h and on foot, on at least three days, plus at least six
hours of clean-air driving to set matched false-alarm thresholds. Each pass is
compared channel against channel on the same plume. **Decision rule:** a MEMS
sensor goes into production only if, at 43 to 65 km/h and at the same false-alarm
rate, its median paired SNR is at least about 0.7 times the better Figaro's and it
detects at least as many passes as the TGS2611.

## What it costs

Per unit, in pounds excluding VAT (add 20 %). The board's numbers at 5 units come
from the actual JLC order; everything marked **est.** is an estimate.

| | 5 units | 50 units | 500 units |
|---|---|---|---|
| Main board, assembled (board or MEMS rig) | 24.80 | 10.50 est. | 6.80 est. |
| Air blade, assembled | 2.60 | 1.35 est. | 0.90 est. |
| MEMS blade, assembled | 9.80 est. | 6.40 est. | 5.10 est. |
| TGS2611 (RS) | 23.33 | 20 est. | 12 est. |
| TGS2610 (RS) | 23.3 est. | 20 est. | 12 est. |
| Battery | 10 est. | 6 est. | 3.50 est. |
| Case and screws | 1.20 | 1.00 est. | 0.80 est. |
| Shipping and import fees | 7 est. | 1.50 est. | 0.50 est. |

| Unit | 5 units | 50 units | 500 units |
|---|---|---|---|
| **(a) MEMS rig, everything** | **£102** | **£67** | **£42** |
| **(b) Board** | **£92** | **£60** | **£37** |
| **(c) Production, TGS2610 only** | **£69** | **£40** | **£25** |
| **(d) Production, one MEMS sensor only** | **£48** | **£22** | **£14** |

Notes:
- (b) at 5 units is the £110 quoted earlier once VAT is added.
- (c) is the board without the TGS2611.
- (d) assumes the 37BPM wins and is placed on the main board by JLC (about £2.20
  each at 5, £1.30 at 500), with the air blade kept for the conditions model. If the
  MiCS-5524 won instead, add about £2 to £3.
- At 50 units, (c) just meets the £40 target and (d) beats it easily. At 500 both do.
- The Figaro volume prices are the biggest guess. RS only shows single-unit prices,
  and Figaro's distributor prices for hundreds were not available.
- Assembly cost at 50 and 500 assumes JLC's fixed fees (set-up, stencil, about $3 per
  extended part type) are spread over the batch, as they were on the 5-unit order.

## What is not proven yet

- **Nothing on the MEMS rig has been built.** Both boards pass KiCad's design-rule,
  connectivity, schematic-parity and electrical-rules checks (19 October 2026).
- **The MEMS blade's redraw is untested.** It was first drawn mirror-image, the
  same mistake as the first batch of air blades, so its pads would have missed J5.
  It was redrawn on 22 October 2026 with the parts the right way round and wire-leg
  holes instead of flat pads, but no blade has been made or offered up to a board.
- **The air blade can't be fitted yet either.** The board's J3 pads sit in a 3.8 mm
  gap between the two 13 mm tall sensor cans, 0.3 mm short of the blade's notch, so a
  blade can't realistically be soldered to them. The air blade is being redesigned.
- **Whether either MEMS sensor sees a leak at speed.** That is the point of the
  survey.
- **The load resistors** (20 k and 200 k) are chosen from datasheet ranges. Once a
  blade is running, check that each sensor's clean-air output sits mid-range
  (roughly 100 to 800 mV at the tap) and change the resistors if not.
- **The MiCS-5524's response time, temperature and humidity behaviour, and
  burn-in** are not in its datasheet.
- **The heat from the LPG can at stops** is an estimate.
- **The 37BPM is thinly stocked** (71 at LCSC). Reserve the parts in your JLC
  parts library before ordering.
- **The MEMS blade's soldered-on foot** is the same right-angle joint as the air
  blade's, on a wider, taller blade: it has not been tried.
- **The blade's panel tabs** sit about level with the case face; the nubs must be
  filed flush or they catch in the slot.

## What could not be determined

- The MiCS-5524's response time, temperature and humidity dependence, recommended
  burn-in, and any methane figure beyond reading its datasheet curve.
- The SY-CH4-37BPM's humidity dependence beyond its one curve, and its long-term
  drift.
- The methane sensitivities above marked "read off its curve" are read from
  datasheet plots, not tables.
- The CO module's and a fan's current draw (assumed 40 mA and 80 mA).
- Figaro prices at 50 and 500 units, and battery prices in volume.
- The LCSC part number C8545 (the 2N7002) was not re-checked against the parts
  API; it is JLC's usual basic part for that transistor.

Candidates looked at and not chosen (checked 19 October 2026):
- **Winsen GM-402B:** discontinued at LCSC/JLC.
- **Saiya SY-CH4-35BPM:** methane-specific, but its reading must be pulsed in time
  with its heater, and only 18 are stocked.
- **MiCS-6814:** almost none stocked.
- **BME688, SGP41, ZMOD4510:** air-quality chips with no methane figure.
- **Winsen MP-4 and MQ-4, Figaro TGS8100:** not stocked.

## Building and ordering

Not yet: the air blade has to be redesigned first, and the redrawn MEMS blade is
untested (see above). When ready:

- **Board:** [hardware/board_mems](../hardware/board_mems/). Upload
  `production/gerbers.zip`, `bom.csv` and `cpl.csv` to JLCPCB as for the board.
- **MEMS blade:** [hardware/mems_blade](../hardware/mems_blade/), ordered as a
  panel of six (`production/panel/`), 1.6 mm thick, two panels minimum.
- **Air blade:** as for the board.
- **Hand-solder** the two Figaro sensors, the air blade into J3, the MEMS blade
  into J5, and if used the CO module and fan on J4.
- **Firmware:** `pio run -d firmware/phone_board -e board_mems --target upload`.
- **Burn in** the MEMS blade for 48 hours before surveying.
