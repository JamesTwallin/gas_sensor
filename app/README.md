# CH4 Survey — companion app

Phone app for the methane detector's phone-companion board, rev B and rev C
([docs/phone_board.md](../docs/phone_board.md)).
The board streams raw samples over BLE; the app turns them into the one thing
that indicates a plume — the slope of each channel's load voltage, with a spike
detector on top — charts it, and adds GPS tagging and CSV recording. Rev A's
HIGH/MED/LOW classifier and its baseline are gone from the screen: the absolute
level wanders too much to mean anything. The rolling baseline is still computed
for the rev A CSV columns only, so the plotting tools keep working.

One codebase: **Expo (SDK 57) + React Native + TypeScript**, built with EAS.

```
app/
  App.tsx          top bar, banners, the three views, action dock
  index.ts         Expo entry point
  app.json         Expo config: permissions, BLE + location plugins
  eas.json         EAS Build profiles (development / preview / production)
  src/core/        pure, DOM-free, unit-tested
    protocol.ts    BLE UUIDs, 20-byte Sample parser, Info JSON, control opcodes
    base64.ts      base64 <-> bytes (react-native-ble-plx speaks base64)
    sensor.ts      VRL = tap × tap_ratio, Rs = RL (VC − VRL) / VRL
    windows.ts     time-based rolling window, rev A percentile
    spike.ts       slope (dVRL/dt) and the adaptive spike threshold
    processor.ts   WARMUP / RUNNING / HEATER_OFF state machine, CSV baseline, LED colour
    csv.ts         exact spec column order, row formatting, file names
    chartData.ts   chart history + peak-per-column decimation
    simulator.ts   simulated board producing protocol-exact packets
    settings.ts    defaults (no warm-up, 1 s slope window, 4 σ / 25 mV/s spike threshold)
  src/controller.ts  the wiring: BLE/simulator -> core -> UI state, GPS, recording
                     (deliberately not src/app/ — Expo treats that as the
                      Expo Router routes directory)
  src/services/    BLE scan + link (auto-reconnect), simulated link, GPS,
                   recorder, keep-awake, settings storage
  src/ui/
    chartPaths.ts  pure chart geometry (unit-tested)
    charts.tsx     react-native-svg rendering of that geometry
    *Screen.tsx    Live / Surveys / Settings, and Present (full-screen slopes for video)
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
- Android Studio + SDK for `expo run:android` (a Mac + Xcode for `run:ios`)
- **pnpm** — install dependencies with `pnpm install`, not `npm install`.
  `npm install` stalls indefinitely on this dependency tree on Windows: it
  creates the ~320 top-level directories in `node_modules/`, writes zero bytes
  and then sits there with the CPU idle. pnpm installs the same tree in about
  20 seconds. `.npmrc` pins `node-linker=hoisted`, which Metro and the Expo
  config plugins need — they resolve modules by walking `node_modules`, so the
  default symlinked pnpm layout breaks them.
- Optional, only for cloud builds: an [Expo](https://expo.dev) account and
  `npm i -g eas-cli`.

## First-time setup

```sh
cd app
pnpm install
```

## Running it

BLE needs native code, so **Expo Go will not work with a real board** — the app
has to be a native build. The simulator, however, runs anywhere.

```sh
npx expo run:android    # builds the native app, installs it, starts Metro
npx expo start          # afterwards: just the bundler
```

`run:android` runs `prebuild` for you, generating `android/` from `app.json`.
Re-run it when a native dependency or anything in `app.json` changes; the rest of
the time `expo start` is enough. `npx expo prebuild --clean` regenerates the
native projects from scratch if they get into a bad state.

### Without hardware

**Settings → Simulated device**, then Connect. The simulator has buttons to drop
the link (tests auto-reconnect), toggle USB and force the heaters off.
Because it touches no native BLE code it also runs in Expo Go (`npm run start:go`),
which is the quickest way to work on the UI.

### Cloud builds (optional)

If you would rather not build locally — or need an iOS build without a Mac —
`eas.json` has development / preview / production profiles:

```sh
eas login
eas init                      # links this folder to your Expo account
npm run build:dev:android     # eas build --profile development --platform android
```

`eas init` writes `extra.eas.projectId` into `app.json`; commit that change.

`android/` and `ios/` are generated, not tracked: `app.json` is the source of
truth and EAS runs `prebuild` itself.

## Tests and type-checking

```sh
pnpm test         # vitest: src/core + src/ui/chartPaths — 105 tests
pnpm typecheck
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

There is no OS device chooser: the app scans for boards advertising the service
UUID and shows its own picker.

## Using it in the field

1. Power the board, tap **Connect**, pick `CH4-XXXX` from the list.
2. The big card shows the **CH4 slope** in mV/s (after **WARMING UP**, if a
   warm-up is set) and turns red while the slope is over the spike threshold: a
   rising edge means you have just walked into a plume. Each channel's card
   charts the slope over the last 60 s, the raw VRL under it, and the peak slope
   over the last 10 min. Raw readings are charted and recorded in every state.
   The board LED follows (green, red while CH4 is spiking).
3. Tap **● Record** to start a survey. Rows are appended to storage every 3 s.
4. Tap **Present** for presentation mode: just the two slopes, full screen and
   large, for filming or screen-recording. The ✕ (or Android back) leaves it.
5. A red **HEATERS OFF** banner means the firmware's low-battery cutoff tripped:
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
