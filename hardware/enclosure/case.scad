// Two-part enclosure for the phone-companion board (hardware/board, 66 x 36 mm): a FRONT
// shell the board screws into, sensors through its face, and a BACK tray that
// carries the battery in its own pocket.
//
//   part = "front" | "back" | "car" | "assembly" | "section" | "mounted" | "mounted_section"
//   (-D part=\"back\")
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
//     separates the cell (EEMB 103454RP 2000 mAh) from the board. The
//     compartment is open at the sensor end, a full-width slot, and the cell
//     slides in through it like a drawer. The divider stops 8 mm short of that
//     end so the lead can come up out of the slot to the board's JST. The front
//     shell's sensor-end wall carries a SKIRT that reaches down over the open
//     end, so once the tray is screwed on the slot is closed and the cell
//     cannot come out. The tray's rim carries a lip that drops into a rebate at
//     the back edge of the front shell on the other three sides; four M2 screws
//     through the tray's corner posts go into the shell's posts.
//   - CAR MOUNT: each half has a flange along its switch-side edge, flush with its
//     outer face; together they make a C-shaped channel the whole depth of the case.
//     A separate CAR adapter (zip-tied to a wing mirror) is a T, the length of the
//     case, that the case slides onto lanyard end first, up to its stop, where a latch
//     arm's bump drops into a notch in the battery side's flange.
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
mems = false;           // true (-D mems=true) for the MEMS test rig (hardware/board_mems):
                        // a second slot in the face for the MEMS blade
board_x = 66;           // board outline
board_y = 36;
board_t = 1.6;
board_r = 2;            // board corner radius
// EEMB 103454 cell, 34.5 mm wide: 5.8 at the long walls is enough for the cell, and puts
// the posts beside the board's long edges instead of off its ends, so the end gaps are: 1.5 at the SHT40 end (the ESP32's antenna edge is flush with the
// board's), 3.5 at the sensor end, where the battery lead comes up past the board.
board_clear = 1.5;        // board edge to the SHT40-end wall
board_clear_end = 3.5;    // board edge to the sensor-end wall
board_clear_y = 5.8;      // board edge to the long walls
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
// EEMB 103454RP 2000 mAh, 56 x 34.5 x 10.3 mm
batt_l = 56;
batt_w = 34.5;
batt_h = 10.3;
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
btn_rst = [22.6, 24.7];
btn_boot = [22.6, 31.4];
// Air blade (hardware/air_blade): a slot in the face between the two sensor caps,
// at the sensor end. The blade (4.7 mm wide above its foot) stands in a
// notch in the board's edge and pokes 4.5 mm out of the slot, so its SHT40 and heated
// thermistor sit in the outside air, level with the sensor caps.
blade_t = 1.6;           // blade PCB thickness: designed for 1.0, the first batch (2026-10) came
                         // at 1.6. The notch is open at the board's end, so its J3 face stays
                         // at x 64.85 and a thicker blade just stands proud of the board's end
blade_slot = [64.85 + blade_t / 2, 15.5];
blade_slot_w = blade_t + 0.4;  // along x: the blade's thickness plus clearance
blade_slot_l = 5.1;      // along y: the blade's width plus clearance
// A guide on the inside of the face continues the slot 4 mm down toward the board, so
// the blade's faces and edges rest in it over 5.8 mm and knocks on the tip do not
// land on the solder joint. Its end walls are thin to keep clear of the sensor cans.
blade_guide_h = 4.0;     // below the face's inner surface (the blade's foot is 1.5 mm higher still)
blade_guide_side = 0.8;  // wall either side of the blade's faces
blade_guide_end = 0.5;   // wall beyond the blade's edges
// The blade's parts (U1 SHT40, C1 0402, RT1 0603: up to 1.0 mm with solder) are on its
// front face, the one facing -x into the case, and the whole tip passes through the guide
// and the slot on the way in. So on that side the slot has a pocket for each prong's parts,
// 1.0 mm + 0.15 deep, and between them (beside the fork's gap, where there are no parts) a
// fin hangs from the face down the guide to keep the blade's front face in place. The guide
// has no -x wall: its corners would hit the sensor cans; its end walls stop short of it too.
blade_pocket_x = 64.85 - 1.0 - 0.15;                // board x of the pockets' -x side
blade_pockets = [[13.3, 14.85], [15.65, 17.75]];    // board y: RT1 13.55-14.35; U1 and C1 16.05-17.55
// MEMS blade (hardware/mems_blade, MEMS test rig only): 11.4 mm wide, 1.6 mm thick, standing in a second
// notch between the LPG can and H1 with its back (foot pads) at board x 64.85 and its parts
// facing the sensor-end wall; its two sensors (1.55 mm tall) sit 0.5-8.0 mm proud of the
// face. The slot passes the blade and the sensors on the way in. It stops 0.03 mm short of
// the LPG cap hole at its corner, and its sensor side is 1.25 mm from the end wall.
mems_slot_x = [64.7, 68.25];   // board x: blade back - 0.15 to sensor tops + 0.2
mems_slot_y = [24.65, 36.35];  // board y: the blade's 24.8-36.2 plus 0.15
btn_d = 4.2;
led = [25.0, 2.6];
led_d = 3.6;
led_window = 0.4;       // diffuser membrane left in the face
sht = [8.5, 30.0];      // SHT40, vented

