// Handheld enclosure for the rev B phone-companion board (66 x 36 mm, the
// boards fabricated in September 2026).
//
//   part = "base" | "lid" | "assembly"   (set on the command line: -D part=\"lid\")
//
// Design notes
//   - The two Figaro sensor cans poke through collars in the lid, so the hot
//     elements sit in open air: that is what makes the response fast.
//   - The case is a chimney: air in through two rows of wall louvres on three
//     sides of the sensor end and the floor vents, up past the sensors, out
//     through a dense hex grille that surrounds the collars.
//   - Four zip-tie eyelets on the long walls; the power switch sits in an open
//     notch with a thumb scallop in the lid.
//   - The SHT40 end has its own vents top and bottom so it measures outside air.
//   - Battery (Pi Hut 2000 mAh, 60 x 38 x 8 mm) sits in a fenced pocket on the
//     floor at the SHT40 end, clear of the H1 screw boss and of the board supports.
//   - The board rests on a shelf at the sensor end and stubs along the long
//     walls; one M2 screw at its right-hand hole stops it lifting. Four M2
//     screws hold the lid down. The lid's lip sits in a rebate in the wall top.
//
// Printing (Bambu A1, 0.4 mm nozzle): PETG or ASA preferred (the board runs warm
// and PLA creeps); 0.2 mm layers, 3 walls, 20 % infill. Both parts print flat,
// no supports: the base floor down, the lid top face down (collars and lip
// print upward). See README.md.

/* [Board] */
board_x = 66;           // board outline
board_y = 36;
board_t = 1.6;          // set 1.0 if you order 1.0 mm boards
board_r = 2;            // board corner radius
board_clear = 5.0;      // gap from board edge to wall: the corner screw posts reach 5.2 mm in, so this
                        // leaves ~1.3 mm between a post and the board's rounded corner (was 4.5: too tight printed)

/* [Cavity] */
wall = 2.4;             // outer wall
floor_t = 1.6;
lid_t = 1.8;
batt_h = 9.5;           // battery pocket height: 8 mm cell + 1.2 mm floor ribs + clearance under the board supports
batt_l = 60;            // Pi Hut 2000 mAh cell, 60 x 38 x 8 mm
batt_w = 38;
fit = 0.3;              // printed-fit clearance used for the cell pocket and the lid lip
board_gap = 2.0;        // clearance under the board (solder joints, battery bulge)
above_board = 7.0;      // clear height above the board (JST plug is the tallest part)
corner_r = 4;           // outer corner radius
post_r = 2.4;           // lid screw posts
screw_pilot = 1.7;      // M2 self-tapping pilot hole
screw_head = 3.9;       // M2 head counterbore in the lid
screw_clear = 2.2;      // M2 clearance hole in the lid

/* [Parts on the board] (x, y from the board's top-left corner, KiCad coords) */
s1 = [60.5, 9.0];       // CH4 sensor can centre
s2 = [60.5, 22.0];      // LPG sensor can centre
can_d = 9.4;            // sensor flange diameter (9.2 max) - stays under the lid
cap_d = 8.3;            // sensor cap diameter (8.1 max) - passes through the collar
cap_clear = 1.6;        // collar hole = cap_d + cap_clear (printed holes come out ~0.3 mm small)
can_h = 13.0;           // can height above the board
usb = [33.0, 36.0];     // USB-C mouth, bottom edge
usb_w = 14.0;           // width of the open USB-C notch (plug overmoulds are ~8.5 x 3.5 mm; chunky ones ~12)
sw1 = [33.0, 0.0];      // power slide switch, lever over the top edge
sw1_w = 11.0;
sw1_h = 4.6;
bat_conn = [50.0, 30.0];// JST-PH, faces the bottom edge (internal: no wall opening)
btn_rst = [29.6, 18.6];
btn_boot = [22.6, 31.4];
btn_d = 4.2;            // poke-through hole (press with a pen)
led = [25.0, 2.6];      // status LED
led_d = 3.6;
led_window = 0.4;       // thin printed diffuser over the LED
mount = [62.0, 32.5];   // board mounting hole that gets a screw (H1)
sht = [8.5, 30.0];      // SHT40 - vented top and bottom so it reads outside air


