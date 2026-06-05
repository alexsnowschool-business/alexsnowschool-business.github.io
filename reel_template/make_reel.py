"""
╔══════════════════════════════════════════════════════════════╗
║           ART REEL GENERATOR — Reusable Template         ║
║  Usage: python reel_template/make_reel.py reels/<name>       ║
║  Each reel folder needs a reel_config.py with CONFIG dict.   ║
╚══════════════════════════════════════════════════════════════╝
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import glob, importlib.util, math, os, random, subprocess, sys

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

    # ── Warm Dark — high-contrast gold on near-black ─────────
    # Contemporary luxury for short-form social: vivid gold,
    # deep warm shadows, desaturated product so typography pops.
    "warm_dark": {
        "bg":           (14, 10, 6),
        "top_gradient": (14, 10, 6),
        "bot_gradient": (8,  5,  2),
        "rule_dim":     (95, 72, 38),
        "rule_bright":  (228, 188, 90),    # vivid warm gold
        "text_bright":  (255, 250, 238),   # near-white warm
        "text_dim":     (165, 130, 70),
        "text_ghost":   (82,  64,  32),
        "text_whisper": (215, 192, 145),
        "text_close":   (182, 158, 112),
        "color_sat":    0.72,              # product desaturated — type dominates
        "color_con":    1.18,              # punchy contrast
        "red_shift":    1.06,
        "blue_shift":   0.86,
        "blue_lift":    -8,
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


# ── Word-caption overlay helpers ──────────────────────────────────────────────

def _active_narration_caption(t_secs: float, captions: list) -> str | None:
    """Return the caption text active at t_secs, or None."""
    for cap in captions:
        if cap["start"] <= t_secs < cap["end"]:
            return cap["text"]
    return None


def _overlay_word_caption(img: Image.Image, text: str, caption_font) -> Image.Image:
    """Draw a word-caption box (white text, multi-script) near the bottom of img, wrapped to 2 lines."""
    out   = img.copy()
    pad   = 18
    max_w = W - 160  # 80px margin each side

    lines = wrap_text(text, caption_font, max_w)[:2]  # hard cap at 2 lines

    def _run_width(s):
        return sum(
            _MEASURE_DRAW.textbbox((0, 0), run, font=f)[2] - _MEASURE_DRAW.textbbox((0, 0), run, font=f)[0]
            for f, run in _split_runs(s, caption_font)
        )

    line_gap    = 8
    line_heights = [caption_font.getbbox(ln)[3] - caption_font.getbbox(ln)[1] for ln in lines]
    line_widths  = [_run_width(ln) for ln in lines]
    block_w = max(line_widths)
    block_h = sum(line_heights) + line_gap * (len(lines) - 1)

    box_x = (W - block_w) // 2
    box_y = H - 480

    bg = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(bg).rounded_rectangle(
        [box_x - pad, box_y - pad, box_x + block_w + pad, box_y + block_h + pad],
        radius=12, fill=(0, 0, 0, 160),
    )
    out  = Image.alpha_composite(out.convert("RGBA"), bg).convert("RGB")
    draw = ImageDraw.Draw(out)

    y = box_y
    for ln, lh in zip(lines, line_heights):
        ctext(draw, y, ln, caption_font, (255, 255, 255))
        y += lh + line_gap

    return out


# ── Unicode fallback fonts ────────────────────────────────────────────────────
# Two-tier fallback:
#   1. NotoSans-Regular.ttf (bundled) — Cyrillic, Greek, Arabic, Hebrew, etc.
#   2. CJK font — Japanese, Chinese, Korean (not bundled due to ~10 MB size)
#
# CJK font resolution order (first path that exists wins):
#   - reel_template/fonts/NotoSansCJK-Regular.ttf  (manually placed, not committed)
#   - macOS: /Library/Fonts/Arial Unicode.ttf
#   - Ubuntu/Debian CI: sudo apt-get install -y fonts-noto-cjk
#
# No code changes needed for CI — just add the apt install step.

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

_GENERAL_FALLBACK_PATH = os.path.join(_THIS_DIR, "fonts", "NotoSans-Regular.ttf")

_CJK_FONT_CANDIDATES = [
    os.path.join(_THIS_DIR, "fonts", "NotoSansCJK-Regular.ttf"),   # manually bundled
    os.path.join(_THIS_DIR, "fonts", "NotoSansSC-Regular.ttf"),
    "/Library/Fonts/Arial Unicode.ttf",                             # macOS
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",       # Ubuntu fonts-noto-cjk
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
]

_fallback_font_cache: dict = {}
_cjk_font_cache: dict = {}
_cjk_font_path: str | None = next((p for p in _CJK_FONT_CANDIDATES if os.path.exists(p)), None)


def _get_general_fallback(size: int):
    if size not in _fallback_font_cache:
        try:
            _fallback_font_cache[size] = ImageFont.truetype(_GENERAL_FALLBACK_PATH, size)
        except Exception:
            _fallback_font_cache[size] = None
    return _fallback_font_cache[size]


def _get_cjk_fallback(size: int):
    if not _cjk_font_path:
        return None
    if size not in _cjk_font_cache:
        try:
            _cjk_font_cache[size] = ImageFont.truetype(_cjk_font_path, size)
        except Exception:
            _cjk_font_cache[size] = None
    return _cjk_font_cache[size]


def _char_category(ch: str) -> str:
    """Return 'latin', 'cjk', or 'other' for font selection."""
    cp = ord(ch)
    if cp <= 0x024F:
        return "latin"
    if 0x2000 <= cp <= 0x206F:   # General Punctuation (em-dash, ellipsis, smart quotes)
        return "latin"
    if (0x3000 <= cp <= 0x9FFF   # CJK symbols, Hiragana, Katakana, unified ideographs
            or 0xAC00 <= cp <= 0xD7AF    # Hangul syllables
            or 0xF900 <= cp <= 0xFAFF):  # CJK compatibility ideographs
        return "cjk"
    return "other"


def _split_runs(text: str, primary):
    """Return list of (font, run_str) — primary for Latin, fallbacks for other scripts."""
    if not text:
        return [(primary, "")]

    def _font_for(cat: str):
        if cat == "latin":
            return primary
        if cat == "cjk":
            return _get_cjk_fallback(primary.size) or _get_general_fallback(primary.size) or primary
        return _get_general_fallback(primary.size) or _get_cjk_fallback(primary.size) or primary

    runs, cur_run = [], ""
    cur_cat = _char_category(text[0])
    for ch in text:
        cat = _char_category(ch)
        if cat != cur_cat:
            if cur_run:
                runs.append((_font_for(cur_cat), cur_run))
            cur_run, cur_cat = "", cat
        cur_run += ch
    if cur_run:
        runs.append((_font_for(cur_cat), cur_run))
    return runs


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
    runs = _split_runs(text, font)
    total_w = sum(draw.textbbox((0, 0), run, font=f)[2] - draw.textbbox((0, 0), run, font=f)[0]
                  for f, run in runs)
    x = (W - total_w) // 2
    sx = x + 2
    for f, run in runs:
        draw.text((sx, y + 3), run, font=f, fill=(0, 0, 0))
        sx += draw.textbbox((0, 0), run, font=f)[2] - draw.textbbox((0, 0), run, font=f)[0]
    tx = x
    for f, run in runs:
        draw.text((tx, y), run, font=f, fill=fill, stroke_width=1, stroke_fill=(0, 0, 0))
        tx += draw.textbbox((0, 0), run, font=f)[2] - draw.textbbox((0, 0), run, font=f)[0]

def wrap_text(text, font, max_width):
    """Split text into lines that each fit within max_width pixels."""
    def _width(s):
        return sum(
            _MEASURE_DRAW.textbbox((0, 0), run, font=f)[2] - _MEASURE_DRAW.textbbox((0, 0), run, font=f)[0]
            for f, run in _split_runs(s, font)
        )
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        if _width(test) <= max_width:
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

def load_photo(fpath, split=False, fit=False, fit_bg=(0, 0, 0), center_crop=False):
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
    dest_h = int(H * 2 / 3) if split else H

    if fit:
        # Fit within frame preserving aspect ratio; pad remaining area with fit_bg
        scale = min(W / pw, dest_h / ph)
        nw, nh = int(pw * scale), int(ph * scale)
        resized = photo.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGB", (W, dest_h), fit_bg)
        canvas.paste(resized, ((W - nw) // 2, (dest_h - nh) // 2))
        return canvas

    # Default: crop-fill to dest size
    target = W / dest_h
    ratio  = pw / ph
    if ratio > target:
        nw = int(ph * target)
        photo = photo.crop(((pw - nw) // 2, 0, (pw - nw) // 2 + nw, ph))
    else:
        nh = int(pw / target)
        top = (ph - nh) // 2 if center_crop else max(0, (ph - nh) // 4)
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
    elif position == "center":          return H // 2
    elif position == "lower_safe":      return H - 560  # BB=1608, clears bottom chrome at H-220=1700
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
        _fc_early = frame_caption or {}
        cap_pos = _fc_early.get("caption_position", cfg.get("caption_position", "upper_third"))
        bottom_cap = cap_pos in ("lower_safe", "lower_third")
        # Reduce top gradient when captions live at the bottom — let the product breathe
        if bottom_cap:
            top_px     = 180 if show_caption else 140
            top_str    = 140 if show_caption else 100
        else:
            top_px     = 420 if show_caption else 200
            top_str    = 235 if show_caption else 180
        gradient_overlay(img, pal["top_gradient"], top_px, strength=top_str)
        bot_gradient_overlay(img, pal["bot_gradient"],
                             bot_px=420 if bottom_cap else 320,
                             strength=200 if bottom_cap else 170)
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

    no_box = cfg.get("caption_no_box", False)

    BT = BB = 0
    if show_caption:
        tag   = fc.get("tag",   cfg.get("caption_tag",   ""))
        line1 = fc.get("line1", cfg.get("caption_line1", ""))
        line2 = fc.get("line2", cfg.get("caption_line2", ""))
        line3 = fc.get("line3", cfg.get("caption_line3", ""))

        col1 = tuple(fc.get("color_line1", cfg.get("color_line1", pal["text_whisper"])))
        col3 = tuple(fc.get("color_line3", cfg.get("color_line3", pal["text_close"])))
        col_tag = tuple(fc.get("color_tag", cfg.get("color_tag", col2)))

        line2_label = fc.get("line2_label", cfg.get("caption_line2_label", ""))

        cap_pos = fc.get("caption_position", cfg.get("caption_position", "upper_third"))
        BT = get_caption_y(cap_pos)
        BB = BT + (380 if line2_label else 288)

        if not no_box:
            # Drop shadow — offset rect, heavily blurred
            _SD = 10
            shadow_mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(shadow_mask).rectangle(
                [(56 + _SD, BT - 22 + _SD), (W - 56 + _SD, BB + 22 + _SD)], fill=160
            )
            shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(28))
            img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, shadow_mask)
            # Backdrop box
            backdrop      = Image.new("RGB", (W, H), (6, 5, 4))
            backdrop_mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(backdrop_mask).rectangle(
                [(56, BT - 22), (W - 56, BB + 22)], fill=190
            )
            backdrop_mask = backdrop_mask.filter(ImageFilter.GaussianBlur(16))
            img = Image.composite(backdrop, img, backdrop_mask)

    # Hook box: question only / question+answer / answer only
    HBT = HBB = 0
    _hook_answer_full = fc.get("_hook_answer_full", hook_answer)
    if hook_question:
        has_answer = bool(hook_answer)
        if has_answer:
            _ans_h = measure_wrapped_height(_hook_answer_full, fnt["serif_med"], max_width=W - 200, line_gap=10)
            HBH = 60 + _ans_h + 32
        else:
            _q_h = measure_wrapped_height(hook_question, fnt["serif_lg"], max_width=W - 200, line_gap=12)
            HBH = 24 + _q_h + 24
        HBT = (BB + 28) if show_caption else (H // 2 - HBH // 2)
        HBB = HBT + HBH
        if not no_box:
            hk_backdrop      = Image.new("RGB", (W, H), (6, 5, 4))
            hk_backdrop_mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(hk_backdrop_mask).rectangle(
                [(56, HBT - 18), (W - 56, HBB + 18)], fill=188
            )
            hk_backdrop_mask = hk_backdrop_mask.filter(ImageFilter.GaussianBlur(14))
            img = Image.composite(hk_backdrop, img, hk_backdrop_mask)
    elif hook_answer:
        # Answer only — no question label, answer fills the box
        _ans_h = measure_wrapped_height(_hook_answer_full, fnt["serif_med"], max_width=W - 200, line_gap=10)
        HBH = 24 + _ans_h + 24
        HBT = (BB + 28) if show_caption else (H // 2 - HBH // 2)
        HBB = HBT + HBH
        if not no_box:
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
        if not no_box:
            ub_back      = Image.new("RGB", (W, H), (6, 5, 4))
            ub_back_mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(ub_back_mask).rectangle(
                [(56, UBT - 16), (W - 56, UBB + 16)], fill=185
            )
            ub_back_mask = ub_back_mask.filter(ImageFilter.GaussianBlur(14))
            img = Image.composite(ub_back, img, ub_back_mask)

    draw = ImageDraw.Draw(img)

    if upper_artist or upper_title:
        if not no_box:
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
        if not no_box:
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
            draw.line([(200, BB-28), (W-200, BB-28)], fill=RD, width=1)

        ctext(draw, BT+18,  tag,   fnt["jura_light"], col_tag)
        ctext_wrapped(draw, BT+56,  line1, fnt["italic_med"], col1, max_width=W - 120)
        if line2_label:
            ctext_wrapped(draw, BT+118, line2_label, fnt["italic_med"], col1, max_width=W - 120)
            ctext_wrapped(draw, BT+196, line2, fnt["serif_lg"], col2, max_width=W - 120)
            ctext_wrapped(draw, BT+312, line3, fnt["italic_med"], col3, max_width=W - 120)
        else:
            ctext_wrapped(draw, BT+106, line2, fnt["serif_lg"],   col2, max_width=W - 120)
            ctext_wrapped(draw, BT+210, line3, fnt["italic_med"], col3, max_width=W - 120)

    if hook_question:
        if not has_answer:
            # Question alone — wrapped, large, attention-grabbing
            ctext_wrapped(draw, HBT + 24, hook_question, fnt["serif_lg"], pal["text_bright"], max_width=W - 200, line_gap=12)
        else:
            # Question shrinks to a small label above the answer
            ctext(draw, HBT + 12, hook_question, fnt["jura_light"], pal["text_dim"])
            draw.line([(160, HBT + 44), (W - 160, HBT + 44)], fill=RD, width=1)
            ctext_wrapped(draw, HBT + 60, hook_answer, fnt["serif_med"],
                          pal["text_bright"], max_width=W - 200, line_gap=10)
    elif hook_answer:
        # Answer only — no question label, fills the box cleanly
        ctext_wrapped(draw, HBT + 24, hook_answer, fnt["serif_med"],
                      pal["text_bright"], max_width=W - 200, line_gap=10)

    # Bottom coordinate labels
    if not cfg.get("hide_chrome", False):
        draw.line([(72, H-220), (W-72, H-220)], fill=pal["rule_dim"], width=1)
        draw.text((86, H-200), cfg["location_coords"], font=fnt["mono"],    fill=pal["text_dim"])
        draw.text((86, H-182), cfg["location_name"],   font=fnt["mono_sm"], fill=pal["text_ghost"])
        draw.text((W-232, H-200), cfg["location_season"], font=fnt["mono"],    fill=pal["text_dim"])
        draw.text((W-200, H-182), cfg["frame_label"],     font=fnt["mono_sm"], fill=pal["text_ghost"])

    img = apply_grain(img)
    return img


# Must match _BLOCK_REVEAL_S in scripts/auto_reel.py — both sides use 4.0s for audio timing.
BLOCK_REVEAL_DURATION = 4.0


def _render_block_reveal_frames(photo, cfg, fnt, fc, show,
                                 frames_dir, frame_i, fps=30,
                                 grid_cols=3, grid_rows=4,
                                 reveal_duration=BLOCK_REVEAL_DURATION):
    """Reveal the full painting block by block after the static Act I hold.

    Starts from a blurred/darkened version of the painting; each block is
    replaced with the crisp, graded original left-to-right, top-to-bottom.
    Returns (new frame_i, last rendered frame) so the caller can use it as
    the base for the next cross-fade.
    """
    from PIL import ImageFilter, ImageEnhance
    pw, ph = photo.size
    bw = pw // grid_cols
    bh = ph // grid_rows

    # Scale frames-per-block to hit ~reveal_duration seconds regardless of fps
    n_blocks = grid_cols * grid_rows
    frames_per_block = max(1, round(reveal_duration * fps / n_blocks))

    hidden = photo.filter(ImageFilter.GaussianBlur(radius=40))
    hidden = ImageEnhance.Brightness(hidden).enhance(0.15)

    canvas = hidden.copy()
    last_frame = None
    for row in range(grid_rows):
        for col in range(grid_cols):
            x = col * bw
            y = row * bh
            w = (pw - x) if col == grid_cols - 1 else bw
            h = (ph - y) if row == grid_rows - 1 else bh
            canvas = canvas.copy()
            canvas.paste(photo.crop((x, y, x + w, y + h)), (x, y))
            last_frame = render_frame(canvas, cfg, fnt, show_caption=show, frame_caption=fc)
            for _ in range(frames_per_block):
                last_frame.save(os.path.join(frames_dir, f"f{frame_i:05d}.png"))
                frame_i += 1

    return frame_i, last_frame


def main():
    if len(sys.argv) < 2:
        print("Usage: python reel_template/make_reel.py reels/<name>")
        sys.exit(1)
    reel_dir = os.path.abspath(sys.argv[1])
    cfg = load_config(reel_dir)
    os.makedirs(cfg["output_folder"], exist_ok=True)

    # Load voiceover timing data if present
    import json as _json
    _timing_path = os.path.join(reel_dir, "voiceover_timing.json")
    _word_timings = None   # [{"word": str, "start": float_secs}]
    _audio_offset = 0.0    # seconds to delay audio track in final MP4
    if os.path.exists(_timing_path):
        _td = _json.load(open(_timing_path))
        _audio_offset = _td.get("audio_offset", 0.0)
        _word_timings = _td.get("word_timings") or None

    print("═" * 60)
    print("REEL GENERATOR")
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

    # Group base images with their tiles/crops. Files named like <base>_tile_<size>_x_y or <base>_crop_<name>
    grouped = {}
    order = []
    for fname in photo_files:
        stem, ext = os.path.splitext(fname)
        if '_tile_' in stem:
            base = stem.split('_tile_')[0]
            grouped.setdefault(base, {'base': None, 'tiles': []})
            grouped[base]['tiles'].append(fname)
            if base not in order:
                order.append(base)
        elif '_crop_' in stem:
            base = stem.split('_crop_')[0]
            grouped.setdefault(base, {'base': None, 'tiles': []})
            grouped[base]['tiles'].append(fname)
            if base not in order:
                order.append(base)
        else:
            base = stem
            grouped.setdefault(base, {'base': None, 'tiles': []})
            grouped[base]['base'] = fname
            if base not in order:
                order.append(base)

    pal = PALETTES[cfg["vibe"]]
    _first_base_loaded = False  # Act I only: full painting fitted with padding
    for base in order:
        base_fname = grouped[base].get('base')
        tiles = grouped[base]['tiles']
        if base_fname:
            base_path = os.path.join(cfg["input_folder"], base_fname)
            use_fit = (not _first_base_loaded) and cfg.get("photo_fit_first", True)
            p = load_photo(base_path, split=split, fit=use_fit, fit_bg=pal["bg"],
                           center_crop=cfg.get("photo_center_crop", False))
            _first_base_loaded = True
            base_photo = grade_photo(p, pal)
            photos.append((base_fname, base_photo))
        else:
            if tiles:
                tpath = os.path.join(cfg["input_folder"], tiles[0])
                p = load_photo(tpath, split=split)
                photos.append((tiles[0], grade_photo(p, pal)))
                tiles = tiles[1:]
        for tname in tiles:
            tpath = os.path.join(cfg["input_folder"], tname)
            try:
                tile = Image.open(tpath).convert("RGB")
            except Exception as e:
                print(f"  ⚠ Could not open tile {tname}: {e}")
                continue
            # Determine inset size: parse tile size if present, else use fraction
            ts = None
            stem = os.path.splitext(tname)[0]
            parts = stem.split('_')
            if 'tile' in parts:
                idx = parts.index('tile')
                if idx + 1 < len(parts):
                    try:
                        ts = int(parts[idx+1])
                    except:
                        ts = None
            inset_w = int(W * cfg.get("tile_inset_fraction", 0.55))
            if ts:
                inset_w = min(inset_w, ts * 3)
            tile = tile.resize((inset_w, inset_w), Image.LANCZOS)
            border = max(6, inset_w // 30)
            inset_bg = Image.new('RGB', (inset_w + border*2, inset_w + border*2), (255,255,255))
            inset_bg.paste(tile, (border, border))
            if base_fname:
                comp = base_photo.copy()
            else:
                comp = Image.new('RGB', (W, H), pal['bg'])
            margin = 72
            x = W - inset_bg.width - margin
            y = margin
            comp.paste(inset_bg, (x, y))
            photos.append((tname, comp))

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

        prev_hook_answer_words = []  # track words already revealed in prior frame

        for i, (fname, photo) in enumerate(photos):
            show, fc = _frame_cap(i)

            # Determine hold in frames and seconds
            if fc and "hold_seconds" in fc:
                hold_seconds = fc["hold_seconds"]
                hold_f = int(hold_seconds * FPS)
            else:
                hold_seconds = cfg["hold_seconds"]
                hold_f = HOLD_F

            hook_answer_text = (fc or {}).get("hook_answer", "")
            all_words = hook_answer_text.split() if hook_answer_text else []
            act2_offset = (fc or {}).get("act2_audio_offset", None)

            if act2_offset is not None and all_words and hold_f > 0:
                # Act II multi-frame: reveal appreciation words by global VO timestamp.
                # act2_offset = seconds into tts_appreciation.mp3 when this crop starts.
                for k in range(hold_f):
                    t_secs = k / FPS + act2_offset
                    if _word_timings:
                        n_shown = max(0, min(len(all_words),
                                            sum(1 for wt in _word_timings if wt["start"] <= t_secs)))
                    else:
                        n_shown = len(all_words)
                    partial_fc = dict(fc) if fc else {}
                    partial_fc["hook_answer"] = " ".join(all_words[:n_shown])
                    partial_fc["_hook_answer_full"] = hook_answer_text
                    base = render_frame(photo, cfg, fnt, show_caption=show, frame_caption=partial_fc)
                    base.save(os.path.join(frames_dir, f"f{frame_i:05d}.png"))
                    frame_i += 1
            else:
                # Determine which words are genuinely NEW in this frame (continuation detection)
                prev_n = len(prev_hook_answer_words)
                is_continuation = (
                    len(all_words) > prev_n and
                    all_words[:prev_n] == prev_hook_answer_words
                )
                new_words = all_words[prev_n:] if is_continuation else all_words
                carried_text = " ".join(all_words[:prev_n]) if is_continuation else ""

                if new_words and hold_f > 1:
                    # Reveal new words: driven by TTS timestamps when available, else 2 frames/word
                    FRAMES_PER_WORD = 2
                    base = None
                    for k in range(hold_f):
                        if _word_timings:
                            t_secs = k / FPS
                            n_new = sum(1 for wt in _word_timings if wt["start"] <= t_secs)
                            n_new = max(1, min(len(new_words), n_new))
                        else:
                            n_new = max(1, min(len(new_words), k // FRAMES_PER_WORD + 1))
                        partial_answer = (carried_text + " " + " ".join(new_words[:n_new])).strip()
                        partial_fc = dict(fc) if fc else {}
                        partial_fc["hook_answer"] = partial_answer
                        partial_fc["_hook_answer_full"] = hook_answer_text
                        frame = render_frame(photo, cfg, fnt, show_caption=show, frame_caption=partial_fc)
                        frame.save(os.path.join(frames_dir, f"f{frame_i:05d}.png"))
                        frame_i += 1
                        base = frame
                else:
                    base = render_frame(photo, cfg, fnt, show_caption=show, frame_caption=fc)
                    for _ in range(hold_f):
                        base.save(os.path.join(frames_dir, f"f{frame_i:05d}.png"))
                        frame_i += 1

            # Act I only: block-by-block reveal (disable with block_reveal: False in config)
            if i == 0 and cfg.get("block_reveal", True):
                frame_i, base = _render_block_reveal_frames(
                    photo, cfg, fnt, fc, show, frames_dir, frame_i, fps=FPS
                )

            prev_hook_answer_words = all_words  # advance cursor for next frame

            if i < len(photos) - 1:
                next_show, next_fc = _frame_cap(i + 1)
                next_base = render_frame(photos[i+1][1], cfg, fnt, show_caption=next_show, frame_caption=next_fc)
                for f in range(FADE_F):
                    t = f / FADE_F
                    blended = Image.blend(base, next_base, alpha=t)
                    blended.save(os.path.join(frames_dir, f"f{frame_i:05d}.png"))
                    frame_i += 1

            print(f"  {i+1}/{len(photos)}: {fname} → {frame_i} frames")

        # ── Narration caption overlay ──────────────────────────
        narration_captions = cfg.get("narration_captions", [])
        if narration_captions:
            print("\n▸ Overlaying word-by-word captions on frames...")
            cap_fnt = fnt.get("serif_med") or fnt.get("italic_med") or fnt.get("jura_light")
            frame_files = sorted(glob.glob(os.path.join(frames_dir, "f*.png")))
            overlaid = 0
            for fpath in frame_files:
                num    = int(os.path.splitext(os.path.basename(fpath))[0][1:])
                t_secs = num / FPS
                text   = _active_narration_caption(t_secs, narration_captions)
                if text:
                    img = Image.open(fpath)
                    img = _overlay_word_caption(img, text, cap_fnt)
                    img.save(fpath)
                    overlaid += 1
            print(f"  ✓ Captioned {overlaid}/{len(frame_files)} frames")

        # Output at 30fps minimum for platform compatibility (TikTok requires 23–60fps).
        # Internal render fps can stay low; ffmpeg duplicates frames to reach output_fps.
        OUTPUT_FPS = max(30, cfg.get("output_fps", 30))
        print(f"\n▸ Encoding MP4 ({frame_i} frames @ {FPS}fps → {OUTPUT_FPS}fps output)...")
        out_mp4 = os.path.join(cfg["output_folder"], "reel.mp4")

        # Mix in voiceover if present in the reel directory
        voiceover_path = os.path.join(reel_dir, "voiceover.mp3")
        has_audio = os.path.exists(voiceover_path)

        if has_audio:
            print(f"  ♪ Mixing voiceover (offset {_audio_offset:.1f}s): voiceover.mp3")
            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(FPS),
                "-i", os.path.join(frames_dir, "f%05d.png"),
                "-itsoffset", str(_audio_offset),
                "-i", voiceover_path,
                "-r", str(OUTPUT_FPS),
                "-c:v", "libx264",
                "-preset", "slow",
                "-crf", "18",
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-vf", f"scale={W}:{H}",
                out_mp4
            ]
        else:
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