/* [Derived] */
cav_x = board_x + board_clear + board_clear_end;
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
                        norm([cx, cy] - [bx(s2[0]), by(s2[1])])) < keep
                    || (norm([cx, cy] - [bx(blade_slot[0]), by(blade_slot[1])]) < 4.5)
                    || (mems && cx > bx(mems_slot_x[0]) - 3.0 && cx < bx(mems_slot_x[1]) + 3.0
                        && cy > by(mems_slot_y[0]) - 3.0 && cy < by(mems_slot_y[1]) + 3.0);
            if (cx <= x1 && cy <= y1 && !clash)
                translate([cx, cy, z0]) cylinder(h = h, d = d, $fn = 6);
        }
}

// Zip-tie eyelets on the long walls (5 mm ties, passing along the wall: the slot runs
// through the eyelet in x, its 5.4 mm width across the wall's height). The outer
// bridge is tie_wall thick (was 0.8 mm). Printed upright, the slot's roof is a 2 mm bridge.
tie_len = 10; tie_h = 8.0;
tie_slot = 5.4;
tie_gap = 2.0;          // the slot, off the wall: room for the tie's thickness
tie_wall = 1.4;         // outer bridge over the tie
tie_proud = 0.8 + tie_gap + tie_wall;
// one eyelet, standing off a wall at y = 0 toward +y, x 0..tie_len, z 0..h
module eyelet(h) difference() {
    hull() {
        cube([tie_len, tie_proud - 1, h]);
        translate([1, 0, 0]) cube([tie_len - 2, tie_proud, h - 1]);
    }
    translate([-1, 0.8, (h - tie_slot) / 2]) cube([tie_len + 2, tie_gap, tie_slot]);
}
module tie_eyelets(z0) {
    // (with the car mount, only the USB-side wall has eyelets: the flange takes the switch side)
    // (the tray is flipped over in assembly, so its high-y wall is the switch side)
    for (m = mount_rail ? [0] : [0, 1]) for (x = [12, out_x - 12 - tie_len])
        // mirrored on the low-y wall so all four have the chamfer on the outside
        translate([x, m ? out_y - eps : eps, z0]) mirror([0, m ? 0 : 1, 0]) eyelet(tie_h);
}

// Lanyard loop on the SHT40 end. loop_rim is the plastic between the hole and
// the outer edge, which is what a cord pulls against (it was 0.5 mm: a string
// would cut through it).
loop_hole = 4.2; loop_rim = 3.0; loop_h = 6.0;
module lanyard_loop(z0) {
    hole_x = -1.5 - loop_hole / 2;              // hole starts 1.5 mm off the wall
    out = -hole_x + loop_hole / 2 + loop_rim;   // how far the loop stands off the wall
    difference() {
        translate([-out, out_y/2 - 6, z0]) rrect(out + 2.5, 12, 3, loop_h);
        translate([hole_x, out_y/2, z0 - eps]) cylinder(h = loop_h + 2*eps, d = loop_hole);
    }
}

// ---- FRONT shell -------------------------------------------------------------------
module blade_guide() {
    x0 = blade_slot[0] - blade_slot_w / 2;   // the slot's -x side, at the blade's front face + 0.2
    x1 = blade_slot[0] + blade_slot_w / 2;
    y0 = blade_slot[1] - blade_slot_l / 2;
    y1 = blade_slot[1] + blade_slot_l / 2;
    module box(xa, xb, ya, yb) translate([bx(xa), by(ya), front_t - eps]) cube([xb - xa, yb - ya, blade_guide_h + eps]);
    box(x1, x1 + blade_guide_side, y0 - blade_guide_end, y1 + blade_guide_end);    // behind the blade
    for (y = [[y0 - blade_guide_end, y0], [y1, y1 + blade_guide_end]])             // beyond its edges
        box(x0 - 0.3, x1, y[0], y[1]);
    box(blade_pocket_x, x0, blade_pockets[0][1], blade_pockets[1][0]);           // the fin, on its front face
}

