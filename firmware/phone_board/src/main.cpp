// Phone-companion board firmware (rev B and rev C, which share one circuit): a
// thin BLE sampler.
//
// docs/phone_board.md is the source of truth for everything this file
// implements (pin map, ADS1115 channels, BLE UUIDs, packet layout, Info JSON,
// Control opcodes). Change the spec first, then this file.
//
// What it does, and deliberately does not do
// ------------------------------------------
// Rev A ran the whole instrument on the board (baseline, classifier, OLED,
// GNSS, SD). Rev B hands all of that to the phone app. The firmware only:
//   1. reads the two bare Figaro sensor load-resistor taps, VBAT and the heater
//      rail on the ADS1115, and temperature/humidity on the SHT40 (there is no
//      pressure sensor on the board; the app uses the phone's barometer);
//   2. averages each ADC channel over the sample interval (default 250 ms);
//   3. sends one 20-byte notification per interval to a subscribed phone, and
//      prints the same sample as a CSV line on USB serial for bench debugging.
// There is no baseline, no HIGH/MED/LOW, no Rs compensation here -- the app does
// that, where it is easier to tune. The status LED colour is set by the app.
//
// Sampling
// --------
// The ADS1115 runs single-shot at 250 SPS, round-robin AIN0 -> AIN1 -> AIN2 ->
// AIN3, as fast as conversions complete (~4 ms each plus I2C). Every conversion
// is added to a per-channel accumulator; at each interval boundary the mean of
// everything collected is taken, so a longer interval simply averages more (at
// 250 ms that is roughly a dozen conversions per channel). The loop is
// non-blocking so the button and LED stay responsive between conversions.
//
// Conversion-ready comes from the ADS ALERT/RDY pin (GPIO10, active low). As a
// guard against a stale low level the pin is only trusted once the nominal
// conversion time has nearly elapsed. If RDY does not arrive in time the config
// register's OS bit is read over I2C instead; if that shows the conversion did
// finish, the RDY trace is assumed broken and after a few such misses the
// sampler switches to I2C polling for good. If the chip does not answer at all
// for several conversions in a row it is marked lost and re-probed every few
// seconds.
//
// Whenever the ADS1115 is absent (or lost) the CH4/LPG taps are read instead by
// the ESP32's own ADC on the 1k fallback pins (GPIO1/GPIO2, oversampled,
// calibrated analogReadMilliVolts) and flag bit3 is cleared so the app knows the
// resolution dropped. VBAT and the heater rail are only wired to the ADS1115,
// so in fallback vbat reads 0 (unknown) and the heater check (bit4) is not
// asserted.
//
// Heaters: HTR_EN (GPIO7) is the boost converter's enable and has a 100k
// pull-down on the board, so the heaters stay off until setup() drives it HIGH.
// Low-battery heater cutoff: the ~115 mA heaters are most of the load, so when
// VBAT stays below 3.3 V for 10 s the firmware drives HTR_EN low and sets flag
// bit6; above 3.5 V it drives the pin HIGH again. While the heaters are held
// off the dead heater rail is not reported as a fault.
// The cutoff is skipped (and cleared) while USB power is present (PGOOD_N low).
// The gas readings are meaningless with the heaters off; the app should say so.
//
// BLE
// ---
// NimBLE, one custom service, one client at a time. Advertising carries the
// flags and the 128-bit service UUID; the name CH4-XXXX (last two bytes of the
// BT MAC) goes in the scan response because both do not fit in 31 bytes. On
// connect the firmware asks for a 45-75 ms connection interval (comfortably
// inside iOS/Android rules and fast enough for 100 ms samples); on disconnect
// it restarts advertising. Notifications are only sent while the client has
// notifications enabled on the Sample characteristic. BLE callbacks run on the
// NimBLE host task, so everything they share with loop() is std::atomic.
//
// LED (WS2812B/SK6812 on GPIO38, standard GRB -- no R/G swap unlike rev A's
// onboard LED): slow dim blue breathe while advertising; solid dim cyan once
// connected until the app sends a colour (opcode 0x03); opcode 0x02 blinks
// white three times. App colours are scaled down (LED_APP_SCALE) to save
// battery -- the app's 255 is our LED_APP_SCALE.

#include <Arduino.h>
#include <Wire.h>
#include <atomic>
#include <cmath>
#include <esp_mac.h>
#include <esp_system.h>
#include <NimBLEDevice.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_SHT4x.h>

static const char *FW_VERSION = "1.0.0";
static const char *BOARD_ID = "rev-b";

// ---- Pins (docs/phone_board.md, ESP32-S3-MINI-1-N8 pin map) -----------------
static const uint8_t PIN_BOOT_BUTTON = 0;   // active low, tact switch to GND
static const uint8_t PIN_CH4_ADC_FB = 1;    // fallback CH4 tap via 1k (ADC1)
static const uint8_t PIN_LPG_ADC_FB = 2;    // fallback LPG tap via 1k (ADC1)
static const uint8_t PIN_CHG_N = 5;         // BQ24073 CHG, low = charging
static const uint8_t PIN_PGOOD_N = 6;       // BQ24073 PGOOD, low = USB power good
static const uint8_t PIN_HTR_EN = 7;        // 100k pull-down: drive HIGH = heaters on, LOW = off
static const uint8_t PIN_I2C_SDA = 8;
static const uint8_t PIN_I2C_SCL = 9;
static const uint8_t PIN_ADS_RDY = 10;      // ADS1115 ALERT/RDY, active low
static const uint8_t PIN_LED_DIN = 38;      // WS2812-class status LED

