// Dual gas sensor bring-up: ESP32-S3-Zero with both Figaro modules, the SSD1306
// OLED and the DFRobot Gravity GNSS (Quectel L76K) sharing the I2C bus. Proves
// the read paths and visualises the signal; the GNSS gives each sample a position
// so the log is a GPS-tagged survey,
// written to a microSD card as well as streamed over the USB serial port.
//
// It samples both modules' VOUT four times a second (every 250 ms) with
// oversampling and plots them on two side-by-side charts. Values are conditioned VOUT in millivolts; for
// reference, both modules read about 2.5 V at their factory alarm concentration.
// This is NOT a calibrated ppm curve, but it is monotonic: higher means more gas.
//
// LEFT chart - raw VOUT. Methane (CH4) is the solid filled area, LP gas (LPG)
// the line on top, and the CH4 adaptive baseline a dotted reference line, so the
// anomaly (rise above local background) shows as the gap above the dots. The
// vertical scale has a fixed lower bound (0) and a dynamic upper bound: the top
// tracks the largest value on screen plus headroom, but never zooms in tighter
// than a floor, so the trace expands for a real signal without blowing small
// noise up to full screen when things are quiet. Because the top is dynamic,
// dashed gridlines every GRID_STEP_MV (1 V) mark the scale; with the bottom fixed
// at 0, counting lines from the bottom reads the magnitude.
//
// RIGHT chart - a long-timebase overview of the CH4 channel: the last 10 minutes
// of VOUT decimated to the column width, one peak-per-column so a brief plume is
// not lost between pixels, with the current baseline drawn as a dotted reference.
// The left chart is the live detail -- its 62 columns span only ~16 s at 250 ms
// -- so the pair reads as detail + overview: the left shows what is happening
// now, the right shows where that sits against the last 10 minutes and catches
// plumes that have already scrolled off the live trace. The overview is on a
// fixed scale (0 to OVERVIEW_MAX_MV, the ~2.5 V factory-alarm level) so it reads
// as a stable absolute reference rather than rescaling, carries the same dashed
// gridlines as the live chart, and is labelled "10m". LPG is left off to keep the
// methane view clean; it could be overlaid the same way.
//
// The CSV (logged to microSD and streamed over USB) carries the raw voltages,
// baselines and deviations, the BME280 environment (temperature, humidity,
// pressure) and the GNSS position (UTC, lat/lon, altitude, satellites, fix) so
// each gas sample is both geotagged and tied to the conditions it was taken in.
// Humidity is the major uncorrected MOX confounder -- the Figaro modules
// compensate temperature internally but not humidity (see docs/sensors.md) -- so
// logging it lets a later reviewer reject anomalies that merely coincide with a
// humidity change.
//
// Sequence after power-on (or a BOOT-button press to re-zero):
//   WARMUP      - ignore readings while the sensor settles
//   BASELINING  - fill the background window before the baseline is trusted
//   RUNNING     - plot VOUT, with the baseline drawn as a dotted line. The
//                 baseline is a low percentile of a rolling VOUT window, so it
//                 tracks slow background drift yet is unmoved by brief positive
//                 plumes (a plume sits in the top of the window, above the
//                 percentile) and recovers on its own -- there is no gate or
//                 freeze state to drift out of sync or lock out.
// The warm-up and baseline windows here are deliberately short for bench
// iteration. Lengthen them for real use; the Figaro "initial action" alone wants
// minutes, not seconds.
//
// Hardware assumed:
//   - Waveshare ESP32-S3-Zero (ESP32-S3FH4R2), native USB CDC
//   - Figaro NGM2611-E13 methane module  -> read on GPIO1 (the CH4 channel)
//   - Figaro LPM2610-D09 LP gas module    -> read on GPIO2 (the LPG channel)
//   - SSD1306 128x64 OLED on I2C
//   - DFRobot Gravity GNSS (Quectel L76K) in I2C mode, sharing the OLED's bus
//   - BME280 temp/humidity/pressure sensor (I2C 0x76), sharing the same bus
//   - Fermion microSD card module (SPI) for on-board CSV logging
//   - BOOT button on GPIO0 used to re-zero the baseline
//   - Onboard WS2812 RGB LED on GPIO21 as a status lamp (no wiring needed): dim
//     blue while warming up/baselining, then green/amber/red for CH4 LOW/MED/HIGH
//
// Wiring (both modules share the 5V and GND rails):
//   - Module VIN  (pin 1) -> 5V rail
//   - Module VOUT (pin 2) -> its ADC pin, via a 10k/10k divider
//                            NGM2611 -> GPIO1, LPM2610 -> GPIO2
//   - Module VREF (pin 3) -> leave unconnected
//   - Module VH-  (pin 4) -> GND rail
//   - Module GND  (pin 5) -> GND rail
//   - OLED SDA -> GPIO6, OLED SCL -> GPIO7, OLED VCC -> 3V3, OLED GND -> GND
//   - GNSS SDA (D/T) -> GPIO6, SCL (C/R) -> GPIO7, + -> 3V3, - -> GND. Shares the
//     OLED's I2C bus; no address clash (OLED 0x3C, GNSS 0x20, BME280 0x76). The
//     bus runs at 100 kHz now that three devices share it.
//   - BME280 SDA -> GPIO6, SCL -> GPIO7, VCC -> 3V3, GND -> GND. Same shared I2C
//     bus, no extra GPIO. 6-pin boards: tie CSB -> 3V3 (I2C mode), SDO -> GND (0x76).
//   - microSD module (its own SPI bus): SCK -> GPIO12, MISO -> GPIO13,
//     MOSI -> GPIO11, CS -> GPIO10, VCC -> 3V3, GND -> GND
//   - Everything shares a common ground.
//
// VOLTAGE WARNING: each module's VOUT can reach ~4.95V, well above the
// ESP32-S3's 3.3V pin limit. Each VOUT must reach its ADC pin through a 10k/10k
// divider so the pin never sees more than ~2.5V. Keep VOUT_DIVIDER_RATIO at 2.0.

