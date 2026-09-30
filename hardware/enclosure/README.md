# Handheld enclosure

Two-part printed cases for the [phone-companion board](../phone_board/).

## `case_revb_v2.scad`: front shell + battery tray (current design)

The layout that replaced the box-and-lid: the board screws into a **front
shell** with the sensors through its face, and a **back tray** carries the
battery in its own pocket and traps it when screwed on.

![v2](build/v2_assembly.png)

- **Case is 81 × 57 mm** (was 51 wide). The cell has to pass between the two
  corner posts at the tray's open end on its way into the compartment, and at
  51 mm wide the gap between them was 36 mm for a 38 mm cell. Now 41.6 mm.
- **Front shell** (81 × 57 × 11.4 mm). Sensor collars and cap holes in the
  face, hex grille around them and at the SHT40 end, RST/BOOT pen holes, LED
  window, engraved lettering. Inside, two 7 mm bosses at the board's H1 and H2
  holes: the board goes in component side first and two M2 × 5 screws through
  the board's back pull it onto them. USB-C and the switch sit in notches open
  to the shell's back edge, so both are reachable with the tray off; the tray's
  rim closes them. Louvres at component level on three sides of the sensor end.
  Four corner posts with pilot holes take the tray screws.
- **Back tray** (78.6 × 57 × 11.8 mm plus a 1 mm lip). A closed compartment
  for the Pi Hut 2000 mAh cell, 60 × 38 × 8 mm: floor, side fences, an end
  fence at the SHT40 end and a 1.2 mm divider plate over the top that keeps the
  cell separate from the board. The compartment is open at the sensor end, a
  full-width slot the cell slides into like a drawer; the divider stops 8 mm
  short of that end so the lead can come up through the gap to the board's
  JST. The front shell's sensor-end wall carries a skirt that reaches down over
  the open end, so with the tray screwed on the slot is closed and the cell is
  captive. Four counterbored corner posts, lip into the shell's rebate on the
  other three sides, zip-tie eyelets on the long walls. No vents in the
  battery compartment.
- **Orientation**: the board lies component side down in the shell. It goes in
  as if turned over about its long axis, so the sensor end stays at the
  lanyard-free end, the switch is on one long edge and USB-C on the other. Seen
  from the front, the two collars are on the left with CH4 the lower one, the
  switch scallop on the bottom edge, and the SHT40 grille top right.
- **Access with the tray on**: matching 20 mm wide, 5 mm deep scallops cut
  through the face and wall at both the switch and the USB-C socket, on top of
  the side notches (14 × 7.4 mm at the USB-C, 15 × 8 mm at the switch), so a
  thumb reaches the lever and a plug goes in from the front edge.
- **Screws**: 4 × M2 × 8 for the tray, 2 × M2 × 5 for the board. The tray's
  counterbores are 9.3 mm deep, leaving 2.5 mm of plastic under each head, so
  an M2 × 8 puts 5.5 mm of thread into the shell's posts (pilots are 7 mm
  deep). A PH0 or PH00 driver reaches the head down the 4.6 mm bore. The tray
  screws pass through the divider plate at the SHT40-end corners.
- **Second print revision (2026-10-01)**: every corner post is now embedded in a
  solid 5.2 mm block joined to the adjacent walls, in both parts. The first
  print's two tray posts at the open end stood alone on the floor and snapped
  off. The battery compartment has 0.6 mm of play around the cell and 1 mm over
  it (was 0.3 and 0.5, too tight printed). The cell stops 0.6 mm short of the
  corner blocks at the open end, which reach 1.8 mm into its width, so the
  block zone is 5.2 mm of room for the lead, which passes between the two
  blocks. Face lettering: CH4, RST, USB by the port scallop, ON / OFF either
  side of the switch scallop (ON is lever toward the sensor end). The BOOT
  button's pen hole is there but unlabelled.
- **Print**: front face down (collars and lettering on the plate), tray outer
  face down. No supports: the divider is a 39 mm bridge between the side
  fences, which PETG on the A1 handles. Files `stl/revb_v2_front.stl`,
  `stl/revb_v2_back.stl`. Overall assembled depth 22.7 mm.
- **Assembly**: fit the sensors' end of the board under the collars and screw
  the board to the bosses. Slide the cell into the tray's open end, lead first
  is easiest, until it meets the end fence. Bring the lead up through the gap
  at the end of the divider, past the end of the board, and plug it into the
  JST. Screw the tray on: the shell's skirt now covers the open end.
- `-D 'part="section"'` cuts the assembled case in half lengthways for a
  clearance check.

The older box-and-lid `case_revb.scad` below is kept for reference.

## `case_revb.scad`: rev B board (the boards in hand)

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

![rev B](build/revb_assembly.png)

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

## `case.scad`: rev C board (not yet fabricated)

74 × 47 × 19.5 mm two-part case for the rev C layout.
The Figaro sensor cans poke through the lid so they sit in open air, and the case
is a chimney: air in through the wall louvres and floor vents, up past the hot
sensors, out through the lid grille.

![assembly](build/assembly.png)

**Status: parameters updated for the rev C board (60 × 33 mm), not yet
re-rendered, printed or fitted.** `case.scad` carries rev C's outline, sensor,
USB-C, switch, button, LED, SHT40 and mounting-hole positions, and the battery
plug opening has moved from the bottom wall to the top wall beside the power
switch, where rev C's JST-PH now points (both power leads leave at the ESP32
end, away from the sensors). The STLs and `build/assembly.png` still show the rev B case:
regenerate them (below) before printing.

**Open problem before printing: the board hold-down.** The rev B case screwed
the board to a floor boss at its H1 hole, in a corner the cell did not reach.
A 60 × 33 mm board is smaller than the cell (the Pi Hut 2000 mAh cell the
pocket is now sized for is 60 × 38 × 8 mm), so every point of the board is over
the cell and the boss at `mount` lands on top of it. Either fit a shorter cell
(a 1000 mAh 50 × 34 mm cell leaves the H1 end clear) or replace the boss with a
hold-down from the lid before trusting the model.

## Files

| File | What |
|---|---|
| `case.scad` | the model, parametric — edit this, not the STLs |
| `stl/base.stl` | print 1 |
| `stl/lid.stl` | print 1 |

Regenerate after editing (OpenSCAD 2021.01+):

```
openscad -o stl/base.stl -D 'part="base"' case.scad
openscad -o stl/lid.stl  -D 'part="lid"'  case.scad
openscad -o build/assembly.png --imgsize=1400,1000 --camera=48,26,14,62,0,28,250 -D 'part="assembly"' case.scad
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

`case.scad` carries the board dimensions and part positions at the top (all in
KiCad board coordinates, origin at the board's top-left corner). Update them
there and re-export; nothing else is hard-coded. Set `board_t = 1.0` if you order
1 mm boards.
