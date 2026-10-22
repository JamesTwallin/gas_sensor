# Gas anomaly detector: design, fit and first results

This report covers the anomaly detector added in firmware 1.1.0: what it does,
how it was fitted and tuned on four surveys recorded with the first board on 6–9 October 2026,
how well it works on those surveys, and what it cannot do yet.

The numbers in the tables come from `python tools/replay.py report`, which
regenerates [report/metrics.md](report/metrics.md), the plots and the CSVs in
[report/](report/). Settings live in
[`firmware/phone_board/lib/anomaly/anomaly_config.h`](../firmware/phone_board/lib/anomaly/anomaly_config.h).

## Update, 11 October 2026: the first real leak

Two more drives (D4, D5, about an hour each) were added. D4 passes a **known
outdoor gas leak**, confirmed by the person surveying: past it
at about 65 km/h, back past at about 43 km/h, then stopped beside it for about
40 s. This is the first positive control on this hardware.

![D4, with the three leak passes shaded at about 51–56 min](report/survey_D4.png)

**What a real leak looks like.** Residual above the conditions model, held-out
model (fitted without D4):

| Pass | Speed | CH4 peak | LPG peak | Above half its peak (CH4 / LPG) |
|---|---|---|---|---|
| 1 | ~65 km/h | 44 mV | 79 mV | 9 s / 19 s |
| 2 | ~43 km/h | 82 mV | 217 mV | 10 s / 26 s |
| 3 | stopped ~40 s | 264 mV | 448 mV | 45 s / 54 s |

- It is big: up to 37 sigma on CH4 and 18–66 sigma on LPG. The everyday noise
  after the model is 4–7 mV.
- **The LPG sensor (TGS2610) responds about twice as strongly as the CH4 sensor**
  (CH4-to-LPG ratio 0.26–0.58), and stays up longer. The synthetic tests had
  assumed the opposite (LPG 0.1–0.9 × CH4), so they understated what a leak
  gives. A plume shape with LPG = 2 × CH4 is now in the synthetic grid.
- The CH4 sensor's plume lasts about as long as the assumed one (10 s at 40–65
  km/h); the LPG sensor's lasts two to three times longer.

**Refit and retune on six surveys.** The leak window is kept out of fitting and
of the false-alarm count (`leak_utc` in `tools/surveys.json`).

- The model fitted on the earlier surveys predicted the new drives well: held-out
  R² 0.86 / 0.88 (CH4 / LPG) on D4 and 0.77 / 0.80 on D5.
- At the old setting (k = 7, N = 2 s) the new daytime drives gave many more
  events, mostly at stops where both sensors rose about equally: **3.2 per hour**
  over all six surveys, against the 1 per hour target. That is the airflow error
  the thermistor is for.
- Retuned for ≤ 1 per hour: **k = 10, N = 8 s**, giving **0.45 per hour** (2
  events in 4.4 hours, 0.009 per km). All three leak passes are still detected,
  as they are at every setting up to k = 12, N = 8 s.
- Synthetic plumes at that setting: leak-like (LPG = 2 × CH4) plumes of 45 mV on
  CH4 are detected **33 %** of the time, 90 mV **74 %**, 135 mV **93 %**. The old
  CH4-led plume shapes now do much worse (45 mV 3–5 %, 90 mV 24–35 %), because N =
  8 s needs a plume that lasts.
- The two remaining events are both strongly LPG-led, like the leak: D3 20:45
  (ratio 0.18) and **D5 15:55, three minutes long (ratio
  0.25)**. Either could be exhaust or another leak; the D5 one is worth a second
  look.

**The THERMAL label was wrong, and is fixed.** It was set by any temperature or
humidity step during an event. Such steps happen in about 5 % of seconds, and
stopping in a plume warms the case air, so 16 of 20 events were marked THERMAL,
including the leak. Only steps from 20 s before an event's onset to 5 s after it
now count (`ANOM_THERMAL_POST_S`). Pass 2 is still marked THERMAL: there was a
humidity step just before it.

