"""Work out JLCPCB placement (CPL) coordinates by matching LCSC's own footprints.

JLC places each part using the origin and 0-degree orientation of *its* footprint
(from EasyEDA/LCSC), which often differ from KiCad's. For every assembled part
this script downloads the LCSC footprint, tries the four rotations, finds the
translation that lands its pads on the pads of the placed KiCad footprint, and
records the winning position + rotation in gen/jlc_placement.json. export.py
writes cpl.csv from that file.

  pip install easyeda2kicad          (any Python; path via EASYEDA2KICAD env var)
  "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" gen/jlc_align.py
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcbnew  # noqa: E402

try:
    import wx
    wx.DisableAsserts()
except Exception:
    pass

import design  # noqa: E402
from kicad_lib import PROJECT_DIR  # noqa: E402

E2K = os.environ.get("EASYEDA2KICAD", "easyeda2kicad")
LCSC_DIR = os.path.join(PROJECT_DIR, "build", "lcsc")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jlc_placement.json")
T, mm = pcbnew.ToMM, pcbnew.FromMM
MATCH = 0.35  # mm, pad centres closer than this count as the same pad


def fetch(lcsc):
    """Download the LCSC footprint (cached per part number); return (pretty dir, name)."""
    os.makedirs(LCSC_DIR, exist_ok=True)
    base = os.path.join(LCSC_DIR, lcsc)
    pretty = base + ".pretty"
    if not (os.path.isdir(pretty) and os.listdir(pretty)):
        subprocess.run([E2K, "--footprint", "--lcsc_id=" + lcsc, "--output", base, "--overwrite"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    mods = [f for f in os.listdir(pretty) if f.endswith(".kicad_mod")]
    if len(mods) != 1:
        raise RuntimeError(f"expected one footprint for {lcsc}, got {mods}")
    return pretty, mods[0][:-len(".kicad_mod")]


def pad_list(fp):
    return [(p.GetNumber(), T(p.GetPosition().x), T(p.GetPosition().y)) for p in fp.Pads()
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]


def align(board_fp, lcsc_fp):
    """Rotation + position that best lays lcsc_fp's pads onto board_fp's pads.

    Libraries draw the same land pattern slightly differently (pad lengths, toe
    extensions), so pad centres rarely coincide exactly. For each of the four
    rotations: start from the centroid offset, refine with a few nearest-neighbour
    (ICP) steps, then score by pads matched within MATCH mm, pads whose numbers
    also agree (this picks pin 1 on symmetric packages), and mean residual."""
    target = pad_list(board_fp)
    best = None
    for rot in (0, 90, 180, 270):
        lcsc_fp.SetPosition(pcbnew.VECTOR2I(0, 0))
        lcsc_fp.SetOrientationDegrees(rot)
        src = pad_list(lcsc_fp)
        if not src or not target:
            continue
        dx = sum(t[1] for t in target) / len(target) - sum(p[1] for p in src) / len(src)
        dy = sum(t[2] for t in target) / len(target) - sum(p[2] for p in src) / len(src)
        for _ in range(8):
            pairs = []
            for sn, sx, sy in src:
                d, tn, tx, ty = min(((tx - sx - dx) ** 2 + (ty - sy - dy) ** 2, tn, tx, ty)
                                    for tn, tx, ty in target)
                if d < 1.0:
                    pairs.append((tx - sx, ty - sy))
            if not pairs:
                break
            dx = sum(p[0] for p in pairs) / len(pairs)
            dy = sum(p[1] for p in pairs) / len(pairs)
        matched = same = 0
        err = 0.0
        for sn, sx, sy in src:
            d, tn = min((((tx - sx - dx) ** 2 + (ty - sy - dy) ** 2) ** 0.5, tn) for tn, tx, ty in target)
            if d < MATCH:
                matched += 1
                err += d
                same += sn == tn
        cand = (matched, same, -err / max(matched, 1), rot, dx, dy)
        if best is None or cand[:3] > best[:3]:
            best = cand
    matched, same, nerr, rot, dx, dy = best
    return dict(x=round(dx, 4), y=round(dy, 4), rot=rot, matched=matched, same_number=same,
                mean_err=round(-nerr, 3), lcsc_pads=len(src), board_pads=len(target))


def main():
    board = pcbnew.LoadBoard(os.path.join(PROJECT_DIR, design.PROJECT + ".kicad_pcb"))
    result = {}
    for part in design.PARTS:
        if part.virtual or part.dnp or getattr(part, "no_assembly", False) or not part.lcsc:
            continue
        fp = board.FindFootprintByReference(part.ref)
        try:
            pretty, name = fetch(part.lcsc)
            lfp = pcbnew.FootprintLoad(pretty, name)
            r = align(fp, lfp)
        except Exception as e:  # keep going; export falls back to KiCad coordinates
            print(f"{part.ref:5} {part.lcsc:10} FAILED: {e}")
            continue
        r.update(lcsc=part.lcsc, lcsc_footprint=name, kicad_x=round(T(fp.GetPosition().x), 4),
                 kicad_y=round(T(fp.GetPosition().y), 4), kicad_rot=fp.GetOrientationDegrees())
        ok = r["matched"] == min(r["lcsc_pads"], r["board_pads"])
        r["ok"] = ok
        result[part.ref] = r
        shift = ((r["x"] - r["kicad_x"]) ** 2 + (r["y"] - r["kicad_y"]) ** 2) ** 0.5
        print(f"{part.ref:5} {part.lcsc:10} rot {r['kicad_rot']:>5.0f} -> {r['rot']:>3}  "
              f"shift {shift:5.2f} mm  pads {r['matched']}/{r['lcsc_pads']} (same no. {r['same_number']})"
              + ("" if ok else "   <-- CHECK"))
    with open(OUT, "w") as f:
        json.dump(result, f, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