// ---- I2C devices ---------------------------------------------------------------
static const uint32_t I2C_CLOCK_HZ = 400000;  // both parts are fast-mode capable
static const uint8_t ADS1115_ADDR = 0x48;
// SHT40-AD1B is fixed at 0x44 (the Adafruit driver hard-codes it).

// ---- Analogue front end (must match Info JSON and the schematic) --------------
static const uint32_t RL_OHM = 40000;      // RLa + RLb (20k + 20k)
static const float TAP_RATIO = 2.0f;       // VRL = 2 x tap
static const uint16_t VC_MV = 5000;        // nominal sensor circuit voltage
static const float VBAT_RATIO = 2.0f;      // 100k/100k on AIN2
static const float HEATER_RATIO = 2.0f;    // 100k/100k on AIN3
static const uint16_t HEATER_MIN_MV = 4800;  // bit4 if outside this window
static const uint16_t HEATER_MAX_MV = 5200;

// ---- Heater turn-on happens first thing in setup(), before the radio, I2C
// and USB are up and with the CPU at 80 MHz, because on USB power alone the
// BQ24073's 500 mA input limit only just covers the boost converter's start-up
// inrush into two cold heaters. Bench evidence (2026-09-28): with heaters
// switched on 3 s after boot, alongside BLE advertising at 240 MHz, the board
// browned out (reset reason 9) at that instant on two consecutive boots and
// only survived once the heaters had warmed a little. A LiPo on J2 removes the
// problem entirely, since the cell holds VSYS up. After enabling, setup() waits
// HEATER_SETTLE_MS before adding any other load.
static const uint32_t HEATER_SETTLE_MS = 500;
static const uint32_t CPU_MHZ = 80;  // plenty for a 4 Hz sampler; ~30 mA less than 240

// ---- Low-battery heater cutoff (drives HTR_EN low) ---------------------------------
static const uint16_t HEATER_CUTOFF_MV = 3300;       // off below this ...
static const uint32_t HEATER_CUTOFF_HOLD_MS = 10000; // ... for longer than this
static const uint16_t HEATER_RESTORE_MV = 3500;      // back on above this

// ---- ADS1115 sampling ---------------------------------------------------------
static const float ADS_MV_PER_COUNT = 0.125f;  // GAIN_ONE, +/-4.096 V
static const uint32_t ADS_MIN_CONV_US = 3200;  // 250 SPS = 4000 us nominal, -20%
static const uint32_t ADS_POLL_AT_US = 4600;   // polling mode: first OS-bit read
static const uint32_t ADS_TIMEOUT_US = 20000;  // give up waiting for RDY
static const uint8_t ADS_RDY_MISSES_TO_POLL = 3;  // then stop trusting GPIO10
static const uint8_t ADS_FAILS_TO_LOST = 5;       // then fall back to ESP32 ADC
static const uint32_t ADS_REPROBE_MS = 5000;

// ---- Fallback ESP32 ADC --------------------------------------------------------
static const uint8_t FALLBACK_OVERSAMPLE = 32;

// ---- Sample interval (Control opcode 0x01 range) -----------------------------
static const uint16_t DEFAULT_INTERVAL_MS = 250;
static const uint16_t MIN_INTERVAL_MS = 100;
static const uint16_t MAX_INTERVAL_MS = 5000;

// ---- Button --------------------------------------------------------------------
static const uint32_t BUTTON_DEBOUNCE_MS = 30;

// ---- BLE ---------------------------------------------------------------------------
static const char *UUID_SERVICE = "6d1a0001-8f3e-4b8a-9c57-2f6c0e3a7b10";
static const char *UUID_SAMPLE = "6d1a0002-8f3e-4b8a-9c57-2f6c0e3a7b10";
static const char *UUID_INFO = "6d1a0003-8f3e-4b8a-9c57-2f6c0e3a7b10";
static const char *UUID_CONTROL = "6d1a0004-8f3e-4b8a-9c57-2f6c0e3a7b10";
static const uint8_t PROTO_VERSION = 1;
static const size_t SAMPLE_PACKET_LEN = 20;
// Requested connection parameters (units: 1.25 ms, 1.25 ms, events, 10 ms).
static const uint16_t CONN_MIN_INTERVAL = 36;  // 45 ms
static const uint16_t CONN_MAX_INTERVAL = 60;  // 75 ms
static const uint16_t CONN_LATENCY = 0;
static const uint16_t CONN_TIMEOUT = 500;      // 5 s

static const uint8_t OP_SET_INTERVAL = 0x01;
static const uint8_t OP_IDENTIFY = 0x02;
static const uint8_t OP_SET_LED = 0x03;