#include <Arduino.h>
#include <Wire.h>
#include <U8g2lib.h>
#include "DFRobot_GNSS.h"
#include <Adafruit_BME280.h>  // temp/humidity/pressure on the shared I2C bus
#include <SPI.h>
#include <SD.h>
#include <algorithm>  // std::nth_element for the percentile background

static const char *FW_VERSION = "0.24.0-bme280";

static const uint8_t PIN_I2C_SDA = 6;
static const uint8_t PIN_I2C_SCL = 7;
static const uint8_t PIN_BOOT_BUTTON = 0;
static const uint8_t PIN_STATUS_LED = 21;  // onboard WS2812 RGB LED (no wiring)
// microSD on its own SPI bus (the ESP32-S3 Arduino default SPI pins).
static const uint8_t PIN_SD_SCK = 12;
static const uint8_t PIN_SD_MISO = 13;
static const uint8_t PIN_SD_MOSI = 11;
static const uint8_t PIN_SD_CS = 10;
// 100 kHz: conservative for the I2C bus now shared by the OLED and the GNSS. The
// DFRobot GNSS library is happiest here, and the OLED still refreshes fast enough
// at the 5 Hz sample rate (a full frame is ~90 ms at 100 kHz).
static const uint32_t I2C_CLOCK_HZ = 100000;

static const float VOUT_DIVIDER_RATIO = 2.0f;
static const uint8_t OVERSAMPLE_COUNT = 64;

// The ADC pin saturates near ~3.1 V under ADC_11db (12-bit). With the 10k/10k
// divider fitted, divided VOUT peaks near 2.5 V even at the factory alarm
// concentration, so a pin reading this high does not mean the gas signal is
// clipping -- it means the divider is missing or open and the pin is taking raw
// (undivided) VOUT. Treat it as a wiring alarm. The check is on the averaged ADC
// pin voltage, before VOUT_DIVIDER_RATIO is applied.
static const float PIN_CEILING_MV = 3000.0f;
// Sample / screen-refresh period. Lower for a snappier graph; the practical
// floor is set by the OLED frame time (~90 ms at 100 kHz, shared bus) and the ADC
// oversampling. 250 ms gives a steady 4 Hz update. Note the scrolling chart
// holds GRAPH_W samples, so a faster rate means a shorter time window on screen.
static const uint32_t SAMPLE_INTERVAL_MS = 250;

// Short bench values. Lengthen for real surveys (see file header).
static const uint32_t WARMUP_MS = 15000;
static const uint32_t BASELINE_MS = 30000;

// Rolling-percentile background. The baseline is a low percentile of the last
// BG_WINDOW_MS of VOUT, recomputed every sample. A brief positive plume occupies
// only the top slice of the window, so it does not move a low percentile: the
// background holds through a plume and tracks slow drift between them, with no
// gate or freeze state to drift out of sync or lock out. The window must be long
// relative to a plume crossing (so a plume stays a small fraction of it) but
// short relative to genuine background drift; the percentile sets how much
// positive excursion is rejected -- a plume only starts dragging the baseline up
// once it fills more than (1 - BG_PERCENTILE) of the window. The cost is a
// window-length lag on genuine downward background steps. All three are
// provisional and want field tuning.
static const uint32_t BG_WINDOW_MS = 120000;  // 2 min rolling background window
static const int BG_WINDOW_SAMPLES = BG_WINDOW_MS / SAMPLE_INTERVAL_MS;  // 600 @200ms
static const float BG_PERCENTILE = 0.15f;     // 15th percentile = clean-air background

// HIGH/MED/LOW classification. A separate, longer (10 min) ring of VOUT. The
// current reading is placed between the window's min and max: bottom third LOW,
// middle MED, top HIGH. So the label answers "how gassy is it right now versus
// the last 10 minutes" -- self-scaling, which suits an uncalibrated sensor. A
// range floor keeps a flat, quiet trace reading LOW instead of amplifying noise
// into spurious HIGHs. Window and floor are provisional and want field tuning.
static const uint32_t CLASS_WINDOW_MS = 600000;  // 10 min classification window
static const int CLASS_WINDOW_SAMPLES = CLASS_WINDOW_MS / SAMPLE_INTERVAL_MS;  // 3000 @200ms
static const float CLASS_RANGE_FLOOR_MV = 150.0f;  // min span before thirds mean anything

// Two side-by-side charts sit below the single header line (the HIGH/MED/LOW
// levels). Each is CHART_W samples wide, one sample per pixel column, separated by a gap
// with a vertical divider down the middle. The left chart starts at x=0, the
// right at RIGHT_X0; the divider sits in the gap between them. SCREEN_W is the
// full panel width, used by the warm-up/baseline progress bar.
static const int SCREEN_W = 128;
static const int CHART_W = 62;
static const int CHART_GAP = 4;
static const int LEFT_X0 = 0;
static const int RIGHT_X0 = CHART_W + CHART_GAP;        // 66; right edge 66+61=127
static const int DIVIDER_X = CHART_W + CHART_GAP / 2;   // 64
static const int GRAPH_TOP = 13;  // just below the single header line
static const int GRAPH_BOTTOM = 63;

// Live (left) chart vertical scale, in millivolts of module VOUT. The lower bound
// is a hard floor. The upper bound is dynamic (tracks the largest value on screen
// plus headroom) but never drops below GRAPH_MAX_FLOOR_MV, so a quiet trace does
// not zoom in on noise. Raise the floor to keep the chart calmer, lower it to
// magnify small signals. Provisional value.
static const float GRAPH_MIN_MV = 0.0f;
static const float GRAPH_MAX_FLOOR_MV = 1000.0f;