**Natural gas is still not labelled.** The leak's ratio (0.26–0.58) overlaps
the LPG-led events that are probably exhaust (0.18–0.33). On this sensor pair, the
ratio alone cannot tell a leak from exhaust, so `ANOM_NG_BAND_VALID` stays 0. A CO
sensor, more leaks, and the exhaust survey ([PROTOCOL.md](PROTOCOL.md) survey 2)
are needed. Pass 1 is labelled HEAVY_HC, pass 3 UNRESOLVED.

**Still thin:** one leak, one day, one wind, no reference instrument (so no ppm),
4.4 ready hours in all. The sections below describe the first four surveys, with
the settings of the time (k = 7, N = 2 s).

## In short

- The board now predicts what each gas sensor *should* read from temperature
  and humidity, and flags readings well above that prediction. It does not try
  to measure ppm.
- On held-out surveys (each survey tested with a model fitted on the other
  three), temperature and humidity explain **62–92 % of the variation** in each
  sensor's reading around its slow baseline.
- What is left (robust SD 11–31 mV over the whole survey) is almost all **slow**:
  at timescales under 15 s the leftover is only 1–3 mV. GPS speed, used offline
  as a stand-in for airflow, removes a large part of it on drives (CH4 robust SD
  12 → 7 mV). This is the strongest evidence yet that the airflow thermistor is
  worth fitting.
- With the shipped settings the detector gives **0.85 events per hour** (0.015
  per km) on held-out data. There is no known leak in any survey, so every event
  counts as a false alarm here; that is an upper bound, since some may be real.
- On the same held-out data, synthetic plumes of 45 mV on the CH4 sensor are
  detected about **18 %** of the time, 90 mV plumes about **77 %**. The plume
  shape is assumed, not measured.
- No event is classified NATURAL_GAS: that class needs the positive-control
  survey ([PROTOCOL.md](PROTOCOL.md)). Events where both sensors rise are
  UNRESOLVED unless they coincide with a temperature step (THERMAL) or are
  strongly LPG-led (HEAVY_HC).
- One change from the original brief is in the shipped settings: a short
  **15 s "high-pass" stage** after the conditions model (section 4). Without it,
  reaching 1 false alarm per hour needs k = 12, and 45 mV plumes are not
  detected at all. Setting `ANOM_RES_HP_TAU_S` to 0 restores the brief's design
  exactly.

## 1. The data

Four app recordings (the first board, bare TGS2611-E00 and TGS2610-D00, SHT40), one
device, 250 ms samples. Position, speed and time of day were used **only** for
reporting; none of them is a model input.

| Id | File | What | Used |
|---|---|---|---|
| D1 | 2026-10-06_17-25-53 | two drives either side of a 96-minute indoor stop | 69 min outdoors; the indoor stop (no GPS fix, 28–32 °C) is excluded |
| D2 | 2026-10-08_17-19-28 | drive, dusk | 34 min after warm-up |
| W1 | 2026-10-09_13-53-47 | walk, about 1 km, day | 13 min |
| D3 | 2026-10-09_20-42-30 | drive, night | 38 min |

That is about 2.6 hours of outdoor data; after each survey's 2-minute settling
time the detector was "ready" for 2.36 hours and 132 km. This is somewhat less
than the 3.2 hours of the earlier analysis; the indoor stop is the main
difference. The list lives in [`tools/surveys.json`](../tools/surveys.json).

The first prototype's logs in `tools/data/` were **not** used: it had the NGM/LPM
modules, with their own temperature compensation and output stage, so their
voltages do not relate to conditions the way the bare sensors do.

## 2. How the detector works

Per sample, for each gas channel separately (`lib/anomaly/anomaly.c`):

1. **Target.** The sensor's load voltage minus a slow baseline: an
   exponentially weighted average with a 300 s time constant. The baseline is
   frozen while that channel is anomalous, for at most 120 s, after which it
   follows again with a slower 1200 s time constant.