// Sentinels for missing environment values (sample packet).
static const int16_t TEMP_MISSING = INT16_MIN;  // 0x8000
static const uint16_t HUM_MISSING = 0xFFFF;
static const uint16_t PRESS_MISSING = 0xFFFF;

// Flag bits (sample packet byte 19).
static const uint8_t FLAG_USB_POWER = 1 << 0;
static const uint8_t FLAG_CHARGING = 1 << 1;
static const uint8_t FLAG_BME_OK = 1 << 2;  // T/RH sensor (SHT40) ok
static const uint8_t FLAG_ADS_OK = 1 << 3;
static const uint8_t FLAG_HEATER_FAULT = 1 << 4;
static const uint8_t FLAG_BUTTON = 1 << 5;
static const uint8_t FLAG_HEATERS_OFF = 1 << 6;  // low-battery cutoff active

// ---- LED (kept dim: this runs off a 1-cell LiPo) ---------------------------------
static const uint32_t LED_UPDATE_MS = 20;
static const uint32_t LED_BREATHE_PERIOD_MS = 3000;
static const uint8_t LED_BREATHE_MIN = 1;
static const uint8_t LED_BREATHE_MAX = 24;
static const uint8_t LED_CONNECTED_G = 10;  // dim cyan
static const uint8_t LED_CONNECTED_B = 10;
static const uint8_t LED_IDENTIFY_LEVEL = 40;  // white
static const uint32_t LED_IDENTIFY_STEP_MS = 200;
static const uint8_t LED_IDENTIFY_BLINKS = 3;
static const uint8_t LED_APP_SCALE = 64;  // app 255 -> 64

// =================================================================================
// State shared with BLE callbacks (NimBLE host task)
// =================================================================================
static std::atomic<uint16_t> sampleIntervalMs{DEFAULT_INTERVAL_MS};
static std::atomic<bool> bleConnected{false};
static std::atomic<bool> notifyEnabled{false};
static std::atomic<bool> identifyRequested{false};
static std::atomic<uint32_t> appLedColour{0};  // 0x01RRGGBB when set, 0 when not
static std::atomic<uint16_t> lastHeaterMv{0};   // for Info JSON, 0 = unknown

static NimBLECharacteristic *sampleChar = nullptr;
static NimBLECharacteristic *infoChar = nullptr;
static char deviceName[16];

// =================================================================================
// Sensors
// =================================================================================
static Adafruit_ADS1115 ads;
static Adafruit_SHT4x sht4;
static bool shtReady = false;

static const uint16_t ADS_MUX[4] = {
    ADS1X15_REG_CONFIG_MUX_SINGLE_0,  // AIN0 CH4 tap
    ADS1X15_REG_CONFIG_MUX_SINGLE_1,  // AIN1 LPG tap
    ADS1X15_REG_CONFIG_MUX_SINGLE_2,  // AIN2 VBAT / 2
    ADS1X15_REG_CONFIG_MUX_SINGLE_3,  // AIN3 +5V_HTR / 2
};
enum AdsChannel { ADS_CH4 = 0, ADS_LPG = 1, ADS_VBAT = 2, ADS_HEATER = 3 };

// Sum of raw counts per channel since the last sample was emitted.
struct AdsAccumulator {
  int32_t sum;
  uint16_t count;
};

struct AdsState {
  bool ok = false;           // chip present and answering
  bool useRdyPin = true;     // false once GPIO10 has proven unreliable
  bool busy = false;         // a conversion is in progress
  uint8_t channel = 0;       // channel of the in-progress conversion
  uint32_t startUs = 0;      // micros() when it was started
  uint8_t rdyMisses = 0;     // consecutive conversions that finished without RDY
  uint8_t failures = 0;      // consecutive conversions that never finished
  uint32_t lastProbeMs = 0;
  AdsAccumulator acc[4] = {};
  float lastMv[4] = {0, 0, 0, 0};  // last window's mean, mV at the ADC pin
  bool haveMv[4] = {false, false, false, false};
};
static AdsState adsState;

static bool probeAds() {
  if (!ads.begin(ADS1115_ADDR, &Wire)) return false;
  ads.setGain(GAIN_ONE);  // +/-4.096 V, 125 uV/LSB
  ads.setDataRate(RATE_ADS1115_250SPS);
  adsState.ok = true;
  adsState.busy = false;
  adsState.channel = 0;
  adsState.failures = 0;
  for (int i = 0; i < 4; i++) {
    adsState.acc[i] = {0, 0};
    adsState.haveMv[i] = false;
  }
  return true;
}

