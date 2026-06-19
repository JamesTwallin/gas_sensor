# Carrier-board connection spec (rev A)

The electrical specification for the first PCB: a **carrier board** that the
ESP32-S3-Zero and every sensor module plug into, replacing the breadboard. Every
active part stays a pre-made breakout on headers; the only components actually
soldered to the board are the two resistor dividers (and optional decoupling /
pull-ups). This document is the source of truth for the schematic — the
`.kicad_sch` is captured from the nets listed here.

It is derived directly from the firmware pin map in
[../src/main.cpp](../src/main.cpp) and the hardware table in the
[../README.md](../README.md). If the firmware pin assignments change, change them
here too.

## Design intent

- **Nothing fine-pitch.** The S3-Zero and all sensors are modules on 2.54 mm
  headers. No bare ICs, no USB, no flash on this board.
- **Two power rails + ground.** A **5 V** rail (Figaro heaters) and a **3V3** rail
  (everything digital), both sourced from the S3-Zero, plus a common GND.
- **The dividers are the only real circuit.** Each Figaro VOUT can reach ~4.95 V;
  a 10k/10k divider halves it to a safe ~2.5 V before it reaches a 3.3 V ADC pin.
- **rev A is a learning board.** Expect to socket, test, and respin.

## Reference designators

| Ref | Part | Plugs in as | Notes |
|---|---|---|---|
| U1 | Waveshare ESP32-S3-Zero | module on female headers | the MCU; sources both rails |
| U2 | Figaro NGM2611-E13 (CH4) | 5-pin module | methane; VOUT → divider → GPIO1 |
| U3 | Figaro LPM2610-D09 (LPG) | 5-pin module | LP gas; VOUT → divider → GPIO2 |
| U4 | SSD1306 128x64 OLED | 4-pin I2C module | addr 0x3C |
| U5 | DFRobot Gravity GNSS (L76K) | Gravity / 4-pin module | addr 0x20, I2C mode |
| U6 | Bosch BME280 | 4- or 6-pin I2C module | addr 0x76 |
| U7 | Fermion microSD module | 6-pin SPI module | own SPI bus |
| R1, R2 | 10 kΩ resistor | soldered | CH4 divider (R1 series, R2 to GND) |
| R3, R4 | 10 kΩ resistor | soldered | LPG divider (R3 series, R4 to GND) |
| C1, C2 | 10 µF + 100 nF (optional) | soldered | bulk + HF decoupling on 5 V rail |
| R5, R6 | 4.7 kΩ (optional) | soldered | I2C pull-ups, only if modules' own are removed |

## Power rails

| Rail | Source | Loads |
|---|---|---|
| **+5V** | U1 `5V` pin (live only when USB-powered) | U2 VIN, U3 VIN |
| **+3V3** | U1 `3V3` pin | U4, U5, U6, U7 VCC |
| **GND** | U1 `GND` | every module GND, R2, R4, divider bottoms |

> **Warning:** the S3-Zero's `5V` pin only carries 5 V when the board is powered
> over its USB port. If you ever power the board through the `3V3` pin instead, the
> Figaro heaters get nothing and the survey silently fails. rev A assumes USB power.

## The divider sub-circuit (×2)

Each Figaro module's conditioned VOUT is halved before it reaches the ADC:

```
   U2 VOUT (CH4) ──[ R1 10k ]──┬──[ R2 10k ]── GND
                               │
                               └──────────────── U1 GPIO1   (net CH4_ADC)

   U3 VOUT (LPG) ──[ R3 10k ]──┬──[ R4 10k ]── GND
                               │
                               └──────────────── U1 GPIO2   (net LPG_ADC)
```

The midpoint is VOUT/2 (~2.5 V at the factory alarm level, well under the 3.3 V
pin limit). The firmware multiplies by `VOUT_DIVIDER_RATIO = 2.0` to recover the
real VOUT, and warns if a pin reads near its ceiling — the signature of a missing
or open divider feeding raw VOUT to the pin. Keep R1–R4 physically close to U1's
ADC pins.

## Connections, by component (pin → net)

### U1 — ESP32-S3-Zero
Only the pins the firmware uses are listed; all others are left unconnected on
rev A (but bring the free ones to a spare header — see Notes).

| U1 pin | Net | Goes to |
|---|---|---|
| 5V | +5V | rail (from USB) → U2/U3 VIN |
| 3V3 | +3V3 | rail → U4/U5/U6/U7 VCC |
| GND | GND | common ground |
| GPIO1 | CH4_ADC | R1/R2 divider midpoint |
| GPIO2 | LPG_ADC | R3/R4 divider midpoint |
| GPIO6 | I2C_SDA | U4 SDA, U5 D/T, U6 SDA |
| GPIO7 | I2C_SCL | U4 SCL, U5 C/R, U6 SCL |
| GPIO10 | SD_CS | U7 CS |
| GPIO11 | SD_MOSI | U7 MOSI |
| GPIO12 | SD_SCK | U7 SCK |
| GPIO13 | SD_MISO | U7 MISO |

GPIO0 (BOOT/re-zero) and GPIO21 (WS2812 status LED) are **onboard the S3-Zero** —
no external wiring.

