# Add-on sensors: airflow thermistor and CO sensor

Two optional additions to the board ([hardware/board](../hardware/board/)).
Both are optional, and the firmware works the same without them.

- **The airflow thermistor** comes ready-made on the
  [air blade](../hardware/air_blade/), a tiny plug-in board that also carries an
  outside-air SHT40 (section 3). It is meant to solder into J3 between the sensor
  cans and poke out through a slot in the front shell. **The current blade
  cannot be fitted:** J3 sits in a 3.8 mm gap between the two 13 mm tall sensor
  cans, and its pads stop 0.3 mm short of the blade's notch, so there is no
  realistic way to solder the blade to them. The blade is being redesigned.
- **The CO module** solders to the six J4 pads on the top edge.

| Add-on | What it is for | Rough cost |
|---|---|---|
| **Airflow thermistor** | Tells the gas detector how much air is blowing past the sensors. Moving air cools the gas sensors' heaters, which changes their readings by tens of millivolts at every stop and start in traffic. Today that is the biggest thing the detector cannot explain. | about £3–4 per assembled air blade |
| **CO sensor** | Exhaust contains carbon monoxide; mains gas does not. Both raise both gas sensors, so CO is the cleanest way to tell a car's exhaust from a gas leak. | about £10–15 |

Background on why these were chosen is in [REPORT.md](REPORT.md). How to
calibrate and test them is in [PROTOCOL.md](PROTOCOL.md). The board's pin map is
in [phone_board.md](phone_board.md).

Prices and stock are snapshots from October 2026. Figures marked *estimate* are
calculated, not taken from a datasheet.

---

## 1. Airflow thermistor

### How it works

