// Phone-companion board firmware (hardware/board, and the MEMS test rig
// hardware/board_mems with HW_MEMS): a thin BLE sampler.
//
// docs/phone_board.md is the source of truth for everything this file
// implements (pin map, ADS1115 channels, BLE UUIDs, packet layout, Info JSON,
// Control opcodes). Change the spec first, then this file.
//
// What it does, and deliberately does not do
// ------------------------------------------
// The phone app does the baseline, classification, display, position and storage.
// The firmware only:
//   1. reads the two bare Figaro sensor load-resistor taps on the ADS1115, VBAT and
//      the heater rail on the ESP32's ADC, and temperature/humidity on the SHT40 (there is no
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
// Whenever the ADS1115 is absent (or lost) there is no backup reading of the
// CH4/LPG taps: they read 0 and flag bit3 is cleared. VBAT and the heater rail
// are on the ESP32's own ADC (GPIO1/GPIO2, oversampled, calibrated
// analogReadMilliVolts), so they and the heater check (bit4) keep working.
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
// Anomaly detector (lib/anomaly, docs/REPORT.md)
// ------------------------------------------------
// The one exception to "no processing here": each sample also goes through the
// gas anomaly detector, which predicts each gas channel from temperature and
// humidity (and airflow / CO when fitted) and flags departures from that
// prediction. Its per-sample result goes out on the Analysis characteristic just
// before the Sample notification, and a closed event's fingerprint on the Event
// characteristic. The app logs both. The detector runs once the heaters have been
// on for WARMUP_MS with good ADS1115 and T/RH readings.
//
// Optional hardware (docs/HARDWARE.md), selected with build flags in
// platformio.ini, off by default:
//   HW_AIRFLOW      the air blade's heated thermistor, on the ADS1115's AIN2.
//   HW_AIRFLOW_REF  an unheated reference thermistor on AIN3 for the ambient
//                   temperature.
//   HW_CO           Winsen ZE15-CO (or ZE07-CO) electrochemical CO module on UART (TP2 =
//                   GPIO44 receives its TX), powered from +5V_HTR (TP6).
//   HW_MEMS         the MEMS test rig (hardware/board_mems): the board plus a plug-in
//                   MEMS blade on J5 with two MEMS gas sensors, mems_a on the first
//                   ADS1115's AIN3 and mems_b on the second's AIN3 (both at +/-2.048 V).
//                   Built with ANOM_NCH = 4, so the detector runs four channels. The blade is detected by its tap voltages (no
//                   blade: the 1M pull-ups lift both past full scale). Its heaters
//                   (GPIO12) come on MEMS_STAGGER_MS after the Figaro heaters, only with
//                   a blade fitted, and the MEMS channels count once MEMS_WARMUP_MS has
//                   passed. Extra readings go out on the Gas2 characteristic and at the
//                   end of the CSV line. Build env `board_mems`.
// The board (hardware/board) reads VBAT and the heater rail on GPIO1 / GPIO2, and a
// second ADS1115 (0x49) reads each heater's current through a 0.5 ohm shunt and the
// 3V3 rail. Build env `board`.
// The on-board SHT40 reads air inside the case. The air blade (hardware/air_blade)
// carries a second SHT40 (0x45 or 0x46) out in the air at the inlet: when it answers, it
// supplies "the" temperature and humidity. Without it, HW_AIRFLOW_REF uses the
// reference thermistor (out in the air) for the temperature and the on-board SHT40's
// water content (absolute humidity, unchanged by the case warming the air),
// re-expressed as RH at that temperature. Either way the on-board readings are still
// logged as the case reading.
// The model only uses airflow or CO once ANOM_USE_AIRFLOW / ANOM_USE_CO are set
// and refitted coefficients are in lib/anomaly/anomaly_config.h; until then the
// readings are logged only.
//
// LED (WS2812B/SK6812 on GPIO38, standard GRB): slow dim blue breathe while advertising; solid dim cyan once
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
#include <Preferences.h>

#include "anomaly.h"

#ifndef HW_AIRFLOW
#define HW_AIRFLOW 0
#endif
#ifndef HW_AIRFLOW_REF
#define HW_AIRFLOW_REF 0
#endif
#ifndef HW_CO
#define HW_CO 0
#endif
#ifndef HW_MEMS
#define HW_MEMS 0
#endif
#if HW_MEMS && ANOM_NCH != 4
#error "HW_MEMS needs ANOM_NCH=4"
#endif
#if HW_MEMS && HW_AIRFLOW_REF
#error "HW_MEMS uses the ADS1115's AIN3, which HW_AIRFLOW_REF wants"
#endif

static const char *FW_VERSION = "1.1.0";
// Sent in the Info JSON and the CSV banner; the app, tools/serial_bridge.py and logged
// surveys know these values, so they stay as they are.
static const char *BOARD_ID = HW_MEMS ? "rev-f" : "rev-e";

// ---- Pins (docs/phone_board.md, ESP32-S3-MINI-1-N8 pin map) -----------------
static const uint8_t PIN_BOOT_BUTTON = 0;   // active low, tact switch to GND
static const uint8_t PIN_CHG_N = 5;         // BQ24073 CHG, low = charging
static const uint8_t PIN_PGOOD_N = 6;       // BQ24073 PGOOD, low = USB power good
static const uint8_t PIN_HTR_EN = 7;        // 100k pull-down: drive HIGH = heaters on, LOW = off
static const uint8_t PIN_I2C_SDA = 8;
static const uint8_t PIN_I2C_SCL = 9;
static const uint8_t PIN_ADS_RDY = 10;      // ADS1115 ALERT/RDY, active low
static const uint8_t PIN_LED_DIN = 38;      // WS2812-class status LED
static const uint8_t PIN_VBAT_ADC = 1;      // VBAT / 2 (1M/1M + 100 nF)
static const uint8_t PIN_HTR_ADC = 2;       // +5V_HTR / 2 (100k/100k + 100 nF)
static const uint8_t PIN_CO_RX = 44;        // HW_CO: RXD0 test pad TP2 <- module TX
static const uint8_t PIN_CO_TX = 43;        // TXD0 test pad TP1 (left unconnected)
static const uint8_t PIN_MEMS_HTR_EN = 12;  // MEMS rig: MEMS heater P-FET, HIGH = on, 100k pull-down

// ---- I2C devices ---------------------------------------------------------------
static const uint32_t I2C_CLOCK_HZ = 400000;  // both parts are fast-mode capable
static const uint8_t ADS1115_ADDR = 0x48;
// SHT40-AD1B is fixed at 0x44 (the Adafruit driver hard-codes it).

// ---- Analogue front end (must match Info JSON and the schematic) --------------
static const uint32_t RL_OHM = 40000;      // RLa + RLb (20k + 20k)
static const float TAP_RATIO = 2.0f;       // VRL = 2 x tap
static const uint16_t VC_MV = 5000;        // nominal sensor circuit voltage
static const float VBAT_RATIO = 2.0f;      // 1M/1M on GPIO1
static const float HEATER_RATIO = 2.0f;    // 100k/100k on GPIO2