// Advance the ADS1115 state machine by at most one step. Called every loop.
static void serviceAds(uint32_t nowMs) {
  if (!adsState.ok) {
    if (nowMs - adsState.lastProbeMs >= ADS_REPROBE_MS) {
      adsState.lastProbeMs = nowMs;
      if (probeAds()) Serial.println("ADS1115 found again; leaving ESP32 ADC fallback.");
    }
    return;
  }

  if (!adsState.busy) {
    ads.startADCReading(ADS_MUX[adsState.channel], /*continuous=*/false);
    adsState.startUs = micros();
    adsState.busy = true;
    return;
  }

  uint32_t elapsedUs = micros() - adsState.startUs;
  if (elapsedUs < ADS_MIN_CONV_US) return;  // too early: RDY may still be stale

  bool ready;
  if (adsState.useRdyPin) {
    ready = (digitalRead(PIN_ADS_RDY) == LOW);
  } else {
    ready = (elapsedUs >= ADS_POLL_AT_US) && ads.conversionComplete();
  }

  if (!ready) {
    if (elapsedUs < ADS_TIMEOUT_US) return;
    // Timed out. Ask the chip directly whether the conversion finished.
    if (ads.conversionComplete()) {
      if (adsState.useRdyPin && ++adsState.rdyMisses >= ADS_RDY_MISSES_TO_POLL) {
        adsState.useRdyPin = false;
        Serial.println("ADS1115 RDY (GPIO10) not asserting; switching to I2C polling.");
      }
    } else {
      adsState.busy = false;  // retry this channel
      if (++adsState.failures >= ADS_FAILS_TO_LOST) {
        adsState.ok = false;
        adsState.lastProbeMs = nowMs;
        Serial.println("ADS1115 not responding; using ESP32 ADC fallback.");
      }
      return;
    }
  } else if (adsState.useRdyPin) {
    adsState.rdyMisses = 0;
  }

  int16_t raw = ads.getLastConversionResults();
  adsState.busy = false;
  adsState.failures = 0;
  if (raw < 0) raw = 0;  // single-ended inputs: only tiny negative offsets
  AdsAccumulator &a = adsState.acc[adsState.channel];
  a.sum += raw;
  a.count++;
  adsState.channel = (adsState.channel + 1) % 4;
}

// Close the current averaging window: fold each channel's accumulator into
// lastMv (mV at the ADC pin). A channel with no conversions in this window
// keeps its previous mean.
static void closeAdsWindow() {
  for (int i = 0; i < 4; i++) {
    AdsAccumulator &a = adsState.acc[i];
    if (a.count > 0) {
      adsState.lastMv[i] = (float)a.sum / a.count * ADS_MV_PER_COUNT;
      adsState.haveMv[i] = true;
    }
    a = {0, 0};
  }
}

// Fallback: oversampled, eFuse-calibrated ESP32 ADC read, in mV at the pin.
static float readFallbackMv(uint8_t pin) {
  uint32_t acc = 0;
  for (uint8_t i = 0; i < FALLBACK_OVERSAMPLE; i++) acc += analogReadMilliVolts(pin);
  return (float)acc / FALLBACK_OVERSAMPLE;
}

static uint16_t clampU16(float v) {
  if (!(v > 0.0f)) return 0;  // also catches NaN
  if (v > 65535.0f) return 65535;
  return (uint16_t)lroundf(v);
}

// =================================================================================
// Button (BOOT, GPIO0): debounced; a press marks the next sample (flag bit5)
// =================================================================================
static bool buttonRaw = false;
static bool buttonStable = false;
static uint32_t buttonChangeMs = 0;
static bool markPending = false;

static void serviceButton(uint32_t nowMs) {
  bool down = (digitalRead(PIN_BOOT_BUTTON) == LOW);
  if (down != buttonRaw) {
    buttonRaw = down;
    buttonChangeMs = nowMs;
  } else if (down != buttonStable && nowMs - buttonChangeMs >= BUTTON_DEBOUNCE_MS) {
    buttonStable = down;
    if (down) markPending = true;
  }
}

// =================================================================================
// Status LED
// =================================================================================
static uint32_t ledLastUpdateMs = 0;
static uint32_t ledShown = 0xFFFFFFFF;  // force the first write
static bool identifyActive = false;
static uint32_t identifyStartMs = 0;

static void ledWrite(uint8_t r, uint8_t g, uint8_t b) {
  uint32_t c = ((uint32_t)r << 16) | ((uint32_t)g << 8) | b;
  if (c == ledShown) return;  // the RMT write is not free; skip repeats
  ledShown = c;
  // Standard WS2812B/SK6812: the core puts GRB on the wire from (r, g, b).
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  rgbLedWrite(PIN_LED_DIN, r, g, b);
#else
  neopixelWrite(PIN_LED_DIN, r, g, b);
#endif
}

static uint8_t scaleApp(uint8_t v) {
  return (uint8_t)(((uint16_t)v * LED_APP_SCALE + 127) / 255);
}

