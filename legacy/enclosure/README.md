# Box-and-lid enclosures (superseded)

> Kept for reference. The current case is the front shell and battery tray in
> [hardware/enclosure](../../hardware/enclosure/).

Two earlier two-part cases for the phone-companion board, both a base with a
screwed-on lid and the sensor cans through collars in the lid.

| File | What |
|---|---|
| `case_revb.scad` | for the 66 × 36 mm rev B board; printed and fitted in September 2026 |
| `stl/revb_base.stl`, `stl/revb_lid.stl` | its parts, after the fit revision described below |
| `case_revc.scad` | the same case re-parameterised for the 60 × 33 mm rev C board; never rendered or printed (it was `case.scad`) |
| `stl/base.stl`, `stl/lid.stl` | exported before `case_revc.scad` was re-parameterised, so they still show the rev B case; do not print them for rev C |

The renders these notes refer to (`build/*.png`) are not tracked; regenerate
them with the OpenSCAD commands below.

## `case_revb.scad`: rev B board

For the 66 × 36 mm rev B boards fabricated in September 2026. The same chimney
case as the rev C one below, with the sensor cans through collars in the lid,
plus:

- a dense hex grille in the lid right up to the sensor collars, and two rows of
  wall louvres on three sides of the sensor end of the base, so the cans sit in
  moving air even when you're standing still;
- four zip-tie eyelets on the outside of the long walls at floor level, taking
  5 mm ties, for strapping the case to a pole, a handlebar or a pack strap;
- the power switch in an open notch through the top of the wall, with a thumb
  scallop in the lid edge, so it can be worked from the side or from above
  without looking;
- an 8.5 mm battery pocket for the Pi Hut 2000 mAh cell (60 × 38 × 8 mm), with a
  stop rib that keeps the cell clear of the H1 screw boss. Push the cell to the
  SHT40 end.

Openings: the USB-C socket sits in a 14 mm wide notch open to the top of the
wall (the lid closes it), so any plug fits and it can be used with the lid off;
the switch is in a similar notch on the opposite edge. There is no opening for
the battery plug, which is internal. Print the base floor down and the lid top face down, no
supports. Files: `stl/revb_base.stl`, `stl/revb_lid.stl`; regenerate with the
OpenSCAD commands below, substituting `case_revb.scad`. Outside size 81 × 51 ×
24 mm, plus the eyelets. `-D 'part="section"'` renders the assembled case cut
in half lengthways, the quickest way to check clearances after a change.

**Fit revision after the first print (2026-09-30).** The first print was too
tight in three places, all fixed:

- the lid's lip dropped inside the cavity wall with 0.35 mm clearance and hit
  the screw posts. The base now has a 1.2 mm rebate around the top of the wall
  and the lip (1.0 mm thick, 1.0 mm tall) sits in that, 0.3 mm clear all round;
- the board's corners were 0.8 mm from the screw posts: `board_clear` is now
  5.0 mm (was 4.5), so the case grew 1 mm each way;
- the cell's top was 0.2 mm into the SHT40-end board shelf. The pocket is now
  9.5 mm deep and the cell sits in a fence (sunk ribs under it, side fences,
  a stop rib at the sensor end); the shelf at that end is replaced by stubs on
  the long walls outside the cell's width. 0.8 mm between cell and supports.

Also widened: sensor collar holes to cap + 1.6 mm (printed holes shrink), the
USB-C opening to 12 × 5 mm.

**Mirror fix, same revision.** The first print's sensor holes and wall openings
were a mirror image of the board. KiCad's y axis runs down the board and the
model's runs up, and the earlier mapping ignored that. `by()` now flips y, so
the KiCad top edge (switch) is the model's high-y wall and the KiCad bottom
edge (USB-C, battery plug) is the low-y wall. Every position in the file is
still written in KiCad coordinates; only the mapping changed.

## `case_revc.scad`: rev C board (not yet fabricated)

74 × 47 × 19.5 mm two-part case for the rev C layout.
The Figaro sensor cans poke through the lid so they sit in open air, and the case
is a chimney: air in through the wall louvres and floor vents, up past the hot
sensors, out through the lid grille.

**Status: parameters updated for the rev C board (60 × 33 mm), not yet
re-rendered, printed or fitted.** `case_revc.scad` carries rev C's outline, sensor,
USB-C, switch, button, LED, SHT40 and mounting-hole positions, and the battery
plug opening has moved from the bottom wall to the top wall beside the power
switch, where rev C's JST-PH now points (both power leads leave at the ESP32
end, away from the sensors). The STLs `stl/base.stl` and `stl/lid.stl` still show the rev B case:
regenerate them (below) before printing.