module front() {
    blade_guide();
    difference() {
        union() {
            rrect(out_x, out_y, corner_r, front_depth);
            lanyard_loop(3.0);
            if (mount_rail) front_flange();   // car-mount flange (the scallop below cuts it)
            // collars on the outside of the face: guide the cans, shed rain
            for (s = [s1, s2]) translate([bx(s[0]), by(s[1]), -1.0])
                cylinder(h = 1.0 + eps, d = cap_d + cap_clear + 2.0);
        }
        // cavity, open at the back
        translate([wall, wall, front_t]) rrect(cav_x, cav_y, 2, front_depth);

        // face: sensor holes, grilles, buttons, LED window, lettering (engraved on the outside)
        for (s = [s1, s2]) translate([bx(s[0]), by(s[1]), -2]) cylinder(h = front_t + 3, d = cap_d + cap_clear);
        hex_vents(bx(42), by(1.5), bx(65.5), by(34.5), -eps, front_t + 2*eps);
        // SHT40-end grille, right over the on-board SHT40 (faces sideways on the car mount)
        hex_vents(bx(2), by(24), bx(14), by(34), -eps, front_t + 2*eps);
        translate([bx(btn_rst[0]), by(btn_rst[1]), -eps]) cylinder(h = front_t + 2*eps, d = btn_d);
        translate([bx(btn_boot[0]), by(btn_boot[1]), -eps]) cylinder(h = front_t + 2*eps, d = btn_d);
        // through the face and the edge of the collars
            translate([bx(blade_slot[0]) - blade_slot_w / 2, by(blade_slot[1]) - blade_slot_l / 2, -2])
                cube([blade_slot_w, blade_slot_l, front_t + 3]);
        // the pockets for the blade's parts
            for (p = blade_pockets)
                translate([bx(blade_pocket_x), by(p[0]), -2])
                    cube([blade_slot[0] - blade_slot_w / 2 - blade_pocket_x + eps, p[1] - p[0], front_t + 3]);
        if (mems)  // the MEMS blade's slot, through the face (and the LPG collar's edge)
            translate([bx(mems_slot_x[0]), by(mems_slot_y[0]), -2])
                cube([mems_slot_x[1] - mems_slot_x[0], mems_slot_y[1] - mems_slot_y[0], front_t + 3]);
        translate([bx(led[0]), by(led[1]), led_window]) cylinder(h = front_t, d = led_d);
        // Lettering is mirrored in x so it reads correctly from outside the face (the -z side).
        // (baseline at board y 9.5, text rising to ~14.5: between the LED at 2.6 and RST at 18.6)
        translate([bx(30), by(9.5), -eps]) linear_extrude(0.5)
            mirror([1, 0, 0]) text("CH4", size = 5, font = "DejaVu Sans:style=Bold", halign = "center");
        // RST and BOOT are stacked, so each label goes beside its hole, toward +x
        translate([bx(btn_rst[0]) + 3.0, by(btn_rst[1]) - 1.2, -eps]) linear_extrude(0.4)
            mirror([1, 0, 0]) text("RST", size = 2.6, font = "DejaVu Sans", halign = "right");
        translate([bx(btn_boot[0]) + 3.0, by(btn_boot[1]) - 1.2, -eps]) linear_extrude(0.4)
            mirror([1, 0, 0]) text("BOOT", size = 2.6, font = "DejaVu Sans", halign = "right");
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
        for (y = [8, 16, 24])                                            // SHT40 end wall
            translate([-eps, by(y) - 1.5, front_t + 1.0]) cube([wall + 2*eps, 3, 4.0]);
        // No USB-side louvres: that wall faces the sky when the case stands on its switch
        // edge on the mirror. The SHT40 gets air from the grille over it and the end-wall slots.

        // USB-C notch (high-y wall) and switch notch (low-y wall): from just in
        // front of the part out through the back edge; the tray's rim closes them
        translate([bx(usb[0]) - usb_w/2, out_y - wall - eps, z_board - usb_body_h - 1.5])   // 7.4 mm tall x 14 wide with the tray on
            cube([usb_w, wall + 2*eps, front_depth]);
        translate([bx(sw1[0]) - (sw1_w + 4)/2, -eps, z_board - sw1_h - 0.8])
            cube([sw1_w + 4, wall + 2*eps, front_depth]);
        // Thumb scallops, one at the switch (low-y edge) and one at the USB-C
        // socket (high-y edge): 20 mm wide, 5 mm deep bites through the face and
        // the whole wall depth, so a thumb or a plug comes in from the front edge.
        // (outside the wall the switch one carries straight on, full width, so where it
        // cuts through the car-mount flange its sides are parallel, not two sharp tips)
        hull() {
            for (dx = [-3, 3]) translate([bx(sw1[0]) + dx, -2, -2]) cylinder(h = front_depth + 4, d = 14);
            translate([bx(sw1[0]) - 10, -12, -2]) cube([20, 10, front_depth + 4]);
        }
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

/* [Car mount] */
mount_rail = true;      // car-mount flanges on the switch-side edge (-D mount_rail=false: plain
                        // case, and the tray's switch-side wall gets its zip-tie eyelets back)
// Each half of the case gets a flange along its switch-side edge, flush with its outer
// face (the battery side's back, the front shell's face), so it prints as that part's
// first layers. Seen end on, a flange is fl_t thick at the wall and thickens at 45 deg to
// fl_h toward its outer edge. Assembled, the two flanges make a C-shaped channel along
// the edge, the whole depth of the case, and the CAR adapter is a T that slides into it.
fl_w = 5.0;             // how far a flange reaches out from the wall
fl_t = 1.8;             // its thickness at the wall
fl_h = 4.8;             // its thickness over the outer fl_w - (fl_h - fl_t) = 2 mm
car_fit = 0.15;         // clearance between the flanges and the adapter, all round
                        // (0.25 slid well but wobbled; 0.2 if this prints too tight)
car_base = 5.0;         // adapter plate between the mirror and the flange tips
car_stop = 3.0;         // end stop at the lanyard end
car_under = 2.5;        // the adapter wraps this far under the battery side's flange (its latch arm)
latch_gap = 1.0;        // slot that frees the latch arm from the plate
latch_len = 20;         // free length of the arm, ending flush with the case's sensor end
latch_catch = 1.2;      // how far its bump rises past the battery side's flange's outer face,
                        // to catch on the end of that flange
car_round = 3;          // rounded ends, seen from the mirror side
car_edge = 1.2;         // chamfer on the adapter's outer long edges

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
        union() {
            back_solid();
            if (mount_rail) switch_side() tray_flange();
        }
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

// ---- CAR mount -------------------------------------------------------------------------
// Tray coords throughout (outer face at z = 0, the front face at face_z), with the
// switch-side wall as y = 0 and the flanges and adapter at y < 0; switch_side() puts them
// on the right wall of the tray, and car_in_place() under the assembled case.
//
// The CAR adapter is one straight T the length of the case: a plate against the mirror,
// and a head that slides into the C between the two flanges and bears on both of them,
// ~19 mm apart, so the case can't be twisted off. The head's sides follow the flanges'
// 45 deg wedges, so pulling the case straight off would have to spread the two halves of
// the case apart. It covers the switch (switch on, then mount) and the switch-side
// louvres. Both flanges end level with the battery side; the adapter ends flush with
// the case. Below the battery side's flange the adapter wraps round under it; at the
// sensor end that strip is a latch arm whose bump springs up past the end of the flange
// when the case is home against the stop at the lanyard end, and catches on that end.
// Press the end of the arm away from the case to release. Zip-tie eyelets on its back,
// the same as the tray's.
//
// Printing: the flanges print flat on the plate as the first layers of each half. The
// adapter prints case side down (its eyelets on top): the head narrows from that face at
// 45 deg into the stem, the plate's inner corners behind the flange tips are 45 deg
// chamfers, the arm and its slot are upright, and the eyelets' slots are bridged.
face_z = front_depth + back_depth;               // the case's front face, in tray coords

// one flange, 2D (u, v) = tray (y, z), reaching 2 mm into the wall so it bonds to it
module flange_2d() polygon([[2, 0], [-fl_w, 0], [-fl_w, fl_h], [-(fl_h - fl_t), fl_h], [0, fl_t], [2, fl_t]]);
// both, as they sit on the assembled case: the front shell's is the mirror image about mid-depth
module case_flanges_2d() { flange_2d(); translate([0, face_z]) mirror([0, 1]) flange_2d(); }
module along_x(x0, x1) translate([x0, 0, 0]) rotate([90, 0, 90]) linear_extrude(x1 - x0) children();
module along_y(y0, y1) translate([0, y1, 0]) rotate([90, 0, 0]) linear_extrude(y1 - y0) children();   // 2D (x, z)

car_y0 = -fl_w - car_fit - car_base;             // the face against the mirror
car_z0 = -car_under;
car_x0 = -car_fit - car_stop;
car_len = out_x;                                 // the adapter ends flush with the case's sensor end
fl_len = tray_x;                                 // both flanges end level with the battery side
arm_top = -car_fit - latch_gap;                  // the arm is car_z0 .. arm_top
bump_top = latch_catch;
latch_root = car_len - latch_len;
latch_x = [fl_len + car_fit, car_len];           // the bump: square catch against the flange's end,
                                                 // then the lead-in ramp out to the adapter's end
tip_y = -fl_w - car_fit;                         // the plate's inner face, behind the flange tips

// the battery side's flange
module tray_flange() along_x(0, fl_len) flange_2d();
// the front shell's flange, in front shell coords: its face is z = 0 there, so the
// profile is the same as the tray's. front() cuts it away at the switch scallop.
module front_flange() along_x(0, fl_len) flange_2d();

// The flanges are drawn on the tray's y = 0 wall, but the tray is turned over onto the
// front shell in assembly (back_in_place), which puts that wall on the USB side. This
// moves them to the y = out_y wall, the switch side. The printed adapter is therefore the
// mirror image of car() (see part "car").
module switch_side() translate([0, out_y, 0]) mirror([0, 1, 0]) children();

// the adapter's cross-section, before the case is cut out of it: a rectangle with its
// two long outer edges (on the mirror side) chamfered
module car_section_2d() polygon([
    [car_y0 + car_edge, car_z0], [-car_fit, car_z0], [-car_fit, face_z],
    [car_y0 + car_edge, face_z], [car_y0, face_z - car_edge], [car_y0, car_z0 + car_edge]]);

module car() {
    intersection() {
        car_body();
        // rounded ends, seen from the mirror side
        translate([0, 0, car_z0 - 1]) linear_extrude(face_z - car_z0 + 2) union() {
            offset(r = car_round) offset(delta = -car_round)
                translate([car_x0, car_y0]) square([car_len - car_x0, -car_y0 + car_round + 1]);
            translate([car_x0 + 5, car_y0 - tie_proud - 1]) square([car_len - car_x0 - 10, tie_proud + 2]);
        }
    }
}

module car_body() {
    difference() {
        along_x(car_x0, car_len) car_section_2d();
        // the case: everything from its wall in (y >= 0) and the two flanges, grown by
        // car_fit. What's left is the plate, the head in the C, and the strip under the
        // battery side's flange. Closed at the lanyard end by the stop.
        along_x(-car_fit, car_len + 1) offset(delta = car_fit) union() {
            case_flanges_2d();
            translate([0, -50]) square([100, 200]);
        }
        // the plate's inner corner behind the front shell's flange tip, a 45 deg chamfer
        along_x(-car_fit, car_len + 1) polygon([[tip_y, face_z - fl_h - car_fit], [tip_y, face_z + 1],
            [tip_y - (fl_h + car_fit + 1), face_z + 1]]);
        // latch: an upright slot frees the arm from latch_root to the end, and over that
        // stretch the plate's inner corner behind the battery side's flange tip is
        // chamfered too (elsewhere it rests on the strip)
        translate([latch_root, car_y0 - 1, arm_top]) cube([car_len - latch_root + 1, -car_y0 + 1, latch_gap]);
        along_x(latch_root, car_len + 1) polygon([[tip_y, fl_h + car_fit], [tip_y, -car_fit],
            [tip_y - (fl_h + 2 * car_fit), -car_fit]]);
    }
    // the bump on the arm, just past the end of the battery side's flange: a square face
    // that catches on that end, and a ramp out to the adapter's end, which the flange
    // rides up on its way in; it reaches to the case-side face it prints on
    intersection() {
        along_y(-fl_w + 0.4, -car_fit) polygon([[latch_x[0], arm_top - eps], [latch_x[1], arm_top - eps],
            [latch_x[1], arm_top + 0.6], [latch_x[0] + 0.5, bump_top], [latch_x[0], bump_top]]);
        along_x(latch_x[0] - 1, latch_x[1] + 1) polygon([[-fl_w + 0.4, arm_top - eps], [-car_fit, arm_top - eps],
            [-car_fit, bump_top], [-fl_w + 0.4 + (bump_top - arm_top), bump_top]]);
    }
    // zip-tie eyelets on its back, like the tray's: same places along the case, centred
    for (x = [12, out_x - 12 - tie_len])
        translate([x, car_y0 + eps, (car_z0 + face_z) / 2 - tie_h / 2]) mirror([0, 1, 0]) eyelet(tie_h);
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
    color("darkgreen") blade_mock();
    if (mems) color("purple") mems_blade_mock();
}

// Air blade (hardware/air_blade/gen/design.py), standing on the component side:
// board x 64.85 to 64.85 + blade_t; foot y 12.65-18.35 up to 1.5 mm; body y 13.15-17.85 up to 7.5 mm;
// then two prongs (SHT40 y 15.75-17.85, thermistor y 13.15-14.75) up to 13.3 mm.
module blade_mock() {
    module slab(y0, y1, h0, h1) translate([bx(64.85), by(y0), z_board - h1]) cube([blade_t, y1 - y0, h1 - h0]);
    slab(12.65, 18.35, 0, 1.5);
    slab(13.15, 17.85, 1.5, 7.5);
    slab(15.75, 17.85, 7.5, 13.3);
    slab(13.15, 14.75, 7.5, 13.3);
    // its parts on the front face (-x): U1 y 16.05-17.55, C1 16.55-17.05, RT1 13.55-14.35
    module part(y0, y1, h0, h1, d) translate([bx(64.85 - d), by(y0), z_board - h1]) cube([d, y1 - y0, h1 - h0]);
    part(16.05, 17.55, 10.8, 12.3, 0.55);
    part(16.55, 17.05, 8.9, 9.9, 0.55);
    part(13.55, 14.35, 10.9, 12.5, 0.85);
}

// MEMS blade (hardware/mems_blade/gen/design.py): body board x 64.85-66.45, y 24.8-36.2,
// from the board to 16.8 mm above it; parts on its +x face: the MiCS-5524 (board y 25.3-30.3,
// 9.3-16.3 mm up), the SY-CH4-37BPM (y 31.65-35.45, 12.05-15.85 mm up), both 1.55 mm deep,
// and the passives low down (0.5-6.6 mm up, ~1 mm deep).
module mems_blade_mock() {
    module box(x0, x1, y0, y1, h0, h1) translate([bx(x0), by(y0), z_board - h1]) cube([x1 - x0, y1 - y0, h1 - h0]);
    box(64.85, 66.45, 24.8, 36.2, 0, 16.8);
    box(66.45, 68.0, 25.3, 30.3, 9.3, 16.3);
    box(66.45, 68.0, 31.65, 35.45, 12.05, 15.85);
    box(66.45, 67.45, 25.0, 36.0, 0.5, 6.6);
}

module back_in_place() {
    // flip the tray over and sit its rim on the shell's back edge
    translate([0, out_y, front_depth + back_depth]) rotate([180, 0, 0]) back();
}

module battery_in_place() {
    // in the flipped tray: the compartment floor is at front_depth + divider_t + pocket_h from the front face
    color("dimgray") translate([pk_x0, pk_y0 + batt_fit, front_depth + divider_t + pocket_h - batt_h]) cube([batt_l, batt_w, batt_h]);
}

module car_in_place() {
    translate([0, out_y, front_depth + back_depth]) rotate([180, 0, 0]) switch_side() car();
}

part = "assembly";
cut_x = 40;             // mounted_section: where to cut across (-D cut_x=2 shows the hook)
if (part == "front") front();
else if (part == "back") back();
else if (part == "car") translate([0, 0, -car_fit]) rotate([90, 0, 0]) mirror([0, 1, 0]) car();   // case side down, eyelets up
// single parts in their assembled places (for make_assembly_html.py)
else if (part == "board_placed") board_mock();
else if (part == "cell_placed") battery_in_place();
else if (part == "back_placed") back_in_place();
else if (part == "car_placed") car_in_place();
else if (part == "mounted") {
    front(); back_in_place(); color("orange") car_in_place();
    %board_mock(); %battery_in_place();
} else if (part == "mounted_section") {
    difference() {
        union() { front(); back_in_place(); color("orange") car_in_place(); }
        translate([cut_x, -20, -5]) cube([out_x + 40, out_y + 40, 60]);
    }
}
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