/* [Derived] */
cav_x = board_x + 2*board_clear;
cav_y = board_y + 2*board_clear;
cav_h = batt_h + board_gap + board_t + above_board;
out_x = cav_x + 2*wall;
out_y = cav_y + 2*wall;
base_h = floor_t + cav_h;
board_z = floor_t + batt_h + board_gap;      // underside of the board
shelf_d = 6.0;          // how far the end shelves reach in under the board
shelf_t = 1.5;
eps = 0.01;
$fn = 48;

// Board coords -> case coords (the board sits centred in the cavity). KiCad's y
// runs DOWN the board as drawn; the model's y runs up, so y is flipped here.
// Without that flip the sensor holes and the wall openings come out mirrored
// (the first print did).
function bx(x) = wall + board_clear + x;
function by(y) = wall + board_clear + (board_y - y);
// Which wall a KiCad edge lands on after the flip:
//   KiCad top edge (y = 0)        -> the model's high-y wall (out_y side)
//   KiCad bottom edge (y = 36)    -> the model's low-y wall (y = 0 side)

module rrect(x, y, r, h) {
    linear_extrude(h) offset(r = r) offset(r = -r) square([x, y]);
}

// Hex grille: airflow with enough bridging for a clean print
module hex_vents(x0, ya, x1, yb, z0, h, d = 4.2, gap = 1.4) {
    y0 = min(ya, yb);   // callers pass board-y limits through by(), which flips them
    y1 = max(ya, yb);
    p = d + gap;
    keep = (cap_d + cap_clear + 2.0) / 2 + d / 2 + 0.8;   // stay off the sensor collars
    for (j = [0 : floor((y1 - y0) / (p * 0.87))])
        for (i = [0 : floor((x1 - x0) / p)]) {
            cx = x0 + i * p + (j % 2) * p / 2;
            cy = y0 + j * p * 0.87;
            clash = min(norm([cx, cy] - [bx(s1[0]), by(s1[1])]),
                        norm([cx, cy] - [bx(s2[0]), by(s2[1])])) < keep;
            if (cx <= x1 && cy <= y1 && !clash)
                translate([cx, cy, z0]) cylinder(h = h, d = d, $fn = 6);
        }
}

module lanyard_loop() {
    // Tab on the left-hand short edge, away from the sensors
    difference() {
        translate([-6.5, out_y/2 - 6, 0]) rrect(9, 12, 3, 4.5);
        translate([-3.2, out_y/2, -eps]) cylinder(h = 10, d = 4.2);
        translate([-9, out_y/2 - 8, -eps]) cube([3.2, 16, 10]);  // blend into the wall
    }
}

// Zip-tie eyelets: four tunnels along the long walls at floor level, a tie
// runs through each parallel to the wall (5 mm wide ties), so the case can be
// strapped to a pole, a pack strap or a handlebar.
tie_len = 10; tie_proud = 3.6; tie_h = 8.0;
module tie_eyelets() {
    for (m = [0, 1]) for (x = [12, out_x - 12 - tie_len])
        translate([x, m ? out_y - eps : -tie_proud + eps, 0]) difference() {
            hull() {   // rounded outer face
                cube([tie_len, tie_proud - 1, tie_h]);
                translate([1, 0, 0]) cube([tie_len - 2, tie_proud, tie_h - 1]);
            }
            translate([-1, 0.8, 1.6]) cube([tie_len + 2, 2.0, 5.4]);   // slot 2.0 x 5.4
        }
}

