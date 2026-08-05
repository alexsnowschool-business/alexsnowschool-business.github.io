#!/usr/bin/env python3
"""
Digest reel — "This Week in the Room"

Static PNG carousel in the same format as beat_the_estimate_cards.py
(1080×1350, cover mosaic + one card per lot). No video, no voiceover.

Narrative shift from beat_the_estimate: the auction result is the hero,
not the % overshoot. Each card leads with the house, the spread, and the
hammer price as a verdict — market analyst voice, not guessing game.

Output:
    output/digest/{date}/
        00_cover.png
        01_lot.png
        02_lot.png
        ...
        meta.json

Usage
    python scripts/digest_reel.py --list              # preview candidates
    python scripts/digest_reel.py --run               # generate cards
    python scripts/digest_reel.py --run --top-n 5    # up to 5 lots
    python scripts/digest_reel.py --run --days 14    # wider lookback
    python scripts/digest_reel.py --run --all-time   # best ever unposted
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

# ── Paths ───────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

load_dotenv(BUSINESS_DIR / ".env", override=False)

import os
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

DB_PATH    = BUSINESS_DIR / "data" / "art.db"
OUTPUT_DIR = BUSINESS_DIR / "output" / "digest"
FONTS_DIR  = BUSINESS_DIR / "reel_template" / "fonts"

# ── Card dimensions — matches beat_the_estimate_cards.py ────────────────────────
W, H       = 1080, 1350
PHOTO_H    = 1000          # artwork occupies the top portion
GOLD_BAR   = 4             # separator between photo and data strip
DATA_Y     = PHOTO_H + GOLD_BAR   # y-origin of the data strip
MARGIN     = 72

# ── Palette — "auction_editorial" (shared with beat_the_estimate_cards.py) ──────
BG         = (20, 18, 16)
GOLD       = (201, 168, 76)
GOLD_DIM   = (100, 82, 45)
IVORY      = (245, 240, 232)
IVORY_DIM  = (185, 165, 130)
GHOST      = (90, 83, 68)

# ── Cover hook lines — results narrative, not guessing game ─────────────────────
_COVER_HOOKS = [
    "This week in the room.",
    "The room's verdict.",
    "Results from the room.",
    "What the room paid.",
    "The hammer has spoken.",
    "This week's results.",
    "The room disagreed.",
]

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _font_cache:
        path = FONTS_DIR / name
        _font_cache[key] = ImageFont.truetype(str(path), size)
    return _font_cache[key]


def _fmt(usd: float) -> str:
    return f"${usd:,.0f}"


def _pct_above(hammer: float, low: float) -> float:
    return round((hammer / low - 1) * 100, 1)


def _clean_artist(name: str) -> str:
    return re.sub(r"\s*\([^)]+\)\s*$", "", name or "").strip().title()


def _clean_house(raw: str) -> str:
    raw = (raw or "").strip()
    for key, label in [
        ("sotheby",  "Sotheby's"),
        ("christie", "Christie's"),
        ("phillips", "Phillips"),
        ("bonham",   "Bonhams"),
        ("ketterer", "Ketterer"),
        ("van ham",  "Van Ham"),
        ("grisebach","Grisebach"),
        ("lempertz", "Lempertz"),
        ("wright",   "Wright"),
    ]:
        if key in raw.lower():
            return label
    return raw or "—"


def _wrap(draw: ImageDraw.ImageDraw, text: str,
          font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_w:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _crop_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale and centre-crop so img exactly covers a w×h box."""
    iw, ih = img.size
    if iw / ih > w / h:
        nw = int(ih * w / h)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = int(iw * h / w)
        top = max(0, (ih - nh) // 3)   # bias slightly upward
        img = img.crop((0, top, iw, top + nh))
    return img.resize((w, h), Image.LANCZOS)


def _download_photo(url: str | None) -> Image.Image | None:
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"  ⚠ photo download failed: {e}")
        return None