// ---- second ADS1115 (heater currents, 3V3 rail) -----------------------
static const uint8_t ADS2_ADDR = 0x49;           // ADDR to VDD
static const float HEATER_SHUNT_OHM = 0.5f;      // R22 (CH4) / R25 (LPG), low side
static const float ADS2_SHUNT_MV_PER_COUNT = 0.0078125f;  // GAIN_SIXTEEN, +/-0.256 V
static const float ADS2_RAIL_MV_PER_COUNT = 0.125f;       // GAIN_ONE, +/-4.096 V
static const float RAIL_RATIO = 2.0f;            // 100k/100k on AIN2
static const uint16_t HEATER_MIN_MV = 4800;  // bit4 if outside this window
static const uint16_t HEATER_MAX_MV = 5200;

// ---- MEMS rig: MEMS blade (two MEMS gas sensors on J5) ------------------------------
// Each sensor: +3V3 -> Rs -> node N -> R -> tap T -> R -> GND (RL = 2R); the ADC reads
// T, which also has a 1M pull-up to +3V3 on the main board (blade detection). Rs is
// solved exactly with the pull-up (memsRsOhm). R: mems_a (SY-CH4-37BPM) 10k, mems_b
// (MiCS-5524) 100k.
static const float MEMS_A_R_OHM = 10000.0f;
static const float MEMS_B_R_OHM = 100000.0f;
static const float MEMS_PULLUP_OHM = 1000000.0f;
static const float MEMS_TAP_RATIO = 2.0f;           // VRL = 2 x tap, as for the Figaros
static const float ADS_MEMS_MV_PER_COUNT = 0.0625f;  // GAIN_TWO, +/-2.048 V
static const float MEMS_VC_FALLBACK_MV = 3300.0f;   // when the 3V3 rail is not measured
// No blade: the pull-up lifts the tap past GAIN_TWO's full scale. A fitted blade gives
// at most ~1.73 V (mems_b, Rs -> 0). Fitted <=> both taps below this.
static const float MEMS_BLADE_MAX_MV = 1850.0f;
#ifndef MEMS_STAGGER_MS
#define MEMS_STAGGER_MS 5000  // MEMS heaters on this long after the Figaro boost
#endif
#ifndef MEMS_WARMUP_MS
#define MEMS_WARMUP_MS 3600000  // the 37BPM datasheet asks for >= 60 min before measuring
#endif
#ifndef MEMS_BURNIN_H
#define MEMS_BURNIN_H 48  // cumulative heater-on hours before the MEMS data is trusted
#endif
static const uint32_t MEMS_BURNIN_SAVE_MS = 600000;  // NVS write at most every 10 min
static const uint32_t ADS2_MEMS_CONV_US = 4600;      // 250 SPS conversion, polled after this
static const uint32_t ADS2_MEMS_TIMEOUT_US = 20000;

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

// ---- Anomaly detector ------------------------------------------------------------
// Same warm-up as the app's heaterWarmupMs: no detection while the elements settle.
static const uint32_t WARMUP_MS = 180000;

// ---- Airflow thermistor (docs/HARDWARE.md) ----------------------------------------
// Heated thermistor: the air blade carries a Murata NCP18XQ102 (1k, B25/50 3650 K),
// fed through 1k from +3V3: about 2.7 mW, roughly 1 K above the air. A hand-wired cheap
// 1k bead works the same; set beta_k from its listing (it barely changes the index).
// The survey analysis (docs/REPORT.md 3) found a slow bead does as well as a fast one.
// For the Amphenol BR16PA202K instead: series 3900, r25 2000, beta about 3500.
static const anom_thermistor AIRFLOW_BEAD_DEFAULT = {
    /*supply_mv*/ 3300.0f, /*series_ohm*/ 1000.0f, /*r25_ohm*/ 1000.0f,
    /*beta_k*/ 3650.0f, /*g_still_mw_k*/ 0.0f, /*min_rise_k*/ 0.2f};
// Reference: TDK B57540G1104F000 (100k, B25/100 4092 K) with 220k from +3V3.
static const float REF_SERIES_OHM = 220000.0f;
static const float REF_R25_OHM = 100000.0f;
static const float REF_BETA_K = 4092.0f;
static const uint8_t AIRFLOW_OVERSAMPLE = 64;
static const uint8_t AIRFLOW_CAL_DEFAULT_S = 60;

// ---- CO module (Winsen ZE15-CO / ZE07-CO, active upload, 9600 8N1, 1 frame/s) ----
static const uint32_t CO_BAUD = 9600;
static const uint32_t CO_STALE_MS = 3000;  // no valid frame for this long = missing

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
static const char *UUID_ANALYSIS = "6d1a0005-8f3e-4b8a-9c57-2f6c0e3a7b10";
static const char *UUID_EVENT = "6d1a0006-8f3e-4b8a-9c57-2f6c0e3a7b10";
#if HW_MEMS
static const char *UUID_GAS2 = "6d1a0007-8f3e-4b8a-9c57-2f6c0e3a7b10";  // MEMS rig only
#endif
static const uint8_t ANALYSIS_VERSION = 1;
static const size_t ANALYSIS_PACKET_LEN = 20;
static const size_t EVENT_PACKET_LEN = 20;
static const uint8_t PROTO_VERSION = 2;   // Info JSON "proto" (2: Gas2 may exist)
static const uint8_t SAMPLE_VERSION = 1;  // Sample packet byte 0, unchanged since proto 1
static const size_t SAMPLE_PACKET_LEN = 20;
static const uint8_t GAS2_VERSION = 1;
static const size_t GAS2_PACKET_LEN = 20;
// Requested connection parameters (units: 1.25 ms, 1.25 ms, events, 10 ms).
static const uint16_t CONN_MIN_INTERVAL = 36;  // 45 ms
static const uint16_t CONN_MAX_INTERVAL = 60;  // 75 ms
static const uint16_t CONN_LATENCY = 0;
static const uint16_t CONN_TIMEOUT = 500;      // 5 s

static const uint8_t OP_SET_INTERVAL = 0x01;
static const uint8_t OP_IDENTIFY = 0x02;
static const uint8_t OP_SET_LED = 0x03;
static const uint8_t OP_CALIBRATE_AIRFLOW = 0x04;

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
static std::atomic<uint8_t> calibrateRequestS{0};  // opcode 0x04: seconds, 0 = none
static std::atomic<float> airflowGStill{0.0f};     // still-air conductance, mW/K