2. **Features, from conditions only.** Temperature and absolute humidity minus
   their own 300 s baselines; their rates of change over 10 s; the temperature
   deviation smoothed over 60 s (the sensor cans lag the air); the airflow index
   and two smoothed versions (5 s, 30 s); the CO rise. Airflow and CO are
   switched off until surveys include them. **The other gas channel is never a
   feature.**
3. **Prediction.** A linear combination of the features, with one coefficient
   set per channel, shared by all places and fitted across all surveys.
4. **Short-timescale stage (new).** The residual (target minus prediction),
   minus its own 15 s trailing average, frozen with the baselines. Section 4
   explains why.
5. **Noise level.** A robust standard deviation (1.4826 × the median absolute
   deviation) of the last 5 minutes of residuals, recomputed every second, never
   below 1 mV. Samples during an anomaly are kept out of it (the same 120 s
   limit).
6. **Detection.** The residual above **k = 10** robust sigmas, held for **N = 8
   s** (k = 7, N = 2 s before the 11 October retune), raises the channel; it stays raised until the residual falls below
   3 sigmas. Only rises count. Detection is briefly suppressed (30 s) after a
   large temperature or humidity step (> 0.06 °C/s or g/m³/s over 10 s), but
   **never for being stationary**.
7. **Event and fingerprint.** An event opens when either channel is raised and
   closes 5 s after both have settled. Its fingerprint: peak residual on each
   channel (mV and sigmas), their ratio (CH4 / LPG), which channel crossed
   3 sigmas first and by how long, duration, airflow during the event, CO rise.
8. **Classification**, from the fingerprint only:

   | Class | Rule |
   |---|---|
   | THERMAL | a temperature/humidity step (> 0.03 per s) during the event or up to 20 s before |
   | EXHAUST | both channels raised (detected, or peak ≥ 3 sigmas) **and** CO rose > 2 ppm. Never assigned until a CO sensor is fitted |
   | HEAVY_HC | LPG raised and CH4 not, or both raised with CH4/LPG ≤ 0.4 (strongly LPG-led) |
   | NATURAL_GAS | both raised, ratio inside the measured natural-gas band, no CO rise. **Disabled**: the band has not been measured |
   | LOW_AIRFLOW | the whole event at low airflow (index < 0.15). Kept as a candidate, not dismissed. Needs the thermistor |
   | UNRESOLVED | both raised, none of the above |
   | UNCLASSIFIED | CH4 only |

   Confidence (0–100) is the detection margin (how far the peak went past k),
   times, for HEAVY_HC and NATURAL_GAS, how firmly the ratio sits inside its
   band. It is a heuristic until labelled events exist.

Nothing is dismissed because both channels moved together; every event is
logged with its full fingerprint.

## 3. The conditions model

Fitted by robust (Huber) least squares on the samples after each survey's
settling time. Leave-one-survey-out: each survey's numbers come from a model
fitted on the other three.

| Survey | Mode | Channel | SD of target, mV | R² held out | Residual SD held out, mV | Robust residual SD, mV | R² own fit |
|---|---|---|---|---|---|---|---|
| D1 | drive | CH4 | 39.8 | 0.739 | 20.3 | 17.5 | 0.761 |
| D1 | drive | LPG | 51.0 | 0.622 | 31.4 | 30.6 | 0.670 |
| D2 | drive | CH4 | 45.5 | 0.808 | 19.9 | 17.5 | 0.879 |
| D2 | drive | LPG | 41.2 | 0.889 | 13.8 | 12.3 | 0.928 |
| W1 | walk | CH4 | 31.7 | 0.903 | 9.9 | 11.0 | 0.930 |
| W1 | walk | LPG | 32.7 | 0.922 | 9.1 | 10.8 | 0.938 |
| D3 | drive | CH4 | 34.3 | 0.777 | 16.2 | 12.6 | 0.794 |
| D3 | drive | LPG | 34.8 | 0.678 | 19.8 | 12.1 | 0.722 |

