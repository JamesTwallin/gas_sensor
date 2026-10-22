# Field protocols: four surveys the detector needs next

The gas detector (see [REPORT.md](REPORT.md)) is fitted from ordinary surveys,
but three things cannot be learnt from ordinary surveys at all:

1. **Airflow calibration** relates the new airflow thermistor to real air speed,
   and checks it explains the gas sensors' airflow effect.
2. **Exhaust characterisation** records what vehicle exhaust looks like on the
   sensors, with and without the CO sensor.
3. **Positive control** measures what a real mains-gas leak looks like on *this*
   hardware: the CH4-to-LPG ratio that defines the NATURAL_GAS class. Until this
   survey is done, the firmware never says NATURAL_GAS.
4. **Sensor comparison** (MEMS rig) runs the two Figaro sensors and the two MEMS
   sensors on the MEMS blade side by side, on the same plumes, to decide which
   sensor a cheaper production unit should carry ([mems_rig.md](mems_rig.md)).

Each section says what to bring, what to do, and what the analysis will produce.

## Before any of these surveys

- **Sensors burnt in.** New Figaro sensors drift for their first 4–7 days of
  power. Run the board on USB for a week before the first survey, and note in
  `tools/surveys.json` any survey recorded during burn-in.
- **Firmware 1.1.0 or later** (the detector), built with the add-ons that are
  fitted (`HW_AIRFLOW`, `HW_AIRFLOW_REF`, `HW_CO`; see [HARDWARE.md](HARDWARE.md)).
- **Warm up for at least 10 minutes** with the device in the open air, in its
  survey position, before the first measurement. The firmware's own warm-up is
  3 minutes, but the elements are still settling after that.
- **Shade the device.** Sun on the case heats the sensors and reads as a
  temperature effect.
- **Same position every time.** In a car: same window, same height, gas inlet
  facing forward, window open by the same amount. On foot: held at chest height
  in front of you, inlet forward, away from your breath.
- **Keep a written log** of what you did and when (phone clock times, to the
  minute): start and end of each segment, anything unusual (a lorry, a bonfire,
  a stop). The BOOT button does not mark the app's log yet, so notes are the
  record.
- After the survey, add the file to `tools/surveys.json` with its mode
  (`drive` / `walk` / `static`) and a note of what it was.

Safety: a driver drives and does nothing else; a second person handles the phone
and the log. Keep to speed limits; choose quiet roads for the speed steps.

---

## 1. Airflow calibration

**Purpose.** The airflow index (from the thermistor) should rise with air speed
in a predictable way, and the gas sensors' unexplained wander at stops and in
traffic should line up with it. This survey measures both. GPS speed is used
here, *offline only*, as the reference for air speed; it never goes into the
model.

**Bring.** Device with the thermistor fitted, phone, a closed cardboard box,
notebook. Optional: a handheld vane anemometer (about £20) for the walking part.

**Steps.**