// The overview (right) chart instead uses a fixed scale from GRAPH_MIN_MV up to
// OVERVIEW_MAX_MV -- the ~2.5 V the modules read at their factory alarm
// concentration -- so it stays a stable absolute reference instead of rescaling
// as data comes and goes. Dashed gridlines every GRID_STEP_MV mark the scale on
// both charts; with the bottom fixed at 0, a line is read by counting up from the
// bottom (1 V, 2 V, ...). Both provisional.
static const float OVERVIEW_MAX_MV = 2500.0f;  // factory-alarm full scale (static)
static const float GRID_STEP_MV = 1000.0f;     // 1 V per dashed gridline

enum State { WARMUP, BASELINING, RUNNING };

// A gas channel: its ADC pin, label, the short VOUT history for the chart, and
// the rolling window the percentile baseline is computed over. GPIO1/GPIO2 are
// both ADC1, which keeps working with Wi-Fi on.
struct GasChannel {
  uint8_t pin;
  const char *label;
  float history[CHART_W];           // absolute VOUT for the chart, mV
  int count;                        // valid samples in the chart history
  float bgRing[BG_WINDOW_SAMPLES];  // rolling raw VOUT, mV, for the percentile
  int bgHead;                       // next write index into bgRing
  int bgCount;                      // valid samples in bgRing (<= window)
  float baselineMv;                 // current background = low percentile of bgRing
  float classRing[CLASS_WINDOW_SAMPLES];  // longer rolling VOUT for HIGH/MED/LOW
  int classHead;                          // next write index into classRing
  int classCount;                         // valid samples in classRing (<= window)
  float lastVoutMv;                 // most recent reading
};

static GasChannel ch4 = {1, "CH4", {0}, 0, {0}, 0, 0, 0, {0}, 0, 0, 0};
static GasChannel lpg = {2, "LPG", {0}, 0, {0}, 0, 0, 0, {0}, 0, 0, 0};

U8G2_SSD1306_128X64_NONAME_F_HW_I2C oled(U8G2_R0, /*reset=*/U8X8_PIN_NONE,
                                         /*clock=*/PIN_I2C_SCL,
                                         /*data=*/PIN_I2C_SDA);

// DFRobot Gravity GNSS on the shared I2C bus. GNSS_DEVICE_ADDR (0x20) is the
// address the Gravity module uses; the library constructor's default (0x75) does
// not match it, so we pass the constant explicitly.
DFRobot_GNSS_I2C gnss(&Wire, GNSS_DEVICE_ADDR);
static bool gnssReady = false;  // set once gnss.begin() acknowledges the device

// One GNSS snapshot, copied out of the library so the chart, the status screen
// and the CSV all work from one consistent reading per poll.
struct GnssReading {
  sTim_t date;    // year, month, date (UTC)
  sTim_t utc;     // hour, minute, second (UTC)
  double lat;     // decimal degrees, +north
  double lon;     // decimal degrees, +east
  double altM;    // metres above mean sea level
  uint8_t sats;   // satellites used in the solution
  bool haveFix;   // inferred; see deriveFix()
};
static GnssReading gps = {};  // latest snapshot (haveFix stays false until a poll)
// The L76K solution updates at ~1 Hz, so polling faster than the gas loop just
// re-reads the same fix; throttle GNSS reads to this period.
static const uint32_t GPS_INTERVAL_MS = 1000;
static uint32_t lastGpsReadMs = 0;
// Anchor for interpolated sub-second timestamps: millis() at which the current
// GNSS whole-second was first observed, and the last second value seen.
static uint32_t gpsSecondMs = 0;
static uint8_t gpsPrevSecond = 255;

// BME280 environment sensor on the shared I2C bus (no extra GPIO). It answers at
// 0x76, or 0x77 if the board's SDO pin is strapped high, so we try both. begin()
// validates the chip id, which is how a BMP280 (pressure + temperature but NO
// humidity) is caught -- it is rejected here rather than silently logging blank
// humidity. If it is absent we carry on logging gas + GNSS only (bmeReady stays
// false), exactly as for a missing card or GNSS.
static const uint8_t BME280_ADDR_PRIMARY = 0x76;
static const uint8_t BME280_ADDR_ALT = 0x77;
static Adafruit_BME280 bme;
static bool bmeReady = false;

// One environment snapshot per sample, so the CSV row works from one consistent
// reading. valid is false until the sensor is up and returns non-NaN readings.
struct EnvReading {
  float tempC;
  float humidityPct;
  float pressureHpa;
  bool valid;
};
static EnvReading env = {};

// Pull a fresh temperature/humidity/pressure reading. In the library's default
// normal mode the sensor measures continuously, so these are register reads.
static EnvReading readBme() {
  EnvReading e = {};
  if (!bmeReady) return e;
  e.tempC = bme.readTemperature();
  e.humidityPct = bme.readHumidity();
  e.pressureHpa = bme.readPressure() / 100.0f;  // Pa -> hPa
  e.valid = !isnan(e.tempC) && !isnan(e.humidityPct) && !isnan(e.pressureHpa);
  return e;
}

// microSD logging. A fresh file per power-on so sessions never overwrite. It opens
// as /gaslogNNN.csv and, the first time the GNSS reports a real UTC time, renames
// itself to that timestamp (FAT forbids ':' so the time uses hyphens). We write
// the same CSV that goes to serial and flush periodically -- often enough that a
// power cut loses at most a few seconds, rarely enough to stall the loop or thrash
// the card.
static bool sdReady = false;
static File logFile;
static char logPath[32];
static bool logRenamed = false;  // true once renamed to the UTC-timestamped name
static const uint32_t SD_FLUSH_MS = 5000;
static uint32_t lastFlushMs = 0;

