"""
╔══════════════════════════════════════════════════════════════╗
║           TRAVEL REEL GENERATOR — Reusable Template         ║
║  Usage: python reel_template/make_reel.py reels/<name>       ║
║  Each reel folder needs a reel_config.py with CONFIG dict.   ║
╚══════════════════════════════════════════════════════════════╝
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import importlib.util, math, os, random, subprocess, sys

# ══════════════════════════════════════════════════════════════
# CONFIG LOADER — reads reel_config.py from the reel folder
# ══════════════════════════════════════════════════════════════

def load_config(reel_dir):
    """Load CONFIG from reel_dir/reel_config.py, with sensible defaults."""
    config_path = os.path.join(reel_dir, "reel_config.py")
    if not os.path.exists(config_path):
        print(f"  ✗ No reel_config.py found in: {reel_dir}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("reel_config", config_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = dict(mod.CONFIG)

    # Resolve relative folder paths against the reel directory
    this_dir   = os.path.dirname(os.path.abspath(__file__))
    fonts_path = os.path.join(this_dir, "fonts")
    cfg.setdefault("input_folder",    os.path.join(reel_dir, "images"))
    cfg.setdefault("output_folder",   os.path.join(reel_dir, "output"))
    cfg.setdefault("fonts_folder",    fonts_path)
    cfg.setdefault("fps",             30)
    cfg.setdefault("hold_seconds",    3.0)
    cfg.setdefault("fade_seconds",    1.0)
    cfg.setdefault("make_image",      True)
    cfg.setdefault("make_video",      True)
    cfg.setdefault("hero_photo",      None)
    cfg.setdefault("caption_position","upper_third")
    return cfg

# ══════════════════════════════════════════════════════════════
# COLOUR PALETTES — matches "vibe" setting above
# ══════════════════════════════════════════════════════════════

PALETTES = {
    "dark_cinematic": {
        "bg":           (5, 6, 11),
        "top_gradient": (5, 6, 11),
        "bot_gradient": (4, 5, 10),
        "rule_dim":     (80, 90, 130),
        "rule_bright":  (180, 190, 220),
        "text_bright":  (255, 255, 255),
        "text_dim":     (110, 120, 160),
        "text_ghost":   (70, 78, 110),
        "text_whisper": (220, 215, 205),
        "text_close":   (200, 195, 185),
        "color_sat":    0.82,
        "color_con":    1.10,
        "red_shift":    0.96,
        "blue_shift":   1.04,
        "blue_lift":    4,
    },
    "warm_golden": {
        "bg":           (14, 10, 6),
        "top_gradient": (14, 10, 6),
        "bot_gradient": (10, 7, 4),
        "rule_dim":     (110, 88, 55),
        "rule_bright":  (160, 130, 80),
        "text_bright":  (245, 235, 200),
        "text_dim":     (140, 115, 75),
        "text_ghost":   (80, 65, 42),
        "text_whisper": (200, 175, 130),
        "text_close":   (175, 152, 110),
        "color_sat":    0.90,
        "color_con":    1.08,
        "red_shift":    1.04,
        "blue_shift":   0.94,
        "blue_lift":    -4,
    },
    "minimal_clean": {
        "bg":           (245, 244, 240),
        "top_gradient": (248, 247, 243),
        "bot_gradient": (240, 239, 235),
        "rule_dim":     (180, 178, 170),
        "rule_bright":  (130, 128, 120),
        "text_bright":  (30, 28, 25),
        "text_dim":     (100, 98, 92),
        "text_ghost":   (160, 158, 150),
        "text_whisper": (80, 78, 72),
        "text_close":   (100, 98, 92),
        "color_sat":    0.75,
        "color_con":    0.95,
        "red_shift":    1.0,
        "blue_shift":   1.0,
        "blue_lift":    0,
    },
    "moody_blue": {
        "bg":           (6, 8, 18),
        "top_gradient": (6, 8, 18),
        "bot_gradient": (4, 6, 14),
        "rule_dim":     (40, 60, 110),
        "rule_bright":  (60, 90, 160),
        "text_bright":  (210, 220, 245),
        "text_dim":     (80, 100, 160),
        "text_ghost":   (40, 55, 100),
        "text_whisper": (150, 170, 215),
        "text_close":   (130, 150, 200),
        "color_sat":    0.78,
        "color_con":    1.12,
        "red_shift":    0.90,
        "blue_shift":   1.10,
        "blue_lift":    8,
    },
    # ── Auction Editorial — The Hammer Price brand palette ────
    # Near-black canvas, warm gold accents, ivory type.
    # Palette mirrors Christie's/Sotheby's auction house gold
    # but with a data-forward, editorial edge.
    "auction_editorial": {
        "bg":           (20, 18, 16),
        "top_gradient": (20, 18, 16),
        "bot_gradient": (14, 12, 10),
        "rule_dim":     (100, 82, 45),
        "rule_bright":  (201, 168, 76),    # brand gold #C9A84C
        "text_bright":  (245, 240, 232),   # ivory #F5F0E8
        "text_dim":     (160, 132, 68),
        "text_ghost":   (80, 66, 34),
        "text_whisper": (210, 195, 165),
        "text_close":   (185, 165, 130),
        "color_sat":    0.70,              # desaturated — like archival photography
        "color_con":    1.06,
        "red_shift":    1.03,              # slight warm push
        "blue_shift":   0.92,
        "blue_lift":    -3,
    },

    # ── Museum Calm — warm parchment tones, hushed light ──────
    # Inspired by the quiet of great museum halls: aged stone,
    # brass fittings, diffused skylight. Relaxing & contemplative.
    "museum_calm": {
        "bg":           (22, 18, 14),
        "top_gradient": (22, 18, 14),
        "bot_gradient": (18, 14, 10),
        "rule_dim":     (105, 92, 72),
        "rule_bright":  (168, 148, 112),
        "text_bright":  (238, 228, 208),
        "text_dim":     (130, 112, 86),
        "text_ghost":   (72, 62, 48),
        "text_whisper": (195, 178, 148),
        "text_close":   (170, 154, 126),
        "color_sat":    0.72,          # desaturated — like old photographs
        "color_con":    1.04,          # gentle contrast lift
        "red_shift":    1.02,          # slight warm push
        "blue_shift":   0.92,          # cool tones pulled back
        "blue_lift":    -6,            # deeper shadows
    },
}

# ══════════════════════════════════════════════════════════════
# CORE ENGINE — no need to edit below this line
# ══════════════════════════════════════════════════════════════

W, H = 1080, 1920

def load_fonts(fonts_dir, scale=1.0, overrides=None):
    def f(name, size):
        path = os.path.join(fonts_dir, name)
        if not os.path.exists(path):
            print(f"  ⚠ Font not found: {path} — using default")
            return ImageFont.load_default()
        return ImageFont.truetype(path, size)
    s = scale
    fonts = {
        "serif_lg":   f("Gloock-Regular.ttf",      int(84 * s)),
        "serif_med":  f("InstrumentSerif-Italic.ttf",   int(58 * s)),
        "italic_med": f("IBMPlexSerif-Italic.ttf",  int(42 * s)),
        "jura_light": f("Jura-Light.ttf",           int(22 * s)),
        "jura_med":   f("Jura-Medium.ttf",          int(24 * s)),
        "mono":       f("DMMono-Regular.ttf",        int(17 * s)),
        "mono_sm":    f("DMMono-Regular.ttf",        int(14 * s)),
    }
    if overrides:
        for key, (fname, size) in overrides.items():
            fonts[key] = f(fname, int(size * s))
    return fonts

def ctext(draw, y, text, font, fill):
    if not text:
        return
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (W - (bbox[2] - bbox[0])) // 2
    draw.text((x + 2, y + 3), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill, stroke_width=1, stroke_fill=(0, 0, 0))

def wrap_text(text, font, max_width):
    """Split text into lines that each fit within max_width pixels."""
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        if font.getlength(test) <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines

def ctext_wrapped(draw, y, text, font, fill, max_width=W - 180, line_gap=10):
    """Draw text wrapped to max_width, centred. Returns y after last line."""
    for line in wrap_text(text, font, max_width):
        ctext(draw, y, line, font, fill)
        bbox = draw.textbbox((0, 0), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y

_MEASURE_DRAW = ImageDraw.Draw(Image.new("RGB", (1, 1)))

def measure_wrapped_height(text, font, max_width=W - 180, line_gap=10):
    """Return total pixel height of text if rendered by ctext_wrapped."""
    if not text:
        return 0
    lines = wrap_text(text, font, max_width)
    total = 0
    for i, line in enumerate(lines):
        bbox = _MEASURE_DRAW.textbbox((0, 0), line, font=font)
        total += bbox[3] - bbox[1]
        if i < len(lines) - 1:
            total += line_gap
    return total

def gradient_overlay(img, color, top_px, strength=235, curve=1.2):
    overlay = Image.new("RGB", (W, H), color)
    mask = Image.new("L", (W, H), 0)
    for y in range(top_px):
        t = 1 - y / top_px
        a = int(strength * (t ** curve))
        ImageDraw.Draw(mask).line([(0, y), (W, y)], fill=a)
    img.paste(overlay, mask=mask)

def bot_gradient_overlay(img, color, bot_px=320, strength=170, curve=1.6):
    overlay = Image.new("RGB", (W, H), color)
    mask = Image.new("L", (W, H), 0)
    for y in range(H - 1, H - bot_px, -1):
        t = (H - y) / bot_px
        a = int(strength * (t ** curve))
        ImageDraw.Draw(mask).line([(0, y), (W, y)], fill=a)
    img.paste(overlay, mask=mask)

def apply_vignette(img, strength=90):
    vig = Image.new("L", (W, H), 0)
    vcx, vcy = W // 2, H // 2
    for step in range(0, min(W, H) // 2, 2):
        t = step / (min(W, H) // 2)
        a = int(strength * ((1 - t) ** 2))
        ImageDraw.Draw(vig).ellipse([vcx-step, vcy-step, vcx+step, vcy+step], fill=a)
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), mask=vig)

def apply_grain(img, seed=42, alpha=0.022):
    random.seed(seed)
    noise = Image.new("L", (W, H), 128)
    for _ in range(W * H // 6):
        nx, ny = random.randint(0, W-1), random.randint(0, H-1)
        noise.putpixel((nx, ny), random.randint(112, 142))
    noise_rgb = Image.merge("RGB", [noise, noise, noise])
    noise_rgb = noise_rgb.filter(ImageFilter.GaussianBlur(0.3))
    return Image.blend(img, noise_rgb, alpha=alpha)

def load_photo(fpath, split=False):
    photo = Image.open(fpath)
    try:
        exif = photo._getexif()
        if exif:
            ori = exif.get(274)
            if ori == 3:   photo = photo.rotate(180, expand=True)
            elif ori == 6: photo = photo.rotate(270, expand=True)
            elif ori == 8: photo = photo.rotate(90,  expand=True)
    except: pass
    photo = photo.convert("RGB")
    pw, ph = photo.size
    # In split mode the photo fills only the bottom 2/3 of the frame
    dest_h = int(H * 2 / 3) if split else H
    target = W / dest_h
    ratio  = pw / ph
    if ratio > target:
        nw = int(ph * target)
        photo = photo.crop(((pw - nw) // 2, 0, (pw - nw) // 2 + nw, ph))
    else:
        nh = int(pw / target)
        top = max(0, (ph - nh) // 4)
        photo = photo.crop((0, top, pw, top + nh))
    return photo.resize((W, dest_h), Image.LANCZOS)

def grade_photo(photo, pal):
    photo = ImageEnhance.Color(photo).enhance(pal["color_sat"])
    photo = ImageEnhance.Contrast(photo).enhance(pal["color_con"])
    r, g, b = photo.split()
    r = r.point(lambda x: max(0, min(255, int(x * pal["red_shift"]))))
    b = b.point(lambda x: max(0, min(255, int(x * pal["blue_shift"] + pal["blue_lift"]))))
    return Image.merge("RGB", (r, g, b))

def get_caption_y(position):
    """Return the BOX_TOP y-coordinate based on caption position."""
    if position == "upper_third":      return 82
    elif position == "upper_third_low": return 200   # nudged down ~120px — good for museum/indoor shots
    elif position == "center":          return H // 2 - 160
    elif position == "lower_third":     return H - 420
    return 82

def render_frame(photo, cfg, fnt, show_caption=True, frame_caption=None):
    """frame_caption overrides cfg caption text for this frame only.
    Expected keys: tag, line1, line2, line3 (all optional, fall back to cfg)."""
    pal = PALETTES[cfg["vibe"]]
    split = cfg.get("photo_split", False)

    if split:
        # Dark canvas, photo pasted into bottom 2/3
        img = Image.new("RGB", (W, H), pal["bg"])
        photo_y = H - photo.height
        img.paste(photo, (0, photo_y))
        # Soft fade at top edge of photo
        fade_h = 140
        fade_overlay = Image.new("RGB", (W, H), pal["bg"])
        fade_mask = Image.new("L", (W, H), 0)
        for y in range(fade_h):
            t = 1 - y / fade_h
            a = int(255 * (t ** 1.5))
            ImageDraw.Draw(fade_mask).line([(0, photo_y + y), (W, photo_y + y)], fill=a)
        img.paste(fade_overlay, mask=fade_mask)
        # Bottom fade
        bot_gradient_overlay(img, pal["bot_gradient"], bot_px=180, strength=140)
    else:
        img = photo.copy()
        top_px = 420 if show_caption else 200
        gradient_overlay(img, pal["top_gradient"], top_px,
                         strength=235 if show_caption else 180)
        bot_gradient_overlay(img, pal["bot_gradient"])
        apply_vignette(img)

    # Frame caption dict can override show_caption per frame
    fc            = frame_caption or {}
    show_caption  = fc.get("show_caption", show_caption)
    hook_question = fc.get("hook_question")
    hook_answer   = fc.get("hook_answer", "")
    upper_artist  = fc.get("upper_artist", "")
    upper_title   = fc.get("upper_title", "")
    UBT = UBB = 0

    # col2 (sold price colour) is also used for the answer text and tag — pull it out early
    col2 = tuple(fc.get("color_line2", cfg.get("color_line2", pal["text_bright"])))

    BT = BB = 0
    if show_caption:
        tag   = fc.get("tag",   cfg.get("caption_tag",   ""))
        line1 = fc.get("line1", cfg.get("caption_line1", ""))
        line2 = fc.get("line2", cfg.get("caption_line2", ""))
        line3 = fc.get("line3", cfg.get("caption_line3", ""))

        col1 = tuple(fc.get("color_line1", cfg.get("color_line1", pal["text_whisper"])))
        col3 = tuple(fc.get("color_line3", cfg.get("color_line3", pal["text_close"])))

        BT = get_caption_y(cfg["caption_position"])
        BB = BT + 288

        backdrop      = Image.new("RGB", (W, H), (6, 5, 4))
        backdrop_mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(backdrop_mask).rectangle(
            [(56, BT - 22), (W - 56, BB + 22)], fill=190
        )
        backdrop_mask = backdrop_mask.filter(ImageFilter.GaussianBlur(16))
        img = Image.composite(backdrop, img, backdrop_mask)

    # Hook box height depends on content:
    # — question only: compact (question in large serif)
    # — question + answer: taller (question shrinks to label, answer dominates in large serif)
    HBT = HBB = 0
    if hook_question:
        has_answer = bool(hook_answer)
        if has_answer:
            _ans_h = measure_wrapped_height(hook_answer, fnt["serif_med"], max_width=W - 200, line_gap=10)
            HBH = 60 + _ans_h + 32   # question label (44px) + gap to answer (16px) + answer + bottom pad
        else:
            HBH = 140
        HBT = (BB + 28) if show_caption else (H // 2 - HBH // 2)
        HBB = HBT + HBH
        hk_backdrop      = Image.new("RGB", (W, H), (6, 5, 4))
        hk_backdrop_mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(hk_backdrop_mask).rectangle(
            [(56, HBT - 18), (W - 56, HBB + 18)], fill=188
        )
        hk_backdrop_mask = hk_backdrop_mask.filter(ImageFilter.GaussianBlur(14))
        img = Image.composite(hk_backdrop, img, hk_backdrop_mask)

    # Upper box: artist name + painting title — height expands to fit content
    if upper_artist or upper_title:
        UBT = 150
        _a_h = measure_wrapped_height(upper_artist, fnt["italic_med"], max_width=W - 200) if upper_artist else 0
        _t_h = measure_wrapped_height(upper_title,  fnt["italic_med"], max_width=W - 200) if upper_title else 0
        _gap = 18 if (upper_artist and upper_title) else 0
        UBH  = 24 + _a_h + _gap + _t_h + 24
        UBB  = UBT + UBH
        ub_back      = Image.new("RGB", (W, H), (6, 5, 4))
        ub_back_mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(ub_back_mask).rectangle(
            [(56, UBT - 16), (W - 56, UBB + 16)], fill=185
        )
        ub_back_mask = ub_back_mask.filter(ImageFilter.GaussianBlur(14))
        img = Image.composite(ub_back, img, ub_back_mask)

    draw = ImageDraw.Draw(img)

    if upper_artist or upper_title:
        RD = pal["rule_dim"]
        RB = pal["rule_bright"]
        draw.line([(72, UBT), (W-72, UBT)], fill=RD, width=1)
        draw.line([(72, UBB), (W-72, UBB)], fill=RD, width=1)
        draw.line([(72, UBT), (72, UBB)],   fill=RD, width=1)
        draw.line([(W-72, UBT), (W-72, UBB)], fill=RD, width=1)
        for (bx, by, dx, dy) in [(72,UBT,1,1),(W-72,UBT,-1,1),(72,UBB,1,-1),(W-72,UBB,-1,-1)]:
            draw.line([(bx,by),(bx+dx*20,by)], fill=RB, width=2)
            draw.line([(bx,by),(bx,by+dy*20)], fill=RB, width=2)
        _uy = UBT + 24
        if upper_artist:
            ctext_wrapped(draw, _uy, upper_artist, fnt["italic_med"], pal["text_bright"], max_width=W - 200)
            _uy += _a_h + _gap
        if upper_title:
            ctext_wrapped(draw, _uy, upper_title, fnt["italic_med"], col2, max_width=W - 200)

    if show_caption:
        RD = pal["rule_dim"]
        RB = pal["rule_bright"]

        draw.line([(72, BT), (W-72, BT)], fill=RD, width=1)
        draw.line([(72, BB), (W-72, BB)], fill=RD, width=1)
        draw.line([(72, BT), (72, BB)],   fill=RD, width=1)
        draw.line([(W-72, BT), (W-72, BB)], fill=RD, width=1)

        for (bx, by, dx, dy) in [(72,BT,1,1),(W-72,BT,-1,1),(72,BB,1,-1),(W-72,BB,-1,-1)]:
            draw.line([(bx,by),(bx+dx*28,by)], fill=RB, width=2)
            draw.line([(bx,by),(bx,by+dy*28)], fill=RB, width=2)

        for x in range(72, W-71, 36):
            draw.line([(x, BB-4), (x, BB+4)], fill=RD, width=1)

        ctext(draw, BT+18,  tag,   fnt["jura_light"], col2)
        ctext(draw, BT+56,  line1, fnt["italic_med"], col1)
        ctext(draw, BT+106, line2, fnt["serif_lg"],   col2)
        ctext(draw, BT+210, line3, fnt["italic_med"], col3)
        draw.line([(200, BB-28), (W-200, BB-28)], fill=RD, width=1)

    if hook_question:
        if not has_answer:
            # Question alone — large, attention-grabbing
            ctext(draw, HBT + 24, hook_question, fnt["serif_lg"], pal["text_bright"])
        else:
            # Question shrinks to a small label above the answer
            ctext(draw, HBT + 12, hook_question, fnt["jura_light"], pal["text_dim"])
            draw.line([(160, HBT + 44), (W - 160, HBT + 44)], fill=RD, width=1)
            # Answer dominates — large serif, wrapped, gold (same as sold price)
            ctext_wrapped(draw, HBT + 60, hook_answer, fnt["serif_med"],
                          pal["text_bright"], max_width=W - 200, line_gap=10)

    # Bottom coordinate labels
    draw.line([(72, H-220), (W-72, H-220)], fill=pal["rule_dim"], width=1)
    draw.text((86, H-200), cfg["location_coords"], font=fnt["mono"],    fill=pal["text_dim"])
    draw.text((86, H-182), cfg["location_name"],   font=fnt["mono_sm"], fill=pal["text_ghost"])
    draw.text((W-232, H-200), cfg["location_season"], font=fnt["mono"],    fill=pal["text_dim"])
    draw.text((W-200, H-182), cfg["frame_label"],     font=fnt["mono_sm"], fill=pal["text_ghost"])

    img = apply_grain(img)
    return img


def main():
    if len(sys.argv) < 2:
        print("Usage: python reel_template/make_reel.py reels/<name>")
        sys.exit(1)
    reel_dir = os.path.abspath(sys.argv[1])
    cfg = load_config(reel_dir)
    os.makedirs(cfg["output_folder"], exist_ok=True)

    print("═" * 60)
    print("  TRAVEL REEL GENERATOR")
    print(f"  Vibe: {cfg['vibe']}  |  Caption: {cfg['caption_position']}")
    print("═" * 60)

    # Load fonts
    print("\n▸ Loading fonts...")
    fnt = load_fonts(cfg["fonts_folder"], scale=cfg.get("font_scale", 1.0), overrides=cfg.get("fonts_override"))

    # Load photos
    print(f"▸ Scanning {cfg['input_folder']}...")
    photo_files = sorted([
        f for f in os.listdir(cfg["input_folder"])
        if f.lower().endswith(('.png', '.jpg', '.jpeg'))
    ])
    if not photo_files:
        print("  ✗ No PNG/JPG files found in input_folder!")
        sys.exit(1)
    print(f"  Found {len(photo_files)} photos: {', '.join(photo_files)}")

    split = cfg.get("photo_split", False)
    photos = []
    for fname in photo_files:
        p = load_photo(os.path.join(cfg["input_folder"], fname), split=split)
        photos.append((fname, grade_photo(p, PALETTES[cfg["vibe"]])))

    # ── STATIC IMAGE ──────────────────────────────────────────
    if cfg["make_image"]:
        print("\n▸ Generating static reel image...")
        hero_file = cfg["hero_photo"] or photo_files[0]
        hero_photo = dict(photos)[hero_file] if cfg["hero_photo"] else photos[0][1]
        frame = render_frame(hero_photo, cfg, fnt, show_caption=True)
        out_img = os.path.join(cfg["output_folder"], "reel.png")
        frame.save(out_img, "PNG", dpi=(300, 300))
        print(f"  ✓ Saved: {out_img}")

    # ── VIDEO ─────────────────────────────────────────────────
    if cfg["make_video"]:
        print("\n▸ Rendering video frames...")
        frames_dir = os.path.join(cfg["output_folder"], "_frames")
        os.makedirs(frames_dir, exist_ok=True)

        FPS     = cfg["fps"]
        HOLD_F  = int(cfg["hold_seconds"] * FPS)
        FADE_F  = int(cfg["fade_seconds"] * FPS)
        frame_i = 0

        always_caption  = cfg.get("caption_all_frames", False)
        per_frame_caps  = cfg.get("per_frame_captions")   # list of dicts, one per photo

        def _frame_cap(i):
            """Return (show_caption, frame_caption_dict) for photo index i."""
            if per_frame_caps:
                fc = per_frame_caps[i] if i < len(per_frame_caps) else None
                if fc is None:
                    return False, None
                # frame dict may carry its own show_caption override
                show = fc.get("show_caption", True)
                return show, fc
            show = always_caption or (i == 0)
            return show, None

        for i, (fname, photo) in enumerate(photos):
            show, fc = _frame_cap(i)
            base = render_frame(photo, cfg, fnt, show_caption=show, frame_caption=fc)

            # Per-frame hold_seconds overrides the global
            if fc and "hold_seconds" in fc:
                hold_f = int(fc["hold_seconds"] * FPS)
            else:
                hold_f = HOLD_F
            for _ in range(hold_f):
                base.save(os.path.join(frames_dir, f"f{frame_i:05d}.png"))
                frame_i += 1

            if i < len(photos) - 1:
                next_show, next_fc = _frame_cap(i + 1)
                next_base = render_frame(photos[i+1][1], cfg, fnt, show_caption=next_show, frame_caption=next_fc)
                for f in range(FADE_F):
                    t = f / FADE_F
                    blended = Image.blend(base, next_base, alpha=t)
                    blended.save(os.path.join(frames_dir, f"f{frame_i:05d}.png"))
                    frame_i += 1

            print(f"  {i+1}/{len(photos)}: {fname} → {frame_i} frames")

        # Output at 30fps minimum for platform compatibility (TikTok requires 23–60fps).
        # Internal render fps can stay low; ffmpeg duplicates frames to reach output_fps.
        OUTPUT_FPS = max(30, cfg.get("output_fps", 30))
        print(f"\n▸ Encoding MP4 ({frame_i} frames @ {FPS}fps → {OUTPUT_FPS}fps output)...")
        out_mp4 = os.path.join(cfg["output_folder"], "reel.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", os.path.join(frames_dir, "f%05d.png"),
            "-r", str(OUTPUT_FPS),
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-vf", f"scale={W}:{H}",
            out_mp4
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            size_mb = os.path.getsize(out_mp4) / 1024 / 1024
            print(f"  ✓ Saved: {out_mp4}  ({size_mb:.1f} MB)")
        else:
            print(f"  ✗ ffmpeg error:\n{result.stderr[-500:]}")

    print("\n" + "═" * 60)
    print("  DONE! Files saved to:", cfg["output_folder"])
    print("═" * 60)


if __name__ == "__main__":
    main()
