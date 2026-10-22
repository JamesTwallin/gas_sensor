"""Build assembly.html: an interactive, explodable 3D view of the case and car mount.

Exports each part from case.scad in its assembled position, packs the
meshes into assembly_template.html, and writes assembly.html, which opens
straight from disk (three.js comes from a CDN).

    python make_assembly_html.py            (OpenSCAD 2021.01+, numpy)
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OPENSCAD = os.environ.get("OPENSCAD") or next(
    (p for p in [r"C:\Program Files\OpenSCAD\openscad.com", "/usr/bin/openscad",
                 "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"] if os.path.exists(p)), "openscad")

# id, part (in its assembled position), label, print file (None = not printed)
PARTS = [
    ("front", "front", "Front shell", "stl/front.stl"),
    ("board", "board_placed", "Board with air blade", None),
    ("cell", "cell_placed", "LiPo cell", None),
    ("back", "back_placed", "Battery side", "stl/back.stl"),
    ("car", "car_placed", "Car adapter", "stl/car_adapter.stl"),
]

VERTEX = re.compile(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)")


def export(part, tmp):
    stl = os.path.join(tmp, "part.stl")
    subprocess.run([OPENSCAD, "-o", stl, "-D", f'part="{part}"',
                    os.path.join(HERE, "case.scad")], check=True, capture_output=True)
    with open(stl, "rb") as f:
        data = f.read()
    v = np.array(VERTEX.findall(data), dtype=np.float32)
    if len(v) == 0 or len(v) % 3:
        sys.exit(f"no mesh for part {part}")
    return v


def pack(v):
    # quantise to uint16 over the part's bounding box (~1.5 um steps for this case)
    lo = v.min(axis=0)
    span = np.maximum(v.max(axis=0) - lo, 1e-6)
    q = np.round((v - lo) / span * 65535).astype("<u2")
    return {"lo": lo.round(4).tolist(), "span": span.round(4).tolist(),
            "tris": len(v) // 3, "data": base64.b64encode(q.tobytes()).decode()}


def main():
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for pid, part, label, stl in PARTS:
            v = export(part, tmp)
            size = (v.max(axis=0) - v.min(axis=0)).round(1).tolist()
            print(f"{pid:6s} {len(v) // 3:6d} triangles  {size}")
            out.append({"id": pid, "label": label, "file": stl, "size": size, **pack(v)})
    with open(os.path.join(HERE, "assembly_template.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace("/*PARTS_JSON*/null", json.dumps(out, separators=(",", ":")))
    path = os.path.join(HERE, "assembly.html")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"wrote {path} ({os.path.getsize(path) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