static NimBLECharacteristic *sampleChar = nullptr;
static NimBLECharacteristic *infoChar = nullptr;
// Where "the" temperature and humidity come from (Info JSON "t_src"): 0 the on-board
// SHT40 (case air), 1 the reference thermistor + case humidity, 2 the air blade's SHT40.
static std::atomic<uint8_t> tSrcFlag{0};
static NimBLECharacteristic *analysisChar = nullptr;
static NimBLECharacteristic *eventChar = nullptr;
static std::atomic<bool> analysisNotify{false};
static std::atomic<bool> eventNotify{false};
#if HW_MEMS
static NimBLECharacteristic *gas2Char = nullptr;
static std::atomic<bool> gas2Notify{false};
static std::atomic<uint8_t> memsBladeFlag{0};   // Info JSON "mems"
static std::atomic<uint32_t> memsBurnH{0};      // Info JSON "mems_burnin_h"
#endif
static char deviceName[16];

// =================================================================================
// Sensors
// =================================================================================
static Adafruit_ADS1115 ads;
static Adafruit_SHT4x sht4;
static bool shtReady = false;
// Air blade: a second SHT40 on the same bus, out in the air at the inlet. Either
// an SHT40-BD1B (0x45) or an SHT40-CD1B (0x46), whichever JLC had in stock; never an
// AD1B, which is 0x44 like the on-board one. Probed at start-up in that order.
// The Adafruit library only talks to 0x44, so it is read directly (Sensirion: command
// 0xF6 = medium precision, about 5 ms; 6 bytes back, each word followed by a CRC-8).
static const uint8_t SHT_BLADE_ADDRS[] = {0x45, 0x46};
static uint8_t shtBladeAddr = 0x45;  // the one that answered
static bool shtBladeReady = false;

static uint8_t sht4Crc(const uint8_t *d) {
  uint8_t crc = 0xFF;
  for (int i = 0; i < 2; i++) {
    crc ^= d[i];
    for (int b = 0; b < 8; b++) crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
  }
  return crc;
}

static bool readBladeSht(float *t, float *h) {
  Wire.beginTransmission(shtBladeAddr);
  Wire.write(0xF6);
  if (Wire.endTransmission() != 0) return false;
  delay(6);
  if (Wire.requestFrom((int)shtBladeAddr, 6) != 6) return false;
  uint8_t b[6];
  for (int i = 0; i < 6; i++) b[i] = Wire.read();
  if (sht4Crc(b) != b[2] || sht4Crc(b + 3) != b[5]) return false;
  *t = -45.0f + 175.0f * (float)((b[0] << 8) | b[1]) / 65535.0f;
  float rh = -6.0f + 125.0f * (float)((b[3] << 8) | b[4]) / 65535.0f;
  *h = rh < 0.0f ? 0.0f : (rh > 100.0f ? 100.0f : rh);
  return true;
}

static const uint16_t ADS_MUX[4] = {
    ADS1X15_REG_CONFIG_MUX_SINGLE_0,  // AIN0 CH4 tap
    ADS1X15_REG_CONFIG_MUX_SINGLE_1,  // AIN1 LPG tap
    ADS1X15_REG_CONFIG_MUX_SINGLE_2,  // AIN2 heated thermistor
    ADS1X15_REG_CONFIG_MUX_SINGLE_3,  // AIN3 reference thermistor (or MEMS sensor A)
};
enum AdsChannel { ADS_CH4 = 0, ADS_LPG = 1 };
static const int ADS_TH_HOT = 2;
static const int ADS_TH_REF = 3;
// MEMS rig: AIN3 reads the MEMS blade's sensor A tap instead (GAIN_TWO).
static const int ADS_MEMS_A = 3;

// Sum of raw counts per channel since the last sample was emitted.
struct AdsAccumulator {
  int32_t sum;
  uint16_t count;
};

static Adafruit_ADS1115 ads2;
static bool ads2Ok = false;

struct Ads2Reading {
  float ch4HtrMa, lpgHtrMa, railMv;  // NAN when unknown
  float memsBMv;                     // MEMS rig: window mean of the mems_b tap, NAN when unknown
};

#if HW_MEMS
// MEMS rig: the mems_b tap (AIN3) is converted in the background between samples, 250 SPS
// single-shot like the first ADS1115, and averaged over the sample window like the
// Figaro taps. readAds2() takes the chip over once per sample, so it first lets any
// conversion in progress finish (a new single-shot request is ignored mid-conversion).
static bool memsBBusy = false;
static uint32_t memsBStartUs = 0;
static AdsAccumulator memsBAcc = {0, 0};

static void collectMemsB() {
  int16_t raw = ads2.getLastConversionResults();
  if (raw < 0) raw = 0;
  memsBAcc.sum += raw;
  memsBAcc.count++;
}

static void serviceMemsB() {
  if (!ads2Ok) return;
  if (!memsBBusy) {
    ads2.setGain(GAIN_TWO);
    ads2.setDataRate(RATE_ADS1115_250SPS);
    ads2.startADCReading(ADS1X15_REG_CONFIG_MUX_SINGLE_3, /*continuous=*/false);
    memsBStartUs = micros();
    memsBBusy = true;
    return;
  }
  uint32_t elapsedUs = micros() - memsBStartUs;
  if (elapsedUs < ADS2_MEMS_CONV_US) return;
  if (ads2.conversionComplete()) {
    collectMemsB();
    memsBBusy = false;
  } else if (elapsedUs >= ADS2_MEMS_TIMEOUT_US) {
    memsBBusy = false;  // lost conversion: start another
  }
}

// Let a conversion in progress finish and keep it, so the chip is idle.
static void finishMemsB() {
  if (!memsBBusy) return;
  while (micros() - memsBStartUs < ADS2_MEMS_TIMEOUT_US) {
    if (ads2.conversionComplete()) {
      collectMemsB();
      break;
    }
    delayMicroseconds(200);
  }
  memsBBusy = false;
}
#endif

// Blocking single-shot reads at 860 SPS (~1.2 ms each), once per sample.
static Ads2Reading readAds2() {
  Ads2Reading r = {NAN, NAN, NAN, NAN};
  if (!ads2Ok) return r;
#if HW_MEMS
  finishMemsB();
  if (memsBAcc.count > 0) r.memsBMv = (float)memsBAcc.sum / memsBAcc.count * ADS_MEMS_MV_PER_COUNT;
  memsBAcc = {0, 0};
  ads2.setDataRate(RATE_ADS1115_860SPS);
#endif
  ads2.setGain(GAIN_SIXTEEN);
  int16_t a0 = ads2.readADC_SingleEnded(0);
  int16_t a1 = ads2.readADC_SingleEnded(1);
  ads2.setGain(GAIN_ONE);
  int16_t a2 = ads2.readADC_SingleEnded(2);
  r.ch4HtrMa = a0 * ADS2_SHUNT_MV_PER_COUNT / HEATER_SHUNT_OHM;
  r.lpgHtrMa = a1 * ADS2_SHUNT_MV_PER_COUNT / HEATER_SHUNT_OHM;
  r.railMv = a2 * ADS2_RAIL_MV_PER_COUNT * RAIL_RATIO;
  return r;
}

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
#if HW_MEMS
    // The MEMS tap (AIN3) is read at +/-2.048 V; the gain goes out with each request.
    ads.setGain(adsState.channel == ADS_MEMS_A ? GAIN_TWO : GAIN_ONE);