Coefficients, all four surveys pooled (shipped in `anomaly_config.h`):

| | bias, mV | dT, mV/°C | dAH, mV per g/m³ | dT/dt, mV per °C/s | dAH/dt, mV per g/m³/s | dT smoothed, mV/°C |
|---|---|---|---|---|---|---|
| CH4 | 9.09 | 52.9 | 25.7 | −116.7 | −94.2 | −14.2 |
| LPG | 19.11 | 44.7 | 18.5 | −117.6 | −67.0 | 1.86 |

- The temperature sensitivity, dT plus the smoothed dT, is about 39 mV/°C for
  CH4 and 47 mV/°C for LPG, in line with the 37–39 mV/°C found earlier.
- The negative rate terms mean the gas sensors lag the air temperature: a fast
  rise in temperature is not yet seen in full by the sensors.
- The walk is explained best (R² 0.90–0.92). The drives are worse, and worst
  for LPG on D1, the drive straight after 96 minutes indoors at 30 °C (its
  second half). The LPG sensor took most of that drive to settle.
- The R² figures are higher than the "about half" found earlier, because the
  target here is the reading minus a 300 s baseline: the slowest drift has
  already gone.

### What is left over, and why it matters

The residual's spread after removing a centred rolling mean of W seconds
(offline analysis, held-out residuals, 60 s baseline):

| | total | W = 5 s | 15 s | 30 s | 60 s | 120 s |
|---|---|---|---|---|---|---|
| D1 CH4 | 14.0 | 1.4 | 3.0 | 4.7 | 7.3 | 10.8 |
| D2 CH4 | 16.1 | 1.0 | 1.9 | 4.0 | 8.4 | 13.9 |
| W1 CH4 | 8.6 | 1.8 | 3.0 | 4.3 | 6.5 | 7.9 |
| D3 CH4 | 11.3 | 1.0 | 2.1 | 3.7 | 5.8 | 8.4 |
| D3 LPG | 16.3 | 1.0 | 2.6 | 4.8 | 8.7 | 13.4 |

(mV; the other rows are similar.) The sensors' own electronic noise is
0.3–0.5 mV. So what the model misses is not noise but slow, real signal, over
tens of seconds to minutes: the stops, starts and changes of speed that change
the airflow over the sensor heaters.

**Diagnostic only: GPS speed as a stand-in for airflow.** Adding √speed and
three smoothed versions of it to the model (held out, offline, never in the
firmware) changes the robust residual SD as follows:

| | D1 | D2 | W1 | D3 |
|---|---|---|---|---|
| CH4 | 11.4 → 7.2 | 12.4 → 6.5 | 8.9 → 10.1 | 6.9 → 5.7 |
| LPG | 13.3 → 10.5 | 8.8 → 7.6 | 8.2 → 10.5 | 7.2 → 8.4 |

On drives, the CH4 channel's leftover error nearly halves. The walk does not
improve, unsurprisingly: GPS speed of 3–5 km/h says little about the air over
the sensor, and the walk's model was already the best. The thermistor measures
the air over the sensors directly, so it should do at least as well as GPS speed
on drives, and might help on foot too.

**End to end through the detector (2026-10-10, `python tools/airflow_check.py`).**
The diagnostic above was offline, with a 60 s baseline and without the 15 s
high-pass stage. This check runs the real detector, with the shipped settings,
using its built-in airflow input (`ANOM_USE_AIRFLOW`). The airflow index is fed
from GPS speed: √speed, the square-root law a heated bead follows, through the
bead's own lag. Coefficients are fitted leave-one-survey-out as usual. Two beads
are modelled: a fast one (1 s lag, like the BR16) and a cheap, slow one (8 s).

Held-out fit (R²) and the detector's residual after its high-pass stage
(robust SD, mV):

