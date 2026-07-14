#!/usr/bin/env python3
"""
Static image cards for the "Beat the Estimate" Instagram/TikTok carousel —
no video. One cover card + one card per featured lot, sized 1080x1350
(4:5 portrait — works for an Instagram carousel post and a TikTok photo post).

Cover card is a full-bleed grid mosaic of every featured lot's photo, with
a bottom gradient and bold sans caps overlay — the punchy Instagram-
carousel look. Per-lot cards share the same Outfit-Bold/Regular pairing
(bold caps artist name, regular everything else) on the existing reel
pipeline's "auction_editorial" gold-on-black palette
(reel_template/make_reel.py), so the whole carousel reads as one set.

Usage (as a library):
    from beat_the_estimate_cards import render_cards
    paths = render_cards(lots, sections, out_dir)

Not meant to be run standalone — called from beat_the_estimate.py.
"""

import random
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

_COVER_HOOKS = [
    "Guess what they paid",
    "Can you guess the price?",
    "Guess the hammer price",
    "What did collectors pay?",
    "Guess what this sold for",
    "Can you guess what it fetched?",
    "What price did this go for?",
    "Guess the sale price",
]

FONTS_DIR = Path(__file__).resolve().parent.parent / "reel_template" / "fonts"

W, H = 1080, 1350

# "auction_editorial" palette (reel_template/make_reel.py) — brand gold on near-black.
BG          = (20, 18, 16)
GOLD        = (201, 168, 76)     # brand gold #C9A84C
GOLD_DIM    = (100, 82, 45)
IVORY       = (245, 240, 232)    # #F5F0E8
IVORY_DIM   = (185, 165, 130)

MARGIN = 72

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONTS_DIR / name), size)
    return _font_cache[key]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _crop_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    """Crop-to-fill: scale + center-crop so `img` exactly covers a w x h box."""
    iw, ih = img.size
    target = w / h
    ratio  = iw / ih
    if ratio > target:
        nw = int(ih * target)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = int(iw / target)
        top = max(0, (ih - nh) // 3)  # bias slightly upward — most auction photos center the work above dead center
        img = img.crop((0, top, iw, top + nh))
    return img.resize((w, h), Image.LANCZOS)


def _download_photo(url: str | None) -> Image.Image | None:
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"  ⚠ image download failed ({url[:60]}...): {e}")
        return None


