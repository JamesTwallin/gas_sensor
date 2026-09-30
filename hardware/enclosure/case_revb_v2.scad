// Two-part enclosure for the rev B phone-companion board (66 x 36 mm): a FRONT
// shell the board screws into, sensors through its face, and a BACK tray that
// carries the battery in its own pocket.
//
//   part = "front" | "back" | "assembly" | "section"   (-D part=\"back\")
//
// How it goes together
//   - FRONT: the sensor cans poke through collars in the face. Two bosses stand
//     off the inside of the face at the board's H1 and H2 holes; the board goes
//     in component side first and two M2 x 5 screws through the board pull it
//     onto them. USB-C and the power switch sit in notches that are open to the
//     back edge of the shell, so they are reachable with the tray off, and the
//     tray's rim closes them when fitted.
//   - BACK: a tray with a closed battery compartment: floor, side fences, an
//     end fence at the SHT40 end, and a DIVIDER plate over the top that
//     separates the cell (Pi Hut 2000 mAh, 60 x 38 x 8 mm) from the board. The
//     compartment is open at the sensor end, a full-width slot, and the cell
//     slides in through it like a drawer. The divider stops 8 mm short of that
//     end so the lead can come up out of the slot to the board's JST. The front
//     shell's sensor-end wall carries a SKIRT that reaches down over the open
//     end, so once the tray is screwed on the slot is closed and the cell
//     cannot come out. The tray's rim carries a lip that drops into a rebate at
//     the back edge of the front shell on the other three sides; four M2 screws
//     through the tray's corner posts go into the shell's posts.
//   - Air: louvres in the front shell's walls at component level on three sides
//     of the sensor end, a hex grille in the face around the collars, and a
//     grille at the SHT40 end. The battery compartment is closed.
//
// Printing (Bambu A1, 0.4 mm nozzle): PETG or ASA; 0.2 mm layers, 3 walls,
// 20 % infill. FRONT prints face down (collars and lettering against the plate,
// posts and bosses rise). BACK prints outer face down. No supports.
//
// Coordinates: every board position is in KiCad coordinates (origin top-left,
// y DOWN the board). The FRONT is modelled with its outer face at z = 0 and
// depth in +z, so the board lies component side DOWN, facing the face. Turned
// over about its x axis, KiCad y then runs the same way as the model's y (see
// bx/by below), which is the opposite of the component-side-up box case. The
// BACK is modelled the same way, outer face at z = 0; "assembly" flips it over
// onto the front.

/* [Board] */
board_x = 66;           // board outline
board_y = 36;
board_t = 1.6;
board_r = 2;            // board corner radius
board_clear = 5.0;      // gap from board edge to end walls (corner posts reach 5.2 mm in)
board_clear_y = 8.0;    // gap from board edge to the long walls: wider, so the 38 mm cell
                        // passes BETWEEN the open-end corner blocks on its way into the
                        // compartment (blocks reach 5.2 mm in from each long wall)
hole1 = [62.0, 32.5];   // H1 (M2)
hole2 = [24.2, 12.9];   // H2 (M2)

/* [Shell] */
wall = 2.4;
front_t = 1.8;          // front face
back_t = 1.6;           // back skin
above_board = 7.0;      // face inner surface to the component side of the board (JST plug 6 mm)
below_board = 1.0;      // solder side to the shell's back edge
corner_r = 4;
post_r = 2.4;           // corner screw posts
screw_pilot = 1.7;      // M2 self-tapping pilot
screw_clear = 2.2;
screw_head = 4.6;       // counterbore for an M2 pan head, wide enough for the driver shaft
under_head = 2.5;       // plastic left under the screw head in the tray: with M2 x 8 that leaves
                        // 5.5 mm of thread into the front shell's posts
fit = 0.3;              // printed-fit clearance (lip, pocket)

/* [Battery] */
batt_l = 60;            // Pi Hut 2000 mAh: 60 x 38 x 8 mm
batt_w = 38;
batt_h = 8;
batt_fit = 0.6;         // play around the cell in the compartment (was 0.3: too tight printed);
                        // plus lead_room (below) at the lead end
pocket_h = batt_h + 1.0;// compartment height under the divider: 1 mm over the cell
fence_t = 1.6;
divider_t = 1.2;        // plate between the cell and the board
lead_gap = 8.0;         // the divider stops this far short of the open end: the lead comes up here
skirt_t = wall;         // the front shell's sensor-end wall continues down over the tray's open end

