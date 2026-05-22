"""
Reading Vibe Reel — Wind-Up Bird Chronicle · Haruki Murakami
Background: beach photo · Quotes as slides · 3fps · ~48s
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import os, subprocess, textwrap, random

BASE       = os.path.dirname(os.path.abspath(__file__))
PROJ_ROOT  = os.path.abspath(os.path.join(BASE, "..", ".."))
FONTS_DIR  = os.path.join(PROJ_ROOT, "reel_template", "fonts")
BG_PATH    = os.path.join(PROJ_ROOT, "images", "2a9a01cc-24f9-45bb-8ee4-723ebde3a9c8.JPG")
OUT_DIR    = os.path.join(BASE, "output")
FRAMES_DIR = os.path.join(OUT_DIR, "_frames")
os.makedirs(FRAMES_DIR, exist_ok=True)

W, H   = 1080, 1920
FPS    = 3
HOLD_F = 15  # 5s × 3fps
FADE_F = 3   # 1s × 3fps

QUOTES = [
    "Is it possible, finally, for one human being to achieve perfect understanding of another?",
    "Human beings were so strange. All you had to do was sit still for ten minutes, and you could see this amazing variety of grays.",
    "When you're supposed to go up, find the highest tower and climb to the top. When you're supposed to go down, find the deepest well and go down to the bottom.",
    "When you get used to that kind of life — of never having anything you want — then you stop knowing what it is you want.",
    "I had to make this thing I called 'I' — or rather, make the things that constituted me.",
    "Spending plenty of time on something can be the most sophisticated form of revenge.",
    "It was wonderful to be able to do that: to reach out and touch something, to feel something warm.",
    "The world looked the same to him as it always had. What most puzzled him was the unfamiliar lack of feeling inside himself.",
]

AUTHOR = "Haruki Murakami"
BOOK   = "Wind-Up Bird Chronicle"

OVERLAY_COL  = (10, 7, 4)
QUOTE_COL    = (245, 236, 210)
ATTR_COL     = (180, 155, 108)
TAG_COL      = (118, 98, 66)
RULE_COL     = (92, 75, 50)
OPENQ_COL    = (138, 112, 74)


def load_font(name, size):
    path = os.path.join(FONTS_DIR, name)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_bg():
    img = Image.open(BG_PATH).convert("RGB")
    try:
        exif = img._getexif()
        if exif:
            ori = exif.get(274)
            if ori == 3:   img = img.rotate(180, expand=True)
            elif ori == 6: img = img.rotate(270, expand=True)
            elif ori == 8: img = img.rotate(90,  expand=True)
    except Exception:
        pass
    pw, ph = img.size
    target = W / H
    if (pw / ph) > target:
        nw = int(ph * target)
        img = img.crop(((pw - nw) // 2, 0, (pw - nw) // 2 + nw, ph))
    else:
        nh = int(pw / target)
        top = max(0, (ph - nh) // 4)
        img = img.crop((0, top, pw, top + nh))
    img = img.resize((W, H), Image.LANCZOS)
    img = ImageEnhance.Color(img).enhance(0.72)
    img = ImageEnhance.Contrast(img).enhance(1.06)
    r, g, b = img.split()
    r = r.point(lambda x: min(255, int(x * 1.04)))
    b = b.point(lambda x: max(0, int(x * 0.88)))
    return Image.merge("RGB", (r, g, b))


def apply_grain(img):
    random.seed(42)
    noise = Image.new("L", (W, H), 128)
    for _ in range(W * H // 8):
        noise.putpixel((random.randint(0, W-1), random.randint(0, H-1)), random.randint(115, 140))
    nr = Image.merge("RGB", [noise, noise, noise]).filter(ImageFilter.GaussianBlur(0.4))
    return Image.blend(img, nr, alpha=0.018)


def add_dark_overlay(img, alpha=158):
    ov = Image.new("RGB", (W, H), OVERLAY_COL)
    img.paste(ov, mask=Image.new("L", (W, H), alpha))


def add_gradient(img, from_bottom=380, from_top=260):
    ov = Image.new("RGB", (W, H), OVERLAY_COL)
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    for y in range(H - 1, H - from_bottom, -1):
        t = (H - y) / from_bottom
        d.line([(0, y), (W, y)], fill=int(200 * t ** 1.8))
    for y in range(from_top):
        t = 1 - y / from_top
        d.line([(0, y), (W, y)], fill=int(175 * t ** 1.5))
    img.paste(ov, mask=mask)


def ctext(draw, y, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (W - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1])


def render_quote_frame(idx):
    img = RAW_BG.copy()
    add_dark_overlay(img)
    add_gradient(img)

    draw = ImageDraw.Draw(img)
    quote = QUOTES[idx]

    fnt_quote = load_font("Lora-Italic.ttf",         52)
    fnt_attr  = load_font("IBMPlexSerif-Italic.ttf",  30)
    fnt_book  = load_font("Jura-Light.ttf",           21)
    fnt_tag   = load_font("DMMono-Regular.ttf",        18)
    fnt_big   = load_font("Lora-Italic.ttf",          120)

    # Top label
    tag = f"reading  ·  {idx + 1} / {len(QUOTES)}"
    ctext(draw, 108, tag, fnt_tag, TAG_COL)
    draw.line([(110, 150), (W - 110, 150)], fill=RULE_COL, width=1)

    # Wrap quote
    lines  = textwrap.wrap(quote, width=27)
    line_h = 70
    block_h = len(lines) * line_h
    quote_top = (H // 2) - (block_h // 2) - 55

    # Opening quote mark
    draw.text((108, quote_top - 60), "\u201c", font=fnt_big, fill=OPENQ_COL)

    y = quote_top
    for line in lines:
        y = ctext(draw, y, line, fnt_quote, QUOTE_COL)
        y += 18  # extra leading

    # Closing quote mark
    draw.text((W - 138, y - 72), "\u201d", font=fnt_big, fill=OPENQ_COL)

    y += 40
    draw.line([(190, y), (W - 190, y)], fill=RULE_COL, width=1)
    y += 24

    y = ctext(draw, y, f"\u2014 {AUTHOR}", fnt_attr, ATTR_COL)
    y += 10
    ctext(draw, y, BOOK.upper(), fnt_book, TAG_COL)

    # Bottom rule
    draw.line([(110, H - 148), (W - 110, H - 148)], fill=RULE_COL, width=1)

    return apply_grain(img)


RAW_BG = load_bg()


def main():
    print("=" * 60)
    print("  READING VIBE REEL — Wind-Up Bird Chronicle")
    est = int(((HOLD_F + FADE_F) / FPS) * len(QUOTES))
    print(f"  {len(QUOTES)} quotes  ·  {FPS}fps  ·  ~{est}s")
    print("=" * 60)

    rendered = []
    for i in range(len(QUOTES)):
        print(f"  Rendering quote {i+1}/{len(QUOTES)}...")
        rendered.append(render_quote_frame(i))

    fi = 0
    for i, frame in enumerate(rendered):
        for _ in range(HOLD_F):
            frame.save(os.path.join(FRAMES_DIR, f"f{fi:05d}.png"))
            fi += 1
        if i < len(rendered) - 1:
            nxt = rendered[i + 1]
            for j in range(FADE_F):
                blend = Image.blend(frame, nxt, alpha=j / FADE_F)
                blend.save(os.path.join(FRAMES_DIR, f"f{fi:05d}.png"))
                fi += 1

    print(f"\n  Total frames: {fi}  (~{fi / FPS:.1f}s)")

    # Hero image
    hero_path = os.path.join(OUT_DIR, "reel.png")
    rendered[0].save(hero_path, "PNG", dpi=(300, 300))
    print(f"  Saved hero: {hero_path}")

    # Encode
    out_mp4 = os.path.join(OUT_DIR, "reel.mp4")
    result = subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(FRAMES_DIR, "f%05d.png"),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-vf", f"scale={W}:{H}",
        out_mp4,
    ], capture_output=True, text=True)

    if result.returncode == 0:
        mb = os.path.getsize(out_mp4) / 1024 / 1024
        print(f"  Saved reel: {out_mp4}  ({mb:.1f} MB)")
    else:
        print(f"  ffmpeg error:\n{result.stderr[-800:]}")

    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