static void serviceLed(uint32_t nowMs) {
  if (identifyRequested.exchange(false)) {
    identifyActive = true;
    identifyStartMs = nowMs;
  }
  if (nowMs - ledLastUpdateMs < LED_UPDATE_MS) return;
  ledLastUpdateMs = nowMs;

  if (identifyActive) {
    uint32_t step = (nowMs - identifyStartMs) / LED_IDENTIFY_STEP_MS;
    if (step < 2u * LED_IDENTIFY_BLINKS) {
      uint8_t v = (step % 2 == 0) ? LED_IDENTIFY_LEVEL : 0;
      ledWrite(v, v, v);
      return;
    }
    identifyActive = false;
  }

  if (!bleConnected.load()) {
    float phase = (float)(nowMs % LED_BREATHE_PERIOD_MS) / LED_BREATHE_PERIOD_MS;
    float k = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * phase);
    ledWrite(0, 0, LED_BREATHE_MIN + (uint8_t)lroundf(k * (LED_BREATHE_MAX - LED_BREATHE_MIN)));
    return;
  }

  uint32_t app = appLedColour.load();
  if (app & 0x01000000UL) {
    ledWrite(scaleApp(app >> 16), scaleApp(app >> 8), scaleApp(app));
  } else {
    ledWrite(0, LED_CONNECTED_G, LED_CONNECTED_B);
  }
}

// =================================================================================
// BLE
// =================================================================================
static void startAdvertising() {
  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  if (!adv->isAdvertising()) adv->start();
}

static void refreshInfo() {
  char json[200];
  snprintf(json, sizeof(json),
           "{\"proto\":%u,\"fw\":\"%s\",\"board\":\"%s\",\"rl_ohm\":%lu,"
           "\"tap_ratio\":%.1f,\"vc_mv\":%u,\"interval_ms\":%u,\"heater_mv\":%u}",
           PROTO_VERSION, FW_VERSION, BOARD_ID, (unsigned long)RL_OHM, TAP_RATIO,
           VC_MV, sampleIntervalMs.load(), lastHeaterMv.load());
  infoChar->setValue(std::string(json));
}

class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer *server, NimBLEConnInfo &info) override {
    bleConnected = true;
    server->updateConnParams(info.getConnHandle(), CONN_MIN_INTERVAL, CONN_MAX_INTERVAL,
                             CONN_LATENCY, CONN_TIMEOUT);
  }
  void onDisconnect(NimBLEServer *server, NimBLEConnInfo &info, int reason) override {
    bleConnected = false;
    notifyEnabled = false;
    appLedColour = 0;  // the next client starts from dim cyan again
    startAdvertising();
  }
};

class SampleCallbacks : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic *chr, NimBLEConnInfo &info,
                   uint16_t subValue) override {
    notifyEnabled = (subValue & 0x0001) != 0;  // bit0 of the CCCD = notifications
  }
};

class InfoCallbacks : public NimBLECharacteristicCallbacks {
  void onRead(NimBLECharacteristic *chr, NimBLEConnInfo &info) override {
    refreshInfo();  // runs before the value is sent, so heater_mv is current
  }
};

class ControlCallbacks : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic *chr, NimBLEConnInfo &info) override {
    NimBLEAttValue v = chr->getValue();
    const uint8_t *d = v.data();
    size_t n = v.size();
    if (n == 0) return;
    switch (d[0]) {
      case OP_SET_INTERVAL:
        if (n >= 3) {
          uint16_t ms = (uint16_t)(d[1] | (d[2] << 8));
          if (ms >= MIN_INTERVAL_MS && ms <= MAX_INTERVAL_MS) {
            sampleIntervalMs = ms;
            refreshInfo();
          }
        }
        break;
      case OP_IDENTIFY:
        identifyRequested = true;
        break;
      case OP_SET_LED:
        if (n >= 4) {
          appLedColour = 0x01000000UL | ((uint32_t)d[1] << 16) | ((uint32_t)d[2] << 8) | d[3];
        }
        break;
      default:
        break;  // unknown opcodes and short payloads are ignored
    }
  }
};

