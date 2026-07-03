#!/usr/bin/env python3
"""
Static image cards for the "Beat the Estimate" Instagram/TikTok carousel —
no video. One cover card + one card per featured lot, sized 1080x1350
(4:5 portrait — works for an Instagram carousel post and a TikTok photo post).

Visual language matches the existing reel pipeline's "auction_editorial"
palette (reel_template/make_reel.py) and font pairing (Italiana headline +
CrimsonPro body) so this reads as the same brand, just a still format.

Usage (as a library):
    from beat_the_estimate_cards import render_cards
    paths = render_cards(lots, sections, out_dir)

Not meant to be run standalone — called from beat_the_estimate.py.
"""

import re
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

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


def _draw_centered(draw: ImageDraw.ImageDraw, y: int, text: str, font: ImageFont.FreeTypeFont, fill, letter_spacing: int = 0) -> int:
    """Draw a single line centered horizontally; returns the y just below it."""
    if letter_spacing:
        widths = [draw.textlength(ch, font=font) for ch in text]
        total = sum(widths) + letter_spacing * (len(text) - 1)
        x = (W - total) / 2
        for ch, w in zip(text, widths):
            draw.text((x, y), ch, font=font, fill=fill)
            x += w + letter_spacing
        bbox = font.getbbox("Hg")
        return y + (bbox[3] - bbox[1]) + 10
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) / 2, y), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1]) + 10


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


def _mosaic(lots: list[dict], w: int, h: int, max_tiles: int = 4) -> Image.Image:
    """Tile up to `max_tiles` lot photos side by side, crop-filled to equal-width columns."""
    canvas = Image.new("RGB", (w, h), (30, 27, 24))
    photos = [p for p in (_download_photo(_first_image_url(lot)) for lot in lots[:max_tiles]) if p]
    if not photos:
        return canvas

    tile_w = w // len(photos)
    x = 0
    for i, photo in enumerate(photos):
        this_w = w - x if i == len(photos) - 1 else tile_w  # last tile absorbs rounding remainder
        canvas.paste(_crop_fill(photo, this_w, h), (x, 0))
        x += this_w
    return canvas


