# Handheld enclosure (rev C board)

74 × 47 × 19.5 mm two-part case for the [phone-companion board](../phone_board/).
The Figaro sensor cans poke through the lid so they sit in open air, and the case
is a chimney: air in through the wall louvres and floor vents, up past the hot
sensors, out through the lid grille.

![assembly](build/assembly.png)

**Status: parameters updated for the rev C board (60 × 33 mm), not yet
re-rendered, printed or fitted.** `case.scad` carries rev C's outline, sensor,
USB-C, switch, button, LED, SHT40 and mounting-hole positions, and the battery
plug opening has moved from the bottom wall to the right wall, where rev C's
JST-PH now points. The STLs and `build/assembly.png` still show the rev B case:
regenerate them (below) before printing.

**Open problem before printing: the board hold-down.** The rev B case screwed
the board to a floor boss at its H1 hole, in a corner the cell did not reach.
A 60 × 33 mm board is smaller than a 60 × 35 mm cell, so every point of the
board is now over the cell and the boss at `mount` lands on top of it. Either
fit a shorter cell (a 1000 mAh 50 × 34 mm cell leaves the H1 end clear) or
replace the boss with a hold-down from the lid before trusting the model.

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
| 1 | 1S LiPo, ~60 × 35 × 5 mm, JST-PH, protected (see the board README) |
| — | optional: 2 mm foam pad under the cell |

The posts take M2 self-tappers directly (1.7 mm pilot holes). If you prefer heat-set
inserts, open the pilots to 3.2 mm and set M2 × 3 mm inserts.

## Assembly

1. Drop the cell into the floor pocket, wires toward the bottom-right, and route
   the lead up the right-hand end. The ribs hold it off the floor vents.
2. Lower the board onto the end shelves, sensors at the right-hand end.
3. Fit the M2 × 5 screw through the board's H1 hole into the boss.
4. Plug the battery into J2 through the right-hand wall opening, under the
   sensors. **Check the polarity first** (board README).
5. Line the sensor cans up with the lid collars and lower the lid. The lip locates
   it; the cans should pass through without touching.
6. Four M2 × 8 screws, gently — they cut their own threads.

## Openings

- **Bottom edge:** USB-C.
- **Right end:** a wide opening at the battery connector, below the sensor louvres.
- **Top edge:** the power slide switch, lever reachable from the side.
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