static void initBle() {
  uint8_t mac[6];
  esp_read_mac(mac, ESP_MAC_BT);
  snprintf(deviceName, sizeof(deviceName), "CH4-%02X%02X", mac[4], mac[5]);

  NimBLEDevice::init(deviceName);
  NimBLEServer *server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  server->advertiseOnDisconnect(false);  // restarted explicitly in onDisconnect

  NimBLEService *svc = server->createService(UUID_SERVICE);
  sampleChar = svc->createCharacteristic(UUID_SAMPLE, NIMBLE_PROPERTY::NOTIFY);
  sampleChar->setCallbacks(new SampleCallbacks());
  infoChar = svc->createCharacteristic(UUID_INFO, NIMBLE_PROPERTY::READ);
  infoChar->setCallbacks(new InfoCallbacks());
  NimBLECharacteristic *ctrl = svc->createCharacteristic(
      UUID_CONTROL, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  ctrl->setCallbacks(new ControlCallbacks());
  refreshInfo();

  // Flags + the 128-bit service UUID take 21 of the 31 advertising bytes, so
  // the name goes in the scan response.
  NimBLEAdvertisementData advData;
  advData.setFlags(BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP);
  advData.addServiceUUID(UUID_SERVICE);
  NimBLEAdvertisementData scanData;
  scanData.setName(deviceName);
  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  adv->setAdvertisementData(advData);
  adv->setScanResponseData(scanData);
  adv->enableScanResponse(true);
  startAdvertising();
}

// =================================================================================
// Sample assembly
// =================================================================================
static uint16_t seq = 0;
static uint32_t nextSampleMs = 0;
static uint32_t setupDoneMs = 0;  // millis() when setup() finished (bench diagnostic)

// Bench diagnostic that survives a USB-triggered reset (RTC slow memory is not
// cleared by a core reset): what the previous run was doing when it died.
static const uint32_t RTC_DIAG_MAGIC = 0xC0FFEE01;
RTC_NOINIT_ATTR static uint32_t rtcMagic;
RTC_NOINIT_ATTR static uint32_t rtcSetupDoneMs;
RTC_NOINIT_ATTR static uint32_t rtcLastLoopMs;
RTC_NOINIT_ATTR static uint32_t rtcLastSeq;
RTC_NOINIT_ATTR static uint32_t rtcStage[6];  // millis() at each setup() stage
RTC_NOINIT_ATTR static uint32_t rtcHeaterOnMs;  // when HTR_EN went high, 0 = never
static void stage(int i) { rtcStage[i] = millis(); }

static const char *CSV_HEADER =
    "ms,seq,adc,ch4_tap_mv,lpg_tap_mv,ch4_vrl_mv,lpg_vrl_mv,ch4_rs_ohm,lpg_rs_ohm,"
    "temp_c,humidity_pct,pressure_hpa,vbat_mv,heater_mv,flags,ble_conn,ble_notify";

// Low-battery heater cutoff. HTR_EN (GPIO7) is the boost enable with a 100k
// pull-down on the board: HIGH = heaters on, LOW = heaters off. Heaters go
// off once VBAT has stayed below HEATER_CUTOFF_MV for HEATER_CUTOFF_HOLD_MS and
// come back only above HEATER_RESTORE_MV. An unknown VBAT (0, no ADS1115)
// neither starts the timer nor restores the heaters.
static bool heatersOffLowBatt = false;
static bool heatersEnabled = false;  // set once setup() has driven HTR_EN high
static uint32_t vbatLowSinceMs = 0;
static bool vbatLowTiming = false;

static void driveHeaterPin() {
  digitalWrite(PIN_HTR_EN, (heatersEnabled && !heatersOffLowBatt) ? HIGH : LOW);
}

static void setHeatersOff(bool off) {
  heatersOffLowBatt = off;
  driveHeaterPin();
}

static void updateHeaterCutoff(uint32_t nowMs, uint16_t vbatMv, bool usbPower) {
  // On USB power VSYS is fed from USB, not the cell: never hold heaters off.
  if (usbPower) {
    vbatLowTiming = false;
    if (heatersOffLowBatt) {
      setHeatersOff(false);
      Serial.println("USB power: heaters back on.");
    }
    return;
  }
  if (vbatMv == 0) {
    vbatLowTiming = false;
    return;
  }
  if (!heatersOffLowBatt) {
    if (vbatMv < HEATER_CUTOFF_MV) {
      if (!vbatLowTiming) {
        vbatLowTiming = true;
        vbatLowSinceMs = nowMs;
      } else if (nowMs - vbatLowSinceMs >= HEATER_CUTOFF_HOLD_MS) {
        setHeatersOff(true);
        vbatLowTiming = false;
        Serial.printf("VBAT %u mV: heaters off (low battery).\n", vbatMv);
      }
    } else {
      vbatLowTiming = false;
    }
  } else if (vbatMv > HEATER_RESTORE_MV) {
    setHeatersOff(false);
    Serial.printf("VBAT %u mV: heaters back on.\n", vbatMv);
  }
}

static void putU16(uint8_t *p, uint16_t v) {
  p[0] = (uint8_t)v;
  p[1] = (uint8_t)(v >> 8);
}
static void putU32(uint8_t *p, uint32_t v) {
  for (int i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i));
}

