# Phone-companion board firmware

Firmware for the phone-companion board
([hardware/board](../../hardware/board/)) and the MEMS rig
([hardware/board_mems](../../hardware/board_mems/)). It does not support the first
board (git tag `rev-b`) any more. It is a thin sampler:
it reads the two gas sensor taps, battery voltage and heater rail on the
ADS1115 and temperature/humidity on the SHT40, averages over the sample
interval (250 ms by default), and sends one 20-byte Bluetooth notification per
interval to the [phone app](../../app/). The same sample is printed as a CSV
line on USB serial for bench work.

From firmware 1.1.0 the board also runs a gas anomaly detector
([lib/anomaly](lib/anomaly/)): it predicts what each gas sensor should read from
temperature and humidity, and flags readings well above that prediction. Its
results go to the app on two extra Bluetooth characteristics and are logged in
the survey CSV. [docs/REPORT.md](../../docs/REPORT.md) explains how it works and
how it was tuned; every setting is in
[lib/anomaly/anomaly_config.h](lib/anomaly/anomaly_config.h). The same C code is
replayed against logged surveys by [tools/replay.py](../../tools/replay.py).

Two optional add-on sensors, an airflow thermistor and a CO sensor, are switched
on with build flags; [docs/HARDWARE.md](../../docs/HARDWARE.md) has the parts and
wiring.

[docs/phone_board.md](../../docs/phone_board.md) is the source of truth for the
pin map, the Bluetooth protocol and the packet layout; the header comment of
[src/main.cpp](src/main.cpp) explains how the sampling, the heater control and
the low-battery cutoff work.

## Build and flash

With [PlatformIO](https://platformio.org/) installed, from the repository root:

```
pio run -d firmware/phone_board                    # build
pio run -d firmware/phone_board --target upload    # flash over USB-C
pio device monitor -d firmware/phone_board         # serial output, 115200
```

There are two build targets: `board` (the default) and `board_mems` for the MEMS
rig (it sets `HW_MEMS`; see [below](#mems-rig)). Library versions are pinned in
[platformio.ini](platformio.ini).

The power switch must be ON to flash, even on USB: it gates the 3.3 V supply.

### First upload to a new board

New boards arrive with blank flash, so the first upload needs the chip put into
its download mode by hand:

1. Switch the board ON and plug in USB-C.
2. Hold **BOOT**, tap **RESET**, then let go of **BOOT**.
3. Run a full upload: `pio run -d firmware/phone_board -t upload`. Don't use
   `-t nobuild` for this one: it skips the bootloader, and a blank board needs it.
4. Press **RESET** when the upload finishes. The board then starts the firmware.

After that, plain uploads work without the buttons. If the board ever stops
showing up on USB, do steps 2–4 again.

The board advertises as `CH4-XXXX` (the last two bytes of its Bluetooth
address) and reports its board type as `rev-e`.

## MEMS rig

The MEMS rig ([hardware/board_mems](../../hardware/board_mems/)) is the board plus
a small plug-in "blade" on J5 carrying two extra gas sensors: a Saiya
SY-CH4-37BPM methane sensor (`mems_a`, LCSC C22363924) and an Amphenol SGX
MiCS-5524 (`mems_b`, LCSC C3659348), which reacts to CO, hydrogen and alcohol and
only weakly to methane. Build and flash it with its own environment:

```
pio run -d firmware/phone_board -e board_mems --target upload
```

It reports its board type as `rev-f`. What it does differently:

- At power-up, with the blade's heaters still off, it checks whether a blade is
  plugged in (with no blade both sensor inputs read near 3.3 V; with one they
  read well under 1.85 V). It keeps checking on every sample.
- The blade's heaters (GPIO12) come on 5 seconds after the main sensors' heaters,
  and only when a blade is fitted. They go off with the low-battery cutoff and come
  back 5 seconds after the main heaters do.
- The anomaly detector ignores the blade for the first hour after its heaters come
  on (the methane sensor's maker asks for at least 60 minutes).
- The total heater-on time is remembered across power cycles. Until it reaches 48
  hours the sensors are still settling ("burn-in"); their readings are still logged
  and checked, and the app is told.
- The detector watches all four sensors, each on its own.
- The blade's readings go to the app on an extra Bluetooth characteristic
  ("Gas2") and are added as 11 extra columns at the end of the USB serial CSV
  line. Older boards and older apps are unaffected.

The warm-up, burn-in and heater delay are `MEMS_WARMUP_MS`, `MEMS_BURNIN_H` and
`MEMS_STAGGER_MS` near the top of [src/main.cpp](src/main.cpp).