module base() {
    difference() {
        union() {
            rrect(out_x, out_y, corner_r, base_h);
            lanyard_loop();
            tie_eyelets();
        }
        // main cavity
        translate([wall, wall, floor_t]) rrect(cav_x, cav_y, 2, cav_h + eps);

        // floor vents: under the sensors (chimney inlet) and under the SHT40
        hex_vents(bx(46), by(2), bx(64), by(32), -eps, floor_t + 2*eps);
        hex_vents(bx(3), by(24), bx(14), by(34), -eps, floor_t + 2*eps);

        // Wall louvres at board level: the cell covers most of the floor, so this
        // is where the air really comes in. Sensor end and SHT40 end.
        for (y = [2 : 4.5 : 34])                            // right end wall: two rows
            for (z = [board_z + 1.2, board_z + board_t + 3.4])
                translate([out_x - wall - eps, by(y) - 1.5, z])
                    cube([wall + 2*eps, 3, 2.6]);
        for (y = [8, 16, 24])                               // left end wall (SHT40)
            translate([-eps, by(y) - 1.5, board_z + 1.2])
                cube([wall + 2*eps, 3, 4.0]);
        for (x = [44 : 4.5 : 66])                           // KiCad top edge (switch side): two rows, sensor end
            for (z = [board_z + 1.2, board_z + board_t + 3.4])
                translate([bx(x) - 1.5, out_y - wall - eps, z])
                    cube([3, wall + 2*eps, 2.6]);
        for (x = [57 : 4.5 : 66])                           // KiCad bottom edge (USB side), sensor end, clear of the JST opening
            for (z = [board_z + 1.2, board_z + board_t + 3.4])
                translate([bx(x) - 1.5, -eps, z])
                    cube([3, wall + 2*eps, 2.6]);
        for (x = [3, 9, 15])                                // KiCad bottom edge, SHT40 end
            translate([bx(x) - 1.5, -eps, board_z + 1.2])
                cube([3, wall + 2*eps, 4.0]);

        // USB-C: KiCad bottom edge -> the low-y wall. An open notch from just
        // below the socket up through the top of the wall, so any plug overmould
        // fits and the cable can be plugged with the lid on or off. The lid
        // closes the top of the notch.
        translate([bx(usb[0]) - usb_w/2, -eps, board_z + board_t - 0.6])
            cube([usb_w, wall + 2*eps, base_h]);
        // (No opening for the battery plug: the cell lives inside the case and
        // the plug is fitted before the board goes in.)
        // Power switch: KiCad top edge -> the high-y wall. An open notch from the
        // lever right up through the top of the wall, so a thumb reaches the
        // lever from the side or from above.
        translate([bx(sw1[0]) - (sw1_w + 4)/2, out_y - wall - eps, board_z + board_t - 0.8])
            cube([sw1_w + 4, wall + 2*eps, base_h]);

        // Rebate around the top of the wall for the lid's lip: the inner 1.2 mm of
        // the wall is dropped by 1.2 mm, so the lip sits in it and locates the lid
        // without fouling the screw posts or the cavity wall.
        translate([wall - 1.2, wall - 1.2, base_h - 1.2]) rrect(cav_x + 2.4, cav_y + 2.4, 2.6, 1.2 + eps);
    }

    // lid screw posts in the cavity corners
    for (p = post_xy()) translate([p[0], p[1], floor_t])
        difference() {
            cylinder(h = cav_h, r = post_r);
            translate([0, 0, cav_h - 7]) cylinder(h = 7 + eps, d = screw_pilot);
        }

    // board support boss at the H1 mounting hole (clear of the battery)
    translate([bx(mount[0]), by(mount[1]), floor_t]) difference() {
        cylinder(h = board_z - floor_t, d = 5);
        translate([0, 0, -eps]) cylinder(h = 10, d = screw_pilot);
    }