**Open problem before printing: the board hold-down.** The rev B case screwed
the board to a floor boss at its H1 hole, in a corner the cell did not reach.
A 60 × 33 mm board is smaller than the cell (the Pi Hut 2000 mAh cell the
pocket is now sized for is 60 × 38 × 8 mm), so every point of the board is over
the cell and the boss at `mount` lands on top of it. Either fit a shorter cell
(a 1000 mAh 50 × 34 mm cell leaves the H1 end clear) or replace the boss with a
hold-down from the lid before trusting the model.

## Regenerating

OpenSCAD 2021.01+; substitute `case_revb.scad` and the `revb_` file names for
the rev B case:

```
openscad -o stl/base.stl -D 'part="base"' case_revc.scad
openscad -o stl/lid.stl  -D 'part="lid"'  case_revc.scad
openscad -o build/assembly.png --imgsize=1400,1000 --camera=48,26,14,62,0,28,250 -D 'part="assembly"' case_revc.scad
```

`part="assembly"` also draws a mock board, sensors and cell, which is the quickest
way to check a change hasn't broken clearances.

## Printing (Bambu A1)

- **Material: PETG or ASA.** The heaters put ~0.6 W inside a small box and the
  case sits in sunlight on surveys; PLA creeps and can sag. PETG is the easy pick.
- **0.2 mm layers, 3 walls, 20 % infill.** No supports, no brim needed.
- **Orientation:**
  - **Base:** floor down, as modelled.
  - **Lid:** **top face down** on the plate. The sensor collars then print up from
    the plate, the locating lip points up, and the LED window prints as a clean
    0.4 mm membrane. Printed the other way up, the lip needs supports.
- Both parts fit the A1 plate easily; together about 35 g.

## Hardware you need

| Qty | Item |
|---|---|
| 4 | M2 × 8 mm self-tapping screws (lid into the corner posts) |
| 1 | M2 × 5 mm self-tapping screw (board to the boss at H1) |
| 1 | 1S LiPo, JST-PH, protected: pocket sized for the Pi Hut 2000 mAh cell, 60 × 38 × 8 mm (`batt_h = 8.5`); a 1200 mAh 60 × 35 × 5 mm cell also fits (see the board README for polarity) |
| — | optional: 2 mm foam pad under the cell |

The posts take M2 self-tappers directly (1.7 mm pilot holes). If you prefer heat-set
inserts, open the pilots to 3.2 mm and set M2 × 3 mm inserts.

## Assembly

1. Drop the cell into the floor pocket, wires toward the bottom-right, and route
   the lead up the right-hand end. The ribs hold it off the floor vents.
2. Lower the board onto the end shelves, sensors at the right-hand end.
3. Fit the M2 × 5 screw through the board's H1 hole into the boss.
4. Plug the battery into J2 through the top-wall opening next to the power
   switch. **Check the polarity first** (board README).
5. Line the sensor cans up with the lid collars and lower the lid. The lip locates
   it; the cans should pass through without touching.
6. Four M2 × 8 screws, gently — they cut their own threads.

## Openings

- **Bottom edge:** USB-C.
- **Top edge:** the battery connector opening and the power slide switch,
  lever reachable from the side.
- **Right end:** louvres only; the sensor cans overhang the board edge here.
- **Lid:** sensor collars, hex grille over the sensor end and over the SHT40,
  RST and BOOT holes (press with a pen or paperclip), LED window.
- **Walls:** louvres at board level, sensor end and SHT40 end.
- **Left end:** lanyard loop.

## Known compromises

- **Not weatherproof.** The sensors need open air; the case is vented top, bottom
  and sides. Drizzle-resistant if the lid faces up, nothing more.
- **The cell covers most of the floor vents.** That's why the wall louvres are
  there. If you run without a battery, airflow is considerably better.
- **The board is supported at its ends**, not the middle. Press RST/BOOT gently.
- **The sensor cans get hot** (~280 mW each). They protrude by design; don't grip
  them, and give the device a minute of settling after handling before trusting
  a reading.
- **SHT40 accuracy:** the tongue on the board and the vents at that end help, but
  temperature inside any case reads slightly high. Compare against a reference
  thermometer before trusting absolute temperature.

## If you change the board

Each model carries the board dimensions and part positions at the top (all in
KiCad board coordinates, origin at the board's top-left corner). Update them
there and re-export; nothing else is hard-coded. Set `board_t = 1.0` if you order
1 mm boards.
