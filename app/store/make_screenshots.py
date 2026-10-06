"""Frame raw phone captures into store-listing screenshots.

Usage: python make_screenshots.py
Reads raw/*.png (full-screen captures from the phone, 1080x2424) and writes:
  ios/      1320x2868  (App Store, iPhone 6.9")
  ios_6_3/  1206x2622  (App Store, iPhone 6.1"/6.3")
  ipad/     2064x2752  (App Store, iPad 13")
  play/     1080x1920  (Google Play phone)
  play/feature_graphic.png 1024x500
Captions live in SHOTS below; edit them and re-run.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
FONTS = HERE.parent / "node_modules/@expo-google-fonts/inter"
BOLD = str(FONTS / "800ExtraBold/Inter_800ExtraBold.ttf")
MED = str(FONTS / "500Medium/Inter_500Medium.ttf")

BG_TOP = (15, 17, 20)
BG_BOT = (20, 40, 66)
TEXT = (245, 246, 248)
MUTED = (170, 178, 190)

# Status bar and gesture bar of the Pixel 9a capture, cropped off.
CROP_TOP, CROP_BOTTOM = 150, 40

SHOTS = [
    ("01_live.png", "See methane live", "Readings from your sensor, four times a second"),
    ("02_present.png", "Spikes you can't miss", "Full-screen view turns red when gas rises"),
    ("03_surveys.png", "Every survey saved", "Logged with GPS, shared as CSV files"),
    ("04_settings.png", "Tune it to your sensor", "Spike alerts, beeps and calibration"),
]


def gradient(w, h):
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        px.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))
    return img


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def phone(raw, target_h):
    """Cropped capture with rounded corners, scaled to target_h."""
    shot = raw.crop((0, CROP_TOP, raw.width, raw.height - CROP_BOTTOM))
    scale = target_h / shot.height
    shot = shot.resize((round(shot.width * scale), target_h), Image.LANCZOS)
    r = round(shot.width * 0.07)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *shot.size], r, fill=255)
    return shot, mask, r


def compose(raw, size, title, sub):
    W, H = size
    img = gradient(W, H)
    d = ImageDraw.Draw(img)
    pad = round(W * 0.07)
    tf = ImageFont.truetype(BOLD, round(W * 0.075))
    sf = ImageFont.truetype(MED, round(W * 0.036))
    y = round(H * 0.045)
    for line in wrap(d, title, tf, W - 2 * pad):
        d.text((W / 2, y), line, font=tf, fill=TEXT, anchor="mt")
        y += round(tf.size * 1.15)
    y += round(sf.size * 0.5)
    for line in wrap(d, sub, sf, W - 2 * pad):
        d.text((W / 2, y), line, font=sf, fill=MUTED, anchor="mt")
        y += round(sf.size * 1.35)
    y += round(H * 0.03)
    avail_h = H - y
    shot, mask, r = phone(raw, round(avail_h * 1.0) + r_bleed(H))
    # Keep the device within 86% of the width.
    if shot.width > W * 0.86:
        shot, mask, r = phone(raw, round(shot.height * W * 0.86 / shot.width))
    x = (W - shot.width) // 2
    # Soft shadow and thin bezel.
    shadow = Image.new("L", (shot.width + 80, shot.height + 80), 0)
    ImageDraw.Draw(shadow).rounded_rectangle([40, 40, 40 + shot.width, 40 + shot.height], r, fill=150)
    shadow = shadow.filter(ImageFilter.GaussianBlur(30))
    img.paste((0, 0, 0), (x - 40, y - 20), shadow)
    bez = max(4, round(W * 0.006))
    d.rounded_rectangle([x - bez, y - bez, x + shot.width + bez, y + shot.height + bez], r + bez, fill=(58, 64, 74))
    img.paste(shot, (x, y), mask)
    return img


def r_bleed(H):
    """Let the phone run off the bottom edge a little, like most store shots."""
    return round(H * 0.06)


def feature_graphic(raw, out):
    """1024x500 Play banner: name and tagline beside the live slope chart."""
    W, H = 1024, 500
    img = gradient(W, H)
    d = ImageDraw.Draw(img)
    chart = raw.crop((42, 895, 1038, 1345))  # the methane slope card
    cw = 470
    chart = chart.resize((cw, round(chart.height * cw / chart.width)), Image.LANCZOS)
    m = Image.new("L", chart.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, *chart.size], 28, fill=255)
    cy = (H - chart.height) // 2
    img.paste(chart, (W - cw - 50, cy), m)
    tf = ImageFont.truetype(BOLD, 44)
    sf = ImageFont.truetype(MED, 26)
    d.text((56, 200), "GasSnifferBuddy", font=tf, fill=TEXT, anchor="lm")
    d.text((58, 262), "Find methane leaks with a", font=sf, fill=MUTED, anchor="lm")
    d.text((58, 298), "pocket gas sensor", font=sf, fill=MUTED, anchor="lm")
    img.save(out)


def main():
    sizes = {"ios": (1320, 2868), "ios_6_3": (1206, 2622), "ipad": (2064, 2752), "play": (1080, 1920)}
    for k in sizes:
        (HERE / k).mkdir(exist_ok=True)
    for name, title, sub in SHOTS:
        src = HERE / "raw" / name
        if not src.exists():
            print("missing", src)
            continue
        raw = Image.open(src).convert("RGB")
        for k, size in sizes.items():
            compose(raw, size, title, sub).save(HERE / k / name)
            print("wrote", k, name)
    live = HERE / "raw" / SHOTS[0][0]
    if live.exists():
        feature_graphic(Image.open(live).convert("RGB"), HERE / "play/feature_graphic.png")
    print("wrote play feature_graphic.png")


if __name__ == "__main__":
    main()
