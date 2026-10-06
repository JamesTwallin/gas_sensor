"""Build the app icon from the real methane spike in raw/02_present.png.

Traces the chart line's centre column by column (skipping the dashed threshold
line), reduces it to its corners (foot, peak, shoulder, foot) on a flat
baseline, and draws that as one bold stroke fading green to red with height,
with a glow and a faint fill, on the app's dark background. Writes the files app.json points at.
"""
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).parent
ASSETS = HERE.parent / "assets"
SRC = HERE / "raw/02_present.png"
CROP = (540, 840, 1010, 1180)  # right-hand part of the methane slope chart

RED = (217, 69, 61)      # theme.critical
GREEN = (34, 196, 138)   # the chart's slope colour
AMBER = (240, 165, 49)
BG_TOP, BG_BOT = (24, 28, 34), (12, 14, 17)


X0, X1 = 775, 988  # one spike with flat baseline either side, in screenshot px


def path():
    """(x, y, is_red) along the chart line's centre, one point per column."""
    im = Image.open(SRC).convert("RGB")
    px = im.load()
    pts = []
    peak = None
    for x in range(X0, X1 + 1):
        red = [y for y in range(CROP[1], CROP[3]) if px[x, y][0] > 170 and px[x, y][1] < 110]
        grn = [y for y in range(CROP[1], CROP[3]) if px[x, y][1] > 140 and px[x, y][1] - px[x, y][0] > 60]
        # Drop the thin dashed threshold line: it is a short run on its own.
        if red and max(red) - min(red) < 6 and grn:
            red = []
        ys = red or grn
        if not ys:
            continue
        pts.append((x, (min(ys) + max(ys)) / 2, bool(red)))
        if red and (peak is None or min(red) < peak[1]):
            peak = (x, min(red) + 6, True)
    # A column midpoint cuts the corner at the very top; put the real peak back.
    pts = [p for p in pts if abs(p[0] - peak[0]) > 2] + [peak]
    pts.sort()
    # Light smoothing of the baseline noise only.
    sm = []
    for i, (x, y, r) in enumerate(pts):
        if not r and 0 < i < len(pts) - 1 and not pts[i - 1][2] and not pts[i + 1][2]:
            y = (pts[i - 1][1] + 2 * y + pts[i + 1][1]) / 4
        sm.append((x, y, r))
    return sm


def simplify(pts, tol):
    """Ramer-Douglas-Peucker: drop points within `tol` px of the line between neighbours."""
    if len(pts) < 3:
        return pts
    (x0, y0, _), (x1, y1, _) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    norm = (dx * dx + dy * dy) ** 0.5 or 1
    i, dmax = 0, -1.0
    for k, (x, y, _) in enumerate(pts[1:-1], 1):
        dist = abs(dy * x - dx * y + x1 * y0 - y1 * x0) / norm
        if dist > dmax:
            i, dmax = k, dist
    if dmax <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[: i + 1], tol)[:-1] + simplify(pts[i:], tol)


def key_points():
    """The spike's shape as a few vertices, normalised to 0..1 (y down).

    A coarse simplification of the real trace keeps its corners (foot of the
    rise, peak, shoulder, foot of the fall); the baseline is then made flat.
    """
    raw = [(x, y, False) for x, y, _ in path()]
    pts = simplify(raw, 9.0)
    base = max(y for _, y, _ in pts)
    xs = [p[0] for p in pts]
    top = min(y for _, y, _ in pts)
    out = []
    for x, y, _ in pts:
        if base - y < 25:  # baseline wiggle: flatten it
            y = base
        out.append(((x - min(xs)) / (max(xs) - min(xs)), (y - top) / (base - top)))
    # Merge consecutive baseline points into the two ends of each flat run.
    merged = [out[0]]
    for i, pt in enumerate(out[1:-1], 1):
        if pt[1] == 1 and merged[-1][1] == 1 and out[i + 1][1] == 1:
            continue
        merged.append(pt)
    merged.append(out[-1])
    return merged


def vgrad(size, top_y, bot_y):
    """RGBA image, red above top_y blending to green at bot_y and below."""
    w, h = size
    img = Image.new("RGBA", size)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = min(1, max(0, (y - top_y) / max(1, bot_y - top_y)))
        # Red at the peak, through amber, to green at the baseline; a straight
        # red-green blend goes muddy olive in the middle.
        if t < 0.5:
            a, b, u = RED, AMBER, t / 0.5
        else:
            a, b, u = AMBER, GREEN, (t - 0.5) / 0.5
        c = tuple(int(x + (y - x) * u) for x, y in zip(a, b))
        d.line([(0, y), (w, y)], fill=c + (255,))
    return img