#endif
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
      float mvPerCount = (HW_MEMS && i == ADS_MEMS_A) ? ADS_MEMS_MV_PER_COUNT : ADS_MV_PER_COUNT;
      adsState.lastMv[i] = (float)a.sum / a.count * mvPerCount;
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
  // About 200 characters (MEMS rig about 235). The closing brace goes on last, so should
  // it ever overflow the app gets invalid JSON rather than a silently cut-short object.
  char json[320];
  int n = snprintf(json, sizeof(json),
                   "{\"proto\":%u,\"fw\":\"%s\",\"board\":\"%s\",\"rl_ohm\":%lu,"
                   "\"tap_ratio\":%.1f,\"vc_mv\":%u,\"interval_ms\":%u,\"heater_mv\":%u,"
                   "\"anomaly\":1,\"airflow\":%d,\"co\":%d,\"g_still\":%.4f,\"t_src\":%u",
                   PROTO_VERSION, FW_VERSION, BOARD_ID, (unsigned long)RL_OHM, TAP_RATIO,
                   VC_MV, sampleIntervalMs.load(), lastHeaterMv.load(), HW_AIRFLOW ? 1 : 0,
                   HW_CO ? 1 : 0, (double)airflowGStill.load(), (unsigned)tSrcFlag.load());
#if HW_MEMS
  if (n > 0 && (size_t)n < sizeof(json)) {
    n += snprintf(json + n, sizeof(json) - n, ",\"mems\":%u,\"mems_burnin_h\":%lu",
                  (unsigned)memsBladeFlag.load(), (unsigned long)memsBurnH.load());
  }
#endif
  if (n > 0 && (size_t)n + 1 < sizeof(json)) {
    json[n] = '}';
    json[n + 1] = '\0';
  }
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
    analysisNotify = false;
    eventNotify = false;
#if HW_MEMS
    gas2Notify = false;
#endif
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

class AnalysisCallbacks : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic *chr, NimBLEConnInfo &info,
                   uint16_t subValue) override {
    analysisNotify = (subValue & 0x0001) != 0;
  }
};

class EventCallbacks : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic *chr, NimBLEConnInfo &info,
                   uint16_t subValue) override {
    eventNotify = (subValue & 0x0001) != 0;
  }
};

#if HW_MEMS
class Gas2Callbacks : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic *chr, NimBLEConnInfo &info,
                   uint16_t subValue) override {
    gas2Notify = (subValue & 0x0001) != 0;
  }
};
#endif

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
      case OP_CALIBRATE_AIRFLOW:
        calibrateRequestS = (n >= 2 && d[1] > 0) ? d[1] : AIRFLOW_CAL_DEFAULT_S;
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
  analysisChar = svc->createCharacteristic(UUID_ANALYSIS, NIMBLE_PROPERTY::NOTIFY);
  analysisChar->setCallbacks(new AnalysisCallbacks());
  eventChar = svc->createCharacteristic(UUID_EVENT, NIMBLE_PROPERTY::NOTIFY);
  eventChar->setCallbacks(new EventCallbacks());
#if HW_MEMS
  gas2Char = svc->createCharacteristic(UUID_GAS2, NIMBLE_PROPERTY::NOTIFY);
  gas2Char->setCallbacks(new Gas2Callbacks());
#endif
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
    "temp_c,humidity_pct,pressure_hpa,vbat_mv,heater_mv,flags,ble_conn,ble_notify,"
    "airflow_raw,airflow_index,co_raw,ch4_res_mv,lpg_res_mv,ch4_sigma_mv,lpg_sigma_mv,"
    "anomaly_ch4,anomaly_lpg,event_class,event_ratio,ch4_htr_ma,lpg_htr_ma,v3v3_mv,"
    "case_temp_c,case_rh_pct"
#if HW_MEMS
    ",mems_a_tap_mv,mems_b_tap_mv,mems_a_rs_ohm,mems_b_rs_ohm,mems_a_res_mv,"
    "mems_a_sigma_mv,mems_b_res_mv,mems_b_sigma_mv,anomaly_mems_a,anomaly_mems_b,mems_flags"
#endif
    ;

// =================================================================================
// Anomaly detector, airflow thermistor and CO module
// =================================================================================
static anom_state anomState;  // fixed size (~10 kB), no allocation
static uint32_t heaterOnSinceMs = 0;  // when the heaters last came on (warm-up clock)
static Preferences prefs;
static anom_thermistor airflowBead = AIRFLOW_BEAD_DEFAULT;

// Still-air calibration (opcode 0x04): average the bead's conductance.
static bool calRunning = false;
static uint32_t calEndMs = 0;
static double calSum = 0;
static uint32_t calCount = 0;

static float readAdcOversampledMv(uint8_t pin, uint8_t n) {
  uint32_t acc = 0;
  for (uint8_t i = 0; i < n; i++) acc += analogReadMilliVolts(pin);
  return (float)acc / n;
}

// Unheated reference thermistor temperature (degC) from its divider voltage.
static float referenceTempC(float vMv) {
  if (!(vMv > 10.0f) || !(vMv < airflowBead.supply_mv - 10.0f)) return NAN;
  float r = REF_SERIES_OHM * vMv / (airflowBead.supply_mv - vMv);
  return 1.0f / (1.0f / 298.15f + logf(r / REF_R25_OHM) / REF_BETA_K) - 273.15f;
}

#if HW_CO
// Winsen ZE15-CO / ZE07-CO active-upload frame, one a second:
//   FF 04 03 01 CH CL FH FL CS,  ppm = ((CH & 0x1F)*256 + CL) * 0.1,
//   CS = (~(byte1 + ... + byte7)) + 1.
// On the ZE15 bit 7 of CH is a sensor-fault flag; the ZE07 never sets it (its
// 500 ppm full scale fits in the low 5 bits).
static uint8_t coBuf[9];
static uint8_t coLen = 0;
static float coPpm = NAN;
static uint32_t coLastMs = 0;

static void serviceCo(uint32_t nowMs) {
  while (Serial1.available()) {
    uint8_t b = (uint8_t)Serial1.read();
    if (coLen == 0 && b != 0xFF) continue;
    coBuf[coLen++] = b;
    if (coLen < 9) continue;
    coLen = 0;
    uint8_t sum = 0;
    for (int i = 1; i < 8; i++) sum += coBuf[i];
    uint8_t cs = (uint8_t)(~sum + 1);
    if (coBuf[1] == 0x04 && cs == coBuf[8] && !(coBuf[4] & 0x80)) {
      coPpm = (float)(((coBuf[4] & 0x1F) << 8) | coBuf[5]) * 0.1f;
      coLastMs = nowMs;
    }
  }
}
#endif

static int16_t clampI16(float v) {
  if (!(v == v)) return INT16_MIN;
  if (v > 32767.0f) return 32767;
  if (v < -32767.0f) return -32767;
  return (int16_t)lroundf(v);
}