static void emitSample(uint32_t nowMs) {
  uint8_t flags = 0;

  // Gas taps, VBAT and heater rail: ADS1115 window means, or the ESP32 fallback.
  closeAdsWindow();
  float ch4Mv, lpgMv;
  uint16_t vbatMv = 0, heaterMv = 0;  // 0 = unknown (no ADS1115)
  bool fromAds = adsState.ok && adsState.haveMv[ADS_CH4] && adsState.haveMv[ADS_LPG];
  if (fromAds) {
    flags |= FLAG_ADS_OK;
    ch4Mv = adsState.lastMv[ADS_CH4];
    lpgMv = adsState.lastMv[ADS_LPG];
    if (adsState.haveMv[ADS_VBAT]) vbatMv = clampU16(adsState.lastMv[ADS_VBAT] * VBAT_RATIO);
  } else {
    ch4Mv = readFallbackMv(PIN_CH4_ADC_FB);
    lpgMv = readFallbackMv(PIN_LPG_ADC_FB);
  }
  updateHeaterCutoff(nowMs, vbatMv, digitalRead(PIN_PGOOD_N) == LOW);
  if (heatersOffLowBatt) flags |= FLAG_HEATERS_OFF;
  if (fromAds && adsState.haveMv[ADS_HEATER]) {
    heaterMv = clampU16(adsState.lastMv[ADS_HEATER] * HEATER_RATIO);
    // A dead rail is expected while we hold the heaters off; not a fault.
    if (heatersEnabled && !heatersOffLowBatt &&
        (heaterMv < HEATER_MIN_MV || heaterMv > HEATER_MAX_MV)) {
      flags |= FLAG_HEATER_FAULT;
    }
  }
  lastHeaterMv = heaterMv;

  // Environment. NaN or physically implausible readings are sent as missing.
  // The board has no pressure sensor, so pressure is always missing.
  float t = NAN, h = NAN, p = NAN;
  if (shtReady) {
    sensors_event_t hum, temp;
    if (sht4.getEvent(&hum, &temp)) {
      t = temp.temperature;
      h = hum.relative_humidity;
    }
  }
  bool tOk = t >= -40.0f && t <= 125.0f;
  bool hOk = h >= 0.0f && h <= 100.0f;
  bool pOk = p >= 300.0f && p <= 1100.0f;
  if (tOk && hOk) flags |= FLAG_BME_OK;

  // Charger status (open-drain with external pull-ups: low = asserted).
  if (digitalRead(PIN_PGOOD_N) == LOW) flags |= FLAG_USB_POWER;
  if (digitalRead(PIN_CHG_N) == LOW) flags |= FLAG_CHARGING;

  if (markPending) {
    flags |= FLAG_BUTTON;
    markPending = false;
  }

  // 20-byte little-endian packet, layout per docs/phone_board.md.
  uint8_t pkt[SAMPLE_PACKET_LEN];
  pkt[0] = PROTO_VERSION;
  putU16(pkt + 1, seq);
  putU32(pkt + 3, nowMs);
  putU16(pkt + 7, clampU16(ch4Mv * 10.0f));  // 0.1 mV
  putU16(pkt + 9, clampU16(lpgMv * 10.0f));
  putU16(pkt + 11, tOk ? (uint16_t)(int16_t)lroundf(t * 100.0f) : (uint16_t)TEMP_MISSING);
  putU16(pkt + 13, hOk ? (uint16_t)lroundf(h * 100.0f) : HUM_MISSING);
  putU16(pkt + 15, pOk ? (uint16_t)lroundf(p * 10.0f) : PRESS_MISSING);
  putU16(pkt + 17, vbatMv);
  pkt[19] = flags;

  if (bleConnected.load() && notifyEnabled.load()) {
    sampleChar->notify(pkt, sizeof(pkt));
  }

  // Bench CSV. Rs uses the nominal VC, as the app does with vc_mv from Info.
  if (Serial) {
    float ch4Vrl = ch4Mv * TAP_RATIO, lpgVrl = lpgMv * TAP_RATIO;
    float ch4Rs = ch4Vrl > 1.0f ? RL_OHM * (VC_MV - ch4Vrl) / ch4Vrl : NAN;
    float lpgRs = lpgVrl > 1.0f ? RL_OHM * (VC_MV - lpgVrl) / lpgVrl : NAN;
    char row[220];
    int n = snprintf(row, sizeof(row), "%lu,%u,%s,%.1f,%.1f,%.0f,%.0f,%.0f,%.0f,",
                     (unsigned long)nowMs, seq, fromAds ? "ads" : "esp", ch4Mv, lpgMv,
                     ch4Vrl, lpgVrl, ch4Rs, lpgRs);
    if (tOk) n += snprintf(row + n, sizeof(row) - n, "%.2f", t);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (hOk) n += snprintf(row + n, sizeof(row) - n, "%.2f", h);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (pOk) n += snprintf(row + n, sizeof(row) - n, "%.1f", p);
    snprintf(row + n, sizeof(row) - n, ",%u,%u,0x%02X,%d,%d", vbatMv, heaterMv, flags,
             bleConnected.load() ? 1 : 0, notifyEnabled.load() ? 1 : 0);
    Serial.println(row);
  }

  seq++;
}

