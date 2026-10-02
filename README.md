# Atmospheric methane detector

A handheld instrument for finding methane on walking surveys. A small board
carries two Figaro metal-oxide gas sensors and streams raw readings over
Bluetooth to a phone app; the phone supplies the screen, the GPS position and
the storage, and logs a geotagged CSV. Python tools turn those logs into maps
and videos. The longer-term aim is to tell fossil from biogenic sources using
the two sensor channels.

This is a citizen-science build, not a product. It finds plumes; it does not
measure concentration.

<p align="center">
  <img src="hardware/phone_board/preview/render_top.png" alt="Render of the rev C board: ESP32-S3 module on the left, the two Figaro sensor positions on the right edge" height="300">
  <img src="hardware/enclosure/build/v2_assembly.png" alt="Render of the two-part printed enclosure with the board and battery inside" height="300">
</p>

## Which version to use

**Rev C is the current design.** Build that one, with the firmware in
[firmware/phone_board](firmware/phone_board/) and the phone app in [app](app/).

| Rev | Where | What | State |
|---|---|---|---|
| **C** | [hardware/phone_board](hardware/phone_board/) | 60 × 33 mm board: bare ESP32-S3 module, two bare Figaro sensors, LiPo charging, BLE to the phone app | **current design**; this layout has not been fabricated yet |
| B | git tag [`rev-b`](https://github.com/JamesTwallin/gas_sensor/tree/rev-b/hardware/phone_board) | the same circuit on a 66 × 36 mm board | built and bench-tested 2026-09-28; superseded by rev C |
| D | [hardware/phone_board_mems](hardware/phone_board_mems/) | rev C with cheaper Winsen MEMS sensors, 55 × 31 mm | draft, nothing built |
| A | [legacy/rev_a](legacy/rev_a/) | first prototype: dev board and sensor modules on a carrier, with its own OLED, GNSS and microSD | retired |

Rev C keeps rev B's schematic, parts and pin map and only shrinks and rearranges
the board, so the rev B test results, the firmware and the app apply to it
unchanged. What has been proven on real hardware so far is rev B: USB flashing,
both gas channels, the temperature/humidity sensor, the heater rail and the
Bluetooth link to the app. Battery operation and the low-battery cutoff have not
been exercised yet.

## How it works

- **The board** only samples. Every 250 ms it sends the two sensor voltages,
  temperature, humidity, battery voltage and status flags as one Bluetooth
  notification. Electrical design, pin map and the Bluetooth protocol are in
  [docs/phone_board.md](docs/phone_board.md).
- **The app** watches the slope of each sensor's voltage. These sensors drift
  with temperature, humidity and airflow, so the absolute level means little;
  walking into a plume shows up as a sharp rise, and the app flags it. It also
  records the survey CSV with the phone's GPS position on every row. See
  [app/README.md](app/README.md).
- **The tools** render the CSVs: a satellite map coloured by reading, and a
  scrolling video of the survey.

Sensor behaviour, and why absolute ppm is only indicative, is covered in
[docs/sensors.md](docs/sensors.md).

## Getting started

1. **Board.** Order from the files in
   [hardware/phone_board/production](hardware/phone_board/production/); the
   [board README](hardware/phone_board/README.md) covers JLCPCB ordering, the
   two sensors you solder yourself, battery polarity and first power-up.
2. **Firmware.** With [PlatformIO](https://platformio.org/) installed, from the
   repository root:

   ```
   pio run -d firmware/phone_board                    # build
   pio run -d firmware/phone_board --target upload    # flash over USB-C
   ```

   If the board is not found, hold **BOOT**, tap **RESET**, release **BOOT** and
   retry.
3. **App.** On Android, scan the code below (or use the
   [direct link](https://expo.dev/artifacts/eas/GfUwoBCFfugQeaA97EXnztzByZKVXR2_-AvwwxxLo4k.apk))
   to download the preview build of 2026-10-02 as an APK; the phone will ask you
   to allow installing from an unknown source. To build it yourself, or for iOS,
   see [app/README.md](app/README.md). The app includes a simulated board, so
   you can try it with no hardware.

   <img src="docs/images/android-app-qr.png" alt="QR code linking to the Android APK of the CH4 Survey app" width="220">

   The download is hosted by Expo and is removed after their retention period;
   if the code no longer works, build the app from source.
4. **Enclosure (optional).** The printed case is in
   [hardware/enclosure](hardware/enclosure/). It currently fits the rev B board;
   a rev C version has not been made yet.
5. **Survey.** Power the board, connect from the app, tap Record and walk. New
   sensors need several days powered before their readings settle.

## Analysis tools

The scripts in [tools/](tools/) read survey CSVs from `tools/data/`:

- **[plot_map.py](tools/plot_map.py)** → `tools/maps/<name>.png`: the GPS track
  over a satellite basemap, each point coloured by sensor reading. `--combine`
  pools several logs; `--diff` maps the CH4/LPG differential.
- **[plot_survey.py](tools/plot_survey.py)** → `tools/videos/<name>.mp4`: a
  real-time scrolling chart of the survey.
- **[plot_spike.py](tools/plot_spike.py)**: a bench log's ppm estimate and its
  slope, with spikes flagged.
- **[serial_bridge.py](tools/serial_bridge.py)**: relays a board plugged into a
  PC to the app over Wi-Fi, for bench work without Bluetooth.

```
pip install -r tools/requirements.txt   # once
python tools/plot_map.py
python tools/plot_survey.py
```

The CSV columns are listed in [docs/phone_board.md](docs/phone_board.md#app-csv-backwards-compatible).
Survey CSVs contain GPS coordinates, so `tools/data/` is not tracked.

## Repository layout

```
app/              phone app (Expo / React Native): Bluetooth, slope and spike detection, GPS, CSV recording
firmware/         board firmware for rev B, C and D (phone_board/, PlatformIO)
hardware/
  phone_board/        rev C board: KiCad project, generator scripts, fabrication files
  phone_board_mems/   rev D draft
  enclosure/          printed case (OpenSCAD + STLs)
docs/             board spec and Bluetooth protocol (phone_board.md), sensor notes (sensors.md)
tools/            Python analysis scripts and the USB serial bridge
legacy/           rev A prototype and superseded enclosure models, kept for reference
```

## Licence

Firmware is MIT (see [LICENSE](LICENSE)). The hardware design will be released
under CERN-OHL-S once it is ready.