// Single source of truth for the CSV column order, shared by serial and SD.
static const char *CSV_HEADER =
    "millis_since_boot,state,ch4_vout_mv,ch4_baseline_mv,ch4_dev_mv,"
    "lpg_vout_mv,lpg_baseline_mv,lpg_dev_mv,"
    "temp_c,humidity_pct,pressure_hpa,"
    "utc_iso8601,lat,lon,alt_m,sats,fix";

static State state = WARMUP;
static uint32_t stateStartMs = 0;
static uint32_t lastSampleMs = 0;
static bool buttonPrevDown = false;

// The I2C GNSS library exposes no fix flag, so infer a boolean: at least one
// satellite used and coordinates that are not NaN, out of range, or the all-zero
// "no fix" placeholder. A heuristic, not a real fix-quality indicator (this
// library gives us neither HDOP nor fix type).
static bool deriveFix(const GnssReading &r) {
  if (!gnssReady || r.sats == 0) return false;
  if (isnan(r.lat) || isnan(r.lon)) return false;
  if (fabs(r.lat) > 90.0 || fabs(r.lon) > 180.0) return false;
  if (r.lat == 0.0 && r.lon == 0.0) return false;  // 0,0 is the no-fix placeholder
  return true;
}

// Pull a fresh snapshot from the GNSS (each getter is its own I2C transaction).
static GnssReading readGnss() {
  GnssReading r = {};
  if (!gnssReady) return r;
  r.date = gnss.getDate();
  r.utc = gnss.getUTC();
  // The library returns the coordinate as an unsigned magnitude plus a separate
  // hemisphere char ('N'/'S', 'E'/'W'); apply that sign ourselves, or a West
  // longitude (all of the UK) reads as East and lands in the sea. (The library
  // spells the longitude field "lonitude".)
  sLonLat_t latRaw = gnss.getLat();
  sLonLat_t lonRaw = gnss.getLon();
  r.lat = (latRaw.latDirection == 'S' ? -1.0 : 1.0) * latRaw.latitudeDegree;
  r.lon = (lonRaw.lonDirection == 'W' ? -1.0 : 1.0) * lonRaw.lonitudeDegree;
  r.altM = gnss.getAlt();
  r.sats = gnss.getNumSatUsed();
  r.haveFix = deriveFix(r);
  return r;
}

// Bring up the microSD card on its own SPI bus and open a new session log. If the
// card is absent or the open fails we carry on logging to serial only (sdReady
// stays false); a survey instrument should not hang because a card popped out.
static void initSdLog() {
  SPI.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
  if (!SD.begin(PIN_SD_CS)) {
    Serial.println("SD card not found. Logging to serial only.");
    return;
  }
  // Lowest unused /gaslogNNN.csv, so each power-on is its own file.
  for (int i = 0; i < 1000; i++) {
    snprintf(logPath, sizeof(logPath), "/gaslog%03d.csv", i);
    if (!SD.exists(logPath)) break;
  }
  logFile = SD.open(logPath, FILE_WRITE);
  if (!logFile) {
    Serial.printf("SD open of %s failed. Logging to serial only.\n", logPath);
    return;
  }
  logFile.println(CSV_HEADER);
  logFile.flush();
  sdReady = true;
  Serial.printf("SD logging to %s\n", logPath);
}

// Returns the averaged ADC pin voltage in millivolts (before the divider ratio
// is applied). analogReadMilliVolts() uses the chip's calibration, so we read it
// directly rather than averaging raw counts and converting; the caller scales by
// VOUT_DIVIDER_RATIO and uses the same pin mV for the divider-missing check.
static float sampleChannel(const GasChannel &ch) {
  uint32_t mvAcc = 0;
  for (uint8_t i = 0; i < OVERSAMPLE_COUNT; i++) {
    mvAcc += analogReadMilliVolts(ch.pin);
  }
  return (float)mvAcc / OVERSAMPLE_COUNT;
}

// Shift a CHART_W-wide ring left by one and append value at the right edge.
static void pushSample(float *hist, float value) {
  for (int i = 1; i < CHART_W; i++) {
    hist[i - 1] = hist[i];
  }
  hist[CHART_W - 1] = value;
}

static void pushHistory(GasChannel &ch, float value) {
  pushSample(ch.history, value);
  if (ch.count < CHART_W) {
    ch.count++;
  }
}

static void startBaselining(uint32_t now) {
  state = BASELINING;
  stateStartMs = now;
  ch4.count = lpg.count = 0;
  ch4.bgHead = lpg.bgHead = 0;
  ch4.bgCount = lpg.bgCount = 0;
  ch4.classHead = lpg.classHead = 0;
  ch4.classCount = lpg.classCount = 0;
}

// Append a VOUT sample to a channel's rolling background and classification rings
// (both fixed-size, wrapping at their window length). Called once per sample from
// BASELINING onward so both windows always hold the most recent history.
static void pushWindows(GasChannel &ch, float value) {
  ch.bgRing[ch.bgHead] = value;
  if (++ch.bgHead >= BG_WINDOW_SAMPLES) ch.bgHead = 0;
  if (ch.bgCount < BG_WINDOW_SAMPLES) ch.bgCount++;

  ch.classRing[ch.classHead] = value;
  if (++ch.classHead >= CLASS_WINDOW_SAMPLES) ch.classHead = 0;
  if (ch.classCount < CLASS_WINDOW_SAMPLES) ch.classCount++;
}

