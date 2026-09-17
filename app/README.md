# CH4 Survey — companion app (rev B board)

Phone app for the rev B methane detector ([docs/phone_board.md](../docs/phone_board.md)).
The board streams raw samples over BLE; the app does everything rev A did in
firmware — warm-up / baselining state machine, rolling-percentile baseline,
HIGH/MED/LOW classifier, charts — plus GPS tagging and CSV recording.

One codebase: **Expo (SDK 57) + React Native + TypeScript**, built with EAS.

```
app/
  App.tsx          top bar, banners, the three views, action dock
  index.ts         Expo entry point
  app.json         Expo config: permissions, BLE + location plugins
  eas.json         EAS Build profiles (development / preview / production)
  src/core/        pure, DOM-free, unit-tested — unchanged from the web build
    protocol.ts    BLE UUIDs, 20-byte Sample parser, Info JSON, control opcodes
    base64.ts      base64 <-> bytes (react-native-ble-plx speaks base64)
    sensor.ts      VRL = tap × tap_ratio, Rs = RL (VC − VRL) / VRL
    windows.ts     time-based rolling window, rev A percentile + classifier
    processor.ts   WARMUP / BASELINING / RUNNING / HEATER_OFF state machine, LED colour
    csv.ts         exact spec column order, row formatting, file names
    chartData.ts   chart history + peak-per-column decimation
    simulator.ts   simulated board producing protocol-exact packets
    settings.ts    defaults (warm-up 3 min, baseline 2 min, 2 min / p15, 10 min / 150 mV)
  src/app/
    controller.ts  the wiring: BLE/simulator -> core -> UI state, GPS, recording
  src/services/    BLE scan + link (auto-reconnect), simulated link, GPS,
                   recorder, keep-awake, settings storage
  src/ui/
    chartPaths.ts  pure chart geometry (unit-tested)
    charts.tsx     react-native-svg rendering of that geometry
    *Screen.tsx    Live / Surveys / Settings
  tests/           vitest — core + chart geometry
```

Samples arrive at 4 Hz, so `AppController` is a plain class holding the mutable
engines (`Processor`, `ChartBuffer`, `Recorder`); React subscribes to it with
`useSyncExternalStore` and sees an immutable snapshot published at most once per
animation frame.

## Requirements

- **Node 22.13+** (or 20.19.4+ / 24.3+). React Native 0.86 and Metro 0.84 refuse
  anything older — Node 22.11 installs with an `EBADENGINE` warning and then
  fails to start the bundler. EAS Build uses its own Node, so this only affects
  running the dev server locally.
- An [Expo](https://expo.dev) account, and the EAS CLI: `npm i -g eas-cli`

## First-time setup

```sh
cd app
npm install
eas login          # your Expo account
eas init           # creates the project on Expo and writes extra.eas.projectId
```

`eas init` is what links this folder to your Expo account; it adds the project ID
to `app.json`. Commit that change.

## Running it

BLE needs native code, so **Expo Go will not work for a real board** — you need a
development build. The simulator, however, runs anywhere.

```sh
# 1. Build a dev client once per platform (cloud build, no Android Studio/Xcode needed)
npm run build:dev:android     # eas build --profile development --platform android
npm run build:dev:ios         # needs an Apple Developer account for a device build

# 2. Install the artefact EAS gives you, then start the bundler
npm start                     # expo start --dev-client
```

Day to day you only repeat step 2. Rebuild the dev client when native
dependencies or anything in `app.json` changes.

### Without hardware

**Settings → Simulated device**, then Connect. The simulator has buttons to press
BOOT, drop the link (tests auto-reconnect), toggle USB and force the heaters off.
Because it touches no native BLE code it also runs in Expo Go (`npm run start:go`)
and in the browser (`npm run web`), which is the quickest way to work on the UI.

### Local native builds (optional)

```sh
npx expo prebuild     # generates android/ and ios/ (both are gitignored)
npm run android       # needs Android Studio + SDK
npm run ios           # needs a Mac + Xcode
```

`android/` and `ios/` are generated, not tracked: `app.json` is the source of
truth and EAS runs `prebuild` itself.

## Tests and type-checking

```sh
npm test         # vitest: src/core + src/ui/chartPaths
npm run typecheck
```

The tests import only pure modules, so they run in plain node with no React
Native or Expo mocking.

## Permissions

Declared in `app.json` and requested at first Connect / Record:

- **Android** — `BLUETOOTH_SCAN` (`neverForLocation`) and `BLUETOOTH_CONNECT` on
  API 31+, legacy `BLUETOOTH`/`BLUETOOTH_ADMIN` below that, `ACCESS_FINE_LOCATION`
  / `ACCESS_COARSE_LOCATION` for the GPS track (foreground only), and `WAKE_LOCK`.
  The BLE plugin is listed before `expo-location` so scanning does not force a
  location grant, while the location permission itself stays uncapped for the
  GPS track.
- **iOS** — `NSBluetoothAlwaysUsageDescription` (from the BLE plugin),
  `NSBluetoothPeripheralUsageDescription` and `NSLocationWhenInUseUsageDescription`.

Unlike the web build, there is no OS device chooser: the app scans for boards
advertising the service UUID and shows its own picker.

## Using it in the field

1. Power the board, tap **Connect**, pick `CH4-XXXX` from the list.
2. The big card shows **WARMING UP** (timed from the board's power-on), then
   **BASELINING**, then **LOW / MED / HIGH** with the CH4 deviation above baseline.
   The board LED follows (blue → green / amber / red).
3. Tap **● Record** to start a survey. Rows are appended to storage every 3 s.
   Press the board's BOOT button or **Re-zero** to restart the baseline.
4. A red **HEATERS OFF** banner means the firmware's low-battery cutoff tripped:
   readings are invalid until the heaters are back and the sensor has warmed up again.

## Getting CSVs into `tools/data/`

**Surveys** tab → **Share / export** on a file, then send it to your computer
(Drive, email, Nearby Share / AirDrop, …) and save it to `tools/data/`.

Surveys live in `<documents>/surveys/`. On iOS that folder is exposed to the
Files app (**On My iPhone → CH4 Survey → surveys**) via `UIFileSharingEnabled`.
On Android (debug build) you can also pull them over USB:

```sh
adb shell run-as io.github.jamestwallin.ch4survey ls files/surveys
adb exec-out run-as io.github.jamestwallin.ch4survey cat files/surveys/2026-09-17_09-05-07.csv > tools/data/2026-09-17_09-05-07.csv
```

The CSV is the rev A column set followed by `ch4_rs_ohm,lpg_rs_ohm,vbat_mv,gps_accuracy_m`
(see the spec). Note the known gap in the spec: `tools/plot_map.py` currently
filters on `sats`, which the phone leaves blank.