def _fit_caps_lines(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, font_name: str,
    start_size: int, min_size: int, max_lines: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Pick the largest size (within start/min) whose wrapped text fits max_lines."""
    size = start_size
    while size >= min_size:
        font  = _font(font_name, size)
        lines = _wrap(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
        size -= 4
    return font, lines


def _full_bleed_mosaic(lots: list[dict], w: int, h: int) -> Image.Image:
    """Tile every featured lot's photo into a grid that fills the whole w x h canvas."""
    canvas = Image.new("RGB", (w, h), (30, 27, 24))
    photos = [p for p in (_download_photo(_first_image_url(lot)) for lot in lots) if p]
    if not photos:
        return canvas

    cols = 1 if len(photos) == 1 else 2
    rows = -(-len(photos) // cols)  # ceil division

    for i, photo in enumerate(photos):
        col, row = i % cols, i // cols
        x0 = (col * w) // cols
        x1 = ((col + 1) * w) // cols
        y0 = (row * h) // rows
        y1 = ((row + 1) * h) // rows
        canvas.paste(_crop_fill(photo, x1 - x0, y1 - y0), (x0, y0))

    return canvas


def render_cover_card(title: str, subtitle: str, date_str: str, count: int, lots: list[dict]) -> Image.Image:  # noqa: ARG001 — title/subtitle replaced by hook
    img = _full_bleed_mosaic(lots, W, H) if lots else Image.new("RGB", (W, H), (30, 27, 24))

    # Bottom gradient so headline text stays legible over a bright/busy painting,
    # without darkening the top of the artwork where the composition reads best.
    fade_top = int(H * 0.42)
    fade_h   = H - fade_top
    fade = Image.new("RGB", (W, fade_h), (8, 7, 6))
    mask = Image.new("L", (W, fade_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    for row in range(fade_h):
        alpha = int(235 * (row / fade_h) ** 1.4)
        mask_draw.line([(0, row), (W, row)], fill=alpha)
    img.paste(fade, (0, fade_top), mask)

    draw = ImageDraw.Draw(img)
    content_w = W - MARGIN * 2

    # Solid backdrop behind the kicker label — a gradient scrim isn't reliable
    # contrast against a mosaic where tile brightness varies tile to tile.
    kicker_font = _font("Outfit-Regular.ttf", 24)
    kicker_text = "The Hammer Price"
    kicker_bbox = draw.textbbox((0, 0), kicker_text, font=kicker_font)
    pad_x, pad_y = 20, 12
    draw.rectangle(
        [
            MARGIN - pad_x, MARGIN - pad_y,
            MARGIN + (kicker_bbox[2] - kicker_bbox[0]) + pad_x,
            MARGIN + (kicker_bbox[3] - kicker_bbox[1]) + pad_y,
        ],
        fill=(8, 7, 6),
    )
    draw.text((MARGIN, MARGIN), kicker_text, font=kicker_font, fill=GOLD)

    hook = random.choice(_COVER_HOOKS).capitalize()
    title_font, title_lines = _fit_caps_lines(
        draw, hook, content_w, "Outfit-Bold.ttf", start_size=88, min_size=48, max_lines=4,
    )
    meta_font = _font("Outfit-Regular.ttf", 24)

    title_bbox   = title_font.getbbox("Hg")
    title_line_h = int((title_bbox[3] - title_bbox[1]) * 1.12)

    block_h = title_line_h * len(title_lines) + 24 + 30  # meta line
    y = H - MARGIN - block_h

    for line in title_lines:
        draw.text((MARGIN, y), line, font=title_font, fill=IVORY)
        y += title_line_h
    y += 24

    draw.text((MARGIN, y), f"{count} results  ·  {date_str}", font=meta_font, fill=GOLD)

    return img


def render_lot_card(lot: dict, rank: int) -> Image.Image:
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    photo_h = 1080
    photo = _download_photo(_first_image_url(lot))
    if photo:
        photo = _crop_fill(photo, W, photo_h)
        img.paste(photo, (0, 0))
    else:
        draw.rectangle([0, 0, W, photo_h], fill=(30, 27, 24))

    draw.rectangle([0, photo_h, W, photo_h + 4], fill=GOLD)

    y = photo_h + 20
    draw.text((MARGIN, y), f"{rank:02d}", font=_font("Outfit-Regular.ttf", 22), fill=GOLD_DIM)
    y += 36

    artist_font = _font("Outfit-Bold.ttf", 40)
    artist = lot.get("artist") or "Unknown"
    for line in _wrap(draw, artist, artist_font, W - MARGIN * 2)[:1]:
        draw.text((MARGIN, y), line, font=artist_font, fill=IVORY)
        bbox = draw.textbbox((0, 0), line, font=artist_font)
        y += (bbox[3] - bbox[1]) + 6
    y += 4

    title_font = _font("Outfit-Regular.ttf", 26)
    title = lot.get("title") or "Untitled"
    for line in _wrap(draw, title, title_font, W - MARGIN * 2)[:1]:
        draw.text((MARGIN, y), line, font=title_font, fill=IVORY_DIM)
        bbox = draw.textbbox((0, 0), line, font=title_font)
        y += (bbox[3] - bbox[1]) + 4
    y += 14

    detail_font = _font("Outfit-Regular.ttf", 23)
    est_lo = f"${lot.get('estimate_low', 0):,.0f}"
    est_hi = f"${(lot.get('estimate_high') or lot.get('estimate_low', 0)):,.0f}"
    draw.text((MARGIN, y), f"Estimate  {est_lo}–{est_hi}", font=detail_font, fill=IVORY_DIM)
    bbox = draw.textbbox((0, 0), f"Estimate  {est_lo}–{est_hi}", font=detail_font)
    y += (bbox[3] - bbox[1]) + 14

    hammer = f"${lot.get('hammer_usd', 0):,.0f}"
    sold_font = _font("Outfit-Bold.ttf", 44)
    draw.text((MARGIN, y), f"Sold for  {hammer}", font=sold_font, fill=GOLD)

    return img


def _first_image_url(lot: dict) -> str | None:
    """Handle both a raw JSON string (from a DB row) and an already-parsed list."""
    raw = lot.get("image_urls")
    if isinstance(raw, list):
        return raw[0] if raw else None
    if isinstance(raw, str):
        import json
        try:
            urls = json.loads(raw)
            return urls[0] if urls else None
        except (TypeError, ValueError):
            return None
    return None


def render_cards(
    lots: list[dict], sections: dict, out_dir: Path, start_date: str | None = None,
) -> list[Path]:
    """Render one cover card + one card per lot. Returns saved file paths in post order.

    `start_date` ("YYYY-MM-DD") is the explicit eligibility cutoff passed to
    beat_the_estimate.py's --start-date, if any — shown on the cover instead
    of just today's date, so a card generated from an older cutoff doesn't
    read as "this week" when it isn't.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    from datetime import date, datetime
    if start_date:
        cutoff = datetime.strptime(start_date, "%Y-%m-%d").strftime("%b %-d, %Y")
        date_str = f"Since {cutoff}"
    else:
        date_str = date.today().strftime("%b %-d, %Y")

    cover = render_cover_card(
        title=sections.get("title", ""),
        subtitle=sections.get("subtitle", ""),
        date_str=date_str,
        count=len(lots),
        lots=lots,
    )
    cover_path = out_dir / "00_cover.png"
    cover.save(cover_path)
    paths.append(cover_path)

    for i, lot in enumerate(lots, start=1):
        card = render_lot_card(lot, i)
        card_path = out_dir / f"{i:02d}_lot.png"
        card.save(card_path)
        paths.append(card_path)

    import json
    meta = {
        "title": sections.get("title", ""),
        "subtitle": sections.get("subtitle", ""),
        "lots": [
            {
                "id": lot.get("id"),
                "artist": lot.get("artist"),
                "title": lot.get("title"),
                "auction_house": lot.get("auction_house"),
                "pct_above": lot.get("pct_above"),
            }
            for lot in lots
        ],
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return paths