### U2 — NGM2611-E13 (methane, CH4)
| U2 pin | Net | Notes |
|---|---|---|
| 1 VIN | +5V | heater + element |
| 2 VOUT | CH4_VOUT | → R1 |
| 3 VREF | — | leave unconnected |
| 4 VH− | GND | heater return |
| 5 GND | GND | |

### U3 — LPM2610-D09 (LP gas, LPG)
| U3 pin | Net | Notes |
|---|---|---|
| 1 VIN | +5V | |
| 2 VOUT | LPG_VOUT | → R3 |
| 3 VREF | — | leave unconnected |
| 4 VH− | GND | |
| 5 GND | GND | |

### U4 — SSD1306 OLED (0x3C)
| U4 pin | Net |
|---|---|
| VCC | +3V3 |
| GND | GND |
| SCL | I2C_SCL |
| SDA | I2C_SDA |

### U5 — DFRobot Gravity GNSS L76K (0x20)
Pads are dual-labelled (I2C vs UART); driving I2C selects it.
| U5 pad | Net | Notes |
|---|---|---|
| + | +3V3 | accepts 3.3–5.5 V |
| − | GND | |
| C/R | I2C_SCL | SCL in I2C mode |
| D/T | I2C_SDA | SDA in I2C mode |

### U6 — BME280 (0x76)
| U6 pin | Net | Notes |
|---|---|---|
| VCC / VIN | +3V3 | |
| GND | GND | |
| SCL | I2C_SCL | |
| SDA | I2C_SDA | |
| CSB | +3V3 | 6-pin boards only: ties to 3V3 to select I2C |
| SDO | GND | 6-pin boards only: ties to GND for addr 0x76 |

### U7 — Fermion microSD module
3.3 V card — VCC to +3V3, **not** 5 V.
| U7 pin | Net |
|---|---|
| VCC | +3V3 |
| GND | GND |
| SCK | SD_SCK |
| MISO | SD_MISO |
| MOSI | SD_MOSI |
| CS | SD_CS |

## Net list (net → pins)

| Net | Connected pins |
|---|---|
| +5V | U1.5V, U2.1, U3.1 (+ C1/C2 if fitted) |
| +3V3 | U1.3V3, U4.VCC, U5.+, U6.VCC, U6.CSB |
| GND | U1.GND, U2.4, U2.5, U3.4, U3.5, U4.GND, U5.−, U6.GND, U6.SDO, U7.GND, R2, R4 |
| I2C_SDA | U1.GPIO6, U4.SDA, U5.D/T, U6.SDA |
| I2C_SCL | U1.GPIO7, U4.SCL, U5.C/R, U6.SCL |
| CH4_VOUT | U2.2, R1 |
| CH4_ADC | U1.GPIO1, R1, R2 |
| LPG_VOUT | U3.2, R3 |
| LPG_ADC | U1.GPIO2, R3, R4 |
| SD_SCK | U1.GPIO12, U7.SCK |
| SD_MISO | U1.GPIO13, U7.MISO |
| SD_MOSI | U1.GPIO11, U7.MOSI |
| SD_CS | U1.GPIO10, U7.CS |

## Bill of materials (electrical)

| Qty | Item | Value / part | Notes |
|---|---|---|---|
| 1 | ESP32-S3-Zero | Waveshare ESP32-S3FH4R2 | socketed |
| 1 | Methane module | Figaro NGM2611-E13 | 5 V |
| 1 | LP-gas module | Figaro LPM2610-D09 | 5 V |
| 1 | OLED | SSD1306 128x64 I2C 0x3C | 3V3 |
| 1 | GNSS | DFRobot Gravity L76K | 3V3, I2C |
| 1 | Environment | Bosch BME280 0x76 | 3V3, I2C |
| 1 | microSD | Fermion microSD module | 3V3, SPI |
| 4 | Resistor | 10 kΩ 1% | R1–R4, the two dividers |
| 1 | Bulk cap | 10 µF | optional, 5 V rail |
| 1 | HF cap | 100 nF | optional, 5 V rail |
| 2 | Resistor | 4.7 kΩ | optional I2C pull-ups (see Notes) |
| — | Headers | 2.54 mm female | one socket per module |

## Notes / gotchas for layout

1. **I2C pull-ups.** SDA/SCL need one pair of pull-ups. Most of U4/U5/U6 carry
   their own, so with three modules you may have three sets in parallel (~1.6k if
   all 4.7k) — usually fine, occasionally too low. If the bus misbehaves, remove
   the pull-ups on two of the modules and fit R5/R6 (4.7k) on the carrier as the
   single set. Leave R5/R6 footprints unpopulated by default.
2. **Heater current.** U2/U3 heaters draw real continuous current on +5V. Make the
   +5V traces wider than signal traces and confirm the USB source can supply both.
3. **Divider placement.** Keep R1–R4 right at U1's GPIO1/GPIO2 pins.
4. **Bring out the free GPIOs.** GPIO4, GPIO5, GPIO8, GPIO9, GPIO14–18 are unused —
   route them to a spare header so the throwaway rev can still grow.
5. **No silicone near the Figaro sensors** — it poisons the element irreversibly
   (see [sensors.md](sensors.md)). Affects enclosure/adhesive choice, not copper.
6. **5V comes from USB only** — see the rail warning above.
