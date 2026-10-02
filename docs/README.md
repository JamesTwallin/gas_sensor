# docs

Project documentation that does not belong in code:

- [phone_board.md](phone_board.md) — the design spec for the current board
  (rev B / C): why each part is there, power, the gas sensor circuit, the pin
  map, the Bluetooth protocol and the CSV the app writes. This is the source of
  truth for the schematic generator, the firmware and the app.
- [sensors.md](sensors.md) — Figaro TGS2611 / TGS2610 behaviour notes: why
  absolute ppm is only indicative, the humidity confounder, warm-up, field
  cautions.

Elsewhere:

- [../hardware/phone_board/README.md](../hardware/phone_board/README.md) —
  building the rev C board: the generator scripts, ordering, first power-up.
- [../hardware/enclosure/README.md](../hardware/enclosure/README.md) — the
  printed case.
- [../app/README.md](../app/README.md) — the phone app.
- [../legacy/rev_a/schematic.md](../legacy/rev_a/schematic.md) — the connection
  spec for the retired rev A carrier board.

The hardware design will be released under CERN-OHL-S when it is ready; the
firmware is MIT (see the top-level LICENSE).
