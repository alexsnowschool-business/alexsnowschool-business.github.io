#!/usr/bin/env python3
"""
Digest reel — "This Week in the Room"

Multi-lot auction-results format: the data is the story, not a punchline.
Each frame = one result (house · estimate → hammer · % above).
No artist biography — pure market signal, read like a Bloomberg ticker.

Frame structure
  [0]   Title card  — "THIS WEEK / IN THE ROOM." + N results · houses
  [1–N] Lot cards   — artwork bg + data overlay (artist / house / est / hammer / %)
  [N+1] Closing     — pattern insight + follow CTA

Usage
    python scripts/digest_reel.py              # last 7 days, top 3 results
    python scripts/digest_reel.py --top-n 5   # up to 5 results
    python scripts/digest_reel.py --days 14   # wider lookback window
    python scripts/digest_reel.py --run        # also renders the reel
    python scripts/digest_reel.py --voice      # add TTS narration
    python scripts/digest_reel.py --list       # preview candidates and exit
    python scripts/digest_reel.py --all-time   # ignore week filter
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from dotenv import load_dotenv

# ── Paths ───────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import reel_utils

load_dotenv(BUSINESS_DIR / ".env", override=False)

DB_PATH       = BUSINESS_DIR / "data" / "art.db"
REELS_DIR     = BUSINESS_DIR / "reels"
REEL_TEMPLATE = BUSINESS_DIR / "reel_template"
FONTS_DIR     = REEL_TEMPLATE / "fonts"

# ── API ─────────────────────────────────────────────────────────────────────────
OPENROUTER_KEY   = os.getenv("OPENROUTER_API_KEY")
ELEVENLABS_KEY   = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "LXu5MIFyvPZCxBst8fPP")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")

# ── Card dimensions (9:16 vertical — Instagram Reel / TikTok) ───────────────────
CARD_W, CARD_H = 1080, 1920

# ── Palette ──────────────────────────────────────────────────────────────────────
_IVORY = (245, 240, 232)    # --ivory: primary text
_GOLD  = (201, 168, 76)     # --gold:  sold price, accent
_DIM   = (155, 143, 118)    # muted ivory: secondary text
_GHOST = (72, 66, 52)       # near-invisible: tags, minor labels
_BG    = (10, 9, 7)         # near-black warm: card backgrounds
_RULE  = (60, 55, 42)       # hairline colour

# ── Pacing ───────────────────────────────────────────────────────────────────────
_TITLE_HOLD   = 3.5   # seconds on title card
_LOT_HOLD     = 6.0   # seconds per lot card
_CLOSING_HOLD = 5.0   # seconds on closing card
_FADE_S       = 0.8   # cross-fade duration

# ── Roman numerals for lot rank ───────────────────────────────────────────────
_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


# ── Formatters ───────────────────────────────────────────────────────────────────

def _fmt_price(usd: float) -> str:
    return f"${usd:,.0f}"


def _fmt_price_tts(usd: float) -> str:
    if usd >= 1_000_000:
        return f"{usd / 1_000_000:.1f} million dollars"
    if usd >= 1_000:
        return f"{usd / 1_000:.0f} thousand dollars"
    return f"{usd:.0f} dollars"


def _pct_above(hammer: float, low: float) -> float:
    return round((hammer / low - 1) * 100, 1)


def _clean_artist(name: str) -> str:
    """Strip birth-year suffix and title-case."""
    return re.sub(r"\s*\([^)]+\)\s*$", "", name or "").strip().title()


def _clean_house(raw: str) -> str:
    """Map verbose auction house names to short canonical forms."""
    raw = (raw or "").strip()
    _MAP = [
        ("sotheby",    "Sotheby's"),
        ("christie",   "Christie's"),
        ("phillips",   "Phillips"),
        ("bonham",     "Bonhams"),
        ("ketterer",   "Ketterer"),
        ("van ham",    "Van Ham"),
        ("grisebach",  "Grisebach"),
        ("lempertz",   "Lempertz"),
        ("wright",     "Wright"),
    ]
    lower = raw.lower()
    for key, label in _MAP:
        if key in lower:
            return label
    return raw or "—"


def _week_bounds(ref: date) -> tuple[str, str]:
    monday = ref - timedelta(days=ref.weekday())
    return monday.isoformat(), (monday + timedelta(days=6)).isoformat()


# ── Font loader ───────────────────────────────────────────────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font from the reel_template fonts dir, with system fallback."""
    path = FONTS_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.truetype("Arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


# ── DB helpers ──────────────────────────────────────────────────────────────────

def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_digest_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS digest_reels (
            lot_id     TEXT,
            artist     TEXT,
            title      TEXT,
            hammer_usd REAL,
            reel_slug  TEXT,
            posted_at  TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (lot_id, reel_slug)
        )
    """)
    conn.commit()


def _digest_posted_ids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT lot_id FROM digest_reels").fetchall()
    return {r[0] for r in rows}


def _record_digest(conn: sqlite3.Connection, lots: list[dict], reel_slug: str) -> None:
    conn.executemany(
        """INSERT OR REPLACE INTO digest_reels
           (lot_id, artist, title, hammer_usd, reel_slug) VALUES (?, ?, ?, ?, ?)""",
        [(l["id"], l.get("artist"), l.get("title"), l.get("hammer_usd"), reel_slug)
         for l in lots],
    )
    conn.commit()


# ── Query helpers ────────────────────────────────────────────────────────────────

def _query_lots(
    conn: sqlite3.Connection,
    limit: int,
    exclude_ids: set[str],
    cutoff_start: str | None = None,
    cutoff_end: str | None = None,
) -> list[dict]:
    """
    Top outperforming lots by % above estimate.
    Restricted to scraped_at window when cutoff_start/cutoff_end are given.
    Excludes lots already featured in a digest.
    """
    excl = tuple(exclude_ids)
    ph   = ",".join("?" * len(excl)) if excl else "NULL"
    date_sql    = "AND substr(scraped_at,1,10) BETWEEN ? AND ?" if cutoff_start else ""
    date_params = (cutoff_start, cutoff_end) if cutoff_start else ()

    rows = conn.execute(f"""
        SELECT id, artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, scraped_at, auction_house, image_urls, source_url,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above
        FROM art_items
        WHERE sale_performance = 'above'
          AND hammer_usd IS NOT NULL
          AND estimate_low IS NOT NULL AND estimate_low > 0
          AND artist IS NOT NULL AND artist != ''
          {date_sql}
          {"AND id NOT IN (" + ph + ")" if excl else ""}
        ORDER BY pct_above DESC
        LIMIT ?
    """, (*date_params, *excl, limit)).fetchall()
    return [dict(r) for r in rows]


# ── Image helpers ─────────────────────────────────────────────────────────────────

def _download_lot_image(lot: dict, dest_dir: Path) -> Path | None:
    """Download the first available image for a lot. Returns local path or None."""
    urls = list(dict.fromkeys(json.loads(lot.get("image_urls") or "[]")))
    if not urls:
        return None
    saved = reel_utils.download_images(urls[:1], dest_dir, max_images=1, headers=_HEADERS)
    return saved[0] if saved else None


def _make_bg(img_path: Path | None) -> Image.Image:
    """
    Build a CARD_W × CARD_H RGB background:
      - With artwork: scale-to-fill, darken to 28%, apply bottom-heavy gradient.
      - Without artwork: solid warm near-black.
    The gradient ensures text in the lower 55% of the frame is always legible.
    """
    base = Image.new("RGB", (CARD_W, CARD_H), _BG)

    if img_path and img_path.exists():
        try:
            with Image.open(img_path) as im:
                im = im.convert("RGB")
                # Scale-to-fill: keep aspect ratio, crop centre
                scale = max(CARD_W / im.width, CARD_H / im.height)
                new_w, new_h = int(im.width * scale), int(im.height * scale)
                im = im.resize((new_w, new_h), Image.LANCZOS)
                x  = (new_w - CARD_W) // 2
                y  = (new_h - CARD_H) // 2
                im = im.crop((x, y, x + CARD_W, y + CARD_H))
                im = ImageEnhance.Brightness(im).enhance(0.28)
                base.paste(im)
        except Exception as e:
            print(f"  ⚠ BG error: {e}")

    # Bottom gradient — dark overlay that grows from transparent to near-opaque
    grad  = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    fade_y = int(CARD_H * 0.38)  # gradient starts here
    for y in range(fade_y, CARD_H):
        t     = (y - fade_y) / (CARD_H - fade_y)
        alpha = int(t * 235)
        gdraw.line([(0, y), (CARD_W, y)], fill=(0, 0, 0, alpha))

    base = base.convert("RGBA")
    base.alpha_composite(grad)
    return base.convert("RGB")


# ── Text layout helpers ────────────────────────────────────────────────────────────

def _text_w(draw: ImageDraw.ImageDraw, text: str,
             font: ImageFont.FreeTypeFont) -> int:
    return int(draw.textlength(text, font=font))


def _draw_hairline(draw: ImageDraw.ImageDraw, y: int,
                   x_pad: int = 72, color: tuple = _RULE) -> None:
    draw.line([(x_pad, y), (CARD_W - x_pad, y)], fill=color, width=1)


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    color: tuple,
    x: int,
    y: int,
    max_w: int,
    line_h: int,
) -> int:
    """Word-wrap `text` into `max_w` pixels wide; returns number of lines drawn."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textlength(test, font=font) <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_h), line, font=font, fill=color)
    return len(lines)


def _wrapped_height(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_w: int,
    line_h: int,
) -> int:
    """Estimate pixel height of word-wrapped text block without drawing."""
    dummy = ImageDraw.Draw(Image.new("RGB", (max_w + 200, 100)))
    lines, current = 0, ""
    for word in text.split():
        test = f"{current} {word}".strip()
        if dummy.textlength(test, font=font) <= max_w:
            current = test
        else:
            if current:
                lines += 1
            current = word
    if current:
        lines += 1
    return lines * line_h


# ── Card renderers ────────────────────────────────────────────────────────────────

def _render_title_card(lots: list[dict], week_label: str) -> Image.Image:
    """
    Solid dark title card — no artwork.

    Layout (top-down from vertical midpoint):
      @thehammerprice                   ← tag, ghost mono
      THIS WEEK                         ← serif XL, ivory
      IN THE                            ← serif XL, ivory
      ROOM.                             ← serif XL, gold
      ───────────────────────
      N results.                        ← mono, ivory
      house1 · house2 · house3          ← mono, dim
      every one above estimate.         ← mono, dim
      ───────────────────────
      week of DD month YYYY             ← small mono, ghost
    """
    img  = Image.new("RGB", (CARD_W, CARD_H), _BG)
    draw = ImageDraw.Draw(img)

    houses    = sorted({_clean_house(l.get("auction_house") or "") for l in lots
                        if l.get("auction_house")})
    house_str = " · ".join(h.lower() for h in houses)
    n         = len(lots)

    x  = 72
    y  = int(CARD_H * 0.33)   # vertical anchor for headline block

    # Tag
    mono_sm = _font("IBMPlexMono-Regular.ttf", 26)
    draw.text((x, y - 72), "@thehammerprice", font=mono_sm, fill=_GHOST)

    # Main headline — three lines
    serif_xl = _font("InstrumentSerif-Regular.ttf", 136)
    draw.text((x, y),        "THIS WEEK", font=serif_xl, fill=_IVORY)
    draw.text((x, y + 138),  "IN THE",   font=serif_xl, fill=_IVORY)
    draw.text((x, y + 276),  "ROOM.",    font=serif_xl, fill=_GOLD)

    y2 = y + 430
    _draw_hairline(draw, y2, x_pad=x)
    y2 += 38

    # Stats block
    body = _font("IBMPlexMono-Regular.ttf", 34)
    draw.text((x, y2),       f"{n} result{'s' if n != 1 else ''}.", font=body, fill=_IVORY)
    draw.text((x, y2 + 52),  house_str,                              font=body, fill=_DIM)
    draw.text((x, y2 + 104), "every one above estimate.",            font=body, fill=_DIM)

    y3 = y2 + 166
    _draw_hairline(draw, y3, x_pad=x)
    y3 += 32

    # Week label
    mono_xs = _font("IBMPlexMono-Regular.ttf", 24)
    draw.text((x, y3), f"week of {week_label}", font=mono_xs, fill=_GHOST)

    return img


def _render_lot_card(
    lot: dict,
    rank: int,
    total: int,
    img_path: Path | None,
) -> Image.Image:
    """
    Artwork background + data overlay for one lot.

    Bottom-up layout (all anchored to y_base = CARD_H - 100):
      +N% above estimate.       ← serif LG, ivory     (data line 3 / hero stat)
      sold: $X,XXX,XXX.         ← serif MED, gold     (data line 2)
      estimate: $X–$X           ← serif MED, dim      (data line 1)
      ─────────────────────
      HOUSE  ·  SALE NAME       ← mono SM, ghost uppercase
      Artist Name               ← italic serif, dim

    Top-left corner:
      I.  of 3.                 ← small roman, ghost
    Top-right corner:
      @thehammerprice           ← mono XS, ghost
    """
    img  = _make_bg(img_path)
    draw = ImageDraw.Draw(img)

    artist   = _clean_artist(lot.get("artist") or "Unknown")
    house    = _clean_house(lot.get("auction_house") or "")
    sale     = (lot.get("sale_name") or "")[:38].upper()
    hammer   = lot["hammer_usd"]
    est_low  = lot["estimate_low"]
    est_high = lot.get("estimate_high") or est_low
    pct      = _pct_above(hammer, est_low)
    roman    = _ROMAN[rank - 1] if rank <= len(_ROMAN) else str(rank)

    x      = 72
    y_base = CARD_H - 108     # bottom anchor for the data block

    # ── Data lines (serif, bottom-up) ──────────────────────────────────────────

    serif_lg  = _font("InstrumentSerif-Regular.ttf", 82)
    serif_med = _font("InstrumentSerif-Regular.ttf", 58)

    # Line 3 — hero stat
    pct_str = f"+{pct:,.0f}% above estimate."
    draw.text((x, y_base - 82), pct_str, font=serif_lg, fill=_IVORY)

    # Line 2 — hammer price
    draw.text((x, y_base - 82 - 66), f"sold: {_fmt_price(hammer)}.", font=serif_med, fill=_GOLD)

    # Line 1 — estimate range
    draw.text((x, y_base - 82 - 66 - 62), f"estimate: {_fmt_price(est_low)}–{_fmt_price(est_high)}", font=serif_med, fill=_DIM)

    # Hairline above data lines
    rule_y = y_base - 82 - 66 - 62 - 28
    _draw_hairline(draw, rule_y, x_pad=x)

    # House · Sale (mono, ghost, uppercase)
    mono_sm   = _font("IBMPlexMono-Regular.ttf", 26)
    house_str = house.upper() + (f"  ·  {sale}" if sale else "")
    draw.text((x, rule_y - 52), house_str, font=mono_sm, fill=_GHOST)

    # Artist name (italic serif, dim)
    italic = _font("InstrumentSerif-Italic.ttf", 52)
    draw.text((x, rule_y - 52 - 64), artist, font=italic, fill=_DIM)

    # ── Corner labels ───────────────────────────────────────────────────────────

    # Top-left: roman numeral rank
    roman_font = _font("InstrumentSerif-Regular.ttf", 44)
    draw.text((x, 72), f"{roman}.  of {total}.", font=roman_font, fill=_GHOST)

    # Top-right: tag
    mono_xs = _font("IBMPlexMono-Regular.ttf", 24)
    tag_w   = _text_w(draw, "@thehammerprice", mono_xs)
    draw.text((CARD_W - x - tag_w, 72), "@thehammerprice", font=mono_xs, fill=_GHOST)

    return img


def _render_closing_card(lots: list[dict], insight: str) -> Image.Image:
    """
    Closing card — no artwork, styled text only.

    Layout:
      @thehammerprice            ← tag, ghost
      the                        ← serif LG, dim
      pattern.                   ← serif LG, ivory
      ────────────────────
      [insight sentence]         ← italic serif, ivory, word-wrapped
      ────────────────────
      follow for weekly          ← mono, dim
      auction data.              ← mono, dim

    Bottom-right: avg overshoot stat (ghost)
    """
    img  = Image.new("RGB", (CARD_W, CARD_H), _BG)
    draw = ImageDraw.Draw(img)

    n       = len(lots)
    avg_pct = sum(_pct_above(l["hammer_usd"], l["estimate_low"]) for l in lots) / max(1, n)

    x  = 72
    y  = int(CARD_H * 0.34)

    # Tag
    mono_sm = _font("IBMPlexMono-Regular.ttf", 26)
    draw.text((x, y - 72), "@thehammerprice", font=mono_sm, fill=_GHOST)

    # Headline
    serif_lg = _font("InstrumentSerif-Regular.ttf", 116)
    draw.text((x, y),        "the",      font=serif_lg, fill=_DIM)
    draw.text((x, y + 118),  "pattern.", font=serif_lg, fill=_IVORY)

    y2 = y + 268
    _draw_hairline(draw, y2, x_pad=x)
    y2 += 44

    # Insight text — word-wrapped
    insight_font  = _font("InstrumentSerif-Italic.ttf", 46)
    insight_clean = insight or (
        f"{n} of {n} lots cleared the low estimate this session. "
        "the catalogue is a floor. the room decides the ceiling."
    )
    max_text_w  = CARD_W - x * 2
    n_lines     = _draw_wrapped(draw, insight_clean, insight_font, _IVORY,
                                x, y2, max_text_w, line_h=62)

    y3 = y2 + n_lines * 62 + 52
    _draw_hairline(draw, y3, x_pad=x)
    y3 += 38

    # CTA
    cta_font = _font("IBMPlexMono-Regular.ttf", 30)
    draw.text((x, y3),      "follow for weekly", font=cta_font, fill=_DIM)
    draw.text((x, y3 + 46), "auction data.",     font=cta_font, fill=_DIM)

    # Bottom-right stat
    stat_font = _font("IBMPlexMono-Regular.ttf", 24)
    stat_str  = f"avg +{avg_pct:.0f}% above estimate this session"
    stat_w    = _text_w(draw, stat_str, stat_font)
    draw.text((CARD_W - x - stat_w, CARD_H - 72), stat_str, font=stat_font, fill=_GHOST)

    return img


# ── Voiceover script ───────────────────────────────────────────────────────────

def _build_vo_script(lots: list[dict], insight: str) -> str:
    """
    Build the full TTS narration script for the digest reel.

    Structure:
      Intro  — "this week in the room. N results from [houses]."
      Lots   — per-lot read: house · sale · artist · est → hammer · % above
      Closing — insight + follow CTA

    Entirely data-driven — no AI required for the body.
    """
    n      = len(lots)
    houses = sorted({_clean_house(l.get("auction_house") or "") for l in lots})
    if len(houses) > 1:
        house_str = ", ".join(houses[:-1]) + f" and {houses[-1]}"
    else:
        house_str = houses[0] if houses else "the major houses"

    parts = [
        f"this week in the room.  {n} result{'s' if n > 1 else ''} from {house_str}.",
    ]

    for i, lot in enumerate(lots, 1):
        artist   = _clean_artist(lot.get("artist") or "Unknown")
        house    = _clean_house(lot.get("auction_house") or "")
        sale     = (lot.get("sale_name") or "").strip()
        hammer   = lot["hammer_usd"]
        est_low  = lot["estimate_low"]
        est_high = lot.get("estimate_high") or est_low
        pct      = _pct_above(hammer, est_low)
        roman    = _ROMAN[i - 1] if i <= len(_ROMAN) else str(i)

        line = (
            f"{roman}.  {house}."
            + (f"  {sale}." if sale else "")
            + f"  {artist}."
            f"  estimated at {_fmt_price_tts(est_low)} to {_fmt_price_tts(est_high)}."
            f"  sold for {_fmt_price_tts(hammer)}."
            f"  plus {pct:.0f} percent above estimate."
        )
        parts.append(line)

    closing = (
        insight
        or f"every lot in this session cleared the low estimate.  "
           "the catalogue is a floor — the room decides the ceiling."
    )
    parts += [
        closing,
        "follow the hammer price for weekly auction data.",
    ]

    return "  ".join(parts)


# ── Social captions ────────────────────────────────────────────────────────────

def _social_captions(lots: list[dict], week_label: str) -> dict:
    """Build platform captions for the digest reel."""
    n       = len(lots)
    houses  = sorted({_clean_house(l.get("auction_house") or "") for l in lots})
    h_str   = " · ".join(h.lower() for h in houses)
    avg_pct = sum(_pct_above(l["hammer_usd"], l["estimate_low"]) for l in lots) / max(1, n)
    best    = max(lots, key=lambda l: _pct_above(l["hammer_usd"], l["estimate_low"]))
    best_a  = _clean_artist(best.get("artist") or "").lower()
    best_p  = _pct_above(best["hammer_usd"], best["estimate_low"])

    ig = (
        f"this week in the room. {n} results. {h_str}.\n\n"
        f"standout: {best_a} — +{best_p:.0f}% above estimate.\n\n"
        f"average overshoot across the session: +{avg_pct:.0f}%.\n\n"
        f"swipe through for the full data.\n\n"
        f"#thehammerprice #artmarket #auctionresults"
    )
    tt = (
        f"{n} lots. {h_str}. every one above estimate.\n"
        f"led by {best_a} at +{best_p:.0f}%. "
        f"watch for the full breakdown.\n\n"
        f"#thehammerprice #artmarket #auctionresults #foryou #artcollecting"
    )
    return {"instagram": ig, "tiktok": tt}


# ── Config generation ──────────────────────────────────────────────────────────

def _generate_config(
    lots: list[dict],
    week_label: str,
    reel_slug: str,
    narration_captions: list[dict] | None = None,
) -> str:
    """
    Write reel_config.py for make_reel.py.

    Since all text is baked into the PIL cards, per_frame_captions have
    show_caption=False — make_reel.py only handles timing and video assembly.
    """
    _esc   = reel_utils.esc
    social = _social_captions(lots, week_label)
    n      = len(lots)

    # One entry per frame: title + lots + closing
    holds  = [_TITLE_HOLD] + [_LOT_HOLD] * n + [_CLOSING_HOLD]
    frames = [
        {"show_caption": False, "hold_seconds": h, "upper_artist": "", "upper_title": ""}
        for h in holds
    ]

    lines = [
        '"""',
        f"Digest reel config — week of {week_label}",
        f"Generated by scripts/digest_reel.py",
        '"""',
        "",
        "CONFIG = {",
        f'    "lot_id":          "{_esc(reel_slug)}",',
        "",
        "    # ── Captions (text baked into PIL cards — overlays disabled) ─────",
        '    "caption_tag":        "",',
        '    "caption_line1":      "",',
        '    "caption_line2":      "",',
        '    "caption_line3":      "",',
        '    "caption_all_frames": False,',
        "",
        "    # ── Layout ────────────────────────────────────────────────────────",
        '    "photo_fit_first":  True,',
        "",
        "    # ── Style ─────────────────────────────────────────────────────────",
        '    "vibe":                "auction_editorial",',
        '    "caption_position":    "lower_safe",',
        '    "bg_music":            True,',
        '    "transitions_enabled": False,',
        '    "block_reveal":        False,',
        # Suppress all make_reel.py text overlays — cards have text baked in
        '    "hide_chrome":         True,',
        "",
        "    # ── Required chrome fields (hidden — cards are pre-rendered) ──────",
        '    "location_coords": "",',
        '    "location_name":   "",',
        '    "location_season": "",',
        '    "frame_label":     "",',
        "",
        "    # ── Pacing ────────────────────────────────────────────────────────",
        '    "fps":              5,',
        '    "hold_seconds":     0.0,',
        f'    "fade_seconds":     {_FADE_S},',
        f'    "cover_hold_seconds": {_TITLE_HOLD},',
        "",
        "    # ── Social captions ───────────────────────────────────────────────",
        '    "topic":        "culture",',
        # repr() handles all escaping: newlines, apostrophes, backslashes
        f'    "caption_full": {repr(social["instagram"])},',
        '    "caption_hero": "this week in the room",',
        "",
        "    # ── Per-frame timing (text baked in — no overlay) ─────────────────",
        '    "per_frame_captions": [',
    ]
    for fc in frames:
        lines.append("        {")
        for k, v in fc.items():
            lines.append(f"            {repr(k)}: {repr(v)},")
        lines.append("        },")
    lines.append("    ],")

    if narration_captions:
        lines += [
            "",
            "    # ── Word-level narration captions ─────────────────────────────",
            '    "narration_captions": [',
        ]
        for cap in narration_captions:
            lines.append(
                f"        {{\"start\": {cap['start']:.3f}, "
                f"\"end\": {cap['end']:.3f}, "
                f"\"text\": {repr(cap['text'])}}},")
        lines.append("    ],")

    lines.append("}")
    return "\n".join(lines) + "\n"


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a digest reel — 'This Week in the Room'"
    )
    parser.add_argument("--days",     type=int, default=7,
                        help="Lookback window in days by scraped_at (default: 7)")
    parser.add_argument("--top-n",    type=int, default=3,
                        help="Max lots to feature (default: 3, max sensible: 5)")
    parser.add_argument("--all-time", action="store_true",
                        help="Ignore date filter — pick best ever unposted")
    parser.add_argument("--run",      action="store_true",
                        help="Run make_reel.py after generation")
    parser.add_argument("--voice",    action="store_true",
                        help="Generate TTS narration via ElevenLabs / Edge TTS")
    parser.add_argument("--list",     action="store_true",
                        help="Preview candidates and exit (no files written)")
    args = parser.parse_args()

    ref_date   = date.today()
    week_label = ref_date.strftime("%-d %B %Y").lower()

    print("═" * 60)
    print("  DIGEST REEL — This Week in the Room")
    print(f"  Mode: {'all-time top unposted' if args.all_time else f'last {args.days} days'}")
    print(f"  Lots: up to {args.top_n}")
    print("═" * 60)

    if not DB_PATH.exists():
        print(f"✗ Database not found: {DB_PATH}")
        sys.exit(1)

    conn = _open_db(DB_PATH)
    _ensure_digest_table(conn)
    skip = _digest_posted_ids(conn)
    if skip:
        print(f"\n  ℹ Skipping {len(skip)} already-digested lot(s).")

    # ── Query candidates ────────────────────────────────────────────────────────
    candidate_n = args.top_n * 4   # fetch extra so we can de-dupe by artist

    if args.all_time:
        lots = _query_lots(conn, candidate_n, skip)
    else:
        cutoff_start = (ref_date - timedelta(days=args.days)).isoformat()
        cutoff_end   = ref_date.isoformat()
        lots = _query_lots(conn, candidate_n, skip, cutoff_start, cutoff_end)
        if not lots:
            print(f"  ⚠ No lots in last {args.days} days — falling back to all-time.")
            lots = _query_lots(conn, candidate_n, skip)

    # De-duplicate: one lot per artist, then take top_n
    seen_artists: set[str] = set()
    chosen: list[dict] = []
    for lot in lots:
        key = _clean_artist(lot.get("artist") or "").lower()
        if key in seen_artists:
            continue
        seen_artists.add(key)
        chosen.append(lot)
        if len(chosen) >= args.top_n:
            break

    # ── --list mode ─────────────────────────────────────────────────────────────
    if args.list:
        if not chosen:
            print("\n  No candidates found.")
        else:
            print(f"\n  {'#':<4} {'Artist':<30} {'House':<18} {'Hammer':>12} {'%+':>7}")
            print("  " + "─" * 76)
            for i, l in enumerate(chosen, 1):
                pct = _pct_above(l["hammer_usd"], l["estimate_low"])
                print(
                    f"  {i:<4} {_clean_artist(l.get('artist') or '')[:29]:<30} "
                    f"{_clean_house(l.get('auction_house') or '')[:17]:<18} "
                    f"{_fmt_price(l['hammer_usd']):>12}  {pct:>5.0f}%"
                )
        conn.close()
        return

    if not chosen:
        print("✗ No suitable lots found in database.")
        conn.close()
        sys.exit(1)

    print(f"\n▸ Selected {len(chosen)} lot(s):")
    for l in chosen:
        pct = _pct_above(l["hammer_usd"], l["estimate_low"])
        print(
            f"  {_clean_artist(l.get('artist') or ''):<32} "
            f"{_fmt_price(l['hammer_usd']):>12}  +{pct:.0f}%  "
            f"({_clean_house(l.get('auction_house') or '')})"
        )

    # ── Create reel folder ──────────────────────────────────────────────────────
    reel_slug = f"{ref_date.isoformat()}_digest_n{len(chosen)}"
    reel_dir  = REELS_DIR / reel_slug
    imgs_dir  = reel_dir / "images"
    out_dir   = reel_dir / "output"
    src_dir   = reel_dir / "_src"

    for d in (imgs_dir, out_dir, src_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"\n▸ Reel folder: {reel_dir}")

    # ── Download artwork images ─────────────────────────────────────────────────
    print("\n▸ Downloading lot images...")
    img_paths: list[Path | None] = []
    for lot in chosen:
        ipath = _download_lot_image(lot, src_dir)
        img_paths.append(ipath)
        label = _clean_artist(lot.get("artist") or "")
        print(f"  {'✓' if ipath else '✗'} {label}"
              + ("" if ipath else " — no image (solid-bg card)"))

    # ── Closing insight ─────────────────────────────────────────────────────────
    insight = ""
    if OPENROUTER_KEY:
        print("\n▸ Generating pattern insight...")
        try:
            from ai_content import generate_digest_insight
            insight = generate_digest_insight(chosen) or ""
            if insight:
                print(f"  ✓ {insight[:80]}{'...' if len(insight) > 80 else ''}")
            else:
                print("  ▸ Using template insight.")
        except (ImportError, AttributeError):
            print("  ▸ generate_digest_insight not found in ai_content — using template.")
        except Exception as e:
            print(f"  ⚠ Insight error: {e}")

    # ── Render PIL cards ────────────────────────────────────────────────────────
    print("\n▸ Rendering cards...")
    n = len(chosen)

    # Title card (frame 0)
    title_card = _render_title_card(chosen, week_label)
    (imgs_dir / "00_title.jpg").write_bytes(
        _pil_to_bytes(title_card)
    )
    print("  ✓ title card")

    # Lot cards (frames 1–N)
    for i, (lot, ipath) in enumerate(zip(chosen, img_paths), 1):
        card = _render_lot_card(lot, i, n, ipath)
        (imgs_dir / f"{i:02d}_lot{i}.jpg").write_bytes(_pil_to_bytes(card))
        print(f"  ✓ lot {i}: {_clean_artist(lot.get('artist') or '')}")

    # Closing card (frame N+1)
    closing_card = _render_closing_card(chosen, insight)
    (imgs_dir / f"{n + 1:02d}_closing.jpg").write_bytes(_pil_to_bytes(closing_card))
    print("  ✓ closing card")

    # Clean up _src
    shutil.rmtree(src_dir, ignore_errors=True)

    total_frames = 1 + n + 1

    # ── Voiceover (optional) ────────────────────────────────────────────────────
    word_timings  : list[dict] = []
    narr_captions : list[dict] = []

    if args.voice:
        print("\n▸ Generating voiceover...")
        vo_script = _build_vo_script(chosen, insight)
        vo_path   = reel_dir / "voiceover.mp3"
        try:
            from ai_content import generate_voiceover
            ok, word_timings = generate_voiceover(vo_script, str(vo_path))
            word_timings  = reel_utils.normalise_word_timings(word_timings)
            if ok and word_timings:
                narr_captions = reel_utils.words_to_captions(word_timings)
                dur = word_timings[-1]["end"] + 0.5
                print(f"  ✓ Voiceover ({dur:.1f}s, {len(word_timings)} words, "
                      f"{len(narr_captions)} caption cues)")
        except Exception as e:
            print(f"  ⚠ Voiceover error: {e}")

    # ── Write reel_config.py ────────────────────────────────────────────────────
    config_path = reel_dir / "reel_config.py"
    config_path.write_text(
        _generate_config(chosen, week_label, reel_slug, narr_captions or None)
    )
    print(f"\n▸ Config written: {config_path}")

    # ── Record in digest_reels ──────────────────────────────────────────────────
    _record_digest(conn, chosen, reel_slug)
    conn.close()
    print(f"  ✓ {n} lot(s) recorded in digest_reels table")

    # ── Summary ─────────────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  READY TO RENDER")
    print(f"  Reel folder: reels/{reel_slug}/")
    print(f"  Frames: {total_frames}  (pre-rendered PIL — text baked in)")
    print()
    print("  To render:")
    print(f"    python reel_template/make_reel.py reels/{reel_slug}")
    print("═" * 60)

    # ── Optionally run make_reel.py ─────────────────────────────────────────────
    if args.run:
        print("\n▸ Running make_reel.py...")
        subprocess.run(
            [sys.executable, str(REEL_TEMPLATE / "make_reel.py"), str(reel_dir)],
            cwd=str(REEL_TEMPLATE.parent),
        )


# ── PIL save helper ────────────────────────────────────────────────────────────

def _pil_to_bytes(img: Image.Image, quality: int = 95) -> bytes:
    """Return JPEG bytes for a PIL image."""
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


if __name__ == "__main__":
    main()