#if HW_MEMS
// MEMS sensor resistance (ohms) from its tap voltage, pull-up included (the app's
// memsRsOhm). NAN when there is no solution (I1 <= 0 or VN >= VC) or no reading.
static float memsRsOhm(float tapMv, float vcMv, float rOhm) {
  if (!(tapMv == tapMv)) return NAN;
  float i1 = tapMv / rOhm - (vcMv - tapMv) / MEMS_PULLUP_OHM;  // mA
  if (!(i1 > 0.0f)) return NAN;
  float vn = tapMv + rOhm * i1;
  if (vn >= vcMv) return NAN;
  return (vcMv - vn) / i1;
}

// Gas2 fields: 0xFFFF (u16) / 0x7FFF (i16) mean missing, so real values stop short.
static uint16_t gas2U16(float v, bool ok) {
  if (!ok || !(v == v)) return 0xFFFF;
  uint16_t u = clampU16(v);
  return u == 0xFFFF ? 0xFFFE : u;
}
static uint16_t gas2I16(float v, bool ok) {
  if (!ok || !(v == v)) return 0x7FFF;
  if (v > 32766.0f) v = 32766.0f;
  if (v < -32768.0f) v = -32768.0f;
  return (uint16_t)(int16_t)lroundf(v);
}
#endif

// Low-battery heater cutoff. HTR_EN (GPIO7) is the boost enable with a 100k
// pull-down on the board: HIGH = heaters on, LOW = heaters off. Heaters go
// off once VBAT has stayed below HEATER_CUTOFF_MV for HEATER_CUTOFF_HOLD_MS and
// come back only above HEATER_RESTORE_MV. An unknown VBAT (0, no ADS1115)
// neither starts the timer nor restores the heaters.
static bool heatersOffLowBatt = false;
static bool heatersEnabled = false;  // set once setup() has driven HTR_EN high
static uint32_t vbatLowSinceMs = 0;
static bool vbatLowTiming = false;

#if HW_MEMS
// MEMS blade heaters (PIN_MEMS_HTR_EN, 100k pull-down: off until driven HIGH).
// They run from +5V_HTR, so they only get power while HTR_EN is high anyway; the pin
// still goes low whenever HTR_EN does. On again MEMS_STAGGER_MS after HTR_EN comes back
// (heaterOnSinceMs), so the boost never starts into all four heaters at once.
static bool memsBlade = false;            // blade fitted (tap test)
static bool memsHeaterOn = false;
static uint32_t memsHeaterOnSinceMs = 0;  // MEMS warm-up clock
// Burn-in: cumulative MEMS heater-on time, kept in NVS ("mems_burn_s").
static uint32_t memsBurnS = 0;
static uint32_t memsBurnRemMs = 0;
static uint32_t memsBurnSavedS = 0;
static uint32_t memsBurnSaveMs = 0;
static uint32_t memsBurnLastMs = 0;

static void setMemsHeater(bool on, uint32_t nowMs) {
  if (on == memsHeaterOn) return;
  memsHeaterOn = on;
  digitalWrite(PIN_MEMS_HTR_EN, on ? HIGH : LOW);
  if (on) memsHeaterOnSinceMs = nowMs;
  Serial.printf("MEMS heaters %s.\n", on ? "on" : "off");
}

// Tap test: fitted <=> both taps below MEMS_BLADE_MAX_MV. A missing reading keeps the
// last answer rather than dropping the heaters (and the hour of warm-up) on an I2C hiccup.
static void updateMemsBlade(float aMv, float bMv) {
  if (!(aMv == aMv) || !(bMv == bMv)) return;
  bool fitted = aMv < MEMS_BLADE_MAX_MV && bMv < MEMS_BLADE_MAX_MV;
  if (fitted == memsBlade) return;
  memsBlade = fitted;
  memsBladeFlag = fitted ? 1 : 0;
  Serial.printf("MEMS blade %s (taps %.0f / %.0f mV).\n", fitted ? "fitted" : "not fitted",
                (double)aMv, (double)bMv);
  if (infoChar) refreshInfo();
}

// Once per sample, after the low-battery cutoff and the blade check.
static void serviceMemsHeater(uint32_t nowMs) {
  if (memsHeaterOn) {
    memsBurnRemMs += nowMs - memsBurnLastMs;
    memsBurnS += memsBurnRemMs / 1000;
    memsBurnRemMs %= 1000;
  }
  memsBurnLastMs = nowMs;
  memsBurnH = memsBurnS / 3600;
  if (memsBurnS != memsBurnSavedS && nowMs - memsBurnSaveMs >= MEMS_BURNIN_SAVE_MS) {
    prefs.putUInt("mems_burn_s", memsBurnS);
    memsBurnSavedS = memsBurnS;
    memsBurnSaveMs = nowMs;
  }
  bool figaroOn = heatersEnabled && !heatersOffLowBatt;
  setMemsHeater(figaroOn && memsBlade &&
                    (int32_t)(nowMs - heaterOnSinceMs) >= (int32_t)MEMS_STAGGER_MS,
                nowMs);
}
#endif

static void driveHeaterPin() {
  digitalWrite(PIN_HTR_EN, (heatersEnabled && !heatersOffLowBatt) ? HIGH : LOW);
#if HW_MEMS
  if (!(heatersEnabled && !heatersOffLowBatt)) setMemsHeater(false, 0);
#endif
}

static void setHeatersOff(bool off) {
  // Heaters coming back on start the warm-up clock again (the elements are cold).
  if (heatersOffLowBatt && !off) heaterOnSinceMs = millis();
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
  } else {
    // GPIO1/2 read VBAT and the heater rail, so there is no fallback gas reading.
    ch4Mv = 0.0f;
    lpgMv = 0.0f;
  }
  // VBAT and the heater rail are on the ESP32's own ADC, always available.
  vbatMv = clampU16(readFallbackMv(PIN_VBAT_ADC) * VBAT_RATIO);
  bool heaterKnown = true;
  float heaterRailMv = readFallbackMv(PIN_HTR_ADC) * HEATER_RATIO;
  updateHeaterCutoff(nowMs, vbatMv, digitalRead(PIN_PGOOD_N) == LOW);
  if (heatersOffLowBatt) flags |= FLAG_HEATERS_OFF;
  if (heaterKnown) {
    heaterMv = clampU16(heaterRailMv);
    // A dead rail is expected while we hold the heaters off; not a fault.
    if (heatersEnabled && !heatersOffLowBatt &&
        (heaterMv < HEATER_MIN_MV || heaterMv > HEATER_MAX_MV)) {
      flags |= FLAG_HEATER_FAULT;
    }
  }
  lastHeaterMv = heaterMv;

  Ads2Reading a2 = readAds2();
  // The thermistor dividers run from +3V3: use the measured rail when we have it.
  airflowBead.supply_mv = (a2.railMv > 2900.0f && a2.railMv < 3700.0f) ? a2.railMv : 3300.0f;