// =================================================================================
// Arduino entry points
// =================================================================================
void setup() {
  // Heaters first, at minimum load (see HEATER_SETTLE_MS). The board's 100k
  // pull-down held the boost off through the bootloader; latch HIGH before
  // enabling the driver so there is no LOW glitch.
  setCpuFrequencyMhz(CPU_MHZ);
  digitalWrite(PIN_HTR_EN, HIGH);
  pinMode(PIN_HTR_EN, OUTPUT);
  heatersEnabled = true;
  rtcHeaterOnMs = millis();
  delay(HEATER_SETTLE_MS);

  Serial.begin(115200);
  // Never let debug output stall sampling when a USB host is attached but no
  // terminal is reading: give up and drop bytes after a short wait. This must
  // NOT be 0: HWCDC::write() in arduino-esp32 2.0.x decrements a uint32 retry
  // counter initialised from this value, so 0 wraps around and write() spins
  // until the host drains the FIFO -- setup() hung for as long as the PC had
  // the port closed. 20 ms is paid once, after which the driver marks the CDC
  // disconnected and later writes return immediately.
  Serial.setTxTimeoutMs(20);
  uint32_t waitStart = millis();
  while (!Serial && millis() - waitStart < 1500) delay(10);

  pinMode(PIN_BOOT_BUTTON, INPUT_PULLUP);
  pinMode(PIN_CHG_N, INPUT);  // external 10k pull-ups
  pinMode(PIN_PGOOD_N, INPUT);
  pinMode(PIN_ADS_RDY, INPUT);

  ledWrite(0, 0, LED_BREATHE_MIN);

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_CH4_ADC_FB, ADC_11db);
  analogSetPinAttenuation(PIN_LPG_ADC_FB, ADC_11db);

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(I2C_CLOCK_HZ);

  Serial.println();
  Serial.printf("=== CH4 phone board (%s) firmware %s, built %s %s ===\n", BOARD_ID,
                FW_VERSION, __DATE__, __TIME__);
  Serial.printf("Reset reason %d, millis %lu at setup, CPU %u MHz, heaters on since %lu ms.\n",
                (int)esp_reset_reason(), (unsigned long)millis(), (unsigned)getCpuFrequencyMhz(),
                (unsigned long)rtcHeaterOnMs);
  if (rtcMagic == RTC_DIAG_MAGIC) {
    Serial.printf("Previous run: setup done at %lu ms, last loop at %lu ms, seq %lu.\n",
                  (unsigned long)rtcSetupDoneMs, (unsigned long)rtcLastLoopMs,
                  (unsigned long)rtcLastSeq);
    Serial.printf("Previous run stages (ms): serial-wait %lu, banner %lu, ads %lu, sht %lu, "
                  "ble %lu, header %lu, heaters on %lu\n", (unsigned long)rtcStage[0],
                  (unsigned long)rtcStage[1], (unsigned long)rtcStage[2],
                  (unsigned long)rtcStage[3], (unsigned long)rtcStage[4],
                  (unsigned long)rtcStage[5], (unsigned long)rtcHeaterOnMs);
  } else {
    Serial.println("Previous run: no record (power-on).");
  }
  rtcMagic = RTC_DIAG_MAGIC;
  rtcSetupDoneMs = 0;
  rtcLastLoopMs = 0;
  rtcLastSeq = 0;
  // rtcHeaterOnMs was set for this run at the top of setup(); keep it.
  for (int i = 0; i < 6; i++) rtcStage[i] = 0;
  stage(0);
  stage(1);

  if (probeAds()) {
    Serial.println("ADS1115 ready at 0x48 (250 SPS, +/-4.096 V).");
  } else {
    adsState.lastProbeMs = millis();
    Serial.println("ADS1115 not found; taps from ESP32 ADC fallback (GPIO1/2).");
  }
  stage(2);

  if (sht4.begin(&Wire)) {
    // Medium precision: ~4.5 ms blocking per read, well inside the ADS1115's
    // 20 ms RDY timeout. No internal heater -- it would bias humidity.
    sht4.setPrecision(SHT4X_MED_PRECISION);
    sht4.setHeater(SHT4X_NO_HEATER);
    shtReady = true;
    Serial.printf("SHT40 ready at 0x44 (serial 0x%08lX).\n", (unsigned long)sht4.readSerial());
  } else {
    Serial.println("SHT40 not found (0x44); environment fields sent as missing.");
  }
  stage(3);

  initBle();
  stage(4);
  Serial.printf("BLE advertising as %s\n", deviceName);
  Serial.println(CSV_HEADER);
  stage(5);

  setupDoneMs = millis();
  rtcSetupDoneMs = setupDoneMs;
  nextSampleMs = setupDoneMs + sampleIntervalMs.load();
}

static uint32_t loopIterations = 0;

void loop() {
  uint32_t nowMs = millis();
  loopIterations++;
  rtcLastLoopMs = nowMs;
  rtcLastSeq = seq;

  // Bench diagnostic: when a USB host opens the port, say how long the loop
  // has already been running so a stall without a host is visible.
  static bool hostWasConnected = false;
  bool hostConnected = (bool)Serial;
  if (hostConnected && !hostWasConnected) {
    Serial.printf("USB host connected at %lu ms: setup done at %lu ms, %lu loop iterations, seq %u\n",
                  (unsigned long)nowMs, (unsigned long)setupDoneMs, (unsigned long)loopIterations,
                  seq);
  }
  hostWasConnected = hostConnected;

  serviceButton(nowMs);
  serviceAds(nowMs);
  serviceLed(nowMs);

  // Apply a newly shortened interval now rather than after the old deadline.
  if ((int32_t)(nextSampleMs - nowMs) > (int32_t)sampleIntervalMs.load()) {
    nextSampleMs = nowMs + sampleIntervalMs.load();
  }

  if ((int32_t)(nowMs - nextSampleMs) >= 0) {
    emitSample(nowMs);
    uint16_t interval = sampleIntervalMs.load();
    nextSampleMs += interval;
    // Fell behind, or the interval just shrank: resynchronise rather than burst.
    if ((int32_t)(nowMs - nextSampleMs) >= 0 || nextSampleMs - nowMs > interval) {
      nextSampleMs = nowMs + interval;
    }
  }

  delay(1);  // yield; a conversion takes ~4 ms, so 1 ms granularity is plenty
}
