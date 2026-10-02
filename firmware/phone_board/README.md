# Phone-companion board firmware

Firmware for the rev B and rev C boards, which share one circuit
([hardware/phone_board](../../hardware/phone_board/)). It is a thin sampler:
it reads the two gas sensor taps, battery voltage and heater rail on the
ADS1115 and temperature/humidity on the SHT40, averages over the sample
interval (250 ms by default), and sends one 20-byte Bluetooth notification per
interval to the [phone app](../../app/). The same sample is printed as a CSV
line on USB serial for bench work. All signal processing happens in the app.

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

The power switch must be ON to flash (it gates the 3.3 V rail). If the board
does not enumerate, hold **BOOT**, tap **RESET**, release **BOOT** and retry.
Library versions are pinned in [platformio.ini](platformio.ini).

The board advertises as `CH4-XXXX` (the last two bytes of its Bluetooth
address) and reports its board type as `rev-b` on both layouts. The rev D draft board needs changed constants that are not written
yet; see [its README](../../hardware/phone_board_mems/README.md).