| | R² base → fast → slow | detector residual base → fast → slow |
|---|---|---|
| D1 CH4 | 0.74 → 0.81 → 0.84 | 6.4 → 5.6 → 5.2 |
| D2 CH4 | 0.81 → 0.91 → 0.93 | 7.2 → 5.3 → 4.5 |
| D3 CH4 | 0.78 → 0.87 → 0.89 | 4.4 → 4.4 → 4.2 |
| W1 CH4 | 0.90 → 0.90 → 0.89 | 7.2 → 6.0 → 6.3 |
| LPG (all four) | no change (±0.01) | no consistent change (−0.5 to +0.9) |

Synthetic plumes (x = 0.3, 10 s), detection at the same thresholds; false alarms
per hour on the held-out surveys in brackets:

| | k = 6 | k = 7 | k = 8 |
|---|---|---|---|
| base, 45 mV | 29 % (3.4/h) | 18 % (0.85/h) | 12 % (0.85/h) |
| fast bead, 45 mV | 43 % (2.1/h) | 31 % (1.3/h) | 20 % (0.85/h) |
| slow bead, 45 mV | 55 % (0.85/h) | 45 % (0.85/h) | 28 % (0.85/h) |
| base, 90 mV | 92 % | 77 % | 62 % |
| slow bead, 90 mV | 95 % | 94 % | 91 % |

What this says:

- **An airflow input helps the CH4 channel on drives, through the real
  detector**: held-out R² up by 0.07–0.12, and 45 mV plumes caught 2–3 times as
  often at the same false-alarm rate (18 % → 45 % at 0.85/h).
- **The LPG channel does not use it.** The TGS2610 is less affected by
  airflow than the TGS2611, or in a way GPS speed does not capture. So the gain
  is in CH4, which is the channel that matters for natural gas.
- **The slow bead does at least as well as the fast one.** The gas sensor's own
  response to airflow is slow (its heater and can have thermal mass), and
  smoothing also takes out GPS jitter. This supports using a cheap, slow bead
  instead of the BR16. A follow-up scan of the bead's lag at k = 7 gave the
  same result from 3 s to 40 s (45 mV plumes 37–49 %, 90 mV 88–94 %, CH4
  held-out R² 0.82–0.94), so even a slow epoxy bead is fine. The board now
  specifies a cheap 1 kΩ bead with R28 = 1 kΩ.
- **No gain on the walk**, as before: walking pace says little about the air at
  the sensor; a real bead sees wind and might do better.
- Caveats: GPS speed is not air speed (no wind, window position, or how the
  device was held), so this is a stand-in, not a measurement. The false-alarm
  counts are 1–3 events in 2.4 hours, so the thresholds are coarse. The
  temperature-from-bead and humidity-from-case changes cannot be tested with this
  data at all: the surveys have no outside-air reading.

## 4. Tuning and the short-timescale stage

**The brief's design** (detect on the model residual directly) was tuned over
baseline time constants of 60, 120 and 300 s, k from 4 to 12 and N from 1 to 8
s, for at most 1 false alarm per hour on held-out surveys. It needs k = 10–12,
and then catches almost no synthetic plume of 45 mV (0–2 %). The reason is in
the table above: the residual's 5-minute robust sigma is 9–18 mV, set by the
slow airflow error, so k × sigma is 100–200 mV.

**The short-timescale stage** subtracts from the residual its own trailing
average over a short time constant (frozen during anomalies). This removes the
slow error the model cannot yet explain. It also removes part of any slow,
sustained rise, which is why it was tested against a 60-second plume as well as
a 10-second one:

| Baseline | High-pass | N | k for ≤ 1/h | False alarms /h | /km | 45 mV, 10 s plume | 45 mV, 60 s plume |
|---|---|---|---|---|---|---|---|
| 300 s | off | 2 s | 12 | 0.85 | 0.015 | 0 % | 0 % |
| 300 s | **15 s** | **2 s** | **7** | **0.85** | **0.015** | **18 %** | **13 %** |
| 300 s | 30 s | 2 s | 10 | 0.42 | 0.008 | 3 % | 0 % |
| 300 s | 60 s | 2 s | 10 | 0.42 | 0.008 | 2 % | 0 % |
| 120 s | off | 2 s | 10 | 0.85 | 0.015 | 2 % | 0 % |
| 120 s | 15 s | 2 s | 7 | 0.42 | 0.008 | 17 % | 15 % |

