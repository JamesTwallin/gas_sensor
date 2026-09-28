// Handheld enclosure for the rev B phone-companion board (66 x 36 mm).
//
//   part = "base" | "lid" | "assembly"   (set on the command line: -D part=\"lid\")
//
// Design notes
//   - The two Figaro sensor cans poke through collars in the lid, so the hot
//     elements sit in open air: that is what makes the response fast.
//   - Air enters through the floor vents, rises past the sensors (they run at
//     ~280 mW each) and leaves through the lid grille: a chimney, not a sealed box.
//   - The SHT40 end has its own vents top and bottom so it measures outside air,
//     not case air.
//   - Battery (1200 mAh, ~60 x 35 x 5 mm) lies under the board on the floor.
//   - The board rests on a ledge; one M2 screw at its right-hand hole stops it
//     lifting. Four M2 screws hold the lid down.
//
// Printing (Bambu A1, 0.4 mm nozzle): PETG or ASA preferred (the board runs warm
// and PLA creeps); 0.2 mm layers, 3 walls, 20 % infill. Both parts print flat,
// no supports. See README.md.

/* [Board] */
board_x = 66;           // board outline
board_y = 36;
board_t = 1.6;          // set 1.0 if you order 1.0 mm boards
board_r = 2;            // board corner radius
board_clear = 4.5;      // gap from board edge to wall (leaves room for the corner screw posts)

/* [Cavity] */
wall = 2.4;             // outer wall
floor_t = 1.6;
lid_t = 1.8;
batt_h = 5.5;           // battery pocket height (1200 mAh cell is ~5 mm)
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
can_h = 13.0;           // can height above the board
usb = [33.0, 36.0];     // USB-C mouth, bottom edge
usb_w = 10.0;
usb_h = 4.0;
sw1 = [33.0, 0.0];      // power slide switch, lever over the top edge
sw1_w = 11.0;
sw1_h = 4.6;
bat_conn = [50.0, 30.0];// JST-PH, opening faces the bottom edge
bat_w = 13.0;
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

// Board coords -> case coords (the board sits centred in the cavity)
function bx(x) = wall + board_clear + x;
function by(y) = wall + board_clear + y;

module rrect(x, y, r, h) {
    linear_extrude(h) offset(r = r) offset(r = -r) square([x, y]);
}

// Hex grille: airflow with enough bridging for a clean print
module hex_vents(x0, y0, x1, y1, z0, h, d = 4.2, gap = 1.4) {
    p = d + gap;
    keep = (cap_d + 3.0) / 2 + d / 2 + 0.8;   // stay off the sensor collars
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

module base() {
    difference() {
        union() {
            rrect(out_x, out_y, corner_r, base_h);
            lanyard_loop();
        }
        // main cavity
        translate([wall, wall, floor_t]) rrect(cav_x, cav_y, 2, cav_h + eps);

        // floor vents: under the sensors (chimney inlet) and under the SHT40
        hex_vents(bx(46), by(2), bx(64), by(32), -eps, floor_t + 2*eps);
        hex_vents(bx(3), by(24), bx(14), by(34), -eps, floor_t + 2*eps);

        // Wall louvres at board level: the cell covers most of the floor, so this
        // is where the air really comes in. Sensor end and SHT40 end.
        for (y = [4, 10, 16, 22, 28])                       // right end wall
            translate([out_x - wall - eps, by(y) - 1.5, board_z + 1.2])
                cube([wall + 2*eps, 3, 4.0]);
        for (y = [8, 16, 24])                               // left end wall (SHT40)
            translate([-eps, by(y) - 1.5, board_z + 1.2])
                cube([wall + 2*eps, 3, 4.0]);
        for (x = [46, 52, 58, 64])                          // top wall, sensor end
            translate([bx(x) - 1.5, -eps, board_z + 1.2])
                cube([3, wall + 2*eps, 4.0]);
        for (x = [58, 64])                                  // bottom wall, sensor end
            translate([bx(x) - 1.5, out_y - wall - eps, board_z + 1.2])
                cube([3, wall + 2*eps, 4.0]);
        for (x = [3, 9, 15])                                // bottom wall, SHT40 end
            translate([bx(x) - 1.5, out_y - wall - eps, board_z + 1.2])
                cube([3, wall + 2*eps, 4.0]);

        // USB-C, power switch, battery plug and vent notch
        translate([bx(usb[0]) - usb_w/2, out_y - wall - eps, board_z + board_t - 0.6])
            cube([usb_w, wall + 2*eps, usb_h]);
        translate([bx(sw1[0]) - sw1_w/2, -eps, board_z + board_t - 0.8])
            cube([sw1_w, wall + 2*eps, sw1_h]);
        translate([bx(bat_conn[0]) - bat_w/2, out_y - wall - eps, board_z + board_t - 0.6])
            cube([bat_w, wall + 2*eps, 6.5]);
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

    // Board shelves on the two short walls: the board lands on these, and the
    // battery slides in underneath between them.
    for (m = [0, 1]) translate([m ? out_x - wall - shelf_d : wall, wall, board_z - shelf_t])
        cube([shelf_d, cav_y, shelf_t]);
    // extra stubs on the long walls at the sensor end, where the cell does not reach
    for (m = [0, 1]) translate([out_x - wall - 14, m ? out_y - wall - shelf_d : wall, board_z - shelf_t])
        cube([10, shelf_d, shelf_t]);

    // battery pocket ribs (keep the cell off the floor vents and clear of the H1 boss)
    for (x = [6 : 12 : 54]) translate([wall + x, wall + 4, floor_t - 0.6])
        cube([1.6, cav_y - 8, 1.8]);   // sunk into the floor: crosses the vents cleanly
}

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
            // lip that drops into the cavity and locates the lid
            translate([wall + 0.35, wall + 0.35, -1.2])
                difference() {
                    rrect(cav_x - 0.7, cav_y - 0.7, 2, 1.2);
                    translate([1.6, 1.6, -eps]) rrect(cav_x - 3.9, cav_y - 3.9, 2, 1.2 + 2*eps);
                }
            // collars around the sensor cans: guide the cans and shed rain
            for (s = [s1, s2]) translate([bx(s[0]), by(s[1]), lid_t - eps])
                difference() {
                    cylinder(h = 1.0, d = cap_d + 3.0);
                    translate([0, 0, -eps]) cylinder(h = 2 + 2*eps, d = cap_d + 1.0);
                }
        }
        // sensor can holes
        for (s = [s1, s2]) translate([bx(s[0]), by(s[1]), -eps])
            cylinder(h = lid_t + 2*eps, d = cap_d + 1.0);