def render_cover_card(title: str, subtitle: str, date_str: str, count: int, lots: list[dict]) -> Image.Image:
    img  = Image.new("RGB", (W, H), BG)

    photo_h = 520
    mosaic = _mosaic(lots, W, photo_h)
    img.paste(mosaic, (0, 0))

    # Dark gradient fade from the mosaic into the solid background so the
    # photos read as a teaser rather than competing with the masthead text.
    fade_h = 160
    fade = Image.new("RGB", (W, fade_h), BG)
    mask = Image.new("L", (W, fade_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    for row in range(fade_h):
        mask_draw.line([(0, row), (W, row)], fill=int(255 * row / fade_h))
    img.paste(fade, (0, photo_h - fade_h), mask)

    draw = ImageDraw.Draw(img)
    draw.rectangle([0, photo_h, W, photo_h + 4], fill=GOLD)
    draw.rectangle([MARGIN, photo_h + 40, W - MARGIN, H - MARGIN], outline=GOLD_DIM, width=2)

    y = photo_h + 90
    y = _draw_centered(draw, y, "THE HAMMER PRICE", _font("CrimsonPro-Regular.ttf", 26), IVORY_DIM, letter_spacing=6)
    y += 34

    y = _draw_centered(draw, y, "BEAT THE ESTIMATE", _font("Italiana-Regular.ttf", 56), IVORY)
    y += 26

    body_font = _font("CrimsonPro-Italic.ttf", 30)
    for line in _wrap(draw, subtitle, body_font, W - MARGIN * 2 - 80):
        y = _draw_centered(draw, y, line, body_font, IVORY_DIM)
    y += 44

    draw.line([(W // 2 - 60, y), (W // 2 + 60, y)], fill=GOLD, width=2)
    y += 36

    _draw_centered(draw, y, f"{count} RESULTS  ·  {date_str}", _font("CrimsonPro-Regular.ttf", 24), GOLD, letter_spacing=3)

    return img


def render_lot_card(lot: dict, rank: int, blurb: str) -> Image.Image:
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    photo_h = 760
    photo = _download_photo(_first_image_url(lot))
    if photo:
        photo = _crop_fill(photo, W, photo_h)
        img.paste(photo, (0, 0))
    else:
        draw.rectangle([0, 0, W, photo_h], fill=(30, 27, 24))

    draw.rectangle([0, photo_h, W, photo_h + 4], fill=GOLD)

    y = photo_h + 36
    draw.text((MARGIN, y), f"{rank:02d}", font=_font("CrimsonPro-Regular.ttf", 22), fill=GOLD_DIM)
    y += 40

    artist_font = _font("Italiana-Regular.ttf", 46)
    artist = (lot.get("artist") or "Unknown").upper()
    for line in _wrap(draw, artist, artist_font, W - MARGIN * 2):
        draw.text((MARGIN, y), line, font=artist_font, fill=IVORY)
        bbox = draw.textbbox((0, 0), line, font=artist_font)
        y += (bbox[3] - bbox[1]) + 8
    y += 6

    title_font = _font("CrimsonPro-Italic.ttf", 32)
    title = lot.get("title") or "Untitled"
    for line in _wrap(draw, title, title_font, W - MARGIN * 2)[:2]:
        draw.text((MARGIN, y), line, font=title_font, fill=IVORY_DIM)
        bbox = draw.textbbox((0, 0), line, font=title_font)
        y += (bbox[3] - bbox[1]) + 6
    y += 20

    pct = lot.get("pct_above", 0)
    pct_font = _font("Italiana-Regular.ttf", 52)
    draw.text((MARGIN, y), f"+{pct:.0f}% ABOVE ESTIMATE", font=pct_font, fill=GOLD)
    bbox = draw.textbbox((0, 0), f"+{pct:.0f}% ABOVE ESTIMATE", font=pct_font)
    y += (bbox[3] - bbox[1]) + 20

    detail_font = _font("CrimsonPro-Regular.ttf", 26)
    house  = lot.get("auction_house", "")
    hammer = f"${lot.get('hammer_usd', 0):,.0f}"
    est_lo = f"${lot.get('estimate_low', 0):,.0f}"
    est_hi = f"${(lot.get('estimate_high') or lot.get('estimate_low', 0)):,.0f}"
    draw.text((MARGIN, y), f"{house}  ·  est. {est_lo}–{est_hi}  ·  hammer {hammer}", font=detail_font, fill=IVORY_DIM)
    y += 50

    if blurb:
        draw.line([(MARGIN, y), (MARGIN + 60, y)], fill=GOLD_DIM, width=2)
        y += 30
        blurb_font  = _font("CrimsonPro-Regular.ttf", 27)
        max_lines   = (H - MARGIN - y) // 42
        all_lines   = _wrap(draw, blurb, blurb_font, W - MARGIN * 2)
        lines       = all_lines[:max_lines]
        if len(all_lines) > max_lines and lines:
            lines[-1] = lines[-1].rstrip(".,;:") + "…"
        for line in lines:
            draw.text((MARGIN, y), line, font=blurb_font, fill=IVORY_DIM)
            y += 42

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


def render_cards(lots: list[dict], sections: dict, out_dir: Path) -> list[Path]:
    """Render one cover card + one card per lot. Returns saved file paths in post order."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    from datetime import date
    cover = render_cover_card(
        title=sections.get("title", ""),
        subtitle=sections.get("subtitle", ""),
        date_str=date.today().strftime("%b %-d, %Y"),
        count=len(lots),
        lots=lots,
    )
    cover_path = out_dir / "00_cover.png"
    cover.save(cover_path)
    paths.append(cover_path)

    blurbs = sections.get("blurbs") or [""] * len(lots)
    for i, (lot, blurb) in enumerate(zip(lots, blurbs), start=1):
        card = render_lot_card(lot, i, blurb)
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