A thermistor is a resistor whose value changes with temperature. A very small
one, fed a little current, warms itself a few degrees above the air around it.
Moving air carries that heat away, so the bead cools. The firmware measures how
much power the bead takes, and how far above the air temperature it sits. Their
ratio is the bead's *heat loss per degree* (its conductance, G, in mW/K). G
rises with air speed in a known way (King's law: G = A + B·√speed), with no
response at all to gas. The firmware reports:

```
airflow index = G / G_still − 1
```

which is 0 in still air and grows with airflow. `G_still` comes from a one-minute
still-air calibration (section 1.6).

This is the same thing that happens to the gas sensors' heaters, but without
any gas sensitivity, which is why it can stand in for an airflow sensor.

### 1.1 Parts

| Part | What | Where to buy | Price |
|---|---|---|---|
| **Heated bead** | on the air blade: Murata **NCP18XQ102** (1 kΩ NTC, 0603, B 3650 K, LCSC C152577), assembled by JLC | comes with the blade | pennies |
| Series resistor | **1 kΩ** 1 %: R28, already on the board | — | — |
| Reference thermistor (optional, not needed with the air blade) | TDK (EPCOS) **B57540G1104F000**: 100 kΩ ±1 % glass bead, B = 4092 K. The blade's SHT40 does this job | DigiKey (search the part number), LCSC | about £2–3 |
| Reference resistor and capacitor (with the reference thermistor) | **220 kΩ** 1 % and **100 nF** | any | pennies |

**Why a cheap bead is enough.** A 1 kΩ bead fed through 1 kΩ from 3.3 V takes
about 2.7 mW, which warms it roughly 1–3 °C above the air (epoxy and chip beads
lose more heat than glass ones, so they sit at the low end). That is a smaller
rise than the expensive Amphenol BR16PA202K micro-bead (about 5 °C on 0.6 mW,
about £23), but the ADC resolves a few thousandths of a degree, so the signal is
still plenty. The cheap bead is also slower (seconds rather than about one), and
that does not matter: the survey analysis ([REPORT.md](REPORT.md) section 3)
found the same benefit for a bead lagging 3 s, 8 s, 20 s or 40 s, because the
gas sensors' own response to airflow is slow too. The bead's B value is set in
the firmware (`AIRFLOW_BEAD_DEFAULT`, `beta_k`; 3650 K, the Murata part's, is
the default); it barely changes the airflow index.

A BR16 also works: fit 3.9 kΩ for R28 and set `series_ohm 3900`,
`r25_ohm 2000`, `beta_k 3500` in `AIRFLOW_BEAD_DEFAULT`.

Sources:
- TDK G540 (B57540) datasheet: https://www.tdk-electronics.tdk.com/inf/50/db/ntc_09/Glass_enc_Sensors__B57540__G540__G1540.pdf
- BR series datasheet (the expensive option): https://amphenol-sensors.com/en/thermometrics/ntc-thermistors/glass/3339-br-series

### 1.2 Circuit

```
 +3V3 ──── R28 1 kΩ ──────┬──── ADS1115 #1 (U6) AIN2
                          ├──── C24 ── GND
                          │
                   J3 pad 1 → 1 kΩ bead on the air blade (heated)
                          │
 GND (J3 pad 2) ──────────┘
```

All of this is on the board and the air blade. The blade's SHT40 gives the air
temperature right beside the bead, so no reference thermistor is needed.

**Optional reference thermistor.** The firmware can also use an unheated
100 kΩ bead for the air temperature, on U6's spare AIN3:

```
 +3V3 ──── 220 kΩ ────┬──── U6 AIN3 (pin 7)
                      ├──── 100 nF ── GND
                  B57540G1104F000 (100 kΩ, unheated)
                      │
 GND ─────────────────┘
```

U6's AIN3 (pin 7) is not connected to anything on the board, so fitting one
means a fine wire to that pin of the chip.

### 1.3 Operating point and expected signal

*Estimates* for a 1 kΩ bead with 1 kΩ, at 20 °C in still air:

| | Value |
|---|---|
| Power in the bead | about 2.7 mW (5.4 mW from the 3.3 V rail in total) |
| Bead temperature above the air | about 1.3 °C for an epoxy bead (about 2 mW/K), about 3 °C for a small glass bead |
| Voltage at the ADC | about 1.65 V |
| Change with bead temperature | about −38 mV per °C |
| Change with airflow | if moving air doubles the heat loss, the rise halves: about +25 mV (epoxy) to +55 mV (glass) |

The heat loss grows with the square root of air speed, so the index rises
fastest at low speeds and flattens at high speeds. That suits walking surveys
and stop-start traffic, which is where the gas sensors are most affected. The
exact curve depends on the bead and has to be calibrated (PROTOCOL.md, survey 1).

**What this means in practice.**
- The full airflow signal is only about 0–100 mV. A 3–4 °C change in air
  temperature would move the reading by the same amount. The firmware therefore
  works from the bead's temperature *rise* above ambient, not the raw voltage.
- **Ambient must be measured right beside the bead.** The air blade's SHT40
  does this. The on-board SHT40 is no good for it: it sits inside the case at
  the far end of the board, on its own thermally isolated tongue, and responds
  more slowly than the bead. When the device moves from a warm car into cold
  air, it lags, and the bead's apparent rise changes for a while, which reads as
  a change in airflow. A reference bead beside the heated one (section 1.2) is
  the other way to get it right.
- The ADS1115 reads the bead in 0.125 mV steps.
- **The 3.3 V supply is measured, not assumed.** A 1 % change in the 3.3 V rail
  would shift the bead's reading by about 11 mV. The second ADS1115 (U8) reads
  the rail every sample, and the firmware uses that as the bead's supply
  voltage (falling back to 3300 mV if the reading is outside 2.9–3.7 V).
- **The bead's B value** affects its absolute temperature but barely changes
  the index. Section 1.6 explains how to measure it.

### 1.4 Where the bead has to sit

The air blade holds its thermistor and SHT40 in the outside air, level with the
sensor caps, in the same place on every unit. Whatever replaces the current
blade has to keep to the same rules:

- **In the same airstream as the gas sensors**, level with the sensor caps, so
  air reaching the sensors passes the bead too.
- **Upstream of the sensors' own heat**, or level with them, never downwind of a
  sensor cap: each sensor heater gives off about 280 mW, which would read as
  warm, still air. With the device facing forward in a car window or held out in
  front on foot, "beside" is fine.
- **In free air**, touching nothing: the blade's tip stands 4.5 mm out of the
  slot.
- A reference bead (if fitted) goes 3–5 mm from the heated bead, at the same
  height, and **not downwind of it**: the heated bead warms the air behind it.
- Shade both from direct sun, as for the gas sensors.

### 1.5 Firmware

The `board` build already has the air blade's thermistor turned on
(`-DHW_AIRFLOW=1` in `firmware/phone_board/platformio.ini`). For a reference
thermistor, add to `build_flags`:

```
    -DHW_AIRFLOW_REF=1      ; reference bead on U6's AIN3
```

Not with the `board_mems` build: the MEMS rig uses AIN3 for one of its sensors.

The raw pin voltage and the index are logged (`airflow_raw`,
`airflow_index`), but **the model does not use them yet.** That needs surveys
recorded with the thermistor fitted, a refit, and `ANOM_USE_AIRFLOW 1` in
`lib/anomaly/anomaly_config.h` (see [REPORT.md](REPORT.md)).

### 1.6 Still-air calibration

1. Let the board run for 5 minutes with the heaters on.
2. Put it in a closed cardboard box (still air, same temperature as the room)
   and leave it 2 minutes to settle.
3. Send Control opcode `0x04` (the app has the encoder,
   `encodeCalibrateAirflow()` in `app/src/core/protocol.ts`, but no button for it
   yet; for now send it from a BLE tool such as nRF Connect: write `04 3C` to the
   Control characteristic). For 60 s the firmware averages the
   bead's conductance and sets bit 7 of the Analysis flags.
4. The result is kept in flash and reported in the Info JSON as `g_still`
   (expect roughly 1–2.5 mW/K for a cheap epoxy bead, about 0.12 for the BR16).
   From then on the index reads near 0 in the box.

To measure the bead's B value (optional): read `airflow_raw` with the bead
**unheated** at two known temperatures. Fit a 100 kΩ series resistor in place of
R28 so it does not self-heat. Then B = ln(R1/R2) / (1/T1 − 1/T2), with T in
kelvin.

---

## 2. CO sensor

### How it works

An electrochemical cell produces a tiny current proportional to the carbon
monoxide reaching it. Small modules add the electronics and send the reading as
a number over a serial line once a second. Mains gas contains no CO, and these
cells barely respond to methane, so CO rises only for combustion: exhaust,
boilers, fires.

### 2.1 Parts

| Part | What | Where to buy | Price |
|---|---|---|---|
| **CO module (recommended)** | Winsen **ZE15-CO**: 0–500 ppm, 0.1 ppm steps, responds in 30 s, UART output, 5–12 V supply | Winsen shop, AliExpress | $20 for two |
| Alternative | Winsen **ZE07-CO**: same output format, slower (60 s) | Winsen shop, AliExpress, Robu.in | about $20 |
| Wire | three or four thin wires, about 10 cm | any | — |

Sources:
- ZE15-CO manual: https://www.winsen-sensor.com/d/files/manual/ze15-co.pdf
- ZE07-CO manual v1.7: https://www.winsen-sensor.com/d/files/ze07-co-module-1_7.pdf
- Shop: https://shop.winsen-sensor.com/products/electrochemical-co-module-ze15-co

A module that runs straight from 3.3 V also exists: DFRobot SEN0466. The firmware driver here is written for the Winsen serial format, not
that one.

### 2.2 Circuit

The six J4 pads on the board's top edge, 1.27 mm apart (labelled 5V G TX RX 5V G):

```
 J4 pin 1  +5V_HTR ──── Vin   (module needs 5–12 V; the board's 3.3 V is not enough)
 J4 pin 2  GND     ──── GND
 J4 pin 3  TX in   ◄─── TXD   (the module's 3 V serial output, 9600 baud, into GPIO44)
 J4 pin 4  RX out  ───► RXD   optional (through R30 1 kΩ from GPIO43; the default mode sends without being asked)
 J4 pin 5  +5V_HTR ──── fan +  (optional 5 V fan)
 J4 pin 6  GND     ──── fan −
```

- **Power comes from the heater rail (+5V_HTR).** It is the board's only
  5 V supply. It is switched off with the heaters (low-battery cutoff), when the
  gas readings are invalid anyway. The module draws a few mA (Winsen states
  under 5 mA for the similar ZE16), which is small next to the heaters'
  115 mA.
- GPIO43/GPIO44 are the ESP32's spare serial port (the console runs over USB
  instead). They also go to test pads TP1/TP2, but nothing else uses them.