/* [Parts on the board] (KiCad coords) */
s1 = [60.5, 9.0];       // CH4 sensor can centre
s2 = [60.5, 22.0];      // LPG sensor can centre
can_d = 9.4;            // sensor flange diameter (stays inside)
cap_d = 8.3;            // sensor cap diameter - passes through the collar
cap_clear = 1.6;        // collar hole = cap_d + cap_clear
can_h = 13.0;           // can height above the board
usb = [33.0, 36.0];     // USB-C, KiCad bottom edge
usb_w = 14.0;           // width of the open notch
usb_body_h = 3.3;       // socket height above the board
sw1 = [33.0, 0.0];      // power slide switch, KiCad top edge
sw1_w = 11.0;
sw1_h = 4.6;
btn_rst = [29.6, 18.6];
btn_boot = [22.6, 31.4];
btn_d = 4.2;
led = [25.0, 2.6];
led_d = 3.6;
led_window = 0.4;       // diffuser membrane left in the face
sht = [8.5, 30.0];      // SHT40, vented

/* [Derived] */
cav_x = board_x + 2*board_clear;
cav_y = board_y + 2*board_clear_y;
out_x = cav_x + 2*wall;
out_y = cav_y + 2*wall;
front_depth = front_t + above_board + board_t + below_board;   // 11.4
back_depth = back_t + pocket_h + divider_t;                      // 11.3
tray_x = out_x - skirt_t;                                        // the tray stops short at the sensor end; the skirt fills it
z_board = front_t + above_board;                                 // component side of the board (from the face)
eps = 0.01;
$fn = 48;

// The board lies COMPONENT SIDE DOWN in the front shell: the box-and-lid case
// had it component side up, and turning it over reverses one axis. It is
// turned about its x axis (sensor end stays at high x), so KiCad y now runs
// the same way as the model's y: KiCad top edge (switch) -> LOW-y wall,
// KiCad bottom edge (USB-C, JST) -> HIGH-y wall. CH4 (S1, y = 9) is the
// lower of the two collars.
function bx(x) = wall + board_clear + x;
function by(y) = wall + board_clear_y + y;
function post_xy() = [
    [wall + post_r + 0.4, wall + post_r + 0.4],
    [out_x - wall - post_r - 0.4, wall + post_r + 0.4],
    [wall + post_r + 0.4, out_y - wall - post_r - 0.4],
    [out_x - wall - post_r - 0.4, out_y - wall - post_r - 0.4],
];

// A corner post embedded in a solid block that reaches the two adjacent walls
// (or the open end of the tray), so it can never stand alone. z0..z0+h.
module corner_post(p, z0, h) {
    x0 = p[0] < out_x / 2 ? wall - eps : p[0] - post_r;
    x1 = p[0] < out_x / 2 ? p[0] + post_r : out_x - wall + eps;
    y0 = p[1] < out_y / 2 ? wall - eps : p[1] - post_r;
    y1 = p[1] < out_y / 2 ? p[1] + post_r : out_y - wall + eps;
    translate([0, 0, z0]) {
        translate([x0, y0, 0]) cube([x1 - x0, y1 - y0, h]);
        translate([p[0], p[1], 0]) cylinder(h = h, r = post_r);
    }
}

module rrect(x, y, r, h) {
    linear_extrude(h) offset(r = r) offset(r = -r) square([x, y]);
}