(65 plumes per cell at 10 s, 62 at 60 s; LPG gets 0.3 × the CH4 plume.)
Freezing the baselines from a lower "candidate" level (`ANOM_K_HOLD` = 3 or 5
instead of k) was also tried; it made matters worse, with no setting meeting
1/h at k ≤ 12, so `ANOM_K_HOLD` stays equal to k.

**Shipped on four surveys:** baseline 300 s, high-pass 15 s, k = 7, N = 2 s,
release 3 sigmas. Retuned on six surveys (11 October, see the update at the
top): k = 10, N = 8 s.
Once the thermistor explains the slow airflow error, the high-pass stage may no
longer be needed; refit both ways then.

**How reliable is this?** Not very. There are 2.36 ready hours, so one event is
0.42 per hour, and "≤ 1 per hour" means "at most two events in the whole data
set". The choice of k and N rests on a handful of events, any of which may be
real. Treat k = 7 as provisional until there are tens of hours of surveys.

## 5. Events found

Held-out, shipped settings:

| Survey | Ready hours | km | Events | Per hour | Per km | Median sigma CH4 / LPG, mV | Time suppressed |
|---|---|---|---|---|---|---|---|
| D1 | 1.05 | 61.8 | 0 | 0 | 0 | 6.1 / 6.7 | 2.9 % |
| D2 | 0.53 | 33.4 | 1 | 1.88 | 0.030 | 6.6 / 4.1 | 0 % |
| W1 | 0.18 | 0.8 | 0 | 0 | 0 | 7.2 / 5.6 | 15.6 % |
| D3 | 0.60 | 35.6 | 1 | 1.68 | 0.028 | 4.4 / 4.3 | 1.8 % |
| **all** | **2.36** | **131.6** | **2** | **0.85** | **0.015** | | |

The walk spent 16 % of its time suppressed after temperature or humidity
steps (going in and out of shade and past buildings); the drives 0–3 %.

The fingerprint library so far ([report/events.csv](report/events.csv)):

| Survey | UTC | Class | Conf. | Duration | CH4 peak | LPG peak | CH4/LPG | Lead | GPS speed (report only) |
|---|---|---|---|---|---|---|---|---|---|
| D2 | 2026-10-08 17:52:03 | HEAVY_HC | 66 | 9.5 s | 4.5 mV (1.0 σ) | 40.9 mV (9.3 σ) | 0.11 | LPG only | 88 km/h |
| D3 | 2026-10-09 20:45:37 | THERMAL | 100 | 59 s | 43.5 mV (11.7 σ) | 165 mV (36.6 σ) | 0.26 | together | 50 km/h |

- **D2 #1** is an LPG-only rise at motorway speed, the same kind of event as the
  strongly LPG-led one in the earlier analysis (possibly fuel vapour from a
  vehicle ahead).
- **D3 #1** rose on both channels, LPG much more, at the same moment as a
  temperature step, so it is THERMAL. It is still logged with its fingerprint,
  not dropped.
- None of the earlier analysis's unresolved both-channel events at stops
  survives the shipped settings on held-out data. With the brief's design at
  lower thresholds they do appear. They remain unexplained: exhaust and low
  airflow are the leading suspects, and survey 2 in [PROTOCOL.md](PROTOCOL.md)
  is designed to tell them apart.

The per-survey plots show the raw signals, the conditions, each channel's
target with the model's expectation, and the residual in sigmas with the
threshold and events marked:

![D1](report/survey_D1.png)
![D2](report/survey_D2.png)
![W1](report/survey_W1.png)
![D3](report/survey_D3.png)

## 6. Synthetic plumes

