# Phone-companion board (rev B / C) — design spec

> **Rev C (`hardware/phone_board`) is the current design.** It is rev B
> compacted from 66 × 36 to 60 × 33 mm with the same schematic, parts and pin
> map, so everything electrical below applies to both. Rev B is the layout that
> was fabricated and bench-tested (git tag `rev-b`); where this document says
> "rev B" it means the circuit the two share.
> Rev D (`hardware/phone_board_mems`, draft) swaps the Figaro cans for Winsen
> GM-402B MEMS sensors on a 2.8 V LDO heater rail; its README lists what that
> changes in the sensor loop, the heater monitor and the firmware constants.

Rev B moves everything a phone already does onto the phone. The board keeps only
what a phone cannot do: the gas sensors, the environment sensor, and a radio.

| Job | rev A (carrier, retired) | rev B / C (this) |
|---|---|---|
| MCU | ESP32-S3-Zero dev board on headers | **bare ESP32-S3-MINI-1 module**, soldered |
| Methane | NGM2611-E13 module (alarm + compensation) | **bare TGS2611-E00**, own load circuit |
| LP gas | LPM2610-D09 module | **bare TGS2610-D00**, own load circuit |
| ADC | ESP32 internal, 12-bit | **ADS1115 16-bit** (ESP32 ADC fallback via hand-fitted R22/R25) |
| Environment | BME280 breakout | **SHT40** temp + humidity chip, thermally isolated (pressure comes from the phone's barometer) |
| Position / time | L76K GNSS | **phone** |
| Display | SSD1306 OLED | **phone** |
| Storage | microSD | **phone** (CSV export) |
| Signal processing | firmware (baseline + classifier) | **phone** (slope + spike detector) |
| Power | USB only | **1-cell LiPo** + USB-C charging |
| Link | USB serial | **BLE** (USB CDC kept for debug/flash) |

The firmware becomes a thin sampler: read, average, notify over BLE. The signal
processing moves to the app, where it is easier to tune. The app does not carry
over rev A's HIGH/MED/LOW classifier or show its percentile baseline: the
absolute level wanders too much. It monitors the slope of each channel instead
(see the CSV section below).

This file is the source of truth for the schematic generator, the firmware and
the app. Change it first.

## Why bare sensors

The NGM/LPM modules hide the sensor resistance Rs behind a thermistor-compensated
comparator circuit. With the bare element and a known load resistor, the app can
compute Rs directly and apply its own temperature/humidity compensation from the
SHT40 — the datasheet curves in [sensors.md](sensors.md) are all in terms of Rs,
so this is the first build where they can actually be applied.

## Power

```
USB-C VBUS ──► BQ24073 charger/power-path ──► VSYS (4.4 V on USB, VBAT on battery)
                     │ BAT ◄── Q1 AO3401A (reverse-battery P-FET) ◄──► 1S LiPo (JST-PH)
SW1 slide switch ──► PWR_EN (VSYS = on, open = off, 1M pull-down) ──► LDO EN
ESP32 GPIO7 ──► HTR_EN (100k pull-down: heaters off until firmware drives it high)
VSYS ──► TPS61023 boost (EN = HTR_EN) ──► +5V_HTR  (both TGS heaters + sensor circuits, ~115 mA)
VSYS ──► AP2112K-3.3 LDO (EN = PWR_EN) ──► +3V3    (ESP32-S3, ADS1115, SHT40, LED)
```

- Heaters want 5.0 V ± 0.2 V; VSYS never exceeds 4.4 V, so a plain boost is enough.
  The TPS61023 truly disconnects its output when disabled.
- The power switch only carries logic current: it switches the regulator enables.
  Off still charges the battery (the BQ24073 has no SYSOFF pin, so its
  battery-to-OUT FET stays on). Off-state drain is < 10 µA: BQ24073 sleep ~5 µA
  plus the 1M/1M VBAT divider ~2 µA. SW1's third throw is left open, so the
  switch can never short VSYS to GND mid-travel.
- Heaters are firmware-controlled: GPIO7 must drive HTR_EN high after boot (and
  low for the low-battery cutoff). Until then the 100k pull-down keeps them off,
  so there is no heater inrush during boot and a firmware crash fails safe.
  The firmware drives it high as the first thing in `setup()`, with the CPU at
  80 MHz and before the radio starts: on USB power with no cell fitted, the
  USB500 input limit is marginal for the boost start-up into cold heaters, and
  enabling them later alongside BLE browned the ESP32 out (bench, 2026-09-28).
- USB flashing needs SW1 ON (+3V3 is gated by it).
- There is no deep-discharge cutoff on the board: **use a cell with a built-in
  protection circuit (PCM)**, and have the firmware sleep on low battery.
- Budget: heaters ~2 × 280 mW + ESP32 BLE ~60 mW avg ≈ 0.65 W → ~5 h on 1000 mAh.
- Charger: EN2 = 0, EN1 = 1 (100k from VBUS) → USB500 input limit; ISET 1.8 kΩ → ~500 mA charge;
  TS has a fixed 10 kΩ (no NTC); TMR open → default safety timers.
- Battery JST-PH: pin 1 = −, pin 2 = + (Adafruit/SparkFun convention). **Check
  your cell's polarity before plugging in.** Q1 protects against a reversed cell
  (the board just won't power), but the cell still won't work until swapped.

## Gas sensor circuit (×2)

Figaro TGS2611-E00 (CH4) / TGS2610-D00 (LPG): heater between pins 1 and 4,
sensing electrodes 2 (−) and 3 (+). Not stocked at LCSC — hand-solder.

```
+5V_HTR ── pin 1 (heater) ── pin 4 ── GND
+5V_HTR ── pin 3 (S+) ── pin 2 (S−) ── RLa 20k ──┬── RLb 20k ── GND
                                                  ├── 100 nF ── GND
                                                  ├── ADS1115 AINx
                                                  └── 1k (NOT FITTED) ── ESP32 GPIO (fallback)
```

- VC = 5.0 V, the datasheet standard test condition, so sensitivity curves apply.
- RL = RLa + RLb = 40 kΩ. Clean-air Rs is roughly 12–125 kΩ (TGS2611) and
  23–230 kΩ (TGS2610) (read off Figaro's typical curves), so RL sits near the
  clean-air value, where the output is most sensitive to small changes.
- The ADC sees the tap, `V_tap = VRL / 2` ≤ 2.5 V — safe for the ADS1115 (VDD
  3.3 V) and the ESP32.
- `Rs = RL × (VC − VRL) / VRL` with `VRL = 2 × V_tap`.
- Sensor power `Ps = VC² · Rs / (Rs + RL)²` peaks at 0.16 mW (Rs = RL), far
  under the 15 mW limit.
- The TGS elements run hot (~280 mW heater each). They sit at one end of the
  board; the SHT40 is at the other end on a tongue cut free by routed slots,
  so board warmth doesn't read as ambient temperature.

## ADS1115 (I2C 0x48, ADDR → GND)

| Input | Signal | Scale |
|---|---|---|
| AIN0 | CH4 tap (VRL/2) | ×2 → VRL |
| AIN1 | LPG tap (VRL/2) | ×2 → VRL |
| AIN2 | VBAT via 1M/1M | ×2 → VBAT (reads a few % low: calibrate) |
| AIN3 | +5V_HTR via 100k/100k | ×2 → heater rail (fault check) |

PGA ±4.096 V (125 µV/LSB). ALERT/RDY → GPIO10.

## ESP32-S3-MINI-1-N8 pin map

| GPIO | Net | Notes |
|---|---|---|
| 0 | BOOT | tact switch to GND; reported to the app as flag bit5 (unused there for now) |
| 1 | CH4_ADC_FB | fallback read of CH4 tap via R22 1k (ADC1) — R22 not fitted by default |
| 2 | LPG_ADC_FB | fallback read of LPG tap via R25 1k (ADC1) — R25 not fitted by default |
| 5 | CHG_N | BQ24073 CHG, open-drain, 10k pull-up to 3V3 |
| 6 | PGOOD_N | BQ24073 PGOOD, open-drain, 10k pull-up to 3V3 |
| 7 | HTR_EN | heater boost enable, 100k pull-down: drive HIGH = heaters on, low/input = off |
| 8 | I2C_SDA | 4.7k pull-up; SHT40 + ADS1115 |
| 9 | I2C_SCL | 4.7k pull-up |
| 10 | ADS_RDY | ADS1115 ALERT/RDY, 10k pull-up |
| 19 / 20 | USB D− / D+ | USB-C, native USB (flash + debug serial) |
| 38 | LED_DIN | WS2812-class RGB status LED |
| 43 / 44 | TXD0 / RXD0 | test pads |
| EN | EN | 10k pull-up + 1 µF, RESET switch to GND |
| 3, 45, 46 | — | strapping pins, leave unconnected |

SHT40-AD1B: I2C 0x44. No pressure sensor on the board: the firmware sends pressure as missing (0xFFFF) and the app should take pressure from the phone barometer where available.

## BLE protocol (v1)

Device name `CH4-XXXX` (last 2 MAC bytes). One custom service:

| | UUID |
|---|---|
| Service | `6d1a0001-8f3e-4b8a-9c57-2f6c0e3a7b10` |
| Sample (notify) | `6d1a0002-8f3e-4b8a-9c57-2f6c0e3a7b10` |
| Info (read, JSON) | `6d1a0003-8f3e-4b8a-9c57-2f6c0e3a7b10` |
| Control (write) | `6d1a0004-8f3e-4b8a-9c57-2f6c0e3a7b10` |

**Sample** — 20 bytes, little-endian, one notification per sample (default every 250 ms), fits the default 23-byte ATT MTU:

| Off | Type | Field | Unit |
|---|---|---|---|
| 0 | u8 | version | = 1 |
| 1 | u16 | seq | wraps |
| 3 | u32 | ms_since_boot | ms |
| 7 | u16 | ch4_tap | 0.1 mV at ADC input (VRL/2) |
| 9 | u16 | lpg_tap | 0.1 mV |
| 11 | i16 | temp | 0.01 °C (0x8000 = missing) |
| 13 | u16 | humidity | 0.01 %RH (0xFFFF = missing) |
| 15 | u16 | pressure | 0.1 hPa (0xFFFF = missing) |
| 17 | u16 | vbat | mV (0 = unknown: VBAT is only wired to the ADS1115) |
| 19 | u8 | flags | bit0 USB power, bit1 charging, bit2 T/RH sensor ok, bit3 ADS ok (0 = taps came from ESP32 fallback ADC), bit4 heater rail out of 4.8–5.2 V (only checked when bit3 = 1, not set while bit6 = 1), bit5 BOOT pressed (see below), bit6 heaters off (low battery: firmware drove HTR_EN low after VBAT < 3.3 V for > 10 s on battery; released when VBAT > 3.5 V or USB power is present, and never applied on USB power), bit7 reserved (0) |

**Info** — UTF-8 JSON, e.g.
`{"proto":1,"fw":"1.0.0","board":"rev-b","rl_ohm":40000,"tap_ratio":2.0,"vc_mv":5000,"interval_ms":250,"heater_mv":5012}`
(`vc_mv` is the nominal circuit voltage; `heater_mv` is the latest measured
rail, 0 when the ADS1115 is absent.)

**Control** — first byte is the opcode:

| Op | Payload | Action |
|---|---|---|
| 0x01 | u16 interval_ms (100–5000) | set sample interval |
| 0x02 | — | blink LED (identify) |
| 0x03 | u8 r, u8 g, u8 b | set status LED (the app drives green, red while CH4 is spiking) |

A BOOT-button press is sent as a sample with no extra field: the firmware sets
flag **bit5** on the next sample. The app currently ignores it (it used to
re-zero the baseline).

## App CSV (backwards compatible)

The app writes the rev A column set unchanged, so `tools/plot_map.py` and
`tools/plot_survey.py` keep working, then appends new columns:

```
millis_since_boot,state,ch4_vout_mv,ch4_baseline_mv,ch4_dev_mv,
lpg_vout_mv,lpg_baseline_mv,lpg_dev_mv,temp_c,humidity_pct,pressure_hpa,
utc_iso8601,lat,lon,alt_m,sats,fix,
ch4_rs_ohm,lpg_rs_ohm,vbat_mv,gps_accuracy_m,ch4_ppm_est,lpg_ppm_est,
ch4_slope_mv_s,lpg_slope_mv_s,spike
```

- `*_baseline_mv` / `*_dev_mv` are kept only so the plotting tools keep
  working: the rev A 15th percentile of the last 2 min, fixed. The app neither
  shows nor acts on them.
- `ch4_slope_mv_s` / `lpg_slope_mv_s` are the first derivative of VRL over the
  app's spike window (default 1 s), and `spike` is `CH4`, `LPG`, `CH4+LPG` or
  blank: the app's plume indicator (`app/src/core/spike.ts`; the threshold is a
  fixed mV/s setting, 25 by default, whereas `tools/plot_spike.py` scales its
  own to the noise). A plume is a rising edge; slow drift is not.
- `ch4_ppm_est` / `lpg_ppm_est` are the app's datasheet-curve estimates
  (`app/src/core/ppm.ts`: Rs/Ro power law with the Table 1 temperature and
  humidity correction, LPG referenced to iso-butane). They are only as good as
  Ro: datasheet-typical until the board is calibrated in a known gas from the
  app's Settings, so treat them as indicative. Blank when Rs is unknown.

- `*_vout_mv` is now VRL (sensor load voltage) — same direction as before
  (higher = more gas), different absolute scale from the rev A modules.
- `utc_iso8601`, `lat`, `lon`, `alt_m` come from the phone. `sats` is blank
  (phones don't expose it); `fix` is 1 when horizontal accuracy ≤ 25 m.
- `millis_since_boot` is the board's `ms_since_boot`; `utc_iso8601` is the phone
  clock when the sample arrived. `lat`/`lon`/`alt_m`/`gps_accuracy_m` are the
  latest phone fix; `fix` is also 0 if that fix is more than 10 s old.
- `state` can also be `HEATER_OFF` (flag bit6). The tools only keep `RUNNING`.
- `tools/plot_map.py` applies its minimum-satellite filter only to rows that
  have a `sats` value (rev A logs); phone rows rely on `fix`.

## Bench: USB bridge for Expo Go

Expo Go cannot load `react-native-ble-plx`, so a phone running the app from
`npx expo start --go` has no Bluetooth. For bench work the board can instead be
plugged into a PC and relayed over Wi-Fi by [tools/serial_bridge.py](../tools/serial_bridge.py),
which turns the firmware's serial CSV back into protocol-v1 Sample packets:

```
python tools/serial_bridge.py            # needs pyserial; PlatformIO's python has it
```

- `http://<pc>:8765/` is a live read-out page; `ws://<pc>:8765/ws` carries the
  packets (binary) and the Info JSON (text) to the app.
- In Expo Go the app uses the bridge automatically, defaulting to the PC that
  served the JS bundle. A dev build keeps BLE unless **Settings → USB bridge via
  PC** is on; **Bridge PC address** overrides the host.
- Control opcodes (interval, LED) are dropped: the serial link is one-way.
- Rev A boards work too (their CSV is mapped to VRL / 2 with `tap_ratio` 2.0).

Real BLE needs a development build: `npx expo run:android` with the phone on
USB debugging, or `eas build --profile development`.