    // Board supports. The board lands on a full-depth shelf along the sensor-end
    // wall, and on stubs along the long walls at both ends. There is no shelf
    // across the SHT40 end any more: the cell reaches under it (see the pocket
    // below), and a shelf there fouled the top of the cell.
    translate([out_x - wall - shelf_d, wall, board_z - shelf_t]) cube([shelf_d, cav_y, shelf_t]);
    for (m = [0, 1]) {
        translate([out_x - wall - 14, m ? out_y - wall - shelf_d : wall, board_z - shelf_t])
            cube([10, shelf_d, shelf_t]);                        // sensor end, long walls
        translate([wall, m ? out_y - wall - 3.0 : wall, board_z - shelf_t])
            cube([12, 3.0, shelf_t]);                            // SHT40 end, long walls (outside the cell's width)
    }

    // Battery pocket: the cell sits on sunk ribs (off the floor vents) inside a
    // fence on three sides, with the cavity wall as the fourth. Stop rib at the
    // sensor end keeps it clear of the H1 boss.
    for (x = [6 : 12 : 54]) translate([wall + x, batt_y0, floor_t - 0.6])
        cube([1.6, batt_w + 2*fit, 1.8]);                        // sunk into the floor: crosses the vents cleanly
    translate([batt_x1, batt_y0 - 1.2, floor_t - eps]) cube([1.2, batt_w + 2*fit + 2.4, batt_fence_h]);  // stop rib
    for (yy = [batt_y0 - 1.2, batt_y0 + batt_w + 2*fit])
        translate([wall + 6, yy, floor_t - eps]) cube([batt_x1 - wall - 6, 1.2, batt_fence_h]);           // side fences
}

// Cell pocket in case coords: against the SHT40-end wall, centred across the cavity.
batt_x0 = wall + fit;
batt_x1 = batt_x0 + batt_l + fit;
batt_y0 = wall + (cav_y - batt_w) / 2 - fit;
batt_fence_h = 4.0;

// Posts sit in the cavity corners, clear of the board's rounded corners
function post_xy() = [
    [wall + post_r + 0.4, wall + post_r + 0.4],
    [out_x - wall - post_r - 0.4, wall + post_r + 0.4],
    [wall + post_r + 0.4, out_y - wall - post_r - 0.4],
    [out_x - wall - post_r - 0.4, out_y - wall - post_r - 0.4],
];

