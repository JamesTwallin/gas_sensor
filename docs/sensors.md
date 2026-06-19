# Sensor notes (Figaro NGM2611-E13 and LPM2610-D09)

Calibration and behaviour notes drawn from the official Figaro datasheets, kept
here for provenance and to inform the firmware. Figures cited are from the
"Technical Information for TGS2611" (Revised 11/17) and the matching TGS2610
documents. Where a value is read off a graph rather than a table it is marked
approximate.

## What is actually inside the modules

- **NGM2611-E13** (methane) contains a **TGS2611-E00** element plus a temperature
  compensation circuit (thermistor + trimmed load resistor) and a comparator.
- **LPM2610-D09** (LP gas) contains a **TGS2610-D00** element with the same kind
  of conditioning.
- The **-E** methane element has a **charcoal filter** in the cap to reject
  interference gases (alcohol, and the heavier hydrocarbons).
- The **-D** LP-gas element uses a **zeolite filter** for the same purpose.

The modules expose a **conditioned VOUT**, not the raw sensor resistance Rs. The
datasheet curves below are all in terms of Rs (or VRL across a load resistor),
which we cannot directly recover from the module output. So these notes explain
the *behaviour* and bound what is honestly claimable; they do not give us a
calibrated VOUT-to-ppm conversion.

## Why absolute ppm is not on the table

- **Huge sensor-to-sensor spread.** TGS2611 Rs in 5000 ppm methane is specified
  as **0.68 kOhm to 6.8 kOhm**, a 10x range across parts. Figaro therefore sort
  sensors into 24 ID groups and match a load resistor per group, and still note
  ~10% accuracy loss versus individual calibration. Without per-sensor
  calibration there is no trustworthy absolute ppm.
- The module hides Rs behind its conditioning circuit, single-point calibrated
  at the factory alarm concentration only.

Conclusion: this instrument is an **anomaly / relative-enhancement mapper**, not
a concentration analyser. Published claims should say "elevated above local
background", not a ppm figure.

## Sensitivity shape (useful for intuition, not calibration)

- Reference points differ between the two sensors: TGS2611 normalises Rs/Ro to
  **5000 ppm methane**; TGS2610 normalises to **1800 ppm iso-butane**.
- The methane response is a power law. From the specified
  **beta = Rs(9000 ppm) / Rs(3000 ppm) = 0.60 +/- 0.06**, the exponent is
  `n = ln(0.60) / ln(3) ~= -0.47`, i.e. **Rs is proportional to ppm^-0.47** for
  methane. Resistance falls (and conditioned VOUT rises) as gas increases.
- The LP-gas response is steeper. From
  **beta = Rs(3000 ppm) / Rs(1000 ppm iso-butane) = 0.56 +/- 0.06**, the exponent
  is `n = ln(0.56) / ln(3) ~= -0.53`, i.e. **Rs proportional to ppm^-0.53** for
  iso-butane. The steeper slope fits the LP sensor responding more strongly than
  the methane one. TGS2610 Rs has the same 0.68 to 6.8 kOhm part spread, at its
  reference of 1800 ppm iso-butane.
- This is the bare-element relationship. It tells us the response is monotonic
  and roughly log-shaped, which is why small near-baseline changes correspond to
  relatively large ppm changes. It does not map to module VOUT without
  characterising the module.

## Temperature and humidity (the confounder, quantified)

TGS2611 Table 1, Rs/Ro at 5000 ppm methane normalised to 20 C / 65 %RH (so
1.00 is the reference point):

| Temp \\ RH | 35% | 50% | 65% | 95% |
|---|---|---|---|---|
| -10 C |  |  |  | 1.51 |
| 0 C |  |  | 1.45 | 1.25 |
| 10 C |  | 1.33 | 1.19 | 1.02 |
| 20 C | 1.25 | 1.11 | 1.00 | 0.87 |
| 30 C | 1.05 | 0.94 | 0.86 | 0.77 |
| 40 C | 0.92 | 0.82 | 0.76 | 0.69 |

Reading this:

- **Both rising temperature and rising humidity lower Rs/Ro**, which on a MOX
  sensor looks like *more reducing gas*. So a humidity rise can masquerade as a
  gas anomaly.
- **Humidity is large.** At 20 C, going from 35 %RH to 95 %RH drops Rs/Ro from
  1.25 to 0.87, roughly a **30% change**. Stepping into fog, dew or rain is a
  real false-positive source.
- **Temperature alone is also large** (1.00 to 0.76 from 20 C to 40 C at 65 %RH),
  **but the module compensates for temperature** via its onboard thermistor. A
  thermistor senses temperature only, so **humidity is not compensated** and is
  the residual confounder we must handle ourselves.

How we handle it: log temperature, humidity and pressure (a **BME280** on the
shared I2C bus) with every reading for provenance, let the adaptive baseline
absorb slow drift, and flag fast humidity changes so a humidity-driven step is
not mistaken for a leak. We do **not** apply a numeric correction from this table
to VOUT, because the table is bare-element Rs/Ro and the module conditions and
hides Rs; doing so would invent precision. (The BME280 was chosen over a bare
AM2302/DHT22 because it joins the existing I2C bus with no extra GPIO or pull-up,
and the barometric channel is a free bonus -- an independent cross-check on the
GNSS altitude.)

TGS2610 Table 1, Rs/Ro at 1800 ppm iso-butane normalised to 20 C / 65 %RH:

| Temp \\ RH | 35% | 50% | 65% | 95% |
|---|---|---|---|---|
| -10 C |  |  |  | 1.60 |
| 0 C |  |  | 1.50 | 1.35 |
| 10 C |  | 1.50 | 1.23 | 1.08 |
| 20 C | 1.52 | 1.19 | 1.00 | 0.85 |
| 30 C | 1.23 | 0.94 | 0.79 | 0.68 |
| 40 C | 0.98 | 0.75 | 0.61 | 0.53 |

**The LP-gas sensor is more temperature- and humidity-dependent than the methane
one.** At 20 C, 35 %RH to 95 %RH drops Rs/Ro from 1.52 to 0.85, about **44%**
(versus ~30% for the methane sensor). So the **LPG channel is the more
humidity-vulnerable of the two**: a humidity rise lifts both channels, but the LP
channel further. The same caveat applies, that the module compensates
temperature but not humidity, so this RH sensitivity largely passes through to
the LPG VOUT.

## Warm-up and "initial action"

- On power-up after being unpowered, Rs drops sharply for the first seconds then
  recovers; this "initial action" can read as a false alarm. TGS2611 Fig. 12
  shows it settling within roughly **3 to 5 minutes**.
- The NGM2611 application guidance uses a **~2.5 minute startup delay**.
- Implication: the firmware's 15 s bench warm-up is only adequate because the
  sensor heater stays powered across reflashes. A genuine cold start needs
  minutes; lengthen WARMUP_MS for real surveys.

## Field cautions that affect the build

- **Silicone will poison the sensor irreversibly.** Do not use silicone RTV,
  sealants, adhesives or greases anywhere near the sensor (common in enclosures).
  Decomposed silicone coats the element and permanently kills sensitivity.
- **Water matters.** Condensation that lingers causes drift; freezing water
  cracks the element. Protect the inlet; keep it out of standing water and rain.
- **Air flow cools the element.** A 3.1 m/s stream changed VRL by about a factor
  of 1.11 (TGS2611 Fig. 16). So an aspirator fan helps sampling but shifts the
  reading; keep airflow consistent if one is fitted.
- **Needs ~21% oxygen** to behave as specified (fine outdoors).
- **The lighter test does not work on the methane channel.** The TGS2611-E
  charcoal filter blocks iso-butane, so lighter gas (butane) will **not** reach
  the methane element. Use lighter gas only to test the LP-gas (LPM2610) channel;
  test the methane channel with an actual methane source (mains natural gas).
  Also: prolonged or >10% iso-butane exposure can damage the element, so keep any
  such test brief.

## Candidate add-on: a particulate/combustion channel to reject traffic

Vehicle exhaust is a known false positive for this instrument. Petrol and diesel
exhaust carry CO, NOx and unburnt VOCs, all reducing gases the MOX elements
respond to -- and crucially the methane channel's **charcoal filter does not
adsorb CO** (too small and non-polar), so exhaust CO reaches the methane element
and mimics a leak. Composition alone (the CH4/LPG channels) therefore cannot
cleanly separate a passing vehicle from a gas leak.

The clean discriminator is a sensor that responds to **combustion but not to a
gas leak**, because a natural-gas leak emits **zero particulates** -- methane,
ethane and propane are gases, no soot. That orthogonality is exactly what a veto
channel needs; there is no cross-talk path from a leak into a particulate count.

- A bare PM sensor (Plantower PMS5003, Sensirion SPS30) flags **diesel** well --
  buses, lorries and idling taxis are the worst MOX confounders and the biggest
  PM emitters. It **under-catches petrol/GDI** exhaust (low PM, but plenty of
  CO/VOC that still hits the MOX) and EVs emit no exhaust gas anyway (only coarse,
  intermittent brake/tyre PM10).
- Preferred: a **Sensirion SEN5x (e.g. SEN55)** -- one **I2C** module giving
  PM1/2.5/4/10 **+ a NOx index + a VOC index + RH/T**. The NOx index rises with
  *all* combustion exhaust (diesel especially), plugging the petrol gap PM leaves;
  PM pins diesel/soot and doubles as an air-quality map; the RH/T feeds the
  humidity confounder we already track. Like the BME280 it joins the **existing
  I2C bus with no extra GPIO** (bare PM sensors such as the PMS5003 are UART).

Use it as a **coincidence veto, not a subtraction**: a transient CH4/LPG spike
arriving *with* a coincident PM/NOx spike is flagged as traffic and downweighted;
a spike with PM/NOx flat is kept as a candidate leak. Layer this on top of the
spatial persistence / revisit test (a real leak is anchored and repeats across
passes; a passing car is a one-time puff) -- the two attack the problem from
independent directions, which is what makes the combination robust.

Caveats: the Sensirion VOC/NOx outputs are *relative index* values (gas-agnostic),
useful as confounder flags but not as species ID; the module is fan-driven and
the docs above note airflow cools the MOX element and shifts its reading, so mount
the PM inlet so its fan does not pull across the gas inlet; and this rejects
*combustion*, not biogenic methane -- separating fossil from biogenic is still the
job of the CH4-vs-LPG differential, not this channel.

## Source documents

- TGS2611 Technical Information (Rev 11/17): sensitivity Fig. 4, T/RH Fig. 6 and
  Table 1, initial action Fig. 12.
- TGS2610 Technical Information (Rev 10/12) and Application Notes (Rev 11/13).
- NGM2611-E13 and LPM2610-D09 module product information (Rev 03).
