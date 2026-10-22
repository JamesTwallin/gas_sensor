# Phone-companion board — design spec

> This is the electrical and Bluetooth spec of the board
> ([hardware/board](../hardware/board/)). The MEMS rig
> ([hardware/board_mems](../hardware/board_mems/), [mems_rig.md](mems_rig.md)) is
> the board plus a socket for the MEMS blade; where it differs, this file says
> so. The first phone-companion board (git tag `rev-b`) shared most of this
> circuit; the board's [README](../hardware/board/README.md) lists what differs
> from it.

The board moves everything a phone already does onto the phone. It keeps only
what a phone cannot do: the gas sensors, the environment sensors, and a radio.

| Job | first prototype (carrier, retired) | the board |
|---|---|---|
| MCU | ESP32-S3-Zero dev board on headers | **bare ESP32-S3-MINI-1 module**, soldered |
| Methane | NGM2611-E13 module (alarm + compensation) | **bare TGS2611-E00**, own load circuit |
| LP gas | LPM2610-D09 module | **bare TGS2610-D00**, own load circuit |
| ADC | ESP32 internal, 12-bit | **two ADS1115s, 16-bit**: gas sensors and airflow thermistor on one; heater currents and the 3.3 V rail on the other. Battery and heater-rail voltages on the ESP32's own ADC |
| Environment | BME280 breakout | **SHT40** temp + humidity chip, thermally isolated, reading the case air; a second SHT40 on the air blade reads the outside air (pressure comes from the phone's barometer) |
| Position / time | L76K GNSS | **phone** |
| Display | SSD1306 OLED | **phone** |
| Storage | microSD | **phone** (CSV export) |
| Signal processing | firmware (baseline + classifier) | **phone** (slope + spike detector), plus the board's own anomaly detector |
| Power | USB only | **1-cell LiPo** + USB-C charging |
| Link | USB serial | **BLE** (USB CDC kept for debug/flash) |

The firmware is a thin sampler: read, average, notify over BLE. Most of the
signal processing is in the app, where it is easier to tune. The app does not
use the first prototype's HIGH/MED/LOW classifier or show its percentile
baseline: the absolute level wanders too much. It monitors the slope of each
channel instead (see the CSV section below).

This file is the source of truth for the schematic generator, the firmware and
the app. Change it first.

## Why bare sensors

The NGM/LPM modules hide the sensor resistance Rs behind a thermistor-compensated
comparator circuit. With the bare element and a known load resistor, the app can
compute Rs directly and apply its own temperature/humidity compensation from the
SHT40 — the datasheet curves in [sensors.md](sensors.md) are all in terms of Rs,
so they can actually be applied.

## Power

```
USB-C VBUS ──► BQ24073 charger/power-path ──► VSYS (4.4 V on USB, VBAT on battery)
                     │ BAT ◄── Q1 AO3401A (reverse-battery P-FET) ◄──► 1S LiPo (JST-PH)
SW1 slide switch ──► PWR_EN (VSYS = on, open = off, 1M pull-down) ──► LDO EN
ESP32 GPIO7 ──► HTR_EN (100k pull-down: heaters off until firmware drives it high)
VSYS ──► TPS61023 boost (EN = HTR_EN) ──► +5V_HTR  (both TGS heaters + sensor circuits, ~115 mA)
VSYS ──► AP2112K-3.3 LDO (EN = PWR_EN) ──► +3V3    (ESP32-S3, both ADS1115s, SHT40s, LED)
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
  enabling them later alongside BLE browned the first board's ESP32 out
  (bench, 2026-09-28). The board also has 2 × 22 µF extra on VSYS (C28, C29)
  for the same reason.
- USB flashing needs SW1 ON (+3V3 is gated by it), even with no battery.
- New boards arrive with blank flash. The first flash needs the bootloader
  (hold BOOT, tap RESET, release BOOT) and a full upload.
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
+5V_HTR ── pin 1 (heater) ── pin 4 ──┬── 0.5 Ω shunt (R22 CH4, R25 LPG) ── GND
                                     └── ADS1115 #2 AINx (heater current)
+5V_HTR ── pin 3 (S+) ── pin 2 (S−) ── RLa 20k ──┬── RLb 20k ── GND
                                                  ├── 100 nF ── GND
                                                  └── ADS1115 #1 AINx
```

- The 0.5 Ω shunt in each heater return lets the second ADS1115 read the heater
  current (about 56 mA, so about 28 mV across the shunt). Fit a 0 Ω link instead
  to switch this off.

- VC = 5.0 V, the datasheet standard test condition, so sensitivity curves apply.
- RL = RLa + RLb = 40 kΩ. Clean-air Rs is roughly 12–125 kΩ (TGS2611) and
  23–230 kΩ (TGS2610) (read off Figaro's typical curves), so RL sits near the
  clean-air value, where the output is most sensitive to small changes.
- The ADC sees the tap, `V_tap = VRL / 2` ≤ 2.5 V — safe for the ADS1115 (VDD
  3.3 V).
- `Rs = RL × (VC − VRL) / VRL` with `VRL = 2 × V_tap`.
- Sensor power `Ps = VC² · Rs / (Rs + RL)²` peaks at 0.16 mW (Rs = RL), far
  under the 15 mW limit.
- The TGS elements run hot (~280 mW heater each). They sit at one end of the
  board; the SHT40 is at the other end on a tongue cut free by routed slots,
  so board warmth doesn't read as ambient temperature.

## ADS1115 #1 (U6, I2C 0x48, ADDR → GND)

| Input | Signal | Scale |
|---|---|---|
| AIN0 | CH4 tap (VRL/2) | ×2 → VRL |
| AIN1 | LPG tap (VRL/2) | ×2 → VRL |
| AIN2 | heated airflow thermistor (air blade on J3 pad 1, fed from +3V3 through R28 1k, C24 100 nF) | mV at the pin (build flag `HW_AIRFLOW`, on by default) |
| AIN3 | spare (pin 7, not connected). Optional unheated reference thermistor (`HW_AIRFLOW_REF`, [HARDWARE.md](HARDWARE.md)); on the MEMS rig, MEMS sensor A | mV at the pin |

PGA ±4.096 V (125 µV/LSB); ±2.048 V for the MEMS tap on the MEMS rig.
ALERT/RDY → GPIO10.

## ADS1115 #2 (U8, I2C 0x49, ADDR → VDD)

| Input | Signal | Scale |
|---|---|---|
| AIN0 | CH4 heater current, across R22 0.5 Ω | ÷ 0.5 Ω → mA (PGA ±0.256 V) |
| AIN1 | LPG heater current, across R25 0.5 Ω | ÷ 0.5 Ω → mA (PGA ±0.256 V) |
| AIN2 | +3V3 via R33/R34 100k/100k, C27 | ×2 → 3.3 V rail (PGA ±4.096 V) |
| AIN3 | spare; on the MEMS rig, MEMS sensor B | |

ALERT/RDY is not connected (polled over I2C). The thermistor dividers run from
+3V3, which the ADS1115 does not use as its reference, so the firmware uses the
measured rail as the thermistor supply. The heater currents and the rail go to
the USB serial log (`ch4_htr_ma`, `lpg_htr_ma`, `v3v3_mv`), not over BLE.

## ESP32 ADC

| GPIO | Signal | Scale |
|---|---|---|
| 1 | VBAT via 1M/1M (R13/R14), C13 at the pin | ×2 → VBAT (calibrate against a meter) |
| 2 | +5V_HTR via 100k/100k (R15/R16), C14 at the pin | ×2 → heater rail (fault check) |

Oversampled, eFuse-calibrated reads (`analogReadMilliVolts`).

## ESP32-S3-MINI-1-N8 pin map

| GPIO | Net | Notes |
|---|---|---|
| 0 | BOOT | tact switch to GND; reported to the app as flag bit5 (unused there for now) |
| 1 | VBAT_ADC | VBAT / 2 (ADC1) |
| 2 | HTR_ADC | +5V_HTR / 2 (ADC1) |
| 5 | CHG_N | BQ24073 CHG, open-drain, 10k pull-up to 3V3 |
| 6 | PGOOD_N | BQ24073 PGOOD, open-drain, 10k pull-up to 3V3 |
| 7 | HTR_EN | heater boost enable, 100k pull-down: drive HIGH = heaters on, low/input = off |
| 8 | I2C_SDA | 4.7k pull-up; both ADS1115s, the on-board SHT40 and the air blade (J3) |
| 9 | I2C_SCL | 4.7k pull-up |
| 10 | ADS_RDY | ADS1115 #1 ALERT/RDY, 10k pull-up |
| 12 | — | MEMS rig only: MEMS heater enable (100k pull-down, HIGH = on) |
| 19 / 20 | USB D− / D+ | USB-C, native USB (flash + debug serial) |
| 38 | LED_DIN | WS2812-class RGB status LED |
| 43 / 44 | TXD0 / RXD0 | test pads TP1 / TP2, and the CO module on J4 (`HW_CO`): module TX → J4 pin 3 (GPIO44, RX), 9600 baud; GPIO43 → R30 1k → J4 pin 4 |
| EN | EN | 10k pull-up + 1 µF, RESET switch to GND |
| 3, 45, 46 | — | strapping pins, leave unconnected |

SHT40-AD1B (on-board, case air): I2C 0x44. The air blade's SHT40 (outside air): 0x46 (SHT40-CD1B) or 0x45 (SHT40-BD1B). The current air blade cannot be fitted to J3 and is being redesigned ([hardware/board](../hardware/board/README.md)). No pressure sensor on the board: the firmware sends pressure as missing (0xFFFF) and the app should take pressure from the phone barometer where available.

## BLE protocol (v1, with the v2 additions for the MEMS rig)

Device name `CH4-XXXX` (last 2 MAC bytes). One custom service:

| | UUID |
|---|---|
| Service | `6d1a0001-8f3e-4b8a-9c57-2f6c0e3a7b10` |
| Sample (notify) | `6d1a0002-8f3e-4b8a-9c57-2f6c0e3a7b10` |
| Info (read, JSON) | `6d1a0003-8f3e-4b8a-9c57-2f6c0e3a7b10` |
| Control (write) | `6d1a0004-8f3e-4b8a-9c57-2f6c0e3a7b10` |
| Analysis (notify) | `6d1a0005-8f3e-4b8a-9c57-2f6c0e3a7b10` |
| Event (notify) | `6d1a0006-8f3e-4b8a-9c57-2f6c0e3a7b10` |
| Gas2 (notify, MEMS rig only) | `6d1a0007-8f3e-4b8a-9c57-2f6c0e3a7b10` |

Analysis and Event come from the on-board anomaly detector
(`firmware/phone_board/lib/anomaly`, explained in [REPORT.md](REPORT.md)).
Firmware 1.0.0 has neither; the app checks they exist before subscribing.

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
| 17 | u16 | vbat | mV (0 = unknown) |
| 19 | u8 | flags | bit0 USB power, bit1 charging, bit2 T/RH sensor ok, bit3 ADS ok (0 = ADS1115 #1 not answering: the taps then read 0, as there is no backup ADC), bit4 heater rail out of 4.8–5.2 V (not set while bit6 = 1), bit5 BOOT pressed (see below), bit6 heaters off (low battery: firmware drove HTR_EN low after VBAT < 3.3 V for > 10 s on battery; released when VBAT > 3.5 V or USB power is present, and never applied on USB power), bit7 reserved (0) |

**Analysis** — 20 bytes, little-endian, one per sample, sent *just before* the
Sample notification with the same `seq` (notifications keep their order, so the
app pairs them by `seq`):

| Off | Type | Field | Unit |
|---|---|---|---|
| 0 | u8 | version | = 1 |
| 1 | u16 | seq | same as the Sample it belongs to |
| 3 | i16 | ch4_res | 0.1 mV: CH4 reading minus its conditions-model prediction (the detection residual) |
| 5 | i16 | lpg_res | 0.1 mV |
| 7 | u16 | ch4_sigma | 0.01 mV: robust spread of ch4_res (0 = not yet known) |
| 9 | u16 | lpg_sigma | 0.01 mV |
| 11 | u16 | airflow_raw | mV at the thermistor pin (0 = not fitted) |
| 13 | i16 | airflow_index | 0.001 (0x8000 = missing) |
| 15 | u16 | co_raw | 0.1 ppm (0xFFFF = not fitted / no reading) |
| 17 | u8 | flags | bit0 CH4 anomaly, bit1 LPG anomaly, bit2 detector ready (warm and settled), bit3 detection suppressed (T/RH step), bit4 event open, bit5 airflow reading ok, bit6 CO reading ok, bit7 still-air calibration running |
| 18 | u8 | event_class | 0 none, 1 NATURAL_GAS, 2 EXHAUST, 3 HEAVY_HC, 4 THERMAL, 5 LOW_AIRFLOW, 6 UNRESOLVED, 7 UNCLASSIFIED. Non-zero only on the sample on which an event closes |
| 19 | u8 | event_ratio | CH4-to-LPG peak residual ratio × 10, capped at 255 (the Event packet has it exactly) |

**Event** — 20 bytes, little-endian, one notification when an event closes,
sent before that sample's Analysis packet. The full fingerprint:

| Off | Type | Field | Unit |
|---|---|---|---|
| 0 | u8 | version | = 1 |
| 1 | u16 | event_id | counts up from 1 per boot |
| 3 | u8 | class | as event_class above |
| 4 | u8 | confidence | 0–100 (a heuristic until labelled events exist) |
| 5 | u16 | duration | 0.1 s, first onset to last raised sample |
| 7 | i16 | ch4_peak | 0.1 mV, peak CH4 residual |
| 9 | i16 | lpg_peak | 0.1 mV |
| 11 | u16 | ratio | CH4-to-LPG peak residual ratio × 100 (0–99) |
| 13 | i16 | lead | 0.1 s, LPG onset minus CH4 onset: positive = CH4 led (0x8000 = not known) |
| 15 | i16 | airflow_mean | 0.001, mean airflow index during the event (0x8000 = not known) |
| 17 | i16 | co_peak | 0.1 ppm, peak CO rise above its baseline (0x8000 = not known) |
| 19 | u8 | flags | bit0 CH4 raised, bit1 LPG raised, bit2 CH4 detected, bit3 LPG detected, bit4 THERMAL step coincided, bit5 whole event at low airflow |

**Gas2** (MEMS rig only, [mems_rig.md](mems_rig.md)): 20 bytes, little-endian, one per sample, sent
*just after* the Sample notification with the same `seq`. It carries the MEMS blade's
two sensors, so the Sample, Analysis and Event packets keep their v1 layouts and older
apps keep working. The board without the MEMS socket simply has no such characteristic.

| Off | Type | Field | Unit |
|---|---|---|---|
| 0 | u8 | version | = 1 |
| 1 | u16 | seq | same as the Sample it belongs to |
| 3 | u16 | mems_a_tap | 0.1 mV at the ADC input, SY-CH4-37BPM (0xFFFF = missing) |
| 5 | u16 | mems_b_tap | 0.1 mV, MiCS-5524 (0xFFFF = missing) |
| 7 | i16 | mems_a_res | 0.1 mV, detector residual (0x7FFF = missing) |
| 9 | u16 | mems_a_sigma | 0.1 mV (0xFFFF = missing) |
| 11 | i16 | mems_b_res | 0.1 mV (0x7FFF = missing) |
| 13 | u16 | mems_b_sigma | 0.1 mV (0xFFFF = missing) |
| 15 | u8 | flags | bit0 sensor A anomaly, bit1 sensor B anomaly, bit2 blade fitted, bit3 MEMS heaters on, bit4 MEMS warm (past the 60-minute warm-up), bit5 burn-in complete |
| 16 | u16 | v3v3 | mV, the measured 3.3 V rail (0xFFFF = missing) |
| 18 | u16 | reserved | 0 |

Each MEMS sensor sits in +3V3 -> sensor -> R -> tap -> R -> GND on the blade (R = 10 k
for A, 100 k for B) with a 1 M pull-up from +3V3 to the tap on the board. So
`I1 = Vtap/R - (V3V3 - Vtap)/1M`, `VN = Vtap + R x I1` and `Rs = (V3V3 - VN)/I1`.
With no blade the pull-up takes the tap above 1.85 V, which is how the firmware knows.

**Info** — UTF-8 JSON, e.g.
`{"proto":2,"fw":"1.1.0","board":"rev-e","rl_ohm":40000,"tap_ratio":2.0,"vc_mv":5000,"interval_ms":250,"heater_mv":5012,"anomaly":1,"airflow":1,"co":0,"g_still":0}`
(`board` is `rev-e` for the board and `rev-f` for the MEMS rig: fixed ID
strings in the protocol. `vc_mv` is the nominal circuit voltage; `heater_mv` is
the latest measured rail, 0 when unknown. `anomaly` = 1 when Analysis/Event exist;
`airflow` and `co` say whether those inputs were built in; `g_still` is the
thermistor's still-air conductance in mW/K, 0 until calibrated.) Current firmware
reports `"proto":2` on every board (the packets are unchanged from 1; 2 means
"Gas2 may exist"). On the MEMS rig it adds `"mems"` (1 = blade fitted) and
`"mems_burnin_h"` (hours the MEMS heaters have run on this board).

**Control** — first byte is the opcode:

| Op | Payload | Action |
|---|---|---|
| 0x01 | u16 interval_ms (100–5000) | set sample interval |
| 0x02 | — | blink LED (identify) |
| 0x03 | u8 r, u8 g, u8 b | set status LED (the app drives green, red while CH4 is spiking) |
| 0x04 | u8 seconds (optional, default 60) | still-air calibration of the airflow thermistor: hold the board in still air (a closed box) while it runs; the result is kept in flash and reported as `g_still` |

A BOOT-button press is sent as a sample with no extra field: the firmware sets
flag **bit5** on the next sample. The app currently ignores it (it used to
re-zero the baseline).

## App CSV (backwards compatible)

The app writes the first prototype's column set unchanged, so `tools/plot_map.py` and
`tools/plot_survey.py` keep working, then appends new columns:

```
millis_since_boot,state,ch4_vout_mv,ch4_baseline_mv,ch4_dev_mv,
lpg_vout_mv,lpg_baseline_mv,lpg_dev_mv,temp_c,humidity_pct,pressure_hpa,
utc_iso8601,lat,lon,alt_m,sats,fix,
ch4_rs_ohm,lpg_rs_ohm,vbat_mv,gps_accuracy_m,ch4_ppm_est,lpg_ppm_est,
ch4_slope_mv_s,lpg_slope_mv_s,spike,
airflow_raw,airflow_index,co_raw,ch4_res_mv,lpg_res_mv,ch4_sigma_mv,lpg_sigma_mv,
anomaly_ch4,anomaly_lpg,event_class,event_ratio,event_fingerprint
```

- The last twelve columns are the board's Analysis packet for that sample
  (blank when the firmware has no detector, or the packet did not arrive).
  `event_class` / `event_ratio` are filled only on the row where an event
  closed, and `event_fingerprint` then carries the whole Event packet as
  `key=value` pairs separated by `;`. `spike` is the old slope detector, kept
  for comparison.

- `*_baseline_mv` / `*_dev_mv` are kept only so the plotting tools keep
  working: the first prototype's 15th percentile of the last 2 min, fixed. The app neither
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
  (higher = more gas), different absolute scale from the first prototype's modules.
- `utc_iso8601`, `lat`, `lon`, `alt_m` come from the phone. `sats` is blank
  (phones don't expose it); `fix` is 1 when horizontal accuracy ≤ 25 m.
- `millis_since_boot` is the board's `ms_since_boot`; `utc_iso8601` is the phone
  clock when the sample arrived. `lat`/`lon`/`alt_m`/`gps_accuracy_m` are the
  latest phone fix; `fix` is also 0 if that fix is more than 10 s old.
- `state` can also be `HEATER_OFF` (flag bit6). The tools only keep `RUNNING`.
- `tools/plot_map.py` applies its minimum-satellite filter only to rows that
  have a `sats` value (first-prototype logs); phone rows rely on `fix`.

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
- The first prototype works too (its CSV is mapped to VRL / 2 with `tap_ratio` 2.0).

Real BLE needs a development build: `npx expo run:android` with the phone on
USB debugging, or `eas build --profile development`.