#if HW_MEMS
  // MEMS blade: window-mean taps (mV at the ADC pin), blade check, heaters, and Rs
  // against the measured 3V3 rail.
  float memsAMv = (adsState.ok && adsState.haveMv[ADS_MEMS_A]) ? adsState.lastMv[ADS_MEMS_A] : NAN;
  float memsBMv = a2.memsBMv;
  updateMemsBlade(memsAMv, memsBMv);
  serviceMemsHeater(nowMs);
  bool memsWarm = memsHeaterOn && (int32_t)(nowMs - memsHeaterOnSinceMs) >= (int32_t)MEMS_WARMUP_MS;
  bool memsBurnedIn = memsBurnS >= (uint32_t)MEMS_BURNIN_H * 3600u;
  float memsVcMv = (a2.railMv > 2900.0f && a2.railMv < 3700.0f) ? a2.railMv : MEMS_VC_FALLBACK_MV;
  float memsARs = memsRsOhm(memsAMv, memsVcMv, MEMS_A_R_OHM);
  float memsBRs = memsRsOhm(memsBMv, memsVcMv, MEMS_B_R_OHM);
#endif

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
  // The on-board SHT40 reads the air inside the case, warmed by the heaters. Better
  // sources supply "the" temperature and humidity when present, and the on-board
  // reading is logged as the case reading (see tSrcFlag):
  //   2  the air blade: an SHT40 out in the air at the inlet;
  //   1  the reference thermistor out in the air (HW_AIRFLOW_REF) for the temperature,
  //      with the case air's water content (absolute humidity, which warming does not
  //      change) re-expressed as RH at that temperature.
  float caseT = t, caseH = h;
  float refC = NAN;
  uint8_t tSrc = 0;
  if (shtBladeReady) {
    float bt, bh;
    if (readBladeSht(&bt, &bh)) {
      t = bt;
      h = bh;
      tSrc = 2;
    }
  }
#if HW_AIRFLOW_REF
  refC = (fromAds && adsState.haveMv[ADS_TH_REF]) ? referenceTempC(adsState.lastMv[ADS_TH_REF]) : NAN;
  if (tSrc == 0 && refC >= -30.0f && refC <= 70.0f && caseT == caseT && caseH == caseH) {
    float rh = 100.0f * anom_abs_humidity(caseT, caseH) / anom_abs_humidity(refC, 100.0f);
    t = refC;
    h = rh > 100.0f ? 100.0f : rh;
    tSrc = 1;
  }