module lid() {
    difference() {
        union() {
            rrect(out_x, out_y, corner_r, lid_t);
            // Lip that drops into the rebate in the top of the base wall (see
            // base()): 1.0 mm thick, 1.0 mm tall, `fit` clear of the rebate on
            // the outside and of the cavity wall on the inside.
            translate([wall - 1.2 + fit, wall - 1.2 + fit, -1.0])
                difference() {
                    rrect(cav_x + 2.4 - 2*fit, cav_y + 2.4 - 2*fit, 2.6, 1.0);
                    translate([1.0, 1.0, -eps]) rrect(cav_x + 2.4 - 2*fit - 2.0, cav_y + 2.4 - 2*fit - 2.0, 2.0, 1.0 + 2*eps);
                }
            // collars around the sensor cans: guide the cans and shed rain
            for (s = [s1, s2]) translate([bx(s[0]), by(s[1]), lid_t - eps])
                difference() {
                    cylinder(h = 1.0, d = cap_d + cap_clear + 2.0);
                    translate([0, 0, -eps]) cylinder(h = 2 + 2*eps, d = cap_d + cap_clear);
                }
        }
        // sensor can holes
        for (s = [s1, s2]) translate([bx(s[0]), by(s[1]), -eps])
            cylinder(h = lid_t + 2*eps, d = cap_d + cap_clear);

        // dense grille right up to the sensor collars (chimney outlet), and over the SHT40
        hex_vents(bx(42), by(1.5), bx(65.5), by(34.5), -eps, lid_t + 2*eps, d = 3.6, gap = 1.3);
        hex_vents(bx(2), by(24), bx(14), by(34), -eps, lid_t + 2*eps);

        // thumb scallop in the lid edge above the power switch (high-y edge; cuts the lip too)
        translate([bx(sw1[0]), out_y, -2]) cylinder(h = lid_t + 4, d = sw1_w + 4);
        // and the same above the USB-C notch (low-y edge): finger room for the plug
        translate([bx(usb[0]), 0, -2]) cylinder(h = lid_t + 4, d = usb_w + 2);

        // button access and LED window
        translate([bx(btn_rst[0]), by(btn_rst[1]), -eps]) cylinder(h = lid_t + 2*eps, d = btn_d);
        translate([bx(btn_boot[0]), by(btn_boot[1]), -eps]) cylinder(h = lid_t + 2*eps, d = btn_d);
        translate([bx(led[0]), by(led[1]), led_window])
            cylinder(h = lid_t, d = led_d);                // 0.4 mm diffuser membrane

        // screw holes, counterbored
        for (p = post_xy()) translate([p[0], p[1], -eps]) {
            cylinder(h = lid_t + 2*eps, d = screw_clear);
            translate([0, 0, lid_t - 1.0]) cylinder(h = 1.0 + eps, d = screw_head);
        }

        // labels
        // label between the LED window (board y 2.6) and the RST hole (y 18.6)
        translate([bx(30), by(14.5), lid_t - 0.5]) linear_extrude(0.5 + eps)
            text("CH4", size = 5, font = "DejaVu Sans:style=Bold", halign = "center");
        translate([bx(btn_rst[0]) + 4.5, by(btn_rst[1]) - 1.2, lid_t - 0.4]) linear_extrude(0.4 + eps)
            text("RST", size = 2.6, font = "DejaVu Sans");
        translate([bx(btn_boot[0]) + 4.5, by(btn_boot[1]) - 1.2, lid_t - 0.4]) linear_extrude(0.4 + eps)
            text("BOOT", size = 2.6, font = "DejaVu Sans");
    }
}

// ---- preview only ----------------------------------------------------------
module board_mock() {
    color("green") translate([bx(0), by(board_y), board_z]) rrect(board_x, board_y, board_r, board_t);
    for (s = [s1, s2]) color("silver")
        translate([bx(s[0]), by(s[1]), board_z + board_t]) cylinder(h = can_h, d = can_d);
    // (each block is placed by its low-y corner: KiCad's larger y is the model's smaller y)
    color("dimgray") translate([bx(usb[0]) - 4.5, by(board_y), board_z + board_t]) cube([9, 7.5, 3.3]);        // USB-C, bottom edge
    color("white") translate([bx(bat_conn[0]) - 4.6, by(bat_conn[1] + 4), board_z + board_t]) cube([9.2, 7, 6]); // JST, bottom edge
    color("black") translate([bx(0), by(20.6), board_z + board_t]) cube([15.4, 20.1, 2.4]);                     // ESP32 module, top-left
    color("silver") translate([bx(sw1[0]) - 5.5, by(3.6), board_z + board_t]) cube([11, 3.6, 4.6]);            // slide switch, top edge
    color("dimgray") translate([batt_x0 + fit, batt_y0 + fit, floor_t + 1.2]) cube([batt_l, batt_w, 8]);  // battery (2000 mAh)
}

// Review aid: everything assembled and cut along the length, seen from the side,
// to check the lip in its rebate, the cell under the board and the collars.
module section() {
    difference() {
        union() {
            base();
            translate([0, 0, base_h]) lid();
            board_mock();
        }
        translate([-20, -20, -1]) cube([out_x + 40, out_y / 2 + 20 - 4, 60]);   // remove the front half
    }
}

part = "assembly";
if (part == "base") base();
else if (part == "lid") lid();
else if (part == "section") section();
else {
    base();
    %board_mock();
    translate([0, 0, base_h + 14]) lid();
}
