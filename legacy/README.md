# Legacy

Earlier versions, kept for reference. **Nothing here is the current design**:
that is the rev C board in [hardware/phone_board](../hardware/phone_board/) with
the firmware in [firmware/phone_board](../firmware/phone_board/) and the phone
app in [app](../app/). Start from the [top-level README](../README.md).

| Folder | What | Why it is here |
|---|---|---|
| [rev_a](rev_a/) | The first prototype: a Waveshare ESP32-S3-Zero and sensor modules on a carrier board, with its own OLED, GNSS receiver and microSD card. Firmware, KiCad project, connection spec and photos. | Replaced by the phone-companion boards (rev B onwards), which move the display, position and storage onto a phone. |
| [enclosure](enclosure/) | The two box-and-lid case models. | Replaced by the front-shell-and-battery-tray case in [hardware/enclosure](../hardware/enclosure/). |

The rev B board (the 66 × 36 mm layout that was built and tested) is not a
folder: rev C replaced it in place. Its files are at the git tag `rev-b`.