def _first_image_url(lot: dict) -> str | None:
    raw = lot.get("image_urls")
    if isinstance(raw, list):
        return raw[0] if raw else None
    if isinstance(raw, str):
        try:
            urls = json.loads(raw)
            return urls[0] if urls else None
        except (TypeError, ValueError):
            return None
    return None


# ── Card renderers ─────────────────────────────────────────────────────────────

def _mosaic(lots: list[dict], w: int, h: int) -> Image.Image:
    """Full-bleed grid mosaic of every featured lot's photo."""
    canvas = Image.new("RGB", (w, h), (30, 27, 24))
    photos = [p for p in (_download_photo(_first_image_url(l)) for l in lots) if p]
    if not photos:
        return canvas
    cols = 1 if len(photos) == 1 else 2
    rows = -(-len(photos) // cols)
    for i, photo in enumerate(photos):
        col, row = i % cols, i // cols
        x0 = (col * w) // cols
        x1 = ((col + 1) * w) // cols
        y0 = (row * h) // rows
        y1 = ((row + 1) * h) // rows
        canvas.paste(_crop_fill(photo, x1 - x0, y1 - y0), (x0, y0))
    return canvas


def render_cover_card(
    lots: list[dict],
    hook: str,
    week_label: str,
) -> Image.Image:
    """
    Cover card: mosaic of lot photos + hook headline + meta line.

    Layout mirrors beat_the_estimate_cards.render_cover_card:
      - Full-bleed photo mosaic (all lots)
      - Bottom gradient
      - "The Hammer Price" kicker (solid bg pill, gold)
      - Hook headline (large Outfit-Bold, ivory)
      - Meta: "{N} results · {houses} · {date}"
    """
    import random
    img = _mosaic(lots, W, H)

    # Bottom gradient — fades in over the lower 58% of the card
    fade_top = int(H * 0.42)
    fade_h   = H - fade_top
    fade     = Image.new("RGB", (W, fade_h), (8, 7, 6))
    mask     = Image.new("L",   (W, fade_h), 0)
    mdraw    = ImageDraw.Draw(mask)
    for row in range(fade_h):
        alpha = int(235 * (row / fade_h) ** 1.4)
        mdraw.line([(0, row), (W, row)], fill=alpha)
    img.paste(fade, (0, fade_top), mask)

    draw       = ImageDraw.Draw(img)
    content_w  = W - MARGIN * 2

    # Kicker label
    kicker_font = _font("Outfit-Regular.ttf", 24)
    kicker_text = "The Hammer Price"
    kb          = draw.textbbox((0, 0), kicker_text, font=kicker_font)
    draw.rectangle(
        [MARGIN - 20, MARGIN - 12,
         MARGIN + (kb[2] - kb[0]) + 20, MARGIN + (kb[3] - kb[1]) + 12],
        fill=(8, 7, 6),
    )
    draw.text((MARGIN, MARGIN), kicker_text, font=kicker_font, fill=GOLD)

    # Hook headline — auto-size to fit in 4 lines
    hook_text  = hook or random.choice(_COVER_HOOKS)
    size       = 88
    hook_font  = _font("Outfit-Bold.ttf", size)
    hook_lines = _wrap(draw, hook_text, hook_font, content_w)
    while len(hook_lines) > 4 and size > 48:
        size -= 4
        hook_font  = _font("Outfit-Bold.ttf", size)
        hook_lines = _wrap(draw, hook_text, hook_font, content_w)

    hb      = hook_font.getbbox("Hg")
    line_h  = int((hb[3] - hb[1]) * 1.12)
    meta_font = _font("Outfit-Regular.ttf", 26)

    # Anchor block to bottom
    block_h = line_h * len(hook_lines) + 28 + 34
    y = H - MARGIN - block_h

    for line in hook_lines:
        draw.text((MARGIN, y), line, font=hook_font, fill=IVORY)
        y += line_h
    y += 28

    # Meta line: N results · house1 · house2 · week
    houses   = sorted({_clean_house(l.get("auction_house") or "") for l in lots})
    meta_str = f"{len(lots)} results  ·  " + "  ·  ".join(houses) + f"  ·  {week_label}"
    draw.text((MARGIN, y), meta_str, font=meta_font, fill=GOLD)

    return img


def render_lot_card(lot: dict, rank: int) -> Image.Image:
    """
    Per-lot card: photo (top PHOTO_H px) + gold bar + data strip.

    Data strip narrative: auction result as hero.
      artist name          (bold, ivory)
      house · sale         (regular, dim)
      ─── (thin rule) ───
      +N% above estimate   (bold, large — hero stat)
      sold: $X,XXX,XXX     (bold, gold)
      estimate: $X–$X      (regular, dim)
    """
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Photo zone
    photo = _download_photo(_first_image_url(lot))
    if photo:
        img.paste(_crop_fill(photo, W, PHOTO_H), (0, 0))
    else:
        draw.rectangle([0, 0, W, PHOTO_H], fill=(30, 27, 24))

    # Gold separator
    draw.rectangle([0, PHOTO_H, W, PHOTO_H + GOLD_BAR], fill=GOLD)

    # Data strip
    y       = DATA_Y + 18
    cw      = W - MARGIN * 2
    artist  = _clean_artist(lot.get("artist") or "Unknown")
    house   = _clean_house(lot.get("auction_house") or "")
    sale    = (lot.get("sale_name") or "")
    hammer  = lot["hammer_usd"]
    est_lo  = lot["estimate_low"]
    est_hi  = lot.get("estimate_high") or est_lo
    pct     = _pct_above(hammer, est_lo)

    # Artist name — one line, bold
    af   = _font("Outfit-Bold.ttf", 38)
    line = _wrap(draw, artist, af, cw)[0] if artist else ""
    draw.text((MARGIN, y), line, font=af, fill=IVORY)
    ab = draw.textbbox((0, 0), line, font=af)
    y += (ab[3] - ab[1]) + 6

    # House · sale — one line, regular, dim
    hf        = _font("Outfit-Regular.ttf", 22)
    house_str = house + (f"  ·  {sale}" if sale else "")
    if draw.textlength(house_str, font=hf) > cw:
        house_str = house   # truncate to house only if too long
    draw.text((MARGIN, y), house_str, font=hf, fill=IVORY_DIM)
    hb = draw.textbbox((0, 0), house_str, font=hf)
    y += (hb[3] - hb[1]) + 12

    # Thin rule
    draw.line([(MARGIN, y), (W - MARGIN, y)], fill=GHOST, width=1)
    y += 14

    # % above estimate — hero stat, bold, ivory
    pf       = _font("Outfit-Bold.ttf", 52)
    pct_str  = f"+{pct:,.0f}% above estimate"
    pct_w    = draw.textlength(pct_str, font=pf)
    if pct_w > cw:
        pf = _font("Outfit-Bold.ttf", 42)   # scale down if too wide
    draw.text((MARGIN, y), pct_str, font=pf, fill=IVORY)
    pb = draw.textbbox((0, 0), pct_str, font=pf)
    y += (pb[3] - pb[1]) + 10

    # Sold for — bold, gold
    sf  = _font("Outfit-Bold.ttf", 38)
    draw.text((MARGIN, y), f"sold  {_fmt(hammer)}", font=sf, fill=GOLD)
    sb = draw.textbbox((0, 0), f"sold  {_fmt(hammer)}", font=sf)
    y += (sb[3] - sb[1]) + 6

    # Estimate — regular, dim
    ef  = _font("Outfit-Regular.ttf", 22)
    draw.text((MARGIN, y), f"estimate  {_fmt(est_lo)}–{_fmt(est_hi)}", font=ef, fill=IVORY_DIM)

    return img


# ── DB helpers ─────────────────────────────────────────────────────────────────

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


def _record_digest(conn: sqlite3.Connection, lots: list[dict], slug: str) -> None:
    conn.executemany(
        """INSERT OR REPLACE INTO digest_reels
           (lot_id, artist, title, hammer_usd, reel_slug) VALUES (?, ?, ?, ?, ?)""",
        [(l["id"], l.get("artist"), l.get("title"), l.get("hammer_usd"), slug)
         for l in lots],
    )
    conn.commit()


def _query_lots(
    conn: sqlite3.Connection,
    limit: int,
    exclude_ids: set[str],
    cutoff_start: str | None = None,
    cutoff_end:   str | None = None,
) -> list[dict]:
    excl        = tuple(exclude_ids)
    ph          = ",".join("?" * len(excl)) if excl else "NULL"
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


# ── Social captions ────────────────────────────────────────────────────────────

def _social_captions(lots: list[dict], week_label: str, insight: str) -> dict:
    n       = len(lots)
    houses  = sorted({_clean_house(l.get("auction_house") or "") for l in lots})
    h_str   = "  ·  ".join(h.lower() for h in houses)
    avg_pct = sum(_pct_above(l["hammer_usd"], l["estimate_low"]) for l in lots) / max(1, n)
    best    = max(lots, key=lambda l: _pct_above(l["hammer_usd"], l["estimate_low"]))
    best_a  = _clean_artist(best.get("artist") or "").lower()
    best_p  = _pct_above(best["hammer_usd"], best["estimate_low"])

    ig = (
        f"this week in the room. {n} results. {h_str}.\n\n"
        f"standout: {best_a} — +{best_p:.0f}% above estimate.\n\n"
        + (f"{insight}\n\n" if insight else "")
        + f"swipe for the full data.\n\n"
        f"#thehammerprice #artmarket #auctionresults"
    )
    tt = (
        f"{n} lots. {h_str}. every one above estimate.\n"
        f"led by {best_a} at +{best_p:.0f}%. swipe for the data.\n\n"
        f"#thehammerprice #artmarket #auctionresults #foryou #artcollecting"
    )
    return {"instagram": ig, "tiktok": tt}


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a digest carousel — 'This Week in the Room'"
    )
    parser.add_argument("--list",     action="store_true",
                        help="Preview candidates without generating any files")
    parser.add_argument("--run",      action="store_true",
                        help="Generate the cards and record featured lots")
    parser.add_argument("--top-n",    type=int, default=3,
                        help="Number of lots to feature (default: 3)")
    parser.add_argument("--days",     type=int, default=7,
                        help="Lookback window in days by scraped_at (default: 7)")
    parser.add_argument("--all-time", action="store_true",
                        help="Ignore date filter — pick best ever unposted")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    if not args.list and not args.run:
        parser.error("Specify --list to preview or --run to generate.")

    ref_date   = date.today()
    week_label = ref_date.strftime("%b %-d, %Y")
    run_label  = ref_date.isoformat()

    print("═" * 60)
    print("  DIGEST CAROUSEL — This Week in the Room")
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
    candidate_n = args.top_n * 4

    if args.all_time:
        lots = _query_lots(conn, candidate_n, skip)
    else:
        cutoff_start = (ref_date - timedelta(days=args.days)).isoformat()
        lots = _query_lots(conn, candidate_n, skip,
                           cutoff_start=cutoff_start,
                           cutoff_end=ref_date.isoformat())
        if not lots:
            print(f"  ⚠ No lots in last {args.days} days — falling back to all-time.")
            lots = _query_lots(conn, candidate_n, skip)

    # One lot per artist
    seen: set[str] = set()
    chosen: list[dict] = []
    for lot in lots:
        key = _clean_artist(lot.get("artist") or "").lower()
        if key in seen:
            continue
        seen.add(key)
        chosen.append(lot)
        if len(chosen) >= args.top_n:
            break

    # ── --list mode ─────────────────────────────────────────────────────────────
    if args.list:
        if not chosen:
            print("\n  No candidates found.")
        else:
            print(f"\n  {'#':<4} {'Artist':<30} {'House':<18} {'Hammer':>12} {'%+':>7}")
            print("  " + "─" * 74)
            for i, l in enumerate(chosen, 1):
                pct = _pct_above(l["hammer_usd"], l["estimate_low"])
                print(
                    f"  {i:<4} {_clean_artist(l.get('artist') or '')[:29]:<30} "
                    f"{_clean_house(l.get('auction_house') or '')[:17]:<18} "
                    f"{_fmt(l['hammer_usd']):>12}  {pct:>5.0f}%"
                )
        conn.close()
        return

    if not chosen:
        print("✗ No suitable lots found.")
        conn.close()
        sys.exit(1)

    print(f"\n▸ {len(chosen)} lot(s) selected:")
    for l in chosen:
        pct = _pct_above(l["hammer_usd"], l["estimate_low"])
        print(
            f"  {_clean_artist(l.get('artist') or ''):<32} "
            f"{_fmt(l['hammer_usd']):>12}  +{pct:.0f}%  "
            f"({_clean_house(l.get('auction_house') or '')})"
        )

    # ── AI insight ──────────────────────────────────────────────────────────────
    insight = ""
    if OPENROUTER_KEY:
        print("\n▸ Generating pattern insight...")
        try:
            from ai_content import generate_digest_insight
            insight = generate_digest_insight(chosen) or ""
            if insight:
                print(f"  ✓ {insight[:90]}{'...' if len(insight) > 90 else ''}")
            else:
                print("  ▸ Template insight will be used.")
        except (ImportError, AttributeError):
            pass
        except Exception as e:
            print(f"  ⚠ {e}")

    # ── Render cards ─────────────────────────────────────────────────────────────
    print("\n▸ Rendering cards...")
    import random
    hook     = random.choice(_COVER_HOOKS)
    out_dir  = Path(args.output_dir) / run_label
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    cover      = render_cover_card(chosen, hook, week_label)
    cover_path = out_dir / "00_cover.png"
    cover.save(cover_path)
    paths.append(cover_path)
    print("  ✓ cover card")

    for i, lot in enumerate(chosen, 1):
        card = render_lot_card(lot, i)
        p    = out_dir / f"{i:02d}_lot.png"
        card.save(p)
        paths.append(p)
        print(f"  ✓ lot {i}: {_clean_artist(lot.get('artist') or '')}")

    # ── meta.json ───────────────────────────────────────────────────────────────
    social = _social_captions(chosen, week_label, insight)
    meta   = {
        "date":      run_label,
        "week":      week_label,
        "hook":      hook,
        "insight":   insight,
        "lots": [
            {
                "id":            l.get("id"),
                "artist":        _clean_artist(l.get("artist") or ""),
                "title":         l.get("title"),
                "auction_house": _clean_house(l.get("auction_house") or ""),
                "hammer_usd":    l.get("hammer_usd"),
                "estimate_low":  l.get("estimate_low"),
                "pct_above":     _pct_above(l["hammer_usd"], l["estimate_low"]),
            }
            for l in chosen
        ],
        "captions": social,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    # ── Record in digest_reels ───────────────────────────────────────────────────
    _record_digest(conn, chosen, run_label)
    conn.close()
    print(f"  ✓ {len(chosen)} lot(s) recorded in digest_reels")

    # ── Summary ─────────────────────────────────────────────────────────────────
    print(f"\n✓ {len(paths)} cards saved → {out_dir}")
    print(f"\n  Instagram caption:\n")
    print("  " + social["instagram"].replace("\n", "\n  "))
    print(f"\n  Post with:")
    print(f"    python scripts/post_beat_the_estimate_to_buffer.py "
          f"{out_dir.relative_to(BUSINESS_DIR)} --dry-run")


if __name__ == "__main__":
    main()