**The plume shape is assumed, not measured.** Each synthetic plume is gas
present for a fixed time (10 s, like driving past a source, or 60 s, like
walking up to one), seen through a 4 s first-order sensor response, peaking at
A mV on the CH4 channel and x × A on the LPG channel. Plumes were added to the
logged readings of each survey every 4 minutes (twice, at different offsets),
and the survey replayed with a model fitted *without* that survey. A plume
counts as detected if an event overlaps it. With nothing injected, no event fell
in those windows (chance rate 0 %); the 2–3 % at 10–20 mV is plumes nudging an
existing near-threshold fluctuation over the line.

![Synthetic detection curves](report/synthetic.png)

Independent per-channel detection (the firmware), fraction detected:

| Exposure | x (LPG share) | 10 mV | 20 | 30 | 45 | 60 | 90 | 135 mV |
|---|---|---|---|---|---|---|---|---|
| 10 s | 0.1 | 0.02 | 0.03 | 0.05 | 0.18 | 0.28 | 0.77 | 0.95 |
| 10 s | 0.3 | 0.02 | 0.03 | 0.05 | 0.18 | 0.28 | 0.77 | 0.95 |
| 10 s | 0.6 | 0.02 | 0.03 | 0.05 | 0.20 | 0.35 | 0.80 | 0.95 |
| 10 s | 0.9 | 0.02 | 0.03 | 0.08 | 0.31 | 0.43 | 0.85 | 0.95 |
| 60 s | 0.1 | 0.02 | 0.02 | 0.02 | 0.13 | 0.21 | 0.58 | 0.94 |
| 60 s | 0.3 | 0.02 | 0.02 | 0.02 | 0.13 | 0.21 | 0.60 | 0.94 |
| 60 s | 0.6 | 0.03 | 0.02 | 0.02 | 0.15 | 0.26 | 0.66 | 0.95 |
| 60 s | 0.9 | 0.02 | 0.02 | 0.05 | 0.18 | 0.29 | 0.74 | 0.95 |

Reference only, **not in the firmware**: detection on CH4 minus β × LPG
(β fitted per held-out survey, 0.67–0.91; same sigma, sustain and false-alarm
target, which needed k = 5):

| Exposure | x | 10 mV | 20 | 30 | 45 | 60 | 90 | 135 mV |
|---|---|---|---|---|---|---|---|---|
| 10 s | 0.1 | 0.06 | 0.08 | 0.11 | 0.15 | 0.34 | 0.66 | 0.89 |
| 10 s | 0.3 | 0.05 | 0.05 | 0.11 | 0.11 | 0.18 | 0.54 | 0.78 |
| 10 s | 0.6 | 0.03 | 0.05 | 0.05 | 0.11 | 0.11 | 0.18 | 0.57 |
| 10 s | 0.9 | 0.03 | 0.05 | 0.05 | 0.05 | 0.08 | 0.08 | 0.15 |
| 60 s | 0.1 | 0.02 | 0.00 | 0.02 | 0.06 | 0.15 | 0.42 | 0.60 |
| 60 s | 0.3 | 0.02 | 0.02 | 0.02 | 0.03 | 0.08 | 0.31 | 0.50 |
| 60 s | 0.6 | 0.00 | 0.02 | 0.02 | 0.02 | 0.03 | 0.06 | 0.32 |
| 60 s | 0.9 | 0.02 | 0.00 | 0.02 | 0.02 | 0.00 | 0.03 | 0.05 |

What this shows:
- **Independent detection does not depend on how much the LPG sensor picks up**
  (if anything, a bigger LPG response helps, because either channel can trigger).
  Subtraction collapses as the LPG share rises: at 90 mV it falls from 66 % to
  8 %. A real natural-gas leak raises both channels by an unknown ratio, which is
  why subtraction is excluded from the firmware.
- Subtraction does a little better for small, almost CH4-only plumes (x = 0.1),
  because cancelling the shared temperature and airflow error lowers its noise.
  The thermistor should give independent detection the same benefit without the
  cost.