// Recompute the baseline as the BG_PERCENTILE of the current background window.
// Scratch is shared across channels because the calls are sequential. A brief
// positive plume sits above a low percentile, so the background holds through it
// and only tracks the slow drift between plumes -- no gate, no freeze, no lockout.
static float bgScratch[BG_WINDOW_SAMPLES];
static void updateBaseline(GasChannel &ch) {
  if (ch.bgCount < 1) return;
  for (int i = 0; i < ch.bgCount; i++) bgScratch[i] = ch.bgRing[i];
  int k = (int)(BG_PERCENTILE * (ch.bgCount - 1));
  std::nth_element(bgScratch, bgScratch + k, bgScratch + ch.bgCount);
  ch.baselineMv = bgScratch[k];
}

enum Level { LVL_NONE, LVL_LOW, LVL_MED, LVL_HIGH };

// Classify the latest reading against the 10 min window: where it sits between
// that window's min and max, in thirds. A range floor stops a flat, quiet trace
// (tiny min..max span) from being magnified into a spurious HIGH.
static Level classifyLevel(const GasChannel &ch) {
  if (ch.classCount < 1) return LVL_NONE;
  float lo = ch.classRing[0], hi = ch.classRing[0];
  for (int i = 1; i < ch.classCount; i++) {
    float v = ch.classRing[i];
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  float range = hi - lo;
  if (range < CLASS_RANGE_FLOOR_MV) range = CLASS_RANGE_FLOOR_MV;
  float frac = (ch.lastVoutMv - lo) / range;
  if (frac < 0.34f) return LVL_LOW;
  if (frac < 0.67f) return LVL_MED;
  return LVL_HIGH;
}

static const char *levelStr(Level l) {
  switch (l) {
    case LVL_LOW: return "LOW";
    case LVL_MED: return "MED";
    case LVL_HIGH: return "HIGH";
    default: return "--";
  }
}

// Set the onboard WS2812 to a logical (r, g, b). This board's LED takes its bytes
// red-first, but the core's neopixelWrite() emits green-first (standard WS2812
// GRB), so the two disagree and red/green come out swapped (green showed as red).
// Swapping the first two arguments here cancels that; blue is unaffected either
// way. neopixelWrite() sets up the RMT internally, so no library or pinMode.
static void ledRGB(uint8_t r, uint8_t g, uint8_t b) {
  neopixelWrite(PIN_STATUS_LED, g, r, b);
}

// Drive the status LED from the current state: dim blue while not yet RUNNING,
// otherwise green/amber/red for CH4 LOW/MED/HIGH. Values are kept low -- the
// onboard LED is very bright.
static void setStatusLed() {
  uint8_t r = 0, g = 0, b = 0;
  if (state != RUNNING) {
    b = 20;  // warming up / baselining: not ready
  } else {
    switch (classifyLevel(ch4)) {
      case LVL_HIGH: r = 40; break;          // red
      case LVL_MED:  r = 35; g = 18; break;  // amber
      default:       g = 30; break;          // green (LOW / no signal yet)
    }
  }
  ledRGB(r, g, b);
}

// Map a VOUT in millivolts to a y pixel, given the current axis bounds.
static int mapY(float mv, float yMin, float yMax) {
  if (mv < yMin) mv = yMin;
  if (mv > yMax) mv = yMax;
  return GRAPH_BOTTOM -
         (int)((mv - yMin) / (yMax - yMin) * (GRAPH_BOTTOM - GRAPH_TOP));
}

// Status screen during warm-up and baselining: a message, a countdown and a
// progress bar, since there is no chart to plot yet.
static void drawStatus(const char *title, uint32_t elapsedMs, uint32_t windowMs) {
  char line[24];
  oled.clearBuffer();
  oled.setFont(u8g2_font_6x10_tf);
  oled.drawStr(0, 20, title);
  uint32_t leftS = (windowMs > elapsedMs) ? (windowMs - elapsedMs) / 1000 : 0;
  snprintf(line, sizeof(line), "%lus left", (unsigned long)leftS);
  oled.drawStr(0, 36, line);
  int w = (int)((float)elapsedMs / windowMs * (SCREEN_W - 1));
  if (w > SCREEN_W - 1) w = SCREEN_W - 1;
  oled.drawFrame(0, 46, SCREEN_W, 8);
  oled.drawBox(0, 46, w, 8);

  char g[24];
  if (sdReady) {
    snprintf(g, sizeof(g), "SD %s", logPath);
  } else {
    snprintf(g, sizeof(g), "SD none");
  }
  oled.drawStr(0, 10, g);

  if (!gnssReady) {
    snprintf(g, sizeof(g), "GPS no module");
  } else if (gps.haveFix) {
    snprintf(g, sizeof(g), "GPS fix  sat %u", gps.sats);
  } else {
    snprintf(g, sizeof(g), "GPS search sat %u", gps.sats);
  }
  oled.drawStr(0, 62, g);
  oled.sendBuffer();
}

// Dashed horizontal gridlines every GRID_STEP_MV, from the 0 floor up to yMax.
// Because the bottom of every chart is fixed at GRAPH_MIN_MV, counting lines from
// the bottom reads the magnitude even when the top is dynamic. The dash is sparser
// (every 6 px) than the baseline dots so the two are not confused. If fillCh is
// non-null, the pixel colour flips where a line sits inside that channel's filled
// area, so the line stays visible against the solid fill. Drawn into [x0, x0+CHART_W).
static void drawGridlines(int x0, float yMax, const GasChannel *fillCh) {
  for (float level = GRID_STEP_MV; level < yMax; level += GRID_STEP_MV) {
    int y = mapY(level, GRAPH_MIN_MV, yMax);
    for (int i = 0; i < CHART_W; i += 6) {
      if (fillCh) {
        int fillY = mapY(fillCh->history[i], GRAPH_MIN_MV, yMax);  // fill spans fillY..bottom
        oled.setDrawColor(y >= fillY ? 0 : 1);
      }
      oled.drawPixel(x0 + i, y);
    }
  }
  oled.setDrawColor(1);
}

// Left chart, raw VOUT: CH4 as a filled area from the bottom up to its VOUT, LPG
// as a line on top, and the CH4 baseline as a dotted reference line. The line and
// the dots switch to the background colour where they sit inside the CH4 fill, so
// they stay visible against the solid area. Drawn into the column [x0, x0+CHART_W).
static void drawRawChart(int x0) {
  if (ch4.count < 2) return;
  int start = CHART_W - ch4.count;

  // Dynamic upper bound with a static floor. The bottom of the axis is fixed at
  // GRAPH_MIN_MV; the top tracks the largest value on screen plus 10% headroom
  // but never drops below GRAPH_MAX_FLOOR_MV.
  float dataMax = GRAPH_MIN_MV;
  for (int i = start; i < CHART_W; i++) {
    if (ch4.history[i] > dataMax) dataMax = ch4.history[i];
    if (lpg.history[i] > dataMax) dataMax = lpg.history[i];
  }
  float yMax = dataMax * 1.1f;
  if (yMax < GRAPH_MAX_FLOOR_MV) yMax = GRAPH_MAX_FLOOR_MV;

  // CH4 filled area.
  for (int i = start; i < CHART_W; i++) {
    int y = mapY(ch4.history[i], GRAPH_MIN_MV, yMax);
    oled.drawVLine(x0 + i, y, GRAPH_BOTTOM - y + 1);
  }

  // Dashed scale gridlines, flipped to stay visible inside the CH4 fill.
  drawGridlines(x0, yMax, &ch4);

  // LPG line on top, drawn in background colour where it lies inside the fill.
  for (int i = start + 1; i < CHART_W; i++) {
    int y0 = mapY(lpg.history[i - 1], GRAPH_MIN_MV, yMax);
    int y1 = mapY(lpg.history[i], GRAPH_MIN_MV, yMax);
    int ch4Y = mapY(ch4.history[i], GRAPH_MIN_MV, yMax);  // fill spans ch4Y..bottom
    oled.setDrawColor(y1 >= ch4Y ? 0 : 1);
    oled.drawLine(x0 + i - 1, y0, x0 + i, y1);
  }

  // CH4 baseline as a dotted reference line, same colour trick so it shows
  // whether it falls above or inside the fill.
  int baseY = mapY(ch4.baselineMv, GRAPH_MIN_MV, yMax);
  for (int i = start; i < CHART_W; i += 3) {
    int ch4Y = mapY(ch4.history[i], GRAPH_MIN_MV, yMax);
    oled.setDrawColor(baseY >= ch4Y ? 0 : 1);
    oled.drawPixel(x0 + i, baseY);
  }

  oled.setDrawColor(1);
}

// Right chart, long-timebase overview: the channel's whole classification window
// (up to 10 min) decimated to the column width, peak-per-column so a transient is
// not lost between pixels, with the current baseline as a dotted reference. The
// trace is right-aligned and the axis has its own max (same floor as the live
// chart). Drawn into [x0, x0+CHART_W).
static void drawOverviewChart(const GasChannel &ch, int x0) {
  if (ch.classCount < 1) return;
  int cols = (ch.classCount < CHART_W) ? ch.classCount : CHART_W;
  int startCol = CHART_W - cols;  // right-align the trace
  int oldest = (ch.classHead - ch.classCount + CLASS_WINDOW_SAMPLES) % CLASS_WINDOW_SAMPLES;

  // Peak-per-column over the window.
  float colVal[CHART_W];
  for (int p = 0; p < cols; p++) {
    int o0 = p * ch.classCount / cols;
    int o1 = (p + 1) * ch.classCount / cols;
    if (o1 <= o0) o1 = o0 + 1;
    float peak = ch.classRing[(oldest + o0) % CLASS_WINDOW_SAMPLES];
    for (int o = o0 + 1; o < o1; o++) {
      float v = ch.classRing[(oldest + o) % CLASS_WINDOW_SAMPLES];
      if (v > peak) peak = v;
    }
    colVal[startCol + p] = peak;
  }

  // Fixed (static) scale: 0 to the factory-alarm full scale. Same dashed grid as
  // the live chart so the two read against the same 1 V lines.
  const float yMax = OVERVIEW_MAX_MV;
  drawGridlines(x0, yMax, nullptr);

  // Current baseline as a dotted reference (the "now" background level).
  int baseY = mapY(ch.baselineMv, GRAPH_MIN_MV, yMax);
  for (int i = startCol; i < CHART_W; i += 3) {
    oled.drawPixel(x0 + i, baseY);
  }

  if (cols == 1) {
    oled.drawPixel(x0 + startCol, mapY(colVal[startCol], GRAPH_MIN_MV, yMax));
    return;
  }
  for (int p = 1; p < cols; p++) {
    int y0 = mapY(colVal[startCol + p - 1], GRAPH_MIN_MV, yMax);
    int y1 = mapY(colVal[startCol + p], GRAPH_MIN_MV, yMax);
    oled.drawLine(x0 + startCol + p - 1, y0, x0 + startCol + p, y1);
  }
}

// Two-column screen: the live raw chart on the left (last ~16 s, both channels),
// a 10-minute CH4 overview on the right, with a header line (the HIGH/MED/LOW
// levels) and a vertical divider down the gap.
static void drawCharts() {
  char line[28];
  oled.clearBuffer();
  oled.setFont(u8g2_font_6x10_tf);

  // Top line: HIGH/MED/LOW for each channel, judged against its 10 min window.
  snprintf(line, sizeof(line), "CH4 %s LPG %s", levelStr(classifyLevel(ch4)),
           levelStr(classifyLevel(lpg)));
  oled.drawStr(0, 9, line);

  // Compact top-right status: SD then GNSS. SD 'R' logging / '-' not. GNSS 'G'+sats
  // (fix), 'g'+sats (searching), 'x' (no module). E.g. "RG7" = recording, 7-sat fix.
  char gpsTok[5];
  if (!gnssReady) {
    snprintf(gpsTok, sizeof(gpsTok), "x");
  } else if (gps.haveFix) {
    snprintf(gpsTok, sizeof(gpsTok), "G%u", gps.sats);
  } else {
    snprintf(gpsTok, sizeof(gpsTok), "g%u", gps.sats);
  }
  char st[8];
  snprintf(st, sizeof(st), "%c%s", sdReady ? 'R' : '-', gpsTok);
  oled.setFont(u8g2_font_4x6_tf);
  oled.drawStr(SCREEN_W - (int)strlen(st) * 4, 6, st);
  oled.setFont(u8g2_font_6x10_tf);

  drawRawChart(LEFT_X0);
  drawOverviewChart(ch4, RIGHT_X0);
  oled.drawVLine(DIVIDER_X, GRAPH_TOP, GRAPH_BOTTOM - GRAPH_TOP + 1);

  // Mark the overview's timebase so it is not mistaken for the live trace.
  oled.setFont(u8g2_font_4x6_tf);
  oled.drawStr(RIGHT_X0 + 1, GRAPH_TOP + 6, "10m");
  oled.setFont(u8g2_font_6x10_tf);

  oled.sendBuffer();
}

static void pollButton(uint32_t now) {
  bool down = (digitalRead(PIN_BOOT_BUTTON) == LOW);
  if (down && !buttonPrevDown) {
    Serial.println("Button: re-zeroing baseline.");
    startBaselining(now);
  }
  buttonPrevDown = down;
}

void setup() {
  Serial.begin(115200);
  uint32_t serialWaitStart = millis();
  while (!Serial && (millis() - serialWaitStart) < 2000) {
  }

  Serial.println();
  Serial.println("=== Dual gas sensor bring-up (fixed scale) ===");
  Serial.printf("Firmware %s, built %s %s\n", FW_VERSION, __DATE__, __TIME__);
  Serial.println("CH4 (fill) GPIO1, LPG (line) GPIO2, GNSS on I2C. BOOT rezeros.");
  Serial.println();

  pinMode(PIN_BOOT_BUTTON, INPUT_PULLUP);

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(I2C_CLOCK_HZ);
  oled.setBusClock(I2C_CLOCK_HZ);
  oled.begin();

  // Bring up the GNSS on the shared bus. A few retries cover its power-on delay;
  // if it never answers we carry on (screen and CSV just report no fix) rather
  // than hang. Wire.begin(SDA, SCL) above means the library's own argument-less
  // Wire.begin() inherits the right pins.
  for (uint8_t attempt = 0; attempt < 5 && !gnssReady; attempt++) {
    if (gnss.begin()) {
      gnssReady = true;
      break;
    }
    Serial.printf("GNSS begin() attempt %u failed\n", attempt + 1);
    delay(500);
  }
  if (gnssReady) {
    gnss.setGnss(eGPS_BeiDou_GLONASS);
    Serial.println("GNSS ready, acquiring fix...");
  } else {
    Serial.println("GNSS not responding on I2C. Check wiring and power.");
  }

  // BME280 on the same shared bus. begin() validates the chip id, so a BMP280
  // (no humidity) fails here rather than logging blank RH. Try both addresses.
  if (bme.begin(BME280_ADDR_PRIMARY, &Wire) || bme.begin(BME280_ADDR_ALT, &Wire)) {
    bmeReady = true;
    Serial.println("BME280 ready (temperature/humidity/pressure).");
  } else {
    Serial.println("BME280 not found on I2C (absent, wrong address, or a BMP280 "
                   "with no humidity). Logging gas + GNSS only.");
  }

  analogReadResolution(12);
  analogSetPinAttenuation(ch4.pin, ADC_11db);
  analogSetPinAttenuation(lpg.pin, ADC_11db);

  initSdLog();  // opens this session's file on the microSD, if present

  state = WARMUP;
  stateStartMs = millis();

  ledRGB(0, 0, 20);  // dim blue: starting up

  Serial.println(CSV_HEADER);
}

void loop() {
  uint32_t now = millis();
  pollButton(now);

  if (now - lastSampleMs < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMs = now;

  float ch4PinMv = sampleChannel(ch4);
  float lpgPinMv = sampleChannel(lpg);
  ch4.lastVoutMv = ch4PinMv * VOUT_DIVIDER_RATIO;
  lpg.lastVoutMv = lpgPinMv * VOUT_DIVIDER_RATIO;

  // Environment (temp/humidity/pressure) for this sample; blank in the row if the
  // sensor is absent, so a parser tells a missing reading from a real value.
  env = readBme();

  // Refresh the GNSS snapshot at ~1 Hz (its solution rate); the gas loop runs
  // faster, so polling every sample would just re-read the same fix.
  if (gnssReady && now - lastGpsReadMs >= GPS_INTERVAL_MS) {
    gps = readGnss();
    lastGpsReadMs = now;
    // Anchor the on-board clock to the GNSS whole-second so rows taken between
    // GNSS updates get interpolated sub-second stamps. When the reported second
    // changes, take millis() now as that second's t=0.
    if (gps.utc.second != gpsPrevSecond) {
      gpsPrevSecond = gps.utc.second;
      gpsSecondMs = now;
    }
  }

  // Rename the SD log to a UTC-timestamped name the first time the GNSS reports a
  // real time. Close/rename/reopen (append) rather than renaming an open handle;
  // if a fix never comes the provisional /gaslogNNN.csv name simply stays.
  if (sdReady && !logRenamed && gps.date.year > 2000) {
    char tsPath[32];
    snprintf(tsPath, sizeof(tsPath), "/%04u-%02u-%02u_%02u-%02u-%02u.csv",
             gps.date.year, gps.date.month, gps.date.date, gps.utc.hour,
             gps.utc.minute, gps.utc.second);
    logFile.flush();
    logFile.close();
    if (!SD.exists(tsPath) && SD.rename(logPath, tsPath)) {
      snprintf(logPath, sizeof(logPath), "%s", tsPath);
      Serial.printf("SD log renamed to %s\n", logPath);
    }
    logFile = SD.open(logPath, FILE_APPEND);
    if (!logFile) sdReady = false;  // reopen failed -- stop SD logging cleanly
    logRenamed = true;
  }

  uint32_t elapsed = now - stateStartMs;

  switch (state) {
    case WARMUP:
      if (elapsed >= WARMUP_MS) {
        startBaselining(now);
      }
      drawStatus("WARMING UP", elapsed, WARMUP_MS);
      break;

    case BASELINING:
      // Fill the rolling windows with clean-air VOUT; the baseline is just the
      // percentile of whatever has accumulated so far. BASELINE_MS is now only a
      // "trust the baseline" delay, not a separate averaging mechanism.
      pushWindows(ch4, ch4.lastVoutMv);
      pushWindows(lpg, lpg.lastVoutMv);
      updateBaseline(ch4);
      updateBaseline(lpg);
      if (elapsed >= BASELINE_MS) {
        state = RUNNING;
        Serial.printf("Baseline set (p%.0f): CH4 %.0f mV, LPG %.0f mV\n",
                      BG_PERCENTILE * 100.0f, ch4.baselineMv, lpg.baselineMv);
      }
      drawStatus("BASELINING", elapsed, BASELINE_MS);
      break;

    case RUNNING: {
      pushWindows(ch4, ch4.lastVoutMv);
      pushWindows(lpg, lpg.lastVoutMv);
      updateBaseline(ch4);
      updateBaseline(lpg);
      pushHistory(ch4, ch4.lastVoutMv);
      pushHistory(lpg, lpg.lastVoutMv);
      drawCharts();
      break;
    }
  }

  const char *stateName =
      (state == WARMUP) ? "WARMUP" : (state == BASELINING) ? "BASELINING" : "RUNNING";
  // Build the whole CSV row once, then emit it to serial and (if present) the SD
  // card so both carry identical lines. GNSS lat/lon/alt are blank without a fix
  // so a parser can tell a real 0 from a missing value.
  char row[200];
  int n = snprintf(row, sizeof(row), "%lu,%s,%.0f,%.0f,%.0f,%.0f,%.0f,%.0f",
                   (unsigned long)now, stateName, ch4.lastVoutMv, ch4.baselineMv,
                   ch4.lastVoutMv - ch4.baselineMv, lpg.lastVoutMv,
                   lpg.baselineMv, lpg.lastVoutMv - lpg.baselineMv);
  // Environment columns (temp_c, humidity_pct, pressure_hpa), or blanks if no
  // BME280, so the column count stays fixed and a missing reading is distinct
  // from a real 0.
  if (env.valid) {
    n += snprintf(row + n, sizeof(row) - n, ",%.2f,%.1f,%.1f",
                  env.tempC, env.humidityPct, env.pressureHpa);
  } else {
    n += snprintf(row + n, sizeof(row) - n, ",,,");
  }
  // utc_iso8601: one ISO-8601-style timestamp, space-separated, with millisecond
  // resolution (YYYY-MM-DD HH:MM:SS.mmm) so rows taken within the same GNSS second
  // stay distinct and ordered. The whole second is the GNSS UTC; the .mmm is the
  // on-board clock since that second's tick was observed (interpolated, not PPS-
  // disciplined). Blank until the GNSS has a valid time (year is 0 before then),
  // so a row never claims a fake 0000-00-00.
  if (gps.date.year > 2000) {
    uint32_t frac = now - gpsSecondMs;
    if (frac > 999) frac = 999;  // clamp if the GNSS poll stalled
    n += snprintf(row + n, sizeof(row) - n, ",%04u-%02u-%02u %02u:%02u:%02u.%03lu",
                  gps.date.year, gps.date.month, gps.date.date, gps.utc.hour,
                  gps.utc.minute, gps.utc.second, (unsigned long)frac);
  } else {
    n += snprintf(row + n, sizeof(row) - n, ",");
  }
  if (gps.haveFix) {
    n += snprintf(row + n, sizeof(row) - n, ",%.6f,%.6f,%.1f", gps.lat, gps.lon,
                  gps.altM);
  } else {
    n += snprintf(row + n, sizeof(row) - n, ",,,");
  }
  snprintf(row + n, sizeof(row) - n, ",%u,%u", gps.sats, gps.haveFix ? 1 : 0);

  Serial.println(row);
  if (sdReady) {
    if (logFile.println(row) == 0) {
      sdReady = false;  // write failed (card pulled or full) -- shown on screen
    } else if (now - lastFlushMs >= SD_FLUSH_MS) {
      logFile.flush();
      lastFlushMs = now;
    }
  }

  setStatusLed();

  if (ch4PinMv > PIN_CEILING_MV || lpgPinMv > PIN_CEILING_MV) {
    Serial.println("  WARNING: an ADC pin is near its ~3.1V ceiling. The 10k/10k "
                   "divider is likely missing or open and the pin is taking raw "
                   "VOUT (not signal clipping). Check the divider wiring.");
  }
}