def trace_layer(n, box, width, glow=True, fill=True):
    """Transparent n x n layer: the stylised spike stretched into `box` (w, h)."""
    k = 4  # supersample
    N = n * k
    bw, bh = box[0] * k, box[1] * k
    W = width * k
    x0, y0 = (N - bw + W) / 2, (N - bh + W) / 2
    pts = [(x0 + x * (bw - W), y0 + y * (bh - W)) for x, y in key_points()]
    base_y = pts[0][1]
    peak_y = min(y for _, y in pts)

    stroke = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(stroke)
    d.line(pts, fill=255, width=round(W), joint="curve")
    r = W / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)

    colour = vgrad((N, N), peak_y + W, base_y - W * 0.2)
    out = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    if fill:
        area = Image.new("L", (N, N), 0)
        ImageDraw.Draw(area).polygon(pts + [(pts[-1][0], base_y), (pts[0][0], base_y)], fill=255)
        fade = Image.new("L", (N, N), 0)
        fd = ImageDraw.Draw(fade)
        for y in range(int(peak_y), int(base_y) + 1):
            fd.line([(0, y), (N, y)], fill=int(70 * (1 - (y - peak_y) / (base_y - peak_y)) ** 0.7))
        area = ImageChops.multiply(area, fade)
        out.paste(colour, (0, 0), area)
    if glow:
        g = stroke.filter(ImageFilter.GaussianBlur(W * 0.9)).point(lambda v: int(v * 0.55))
        layer = Image.new("RGBA", (N, N), (0, 0, 0, 0))
        layer.paste(colour, (0, 0), g)
        out.alpha_composite(layer)
    line = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    line.paste(colour, (0, 0), stroke)
    out.alpha_composite(line)
    return out.resize((n, n), Image.LANCZOS), stroke.resize((n, n), Image.LANCZOS)


def gradient(n):
    img = Image.new("RGB", (n, n))
    d = ImageDraw.Draw(img)
    for y in range(n):
        t = y / (n - 1)
        d.line([(0, y), (n, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))
    return img


def background(n):
    """Dark gradient with a faint red bloom behind the peak."""
    img = gradient(n).convert("RGBA")
    bloom = Image.new("L", (n, n), 0)
    ImageDraw.Draw(bloom).ellipse([n * 0.25, n * 0.05, n * 0.75, n * 0.55], fill=60)
    bloom = bloom.filter(ImageFilter.GaussianBlur(n * 0.12))
    img.paste(RED + (255,), (0, 0), bloom)
    return img


def art(n, box, stroke, bg=True):
    """Icon artwork n x n, spike stretched to fill `box` (w, h) px, centred."""
    base = background(n) if bg else Image.new("RGBA", (n, n), (0, 0, 0, 0))
    base.alpha_composite(trace_layer(n, box, stroke)[0])
    return base


def main():
    # iOS / Play icon: full bleed, no transparency; the OS rounds the corners.
    art(1024, (800, 600), 64).convert("RGB").save(ASSETS / "icon.png")
    # Android adaptive icon: the launcher masks to a circle or squircle, so
    # keep the trace inside the central safe zone (~66% of 1024).
    art(1024, (600, 450), 52, bg=False).save(ASSETS / "android-icon-foreground.png")
    gradient(1024).save(ASSETS / "android-icon-background.png")
    alpha = trace_layer(1024, (600, 450), 52, glow=False, fill=False)[1]
    mono = Image.new("RGBA", alpha.size, (255, 255, 255, 0))
    mono.putalpha(alpha)
    mono.save(ASSETS / "android-icon-monochrome.png")
    # Splash: transparent, shown on the splash background colour.
    art(1024, (700, 520), 56, bg=False).save(ASSETS / "splash-icon.png")
    art(196, (160, 120), 14).convert("RGB").save(ASSETS / "favicon.png")
    # Play Store listing icon.
    art(512, (400, 300), 32).convert("RGB").save(HERE / "play/icon_512.png")
    print("icons written")


if __name__ == "__main__":
    main()
