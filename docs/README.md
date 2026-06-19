# docs

Project documentation that does not belong in code:

- [sensors.md](sensors.md) — Figaro NGM2611 / LPM2610 calibration and behaviour
  notes (why absolute ppm is off the table, the humidity confounder, field cautions).
- [schematic.md](schematic.md) — the carrier-board connection spec (rev A): every
  component, pin and net, the two power rails, the divider sub-circuit and the BOM.
  This is the source of truth the KiCad schematic is captured from.

Still to come:

- PCB layout exports (Gerbers) once rev A is routed
- Calibration notes: field-test results once the carrier board is built
- Survey methodology notes relevant to data provenance

The KiCad project lives in [../hardware/carrier_board/](../hardware/carrier_board/).
The hardware design will be released under CERN-OHL-S when it is ready; the
firmware is MIT (see the top-level LICENSE).