1. **Still-air calibration.** Box calibration as in
   [HARDWARE.md](HARDWARE.md#16-still-air-calibration) (opcode 0x04, 60 s).
   Write down `g_still` from the Info JSON.
2. **Static, open air, 5 min.** Device in its car position, engine off, window
   open, car parked out of the wind if possible. Note the wind (calm / light /
   breezy, and direction).
3. **Speed steps on a quiet, straight, level road**, the same stretch in both
   directions (driving both ways averages out the wind):
   - hold each speed steady for **2 minutes**: **0** (stopped, engine running),
     **10, 20, 30, 50, 70 km/h** (only where legal and safe);
   - then come back down: 50, 30, 20, 10, 0;
   - then repeat the whole up-and-down sequence in the other direction.
   Log the start time of each step.
4. **Walk.** On a quiet path: stand still 2 min, walk slowly 2 min, walk briskly
   2 min, stand still 2 min. Repeat once facing the other way. If you have a
   vane anemometer, hold it beside the device for 30 s in each step and note the
   reading.
5. **Still-air calibration again** in the box at the end. A big change from
   step 1 means the bead or its mounting moved.

**Analysis.**
- Fit King's law, `G = A + B·speed^n`, to the airflow conductance against GPS
  speed (car) or anemometer speed (walk), per step. Check that it is the same up
  and down, and both directions.
- Plot the conditions-model residual of each gas channel (with airflow switched
  *off*) against the airflow index and its smoothed versions. The step changes
  at 0 ↔ 10 ↔ 20 km/h should line up in both.
- Set `ANOM_USE_AIRFLOW 1`, refit (`python tools/replay.py fit --write-config`,
  then `tune`), and compare the residual sigma and synthetic detection with the
  airflow-off model. Expect the biggest gain on drives, CH4 channel (an offline
  test with GPS speed as a stand-in cut its robust residual SD from about 12 to
  about 7 mV; see REPORT.md).
- Check that `ANOM_AIR_LOW_INDEX` (the LOW_AIRFLOW threshold) sits between the
  "stopped" and "10 km/h" readings.

---

## 2. Exhaust characterisation

**Purpose.** Stops and slow traffic raise both gas channels. Some of that is
airflow, and some is other vehicles' exhaust. This survey records the exhaust
fingerprint (CH4-to-LPG ratio, which channel leads, duration, and the CO rise)
so the classifier can recognise it. Do it twice if you can: once **without** the
CO sensor, and once with it.

**Bring.** Device (CO sensor fitted for the second run), a car you can leave
idling outdoors, a second vehicle if possible (petrol and diesel differ), tape
measure, notebook.

**Safety.** Outdoors only, never in a garage or enclosed space. Stand to the
side of the exhaust, not in it. Do not idle longer than needed.

**Steps.**

1. **Clean-air reference**, 5 min, 20 m upwind of the parked car.
2. **Behind a running vehicle**, engine idling, device at tailpipe height,
   **downwind**:
   - 10 m back, 2 min; then 2 min clean air (walk 20 m upwind);
   - 3 m back, 2 min; then 2 min clean air;
   - 1 m back, 1 min; then 3 min clean air.
   Do this with the engine **cold** (first start of the day) and again **warm**
   (after a 15-minute drive). Different engines if available (petrol, diesel,
   hybrid).
3. **Slow traffic.** Drive 15–20 minutes in stop-start traffic (a queue at
   lights, a town centre at rush hour). Log when you are directly behind a bus,
   lorry or old car.
4. **Free-flowing comparison.** 10 minutes on a quiet road at a steady speed.

**Analysis.**
- Replay with `python tools/replay.py run FILE.csv`. Each stationary exposure
  should produce an event; collect their fingerprints (ratio, lead, duration,
  peak residuals, CO rise and its lag after the gas channels).
- Compare the exposures with the unresolved slow-traffic events from ordinary
  surveys (REPORT.md). If they match, those events were very likely exhaust.
- With CO: set `ANOM_CO_RISE_PPM` to a level that every close exposure clears
  but clean air does not, and `ANOM_CO_TAIL_S` to cover the CO sensor's lag. Then
  set `ANOM_USE_CO 1` and refit. Both-channel events with a CO rise then become
  EXHAUST.
- Note how often a warm, modern engine gives *no* CO rise. That is how much
  exhaust the CO rule will miss.

---

## 3. Positive control: a confirmed mains-gas leak

**Status (11 October 2026): first visit done.** Three passes of one known outdoor
leak in survey D4 (two driving, one stopped), with no reference instrument. All
three were detected. The LPG sensor rose about twice as much as the CH4 sensor,
and the ratio overlaps probable exhaust events. See the update at the top of
[REPORT.md](REPORT.md). Still needed: the walking passes, more visits in other
winds, a reference reading, and other leaks.

**Purpose.** No confirmed gas leak has been surveyed with this hardware, so
nobody knows what ratio of CH4 to LPG response a real leak gives. That ratio
depends on the local gas mix (methane plus a little ethane, propane, butane, and
the odorant) and on this particular sensor pair. Until it is measured, the
classifier calls every both-channel event UNRESOLVED.

**Finding a leak, safely.**
- **Never go looking for a leak on your own initiative near buildings.** If you
  smell gas, or the detector shows something near a house, call the **National
  Gas Emergency Service on 0800 111 999** (Great Britain) and move away.
- The proper route is the **local gas distribution network** (Cadent, SGN,
  Northern Gas Networks or Wales & West Utilities). They keep records of
  outdoor, non-hazardous leaks awaiting repair, and have leak survey teams with
  calibrated instruments. Ask whether you may survey one known outdoor leak,
  with their staff present or with their permission. Explain it is for a
  low-cost survey sensor that you want to calibrate.
- Alternatively, ask a university group or consultancy that does methane
  surveys (they often know of persistent street leaks).
- Get a **reference reading**: the network's or the group's instrument
  (flame-ionisation or laser methane detector) at the same spot and time. That is
  what turns the survey into a calibration.

**Bring.** Device (CO sensor too, if you have one: its trace should stay flat at
a gas leak), phone, notebook, the reference reading (or the person who takes
it). Record the wind (direction and strength) at the start and end of each
visit; a phone weather app is fine, a handheld anemometer is better.

**Steps.**

1. Warm up 10 minutes, shaded, 50 m or more upwind of the leak.
2. **On foot, at least 10 passes**, at walking pace, 0.5–1 m from the leak
   point (kerb, verge, valve cover), from different sides. Between passes walk
   30–50 m away so the sensors recover. Then **3 minutes held still** next to the
   leak (stationary detection must still work), then 5 minutes away.
3. **By car, at least 10 passes**, at 20–30 km/h, nearest lane, window open, the
   same side each time. Then 10 more from the opposite direction.
4. **Repeat on at least two more days**, with the wind from a different
   direction each time, and at a different time of day if possible.
5. Log every pass start time, and the reference instrument readings.

**Analysis.**
- Replay all positive-control files. Every pass should give an event (if not,
  that is the detection rate at this leak's strength).
- For each event, take the CH4-to-LPG peak residual ratio and both peaks. Plot
  the ratio against the CH4 peak: **expect the ratio to change with plume
  strength**. The two sensors respond to concentration with different power
  laws, so a single fixed ratio band will not fit large and small plumes alike.
- Define the NATURAL_GAS band from the spread of the ratio (for example the 5th
  to 95th percentile, or a band that widens at small amplitudes). Set
  `ANOM_NG_RATIO_LO`, `ANOM_NG_RATIO_HI` and `ANOM_NG_BAND_VALID 1` in
  `anomaly_config.h`.
- Check the band does **not** contain the exhaust events from survey 2. If it
  does, NATURAL_GAS can only be assigned with the CO sensor fitted (leave
  `ANOM_NG_WITHOUT_CO 0`).
- Record these events as labelled `confirmed_leak` in the fingerprint library
  (`tools/aggregate.py --labels`), with the reference reading in
  `measured_ppm`.
- Re-check against the leak's measured concentration: this gives the first real
  mV-per-ppm figure for each channel on this hardware.

## 4. Sensor comparison (MEMS rig)

**Purpose.** The MEMS rig carries four gas sensors in the same inlet air: the Figaro
TGS2611 (CH4) and TGS2610 (LPG), and on the MEMS blade a Saiya SY-CH4-37BPM
(methane) and an SGX MiCS-5524 (CO, hydrogen and other reducing gases, weak on
methane). This survey answers one question: **does a MEMS sensor see a real leak
as well as the Figaros, at the speeds we survey at?** On the 11 October leak the
signal after the conditions model was about 5, 16 and 37 robust SD on the TGS2611
and 18, 40 and 66 SD on the TGS2610, at 65 km/h, 43 km/h and stopped. A MEMS sensor
is worth switching to only if it gets comparable SD at 43 to 65 km/h, at the same
false-alarm rate.

**Why this design.** Every pass is seen by all four sensors at once, so the
comparison is paired: plume strength, wind and traffic cancel out, and what is
left is the difference between sensors. The spread of that paired difference
from pass to pass is not known yet; 10 passes at each speed is enough to tell a
1.5 times difference in SNR from no difference if the pass-to-pass spread of the
log ratio is up to about 0.3 (an assumption, to be checked after the first
visit). Detection rates need more passes than SNR does, so the analysis leans on
SNR and uses detection as a check. False alarms are rare (the target is about
one an hour), so the clean-air drives need hours, not minutes.

**Before you go.**
- Everything in "Before any of these surveys" above, plus:
- **Burn in the MEMS blade.** Run the board with the blade fitted for at least
  48 hours before the first survey (the firmware counts the hours and reports
  `mems_burnin_h` in its info; the Saiya datasheet asks for at least 4 hours after
  soldering, and both makers' parts drift for longer than that). Note in
  `tools/surveys.json` any survey recorded before burn-in finished.
- **Warm up for at least 60 minutes** with the heaters on before the first pass.
  The 37BPM datasheet asks for an hour after every power-up; the firmware does not
  use the MEMS channels until `MEMS_WARMUP_MS` (60 minutes) has passed, and the
  app's MEMS tile says "warming" until then.
- **Firmware built with `-e board_mems`**, app recording the MEMS columns
  (check one row of the CSV has `mems_a_vout_mv` filled in).
- **Fitted blade, case closed.** The MEMS blade's tip should stand about 8 mm out
  of its slot, beside the LPG sensor's cap, touching nothing.
- A **confirmed leak** found as in survey 3 (same safety rules: never go looking
  near buildings, and arrange it through the gas network or a survey group).
  Ideally the same leak as survey 3, with a reference reading.

**Steps (one visit).**

1. Warm up 60 minutes, shaded, 50 m or more upwind of the leak.
2. **Clean-air drive, 60 minutes**, on roads away from the leak, at the mix of
   speeds you normally survey at. Start the recording and note the time.
3. **Passes by car, 10 at each steady speed: 30, 50 and 65 km/h** (only where
   those speeds are legal and safe; drop a speed rather than speed up near the
   leak). Hold the speed steady for at least 100 m before and after the leak.
   Same lane and side each time, window position unchanged. Between passes drive
   at least 300 m on, turn round and come back, so the sensors recover (at least
   60 seconds between passes). Alternate the direction of travel if the road
   allows; note it.
4. **On foot, 10 passes** at walking pace, 0.5 to 1 m from the leak point,
   with 30 to 50 m between passes, then **3 minutes held still** next to the
   leak and 5 minutes away.
5. **Clean-air drive, 60 minutes** again on the way back.
6. Write down every pass: start time (to the second, from the phone), speed,
   direction, and anything odd (a lorry, a bus, a smoker, roadworks).

**Repeat** on at least **three days** with different wind directions, so each
speed gets 30 passes in all, and clean air gets 6 hours or more. If a second
confirmed leak is available, give it one visit too: one leak only tests one
strength and one gas mix.

**Record.** Add each file to `tools/surveys.json` with a `leak_utc` window for
every pass (start to 30 seconds after the leak point), and `exclude_utc` windows
for anything not to be scored (stops at the leak beyond the 3 minutes, traffic
incidents). Do not commit the survey files or anything derived from them: they
contain GPS tracks.

**Analysis.** `python tools/compare_sensors.py --surveys <ids>` does all of this
per channel; it reads the labelled windows from `tools/surveys.json`.
- Fit each channel's conditions model on the clean-air drives only
  (`python tools/replay.py fit`), so that the leak passes do not tune the model.
  The MEMS channels start with empty coefficient rows; this survey is what fills
  them.
- **Noise:** robust SD of each channel's residual on the clean-air drives.
- **Matched false alarms:** for each channel, the threshold that gives one alarm
  an hour (and one every five hours) on the clean-air drives. All detection
  numbers below are at those thresholds, so no sensor wins by being trigger-happy.
- **Per pass:** peak residual, SNR in robust SD, and detected or not, for every
  channel. Compare channels **pass by pass** (the log of the SNR ratio, and how
  many passes each channel detected that the other missed), at each speed.
- **Airflow:** how much each channel's residual moves with the air blade's
  airflow index on the clean-air drives. A sensor that is less upset by airflow
  is worth more at speed than its still-air SNR suggests.
- **Temperature and humidity:** each channel's conditions-model coefficients, and
  the size of the conditions effect in mV per degree and per g/m3.
- **Response time:** 10 to 90 % rise time on the walking and 30 km/h passes, and
  each channel's lag behind the fastest one.
- **Secondary:** synthetic plumes added to the clean-air drives
  (`compare_sensors.py` does this unless `--no-synth`), for detection against
  plume size where the real leak gives too few points.

**Decision rule.** Carry a MEMS sensor into production only if, at 43 to 65 km/h
and at matched false alarms, its median paired SNR is at least about 0.7 times
the better Figaro's and it detects at least as many passes as the TGS2611.
Otherwise production keeps the TGS2610 (the stronger grid-gas channel so far).
Write the result, with the numbers, into [mems_rig.md](mems_rig.md).