#endif
  if (tSrc != tSrcFlag.load()) {
    tSrcFlag = tSrc;
    if (infoChar) refreshInfo();
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

  // ---- Airflow thermistor and CO ------------------------------------------------
  float airflowRawMv = 0.0f, airflowIdx = 0.0f;
  uint8_t airflowOk = 0;
#if HW_AIRFLOW
  airflowRawMv = (fromAds && adsState.haveMv[ADS_TH_HOT]) ? adsState.lastMv[ADS_TH_HOT] : 0.0f;
  // Ambient for the heated thermistor: the air blade's SHT40 right beside it, else the
  // reference thermistor, else the on-board SHT40.
  float ambientC = t;
#if HW_AIRFLOW_REF
  if (tSrc != 2) ambientC = refC;
#endif
  if (ambientC == ambientC) {
    airflowBead.g_still_mw_k = airflowGStill.load();
    airflowIdx = anom_airflow_index(&airflowBead, airflowRawMv, ambientC, &airflowOk);
    uint8_t gOk = 0;
    float g = anom_thermistor_conductance(&airflowBead, airflowRawMv, ambientC, &gOk);
    uint8_t req = calibrateRequestS.exchange(0);
    if (req) {
      calRunning = true;
      calEndMs = nowMs + (uint32_t)req * 1000u;
      calSum = 0;
      calCount = 0;
      Serial.printf("Airflow still-air calibration for %u s: keep the board in still air.\n", req);
    }
    if (calRunning) {
      if (gOk) {
        calSum += g;
        calCount++;
      }
      if ((int32_t)(nowMs - calEndMs) >= 0) {
        calRunning = false;
        if (calCount > 0) {
          float gStill = (float)(calSum / calCount);
          airflowGStill = gStill;
          prefs.putFloat("g_still", gStill);
          refreshInfo();
          Serial.printf("Airflow still-air conductance %.4f mW/K from %lu samples (saved).\n",
                        (double)gStill, (unsigned long)calCount);
        } else {
          Serial.println("Airflow calibration failed: no usable thermistor readings.");
        }
      }
    }
  }
#else
  calibrateRequestS = 0;
#endif
  float coPpmNow = NAN;
#if HW_CO
  if (coLastMs != 0 && nowMs - coLastMs <= CO_STALE_MS) coPpmNow = coPpm;
#endif

  // ---- Anomaly detector ------------------------------------------------------------
  anom_input ain = {};
  ain.t_ms = nowMs;
  ain.gas_mv[ANOM_CH4] = ch4Mv * TAP_RATIO;  // VRL, as the app logs it
  ain.gas_mv[ANOM_LPG] = lpgMv * TAP_RATIO;
  ain.temp_c = tOk ? t : 0.0f;
  ain.rh_pct = hOk ? h : 0.0f;
  ain.airflow_index = airflowIdx;
  ain.airflow_ok = airflowOk;
  ain.co_ok = (coPpmNow == coPpmNow) ? 1 : 0;
  ain.co_ppm = ain.co_ok ? coPpmNow : 0.0f;
  bool heatersRunning = heatersEnabled && !heatersOffLowBatt;
  ain.valid = fromAds && tOk && hOk && heatersRunning && nowMs - heaterOnSinceMs >= WARMUP_MS;
#if HW_MEMS
  // MEMS channels in the same units as the Figaros (VRL = 2 x tap). Each counts only with
  // the blade fitted, its heaters on and past warm-up, and a reading this sample.
  bool memsOk = memsBlade && memsHeaterOn && memsWarm;
  ain.gas_mv[ANOM_MEMS_A] = memsAMv == memsAMv ? memsAMv * MEMS_TAP_RATIO : 0.0f;
  ain.gas_mv[ANOM_MEMS_B] = memsBMv == memsBMv ? memsBMv * MEMS_TAP_RATIO : 0.0f;
  if (memsOk && memsAMv == memsAMv) ain.ch_valid |= 1 << ANOM_MEMS_A;
  if (memsOk && memsBMv == memsBMv) ain.ch_valid |= 1 << ANOM_MEMS_B;
#endif
  anom_output aout;
  anom_step(&anomState, &ain, &aout);
#if HW_MEMS
  bool memsAReady = ain.valid && (ain.ch_valid & (1 << ANOM_MEMS_A)) && aout.ch_ready[ANOM_MEMS_A];
  bool memsBReady = ain.valid && (ain.ch_valid & (1 << ANOM_MEMS_B)) && aout.ch_ready[ANOM_MEMS_B];
  uint8_t memsFlags = 0;
  if (aout.anomaly[ANOM_MEMS_A]) memsFlags |= 1 << 0;
  if (aout.anomaly[ANOM_MEMS_B]) memsFlags |= 1 << 1;
  if (memsBlade) memsFlags |= 1 << 2;
  if (memsHeaterOn) memsFlags |= 1 << 3;
  if (memsWarm) memsFlags |= 1 << 4;
  if (memsBurnedIn) memsFlags |= 1 << 5;
#endif

  uint8_t aflags = 0;
  if (aout.anomaly[ANOM_CH4]) aflags |= 1 << 0;
  if (aout.anomaly[ANOM_LPG]) aflags |= 1 << 1;
  if (aout.ready) aflags |= 1 << 2;
  if (aout.suppressed) aflags |= 1 << 3;
  if (aout.event_open) aflags |= 1 << 4;
  if (airflowOk) aflags |= 1 << 5;
  if (ain.co_ok) aflags |= 1 << 6;
  if (calRunning) aflags |= 1 << 7;
  bool aValid = ain.valid && aout.ready;

  bool linkUp = bleConnected.load();
  if (aout.event_closed && linkUp && eventNotify.load()) {
    const anom_event &e = aout.event;
    uint8_t ep[EVENT_PACKET_LEN];
    ep[0] = ANALYSIS_VERSION;
    putU16(ep + 1, e.id);
    ep[3] = (uint8_t)e.cls;
    ep[4] = e.confidence;
    putU16(ep + 5, clampU16((float)(e.t_end_ms - e.t_start_ms) / 100.0f));
    putU16(ep + 7, (uint16_t)clampI16(e.peak_res_mv[ANOM_CH4] * 10.0f));
    putU16(ep + 9, (uint16_t)clampI16(e.peak_res_mv[ANOM_LPG] * 10.0f));
    putU16(ep + 11, clampU16(e.ratio * 100.0f));
    putU16(ep + 13, (uint16_t)(e.lead_known ? clampI16(e.lead_s * 10.0f) : INT16_MIN));
    putU16(ep + 15, (uint16_t)(e.airflow_known ? clampI16(e.airflow_mean * 1000.0f) : INT16_MIN));
    putU16(ep + 17, (uint16_t)(e.co_known ? clampI16(e.co_peak_ppm * 10.0f) : INT16_MIN));
    ep[19] = (uint8_t)((e.raised[ANOM_CH4] ? 1 : 0) | (e.raised[ANOM_LPG] ? 2 : 0) |
                       (e.detected[ANOM_CH4] ? 4 : 0) | (e.detected[ANOM_LPG] ? 8 : 0) |
                       (e.thermal ? 16 : 0) | (e.low_airflow ? 32 : 0));
    eventChar->notify(ep, sizeof(ep));
  }
  if (linkUp && analysisNotify.load()) {
    uint8_t ap[ANALYSIS_PACKET_LEN];
    ap[0] = ANALYSIS_VERSION;
    putU16(ap + 1, seq);
    putU16(ap + 3, (uint16_t)(aValid ? clampI16(aout.res_mv[ANOM_CH4] * 10.0f) : INT16_MIN));
    putU16(ap + 5, (uint16_t)(aValid ? clampI16(aout.res_mv[ANOM_LPG] * 10.0f) : INT16_MIN));
    putU16(ap + 7, aValid ? clampU16(aout.sigma_mv[ANOM_CH4] * 100.0f) : 0);
    putU16(ap + 9, aValid ? clampU16(aout.sigma_mv[ANOM_LPG] * 100.0f) : 0);
    putU16(ap + 11, clampU16(airflowRawMv));
    putU16(ap + 13, (uint16_t)(airflowOk ? clampI16(airflowIdx * 1000.0f) : INT16_MIN));
    uint16_t coRaw = 0xFFFF;
    if (ain.co_ok) {
      coRaw = clampU16(coPpmNow * 10.0f);
      if (coRaw == 0xFFFF) coRaw = 0xFFFE;
    }
    putU16(ap + 15, coRaw);
    ap[17] = aflags;
    ap[18] = aout.event_closed ? (uint8_t)aout.event.cls : 0;
    long r10 = aout.event_closed ? lroundf(aout.event.ratio * 10.0f) : 0;
    ap[19] = (uint8_t)(r10 > 255 ? 255 : r10);
    analysisChar->notify(ap, sizeof(ap));
  }

  // 20-byte little-endian packet, layout per docs/phone_board.md.
  uint8_t pkt[SAMPLE_PACKET_LEN];
  pkt[0] = SAMPLE_VERSION;
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

#if HW_MEMS
  // Gas2: the MEMS half of this sample, same seq, right after the Sample packet.
  if (bleConnected.load() && gas2Notify.load()) {
    uint8_t gp[GAS2_PACKET_LEN];
    gp[0] = GAS2_VERSION;
    putU16(gp + 1, seq);
    putU16(gp + 3, gas2U16(memsAMv * 10.0f, true));  // 0.1 mV
    putU16(gp + 5, gas2U16(memsBMv * 10.0f, true));
    putU16(gp + 7, gas2I16(aout.res_mv[ANOM_MEMS_A] * 10.0f, memsAReady));
    putU16(gp + 9, gas2U16(aout.sigma_mv[ANOM_MEMS_A] * 10.0f, memsAReady));
    putU16(gp + 11, gas2I16(aout.res_mv[ANOM_MEMS_B] * 10.0f, memsBReady));
    putU16(gp + 13, gas2U16(aout.sigma_mv[ANOM_MEMS_B] * 10.0f, memsBReady));
    gp[15] = memsFlags;
    putU16(gp + 16, gas2U16(a2.railMv, true));
    putU16(gp + 18, 0);  // reserved
    gas2Char->notify(gp, sizeof(gp));
  }
#endif

  // Bench CSV. Rs uses the nominal VC, as the app does with vc_mv from Info.
  if (Serial) {
    float ch4Vrl = ch4Mv * TAP_RATIO, lpgVrl = lpgMv * TAP_RATIO;
    float ch4Rs = ch4Vrl > 1.0f ? RL_OHM * (VC_MV - ch4Vrl) / ch4Vrl : NAN;
    float lpgRs = lpgVrl > 1.0f ? RL_OHM * (VC_MV - lpgVrl) / lpgVrl : NAN;
    char row[HW_MEMS ? 600 : 440];  // the MEMS rig adds up to ~95 characters
    int n = snprintf(row, sizeof(row), "%lu,%u,%s,%.1f,%.1f,%.0f,%.0f,%.0f,%.0f,",
                     (unsigned long)nowMs, seq, fromAds ? "ads" : "esp", ch4Mv, lpgMv,
                     ch4Vrl, lpgVrl, ch4Rs, lpgRs);
    if (tOk) n += snprintf(row + n, sizeof(row) - n, "%.2f", t);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (hOk) n += snprintf(row + n, sizeof(row) - n, "%.2f", h);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (pOk) n += snprintf(row + n, sizeof(row) - n, "%.1f", p);
    n += snprintf(row + n, sizeof(row) - n, ",%u,%u,0x%02X,%d,%d", vbatMv, heaterMv, flags,
                  bleConnected.load() ? 1 : 0, notifyEnabled.load() ? 1 : 0);
    // Detector fields; blank where unknown.
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (HW_AIRFLOW) n += snprintf(row + n, sizeof(row) - n, "%.1f", (double)airflowRawMv);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (airflowOk) n += snprintf(row + n, sizeof(row) - n, "%.3f", (double)airflowIdx);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (ain.co_ok) n += snprintf(row + n, sizeof(row) - n, "%.1f", (double)coPpmNow);
    if (aValid) {
      n += snprintf(row + n, sizeof(row) - n, ",%.1f,%.1f,%.2f,%.2f",
                    (double)aout.res_mv[ANOM_CH4], (double)aout.res_mv[ANOM_LPG],
                    (double)aout.sigma_mv[ANOM_CH4], (double)aout.sigma_mv[ANOM_LPG]);
    } else {
      n += snprintf(row + n, sizeof(row) - n, ",,,,");
    }
    n += snprintf(row + n, sizeof(row) - n, ",%d,%d,%s,", aout.anomaly[ANOM_CH4],
                  aout.anomaly[ANOM_LPG], aout.event_closed ? anom_class_name(aout.event.cls) : "");
    if (aout.event_closed) n += snprintf(row + n, sizeof(row) - n, "%.2f", (double)aout.event.ratio);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (a2.ch4HtrMa == a2.ch4HtrMa) n += snprintf(row + n, sizeof(row) - n, "%.3f", (double)a2.ch4HtrMa);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (a2.lpgHtrMa == a2.lpgHtrMa) n += snprintf(row + n, sizeof(row) - n, "%.3f", (double)a2.lpgHtrMa);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (a2.railMv == a2.railMv) n += snprintf(row + n, sizeof(row) - n, "%.1f", (double)a2.railMv);
    // Case reading: the on-board SHT40, when something else supplies temp_c.
    bool airSep = tSrc != 0;
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (airSep && caseT == caseT) n += snprintf(row + n, sizeof(row) - n, "%.2f", (double)caseT);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (airSep && caseH == caseH) n += snprintf(row + n, sizeof(row) - n, "%.2f", (double)caseH);
#if HW_MEMS
    // MEMS blade columns, at the end so older parsers keep working.
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (memsAMv == memsAMv) n += snprintf(row + n, sizeof(row) - n, "%.1f", (double)memsAMv);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (memsBMv == memsBMv) n += snprintf(row + n, sizeof(row) - n, "%.1f", (double)memsBMv);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (memsARs == memsARs) n += snprintf(row + n, sizeof(row) - n, "%.0f", (double)memsARs);
    n += snprintf(row + n, sizeof(row) - n, ",");
    if (memsBRs == memsBRs) n += snprintf(row + n, sizeof(row) - n, "%.0f", (double)memsBRs);
    if (memsAReady) {
      n += snprintf(row + n, sizeof(row) - n, ",%.1f,%.2f", (double)aout.res_mv[ANOM_MEMS_A],
                    (double)aout.sigma_mv[ANOM_MEMS_A]);
    } else {
      n += snprintf(row + n, sizeof(row) - n, ",,");
    }
    if (memsBReady) {
      n += snprintf(row + n, sizeof(row) - n, ",%.1f,%.2f", (double)aout.res_mv[ANOM_MEMS_B],
                    (double)aout.sigma_mv[ANOM_MEMS_B]);
    } else {
      n += snprintf(row + n, sizeof(row) - n, ",,");
    }
    snprintf(row + n, sizeof(row) - n, ",%d,%d,0x%02X", aout.anomaly[ANOM_MEMS_A],
             aout.anomaly[ANOM_MEMS_B], memsFlags);
#endif
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
  heaterOnSinceMs = rtcHeaterOnMs;
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
#if HW_MEMS
  // MEMS heaters stay off (the pull-down already holds them) until the blade check and
  // the stagger say otherwise.
  digitalWrite(PIN_MEMS_HTR_EN, LOW);
  pinMode(PIN_MEMS_HTR_EN, OUTPUT);
#endif

  ledWrite(0, 0, LED_BREATHE_MIN);

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_VBAT_ADC, ADC_11db);
  analogSetPinAttenuation(PIN_HTR_ADC, ADC_11db);

  anom_init(&anomState);
  prefs.begin("anom", false);
  airflowGStill = prefs.getFloat("g_still", 0.0f);
#if HW_MEMS
  memsBurnS = prefs.getUInt("mems_burn_s", 0);
  memsBurnSavedS = memsBurnS;
  memsBurnH = memsBurnS / 3600;
#endif
#if HW_CO
  Serial1.begin(CO_BAUD, SERIAL_8N1, PIN_CO_RX, PIN_CO_TX);
#endif

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

  ads2Ok = ads2.begin(ADS2_ADDR, &Wire);
  if (ads2Ok) {
    ads2.setDataRate(RATE_ADS1115_860SPS);
    Serial.println("ADS1115 #2 ready at 0x49 (heater currents, 3V3 rail).");
  } else {
    Serial.println("ADS1115 #2 (0x49) not found; heater currents not logged.");
  }
  if (probeAds()) {
    Serial.println("ADS1115 ready at 0x48 (250 SPS, +/-4.096 V).");
  } else {
    adsState.lastProbeMs = millis();
    Serial.println("ADS1115 not found; taps from ESP32 ADC fallback (GPIO1/2).");
  }
#if HW_MEMS
  // Blade check with the MEMS heaters still off (fitted: mems_a ~15-35 mV, mems_b
  // ~150-300 mV; no blade: both at full scale). Rechecked on every sample.
  {
    float bootA = NAN, bootB = NAN;
    if (adsState.ok) {
      ads.setGain(GAIN_TWO);
      int16_t raw = ads.readADC_SingleEnded(ADS_MEMS_A);
      ads.setGain(GAIN_ONE);
      bootA = (raw < 0 ? 0 : raw) * ADS_MEMS_MV_PER_COUNT;
    }
    if (ads2Ok) {
      ads2.setGain(GAIN_TWO);
      int16_t raw = ads2.readADC_SingleEnded(3);
      bootB = (raw < 0 ? 0 : raw) * ADS_MEMS_MV_PER_COUNT;
    }
    updateMemsBlade(bootA, bootB);
    if (!memsBlade) {
      Serial.printf("MEMS blade not detected (taps %.0f / %.0f mV); MEMS heaters stay off.\n",
                    (double)bootA, (double)bootB);
    }
  }
#endif
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
  for (uint8_t a : SHT_BLADE_ADDRS) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      shtBladeAddr = a;
      shtBladeReady = true;
      Serial.printf("Air blade SHT40 found at 0x%02X: it supplies temp/humidity; on-board = case reading.\n", a);
      break;
    }
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
#if HW_MEMS
  serviceMemsB();
#endif
#if HW_CO
  serviceCo(nowMs);
#endif
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
