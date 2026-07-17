#!/usr/bin/env python3
"""
Artist life story carousel — full-bleed painting, bottom gradient scrim, text overlay.

Card sequence:
  1. Cover    — artist portrait, name, dates, movement
  2. Bio      — life story excerpt
  3. Work I   — famous artwork, title, year
  4. Work II  — famous artwork, title, year
  5. Work III — famous artwork, title, year
  6. Quote    — artist quote

Usage:
    python scripts/artist_story_cards.py
    python scripts/artist_story_cards.py "Marc Chagall"
    python scripts/artist_story_cards.py --force
"""

import argparse
import io
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent
FONTS_DIR    = BUSINESS_DIR / "reel_template" / "fonts"
OUTPUT_DIR   = BUSINESS_DIR / "output" / "artist_cards"
sys.path.insert(0, str(SCRIPT_DIR))

from quote_reel import pick_art_image_url, download_image, _palette  # noqa: E402

W, H   = 1080, 1350
MARGIN = 72

GOLD      = (201, 168, 76)
IVORY     = (245, 240, 232)
IVORY_DIM = (185, 165, 130)
BLACK     = (0,   0,   0)

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONTS_DIR / name), size)
    return _font_cache[key]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
          max_width: int) -> list[str]:
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


def _fit_contain(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale painting to fit entirely within the frame; fill remaining space with dark background."""
    iw, ih = img.size
    scale  = min(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    resized = img.resize((nw, nh), Image.LANCZOS)
    canvas  = Image.new("RGB", (w, h), (18, 15, 12))
    canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2))
    return canvas


def _bottom_scrim(img: Image.Image, scrim_start: float = 0.45,
                  max_alpha: int = 210) -> Image.Image:
    img   = img.convert("RGBA")
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(scrim)
    top_y = int(H * scrim_start)
    for y in range(top_y, H):
        t     = (y - top_y) / (H - top_y)
        alpha = int(max_alpha * (t ** 1.6))
        draw.line([(0, y), (W, y)], fill=(8, 6, 4, alpha))
    return Image.alpha_composite(img, scrim)


def _shadow(draw: ImageDraw.ImageDraw, xy, text, font, fill, shadow_alpha=150):
    draw.text((xy[0] + 2, xy[1] + 3), text, font=font, fill=(*BLACK, shadow_alpha))
    draw.text(xy, text, font=font, fill=fill)


def _base_card(photo: Image.Image, scrim_start: float = 0.45) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    filled = _fit_contain(photo.convert("RGB"), W, H)
    card   = _bottom_scrim(filled, scrim_start=scrim_start)
    return card, ImageDraw.Draw(card, "RGBA")


# ── Card renderers ────────────────────────────────────────────────────────────

def render_cover(photo: Image.Image, profile: dict, index: int, total: int) -> Image.Image:
    card, draw = _base_card(photo, scrim_start=0.38)
    content_w  = W - MARGIN * 2

    _shadow(draw, (MARGIN, MARGIN), f"{index:02d} / {total}",
            _font("Outfit-Bold.ttf", 24), (*GOLD, 200))

    y = H - MARGIN

    nat = profile.get("nationality", "")
    mvt = profile.get("art_movement", "")
    sub = "  ·  ".join(p for p in [nat, mvt] if p)
    if sub:
        f   = _font("Outfit-Bold.ttf", 26)
        y  -= f.getbbox("Hg")[3] + 4
        _shadow(draw, (MARGIN, y), sub, f, (*GOLD, 230))

    birth = profile.get("birth_date", "")
    death = profile.get("death_date", "")

    def _parse_date(s: str) -> date | None:
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y"):
            try:
                return date(*__import__("time").strptime(s.strip(), fmt)[:3])
            except (ValueError, TypeError):
                pass
        return None

    bd, dd = _parse_date(birth), _parse_date(death)
    age_str = ""
    if bd:
        end = dd if dd else date.today()
        age = end.year - bd.year - ((end.month, end.day) < (bd.month, bd.day))
        age_str = f"  ·  {age} years"

    dates = f"{birth} – {death}" if death else (f"b. {birth}" if birth else "")
    if dates:
        f   = _font("Outfit-Bold.ttf", 28)
        y  -= f.getbbox("Hg")[3] + 16
        _shadow(draw, (MARGIN, y), dates + age_str, f, (*IVORY_DIM, 240))

    name       = profile.get("full_name") or profile.get("artist_name", "")
    n_font     = _font("Outfit-Bold.ttf", 72)
    name_lines = _wrap(draw, name, n_font, content_w)[:2]
    line_h     = n_font.getbbox("Hg")[3] + 8
    y         -= line_h * len(name_lines) + 20
    for line in name_lines:
        _shadow(draw, (MARGIN, y), line, n_font, (*IVORY, 255))
        y += line_h

    return card.convert("RGB")


def _bio_timeline(profile: dict) -> list[tuple[str, str]]:
    """Return (year, description) pairs — Wikipedia timeline preferred, bio text as fallback."""
    wiki = profile.get("timeline", [])
    if wiki:
        return [(str(e["year"]), e["event"]) for e in wiki[:6]]

    # Fallback: extract from GAC bio text
    bio        = profile.get("bio", "")
    birth_date = profile.get("birth_date", "")
    death_date = profile.get("death_date", "")
    events: dict[int, str] = {}

    m = re.search(r"\b(\d{4})\b", birth_date)
    if m:
        events[int(m.group(1))] = f"Born, {birth_date}"
    m = re.search(r"\b(\d{4})\b", death_date)
    if m:
        events[int(m.group(1))] = f"Died, {death_date}"

    for sent in re.split(r"(?<=[.!?])\s+", bio):
        m = re.search(r"\b(1[5-9]\d{2}|20[0-2]\d)\b", sent)
        if not m:
            continue
        year = int(m.group(1))
        if year in events:
            continue
        clean = re.sub(r"^(He|She|They)\s+", "", sent).strip()
        clean = re.sub(r"\s+", " ", clean)
        if len(clean) > 68:
            clean = clean[:65].rsplit(" ", 1)[0] + "…"
        events[year] = clean

    return sorted(events.items())[:6]


def render_bio(photo: Image.Image, profile: dict, index: int, total: int) -> Image.Image:
    card, draw = _base_card(photo, scrim_start=0.25)
    content_w  = W - MARGIN * 2

    _shadow(draw, (MARGIN, MARGIN), f"{index:02d} / {total}",
            _font("Outfit-Bold.ttf", 24), (*GOLD, 200))
    _shadow(draw, (MARGIN, MARGIN + 44), "TIMELINE",
            _font("Outfit-Bold.ttf", 22), (*GOLD, 180))

    events    = _bio_timeline(profile)
    year_font = _font("Outfit-Bold.ttf", 34)
    evt_font  = _font("Outfit-Regular.ttf", 28)
    year_h    = year_font.getbbox("Hg")[3]
    evt_h     = evt_font.getbbox("Hg")[3]
    row_h     = year_h + evt_h + 18   # gap between event rows

    total_h = row_h * len(events)
    y       = H - MARGIN - total_h

    for year, desc in events:
        _shadow(draw, (MARGIN, y), str(year), year_font, (*GOLD, 240))
        _shadow(draw, (MARGIN, y + year_h + 4), desc, evt_font, (*IVORY, 230))
        y += row_h

    return card.convert("RGB")


def render_artwork(photo: Image.Image, artwork, index: int, total: int) -> Image.Image:
    card, draw = _base_card(photo, scrim_start=0.52)
    content_w  = W - MARGIN * 2

    _shadow(draw, (MARGIN, MARGIN), f"{index:02d} / {total}",
            _font("Outfit-Bold.ttf", 24), (*GOLD, 200))
    _shadow(draw, (MARGIN, MARGIN + 44), "FAMOUS WORK",
            _font("Outfit-Bold.ttf", 22), (*GOLD, 180))

    raw   = artwork.get("title", "") if isinstance(artwork, dict) else str(artwork)
    m     = re.match(r"^(.+?)\s*\((\d{4})\)$", raw)
    title = m.group(1).strip() if m else raw
    year  = m.group(2) if m else ""

    title_font  = _font("Outfit-Bold.ttf", 52)
    year_font   = _font("Outfit-Bold.ttf", 30)
    title_lines = _wrap(draw, title, title_font, content_w)[:2]
    line_h      = title_font.getbbox("Hg")[3] + 8
    year_h      = year_font.getbbox("Hg")[3]

    y_year  = H - MARGIN - year_h
    y_title = y_year - 18 - line_h * len(title_lines)
    y       = y_title
    for line in title_lines:
        _shadow(draw, (MARGIN, y), line, title_font, (*IVORY, 255))
        y += line_h
    if year:
        _shadow(draw, (MARGIN, y_year), year, year_font, (*GOLD, 230))

    return card.convert("RGB")


def render_quote(photo: Image.Image, profile: dict, index: int, total: int) -> Image.Image:
    card, draw = _base_card(photo, scrim_start=0.28)
    content_w  = W - MARGIN * 2

    _shadow(draw, (MARGIN, MARGIN), f"{index:02d} / {total}",
            _font("Outfit-Bold.ttf", 24), (*GOLD, 200))
    _shadow(draw, (MARGIN, MARGIN + 44), "IN THEIR WORDS",
            _font("Outfit-Bold.ttf", 22), (*GOLD, 180))

    quote     = profile.get("quote", "")
    name      = profile.get("full_name") or profile.get("artist_name", "")
    q_font    = _font("Lora-Italic.ttf", 36)
    attr_font = _font("Outfit-Bold.ttf", 26)
    lines     = _wrap(draw, f'"{quote}"', q_font, content_w)[:5]
    line_h    = q_font.getbbox("Hg")[3] + 10
    attr_h    = attr_font.getbbox("Hg")[3]

    y_attr  = H - MARGIN - attr_h
    y_quote = y_attr - 18 - line_h * len(lines)
    y       = y_quote
    for line in lines:
        _shadow(draw, (MARGIN, y), line, q_font, (*IVORY, 248))
        y += line_h
    _shadow(draw, (MARGIN, y_attr), f"— {name}", attr_font, (*GOLD, 220))

    return card.convert("RGB")


# ── Image helpers ─────────────────────────────────────────────────────────────

def _fetch_artwork_image(artwork: dict) -> Image.Image | None:
    for url_key in ("ext_url", "image_url"):
        url = artwork.get(url_key, "")
        if not url:
            continue
        try:
            r = requests.get(url, headers=_FETCH_HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            if "text/html" in r.headers.get("content-type", ""):
                m = re.search(r'<meta property="og:image" content="([^"]+)"', r.text)
                if not m:
                    continue
                img_r = requests.get(m.group(1), headers=_FETCH_HEADERS, timeout=15)
                img_r.raise_for_status()
                return Image.open(io.BytesIO(img_r.content)).convert("RGB")
            return Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception as e:
            print(f"  [warn] image fetch failed ({url_key}): {e}")
    return None


def _painting_bg(art_conn: sqlite3.Connection, used_urls: set[str],
                 palette: dict) -> Image.Image:
    for _ in range(15):
        result = pick_art_image_url(art_conn, only_paintings=True)
        if result and result[0] not in used_urls:
            url, _, _ = result
            used_urls.add(url)
            img = download_image(url)
            if img:
                return img
    return Image.new("RGB", (W, H), (30, 27, 24))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artist", nargs="?", help="Artist name")
    parser.add_argument("--force", action="store_true", help="Re-fetch profile")
    parser.add_argument("--account", default="lifequoteshere")
    args = parser.parse_args()

    if args.artist:
        artist_name = args.artist
    else:
        result = subprocess.run(
            ["python3", "scripts/campaign_artist.py"],
            capture_output=True, text=True, cwd=BUSINESS_DIR,
        )
        artist_name = result.stdout.strip()
        if not artist_name:
            print("Could not determine campaign artist.")
            sys.exit(1)
        print(f"Campaign artist: {artist_name}")

    result = subprocess.run(
        ["python3", "scripts/fetch_artist_profile.py", artist_name]
        + (["--force"] if args.force else []),
        capture_output=True, text=True, cwd=BUSINESS_DIR,
    )
    lines = result.stdout.strip().splitlines()
    json_start = next((i for i, l in enumerate(lines) if l.startswith("{")), None)
    if json_start is None:
        print("Failed to load profile."); print(result.stdout); sys.exit(1)
    profile = json.loads("\n".join(lines[json_start:]))

    import account_config
    try:
        cfg = account_config.load(args.account)
    except FileNotFoundError:
        cfg = {}
    palette  = _palette(cfg)
    art_path = BUSINESS_DIR / cfg.get("art_db", "data/art.db")
    art_conn = sqlite3.connect(art_path)
    used_urls: set[str] = set()

    def _bg() -> Image.Image:
        return _painting_bg(art_conn, used_urls, palette)

    def _artist_photo() -> Image.Image:
        url = profile.get("portrait_url", "") or profile.get("image_url", "")
        if url:
            try:
                wiki_headers = {**_FETCH_HEADERS, "Referer": "https://en.wikipedia.org/"}
                r = requests.get(url, headers=wiki_headers, timeout=15)
                if r.status_code == 200:
                    return Image.open(io.BytesIO(r.content)).convert("RGB")
            except Exception as e:
                print(f"  [warn] artist photo failed: {e}")
        return _bg()

    def _artwork_photo(aw) -> Image.Image:
        if isinstance(aw, dict):
            print(f"  Fetching: {aw.get('title', '')}")
            img = _fetch_artwork_image(aw)
            if img:
                return img
        return _bg()

    artworks = profile.get("famous_artworks", [])[:5]
    while len(artworks) < 5:
        artworks.append({"title": "Untitled Work", "image_url": "", "ext_url": ""})

    total = 6
    print("  Fetching: artist portrait")
    bio_photo   = _artwork_photo(artworks[3]) if artworks[3].get("image_url") or artworks[3].get("ext_url") else _bg()
    quote_photo = _artwork_photo(artworks[4]) if artworks[4].get("image_url") or artworks[4].get("ext_url") else _bg()
    cards = [
        render_cover(  _artist_photo(),            profile,    1, total),
        render_bio(    bio_photo,                  profile,    2, total),
        render_artwork(_artwork_photo(artworks[0]), artworks[0], 3, total),
        render_artwork(_artwork_photo(artworks[1]), artworks[1], 4, total),
        render_artwork(_artwork_photo(artworks[2]), artworks[2], 5, total),
        render_quote(  quote_photo,                profile,    6, total),
    ]
    art_conn.close()

    slug    = re.sub(r"[^\w]+", "-", artist_name.lower()).strip("-")
    out_dir = OUTPUT_DIR / f"artist-{date.today().isoformat()}-{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = ["01_cover", "02_bio", "03_work_i", "04_work_ii", "05_work_iii", "06_quote"]
    for label, card in zip(labels, cards):
        path = out_dir / f"{label}.png"
        card.save(path, "PNG")
        print(f"  saved: {path.name}")

    meta = {
        "artist_name": artist_name,
        "profile": profile,
        "artworks_shown": [a.get("title", a) if isinstance(a, dict) else a for a in artworks],
        "generated": date.today().isoformat(),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"\nDone — {len(cards)} cards → {out_dir}")


if __name__ == "__main__":
    main()