        // grille over the sensor end (chimney outlet) and over the SHT40
        hex_vents(bx(44), by(2), bx(56), by(34), -eps, lid_t + 2*eps);
        hex_vents(bx(2), by(24), bx(14), by(34), -eps, lid_t + 2*eps);

        // button access and LED window
        translate([bx(btn_rst[0]), by(btn_rst[1]), -eps]) cylinder(h = lid_t + 2*eps, d = btn_d);
        translate([bx(btn_boot[0]), by(btn_boot[1]), -eps]) cylinder(h = lid_t + 2*eps, d = btn_d);
        translate([bx(led[0]), by(led[1]), led_window])
            cylinder(h = lid_t, d = led_d);

        // screw holes, counterbored
        for (p = post_xy()) translate([p[0], p[1], -eps]) {
            cylinder(h = lid_t + 2*eps, d = screw_clear);
            translate([0, 0, lid_t - 1.0]) cylinder(h = 1.0 + eps, d = screw_head);
        }

        // labels
        translate([bx(30), by(8.5), lid_t - 0.5]) linear_extrude(0.5 + eps)
            text("CH4", size = 5, font = "DejaVu Sans:style=Bold", halign = "center");
        translate([bx(btn_rst[0]) + 4.5, by(btn_rst[1]) - 1.2, lid_t - 0.4]) linear_extrude(0.4 + eps)
            text("RST", size = 2.6, font = "DejaVu Sans");
        translate([bx(btn_boot[0]) + 4.5, by(btn_boot[1]) - 1.2, lid_t - 0.4]) linear_extrude(0.4 + eps)
            text("BOOT", size = 2.6, font = "DejaVu Sans");
    }
}

// ---- preview only ----------------------------------------------------------
module board_mock() {
    color("green") translate([bx(0), by(0), board_z]) rrect(board_x, board_y, board_r, board_t);
    for (s = [s1, s2]) color("silver")
        translate([bx(s[0]), by(s[1]), board_z + board_t]) cylinder(h = can_h, d = can_d);
    color("dimgray") translate([bx(usb[0]) - 4.5, by(30), board_z + board_t]) cube([9, 7.5, 3.3]);
    color("white") translate([bx(bat_conn[0]) - 4.6, by(26.5), board_z + board_t]) cube([9.2, 7, 6]);
    color("black") translate([bx(9.8) - 7.7, by(10.5) - 10, board_z + board_t]) cube([15.4, 20.5, 2.4]);
    color("dimgray") translate([wall + 4, wall + 5, floor_t + 1.2]) cube([60, 35, batt_h - 1.2]);  // battery
}

part = "assembly";
if (part == "base") base();
else if (part == "lid") lid();
else {
    base();
    %board_mock();
    translate([0, 0, base_h + 14]) lid();
}