// Hex grille that keeps clear of the sensor collars
module hex_vents(x0, ya, x1, yb, z0, h, d = 3.6, gap = 1.3) {
    y0 = min(ya, yb);
    y1 = max(ya, yb);
    p = d + gap;
    keep = (cap_d + cap_clear + 2.0) / 2 + d / 2 + 0.8;
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

// Zip-tie eyelets on the long walls (5 mm ties, running parallel to the wall)
tie_len = 10; tie_proud = 3.6; tie_h = 8.0;
module tie_eyelets(z0) {
    for (m = [0, 1]) for (x = [12, out_x - 12 - tie_len])
        translate([x, m ? out_y - eps : -tie_proud + eps, z0]) difference() {
            hull() {
                cube([tie_len, tie_proud - 1, tie_h]);
                translate([1, 0, 0]) cube([tie_len - 2, tie_proud, tie_h - 1]);
            }
            translate([-1, 0.8, 1.6]) cube([tie_len + 2, 2.0, 5.4]);
        }
}

module lanyard_loop(z0) {
    difference() {
        translate([-6.5, out_y/2 - 6, z0]) rrect(9, 12, 3, 4.5);
        translate([-3.2, out_y/2, z0 - eps]) cylinder(h = 10, d = 4.2);
        translate([-9, out_y/2 - 8, z0 - eps]) cube([3.2, 16, 10]);
    }
}

// ---- FRONT shell -------------------------------------------------------------------
module front() {
    difference() {
        union() {
            rrect(out_x, out_y, corner_r, front_depth);
            lanyard_loop(3.0);
            // collars on the outside of the face: guide the cans, shed rain
            for (s = [s1, s2]) translate([bx(s[0]), by(s[1]), -1.0])
                cylinder(h = 1.0 + eps, d = cap_d + cap_clear + 2.0);
        }
        // cavity, open at the back
        translate([wall, wall, front_t]) rrect(cav_x, cav_y, 2, front_depth);

        // face: sensor holes, grilles, buttons, LED window, lettering (engraved on the outside)
        for (s = [s1, s2]) translate([bx(s[0]), by(s[1]), -2]) cylinder(h = front_t + 3, d = cap_d + cap_clear);
        hex_vents(bx(42), by(1.5), bx(65.5), by(34.5), -eps, front_t + 2*eps);
        hex_vents(bx(2), by(24), bx(14), by(34), -eps, front_t + 2*eps);
        translate([bx(btn_rst[0]), by(btn_rst[1]), -eps]) cylinder(h = front_t + 2*eps, d = btn_d);
        translate([bx(btn_boot[0]), by(btn_boot[1]), -eps]) cylinder(h = front_t + 2*eps, d = btn_d);
        translate([bx(led[0]), by(led[1]), led_window]) cylinder(h = front_t, d = led_d);
        // Lettering is mirrored in x so it reads correctly from outside the face (the -z side).
        // (baseline at board y 9.5, text rising to ~14.5: between the LED at 2.6 and RST at 18.6)
        translate([bx(30), by(9.5), -eps]) linear_extrude(0.5)
            mirror([1, 0, 0]) text("CH4", size = 5, font = "DejaVu Sans:style=Bold", halign = "center");
        // (RST's label runs toward -x, away from the sensor grille; BOOT's toward +x, away from the SHT40 grille)
        translate([bx(btn_rst[0]) - 4.5, by(btn_rst[1]) - 1.2, -eps]) linear_extrude(0.4)
            mirror([1, 0, 0]) text("RST", size = 2.6, font = "DejaVu Sans", halign = "left");
        // (the second pen hole, by the USB edge, is the BOOT button; unlabelled by request)
        // port and switch annotations beside their scallops. The switch is ON with
        // the lever toward the sensor end (pin 1 = VSYS is on that side), which is
        // the viewer's left from the front, i.e. model +x.
        translate([bx(usb[0]) - 12, out_y - 9.5, -eps]) linear_extrude(0.4)
            mirror([1, 0, 0]) text("USB", size = 2.6, font = "DejaVu Sans", halign = "center");
        translate([bx(sw1[0]) + 4.0, 7.0, -eps]) linear_extrude(0.4)
            mirror([1, 0, 0]) text("ON", size = 2.6, font = "DejaVu Sans", halign = "center");
        translate([bx(sw1[0]) - 5.5, 7.0, -eps]) linear_extrude(0.4)
            mirror([1, 0, 0]) text("OFF", size = 2.6, font = "DejaVu Sans", halign = "center");

        // wall louvres at component level, sensor end, three sides
        for (y = [2 : 4.5 : 34], z = [front_t + 1.0, front_t + 3.8])
            translate([out_x - wall - eps, by(y) - 1.5, z]) cube([wall + 2*eps, 3, 2.2]);
        for (x = [44 : 4.5 : 66], z = [front_t + 1.0, front_t + 3.8])           // KiCad top edge (switch side) -> low-y wall
            translate([bx(x) - 1.5, -eps, z]) cube([3, wall + 2*eps, 2.2]);
        for (x = [50 : 4.5 : 66], z = [front_t + 1.0, front_t + 3.8])           // KiCad bottom edge (USB side) -> high-y wall
            translate([bx(x) - 1.5, out_y - wall - eps, z]) cube([3, wall + 2*eps, 2.2]);
        for (y = [8, 16, 24])                                            // SHT40 end wall
            translate([-eps, by(y) - 1.5, front_t + 1.0]) cube([wall + 2*eps, 3, 4.0]);
        for (x = [3, 9, 15])                                             // SHT40 end, USB-side wall
            translate([bx(x) - 1.5, out_y - wall - eps, front_t + 1.0]) cube([3, wall + 2*eps, 4.0]);

        // USB-C notch (high-y wall) and switch notch (low-y wall): from just in
        // front of the part out through the back edge; the tray's rim closes them
        translate([bx(usb[0]) - usb_w/2, out_y - wall - eps, z_board - usb_body_h - 1.5])   // 7.4 mm tall x 14 wide with the tray on
            cube([usb_w, wall + 2*eps, front_depth]);
        translate([bx(sw1[0]) - (sw1_w + 4)/2, -eps, z_board - sw1_h - 0.8])
            cube([sw1_w + 4, wall + 2*eps, front_depth]);
        // Thumb scallops, one at the switch (low-y edge) and one at the USB-C
        // socket (high-y edge): 20 mm wide, 5 mm deep bites through the face and
        // the whole wall depth, so a thumb or a plug comes in from the front edge.
        hull() for (dx = [-3, 3])
            translate([bx(sw1[0]) + dx, -2, -2]) cylinder(h = front_depth + 4, d = 14);
        hull() for (dx = [-3, 3])
            translate([bx(usb[0]) + dx, out_y + 2, -2]) cylinder(h = front_depth + 4, d = 14);

        // rebate at the back edge for the tray's lip, on the three sides that have a lip
        // (the sensor-end wall carries the skirt instead)
        intersection() {
            translate([wall - 1.2, wall - 1.2, front_depth - 1.2]) rrect(cav_x + 2.4, cav_y + 2.4, 2.6, 1.2 + eps);
            translate([-1, -1, front_depth - 2]) cube([tray_x - 2.0 + 1, out_y + 2, 4]);
        }
    }