- The module's serial output is 3 V, which the ESP32 reads directly. The
  module's RXD input is rated to 3.0 V, which is why R30 (1 kΩ) sits in series
  on pin 4.
- Solder thin wire straight onto the pads.

### 2.3 Mounting

- Close to the gas sensors' inlet, so it samples the same air, but **not in the
  direct jet**. Winsen warns against strong air movement over the cell. Behind
  the hex grille, facing sideways rather than straight into the airflow, is
  about right.
- After power-on the module needs **3 minutes to warm up**, about the same as
  the gas sensors (5 minutes the first time it is used).

### 2.4 Expected signal and limits

- Resolution 0.1 ppm. The firmware treats a rise of more than **2 ppm** above
  CO's own slow baseline during an event as "CO present" (`ANOM_CO_RISE_PPM`).
  That threshold is a placeholder: the exhaust survey in
  [PROTOCOL.md](PROTOCOL.md) is there to set it from real exhaust.
- **It is slow.** A 30–60 s response against a few seconds for the gas sensors
  means a passing exhaust plume shows up in CO late and smeared out. The
  detector therefore keeps watching CO for 45 s after the gas channels settle
  before it closes an event (`ANOM_CO_TAIL_S`).
- **Not every engine makes much CO.** Modern petrol cars with warm catalytic
  converters and diesels emit little. "No CO rise" does not prove "not exhaust".
