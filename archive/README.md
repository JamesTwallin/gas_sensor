# Archive

Old designs, kept for reference. **Nothing here is current.** The current board
is [hardware/board](../hardware/board/), the firmware is
[firmware/phone_board](../firmware/phone_board/) and the app is [app](../app/).
Start from the [top-level README](../README.md).

Links inside these folders point at where things used to live, so some are broken.

| Folder | What it is | Why it is here |
|---|---|---|
| [first_prototype](first_prototype/) | The first prototype: a Waveshare ESP32-S3-Zero and sensor modules on a carrier board, with its own screen, GPS and memory card. Firmware, KiCad project, wiring notes and photos. | Replaced by the phone-companion board, which moves the screen, position and storage onto a phone. |
| [enclosure_boxes](enclosure_boxes/) | The first two box-and-lid case models. | Replaced by the front-shell-and-battery-tray case in [hardware/enclosure](../hardware/enclosure/). |
| [enclosure_rev_b](enclosure_rev_b/) | Case parts for the first phone-companion board (Pi Hut battery). | That board is no longer supported; the current case is in [hardware/enclosure](../hardware/enclosure/). |
| [board_rev_c](board_rev_c/) | A smaller (60 × 33 mm) version of the first board. | Never made. The current board took its circuit instead. |
| [board_gm402b](board_gm402b/) | A draft with Winsen GM-402B MEMS sensors instead of the Figaro ones. | Never made, and the GM-402B has been discontinued. |
| [air_blade_first_batch](air_blade_first_batch/) | The first air blades JLC made. | Drawn mirror-image: soldered in, they jam the board's I2C bus. Unusable. |

The first phone-companion board (66 × 36 mm, built and tested in September 2026)
is not a folder here: its files are at the git tag `rev-b`.