    // skirt: the sensor-end wall continues down past the back edge, over the
    // tray's open end. With the tray screwed on, this is what stops the cell
    // sliding out. Its inside face is flush with the shell's inner wall.
    translate([tray_x, 0, front_depth - eps]) intersection() {
        translate([-tray_x, 0, 0]) rrect(out_x, out_y, corner_r, back_depth + eps);
        cube([skirt_t + 1, out_y, back_depth + eps]);
    }

    // corner posts: from the face to the back edge (the tray's posts bear on
    // them), pilot holes for the tray screws
    for (p = post_xy()) difference() {
        corner_post(p, front_t - eps, front_depth - front_t + eps);
        translate([p[0], p[1], front_depth - 7]) cylinder(h = 8, d = screw_pilot);
    }

    // board bosses at H1 and H2: the board screws onto these from its back
    for (h = [hole1, hole2]) translate([bx(h[0]), by(h[1]), front_t - eps]) difference() {
        cylinder(h = above_board + eps, d = 5.0);
        translate([0, 0, above_board - 6]) cylinder(h = 7, d = screw_pilot);
    }
}

// ---- BACK tray ------------------------------------------------------------------------
// Compartment in tray coords (outer face at z = 0). The cell butts against the
// SHT40-end fence and reaches the open sensor end; the side fences stop short
// of the sensor-end corner posts.
pk_w = batt_w + 2*batt_fit;
pk_y0 = wall + (cav_y - pk_w) / 2;
pk_x1 = tray_x;                          // open end
// The cell stops short of the corner blocks at the open end (they reach 1.8 mm
// into its width), so its lead end sits batt_fit before the blocks. That leaves
// the block zone, 5.2 mm, as room for the lead between the two blocks.
block_x = out_x - wall - 2*post_r - 0.4;           // where the open-end corner blocks start
pk_x0 = block_x - batt_fit - batt_l;               // SHT40-end fence face
lead_room = pk_x1 - block_x;                       // 5.2 mm
fence_x_end = out_x - wall - post_r - 0.4 - post_r - 0.6;   // clear of the sensor-end posts

module back() {
    // The screw holes are cut LAST, through everything (body, divider plate and
    // posts), so nothing can bridge them: the divider covers the two SHT40-end
    // posts and would otherwise plug those holes.
    difference() {
        back_solid();
        for (p = post_xy()) translate([p[0], p[1], -1]) {
            cylinder(h = back_depth + 4, d = screw_clear);                        // clearance, full depth
            cylinder(h = back_depth - under_head + 1 + eps, d = screw_head);      // deep counterbore from the outer face
        }
    }
}

module back_solid() {
    difference() {
        union() {
            // body, stopping short at the sensor end where the shell's skirt takes over
            intersection() {
                rrect(out_x, out_y, corner_r, back_depth);
                cube([tray_x, out_y, back_depth + 1]);
            }
            tie_eyelets(0.6);
            // lip on the rim, three sides (none at the open end), and cut away
            // where it would cross the USB-C and switch notches in the shell
            difference() {
                intersection() {
                    translate([wall - 1.2 + fit, wall - 1.2 + fit, back_depth - eps])
                        difference() {
                            rrect(cav_x + 2.4 - 2*fit, cav_y + 2.4 - 2*fit, 2.6, 1.0 + eps);
                            translate([1.0, 1.0, -eps]) rrect(cav_x + 2.4 - 2*fit - 2.0, cav_y + 2.4 - 2*fit - 2.0, 2.0, 1.0 + 3*eps);
                        }
                    cube([tray_x - 2.0, out_y, back_depth + 3]);
                }
                translate([bx(usb[0]) - 11, out_y - wall - 1, back_depth - 1]) cube([22, wall + 2, 4]);   // matches the scallops
                translate([bx(sw1[0]) - 11, -1, back_depth - 1]) cube([22, wall + 2, 4]);
            }
        }
        // compartment: full height between floor and divider, open at the sensor end
        translate([wall, wall, back_t]) cube([tray_x, cav_y, pocket_h]);
        // above the divider: open toward the board (the lead gap and the space the posts stand in)
        translate([wall, wall, back_t + pocket_h - eps]) cube([tray_x, cav_y, divider_t + 1]);
    }
    // divider plate over the compartment, stopping lead_gap short of the open end
    translate([wall - eps, wall - eps, back_t + pocket_h]) cube([pk_x1 - lead_gap - wall + eps, cav_y + 2*eps, divider_t]);
    // fences: SHT40 end (between the posts) and both long sides (up to the sensor-end posts)
    translate([pk_x0 - fence_t, wall + 2*post_r + 0.8, back_t - eps]) cube([fence_t, cav_y - 4*post_r - 1.6, pocket_h + eps]);
    for (yy = [pk_y0 - fence_t, pk_y0 + pk_w])
        translate([pk_x0 - fence_t, yy, back_t - eps]) cube([fence_x_end - (pk_x0 - fence_t), fence_t, pocket_h + eps]);
    // corner posts, solid and embedded in blocks joined to the walls: floor to rim,
    // through the divider (the holes come in back()). At the open end the block
    // runs out flush with the tray's cut edge, so those posts are held by the
    // long side walls instead of standing alone.
    for (p = post_xy()) intersection() {
        corner_post(p, back_t - eps, back_depth - back_t + eps);
        cube([tray_x, out_y, back_depth + 2]);
    }
}

// ---- preview -------------------------------------------------------------------------
module board_mock() {
    // component side faces -z (toward the front face)
    color("green") translate([bx(0), by(0), z_board]) rrect(board_x, board_y, board_r, board_t);
    for (s = [s1, s2]) color("silver")
        translate([bx(s[0]), by(s[1]), z_board - can_h]) cylinder(h = can_h, d = can_d);
    color("dimgray") translate([bx(usb[0]) - 4.5, by(board_y - 7.5), z_board - usb_body_h]) cube([9, 7.5, usb_body_h]);
    color("white") translate([bx(50) - 4.6, by(27), z_board - 6]) cube([9.2, 7, 6]);                 // JST
    color("black") translate([bx(0), by(0.5), z_board - 2.4]) cube([15.4, 20.1, 2.4]);               // ESP32
    color("silver") translate([bx(sw1[0]) - 5.5, by(-3.6), z_board - sw1_h]) cube([11, 3.6, sw1_h]); // switch
}

module back_in_place() {
    // flip the tray over and sit its rim on the shell's back edge
    translate([0, out_y, front_depth + back_depth]) rotate([180, 0, 0]) back();
}

module battery_in_place() {
    // in the flipped tray: the compartment floor is at front_depth + divider_t + pocket_h from the front face
    color("dimgray") translate([pk_x0, pk_y0 + batt_fit, front_depth + divider_t + pocket_h - batt_h]) cube([batt_l, batt_w, batt_h]);
}

part = "assembly";
if (part == "front") front();
else if (part == "back") back();
else if (part == "section") {
    difference() {
        union() { front(); back_in_place(); board_mock(); battery_in_place(); }
        translate([-20, -20, -5]) cube([out_x + 40, out_y / 2 + 20 - 4, 60]);
    }
} else {
    front();
    %board_mock();
    %battery_in_place();
    translate([0, 0, 12]) back_in_place();
}