- **Cross-sensitivity.** Winsen publishes no figures for the module itself. For
  its ME2-CO cells: 500 ppm hydrogen reads as about 43 ppm CO. Rich or
  cold-start exhaust contains hydrogen, which helps here. Ethylene also reads
  strongly. Winsen gives no figure for methane; electrochemical CO cells are
  generally regarded as insensitive to it. **This must be checked on the
  positive-control survey** (the CO trace should stay flat at a gas leak).

### 2.5 Firmware

```
    -DHW_CO=1               ; CO module on J4 (GPIO44)
```

The reading is logged as `co_raw` (ppm). As with airflow, the model and the
classifier only use it once `ANOM_USE_CO 1` is set in `anomaly_config.h`. With
it set, an event in which both gas channels rise together with CO is classed
**EXHAUST**. Without CO, such an event stays **UNRESOLVED**.

---

## 3. Outside-air temperature and humidity

### Why

The board's own SHT40 sits inside the case. The survey data shows it reads the
case air: on every drive it was 0.6-0.9 °C warmer at walking pace than at
motorway speed, and it read 28-32 °C during an indoor stop, because the sensor
heaters (about 0.6 W) warm the inside of the case and airflow cools it. The
detector needs the temperature and humidity of the air the gas sensors are
sampling.

### The air blade's SHT40

The [air blade](../hardware/air_blade/) carries a second SHT40 (the 0x46 variant,
SHT40-CD1B; the firmware also accepts the 0x45 SHT40-BD1B) on its tip, out in the air beside the sensor caps. The firmware looks
for it at start-up. When it answers, it supplies the temperature and humidity to
the phone and the detector, and the ambient temperature for the airflow
calculation; the on-board SHT40 is logged as `case_temp_c` / `case_rh_pct` on USB
serial, and the Info JSON reports `"t_src":2`. Nothing to buy or wire beyond the
blade itself, but the current blade cannot be fitted (see the top of this page).

### With a reference thermistor instead: no extra sensor

- **Temperature:** the reference bead (section 1.2) sits out in the air beside
  the sensor caps, so it reads the outside temperature directly.
- **Humidity:** warming air inside the case lowers its *relative* humidity but
  does not change how much water it holds (its *absolute* humidity). So the
  on-board SHT40 still gives the outside air's water content. The firmware takes
  that and works out the relative humidity it means at the reference bead's
  temperature.

Built with `HW_AIRFLOW_REF`, the firmware does this whenever the blade's SHT40 is
absent and the reference bead gives a sensible reading (Info JSON `"t_src":1`).
The catch: the case swaps its air with the outside slowly, so humidity changes
reach the on-board SHT40 late (probably tens of seconds; not yet measured). The
air blade has no such delay.

Without either, the firmware uses the on-board SHT40 (`"t_src":0`).

### Refit

The detector's coefficients were fitted on case-air readings, so refit after the
first surveys with outside-air readings (`python tools/replay.py fit`).

## 4. What is not known yet

- The heated bead's exact B value and heat loss (from its datasheet, or measure them, section 1.6).
- How the bead's heat loss really varies with air speed in this enclosure. The
  table in 1.3 is a physics estimate. The airflow calibration survey in
  [PROTOCOL.md](PROTOCOL.md) measures it.
- Whether the airflow index tracks the gas sensors' own airflow response closely
  enough. That is also what the airflow calibration survey is for.
- The CO module's current draw (not stated by Winsen) and its methane
  cross-sensitivity (not published).
- The board itself is made and bench-tested, but neither add-on has been
  fitted to it yet: every number above is from datasheets and calculation.