- **Practical threshold today:** on drives, plumes of about 90 mV or more on the
  CH4 sensor are caught most of the time; 45 mV only about 1 time in 5. The
  earlier analysis's 30 % at 45 mV used a different (also assumed) plume shape
  and a different detector, so the two are not directly comparable.

## 7. Firmware and parity

- The detector is plain C99 with fixed-size state (no allocation): about
  15.5 kB more RAM (30.4 → 45.9 kB of 320 kB) and 8 kB more flash. It runs once
  per sample, after a 3-minute warm-up from heater-on. Each sample's residuals,
  sigmas and flags go to the app on the new Analysis characteristic, and each
  closed event's fingerprint on the Event characteristic
  ([phone_board.md](phone_board.md)). The app logs them as new CSV columns; the
  old `spike` column is kept for comparison.
- `python tools/replay.py parity` builds the same C file for the PC (zig cc) and
  replays all four surveys through it and through the Python twin, in three
  variants: shipped settings; a 30 s high-pass; and airflow + CO + per-unit
  adaptation with made-up airflow and CO signals:
  - **double-precision C matches Python** to 3 × 10⁻¹³ mV, with identical flags,
    events and classes, in every variant;
  - **single-precision C, as on the device**, differs by at most 0.006 mV, with
    no flag or class differences on these surveys. Where a residual sits within
    a few hundredths of a mV of the threshold, float rounding can move a
    detection by one sample. That was seen once, in an earlier test
    configuration, and is expected behaviour. The per-unit adaptation therefore
    keeps its state in double precision on the device.

## 8. Platform prototype

`tools/aggregate.py` bins every sample and event into 30 m cells and scores each
cell on persistence: the fraction of independent passes (re-entries within
10 minutes count as one) on which a channel was raised; the weakest peak over
all passes; and how many different times of day, travel directions, airflow
states and surveys the flagged passes cover. It never compares a cell with its
own average; only residuals from the shared model are used. It writes a ranked
candidate list with every event's fingerprint (UNRESOLVED included), a labels
template (unchecked / confirmed_leak / rejected / other_source), and a
fingerprint library of labelled events for retraining.

On these four surveys no cell has more than one flagged pass, so there is no
persistence yet: one device has rarely driven the same road twice under
different conditions.

## 9. What could not be determined

- **The natural-gas ratio** on this hardware: one confirmed leak (11 October)
  gave 0.26–0.58, which overlaps probable exhaust. NATURAL_GAS stays disabled.
- **Whether the false-alarm rate is right.** With about two events in the data,
  "1 per hour" is set by a handful of events, some possibly real.
- **What the unresolved both-channel events at stops were.** Not resolved; needs
  the exhaust survey and the thermistor.
- **The real plume shape.** Partly measured now (the update at the top): the
  LPG sensor responds more strongly and for longer than the CH4 sensor. The
  synthetic tests otherwise assume a top-hat exposure (10 s
  or 60 s) through a 4 s sensor lag, with the same lag on both channels. Real
  plumes from a leak are patchier, and the TGS2610 and TGS2611 may not respond
  at the same speed.
- **How the CH4/LPG ratio changes with concentration.** Probably substantially;
  the two sensors follow different power laws.
- **The thermistor's real airflow response, the bead's B value, and the CO
  module's current draw and methane response.** All of the hardware in
  [HARDWARE.md](HARDWARE.md) is designed from datasheets and calculation, and
  none of it has been built.
- **Whether the high-pass stage is still needed** once airflow is in the model.
- **Confidence values** are heuristics: there are no labelled events to
  calibrate them against.
- **Per-unit adaptation** (`ANOM_USE_RLS`) compiles and passes the parity test,
  but has not been evaluated: one device and four surveys cannot show whether it
  helps.
- **The bench bridge** (`tools/serial_bridge.py`) does not forward the new
  Analysis and Event packets, so the app shows no detector results in Expo Go;
  the serial CSV has them.
