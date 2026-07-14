#!/usr/bin/env python3
"""
Quote card carousel — Hermès aesthetic, still images.

Renders 5 independent 1080x1350 (4:5) cards, each with the FULL quote text
visible (no reveal animation — unlike quote_reel.py, this is meant to be a
scroll-stopping grid thumbnail and swipe-through carousel on Instagram, so
every slide has to read completely at a glance). Each card uses a different
piece of art as its background so the set doesn't feel repetitive on swipe.

Usage:
    python scripts/quote_cards.py                          # auto-pick 5 unused quotes
    python scripts/quote_cards.py --account stoicism        # use a different account
    python scripts/quote_cards.py --count 3                 # fewer/more cards
    python scripts/quote_cards.py --dry-run                 # print chosen quotes, do nothing
"""

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPT_DIR   = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
BUSINESS_DIR = SCRIPT_DIR.parent

from quote_reel import (  # noqa: E402 — needs sys.path insert above
    load_font, pick_quote, mark_quote_used, pick_art_image_url, download_image,
    _palette, wrap_quote,
)

OUTPUT_DIR = BUSINESS_DIR / "output" / "quote_cards"

W, H = 1080, 1350


# ── Image pipeline (card-sized copies of quote_reel.py's art prep) ───────────

def prepare_art(art_img: Image.Image | None, palette: dict) -> Image.Image:
    from PIL import ImageEnhance, ImageFilter
    base = Image.new("RGB", (W, H), palette["bg"])
    if art_img is None:
        return base

    aw, ah = art_img.size
    scale = max(W / aw, H / ah)
    nw, nh = int(aw * scale), int(ah * scale)
    art_img = art_img.resize((nw, nh), Image.LANCZOS)
    x = (nw - W) // 2
    y = (nh - H) // 2
    art_img = art_img.crop((x, y, x + W, y + H))

    art_img = ImageEnhance.Color(art_img).enhance(0.90)
    art_img = ImageEnhance.Contrast(art_img).enhance(0.95)
    art_img = ImageEnhance.Brightness(art_img).enhance(0.90)
    r, g, b = art_img.split()
    r = r.point(lambda v: min(255, int(v * 1.04)))
    b = b.point(lambda v: max(0, int(v * 0.88)))
    art_img = Image.merge("RGB", (r, g, b))
    art_img = art_img.filter(ImageFilter.GaussianBlur(radius=3))

    base.paste(art_img)
    return base


def prepare_background(art_img: Image.Image | None, palette: dict) -> Image.Image:
    base = prepare_art(art_img, palette)
    if art_img is None:
        return base

    overlay = Image.new("RGB", (W, H), palette["bg"])
    mask    = Image.new("L", (W, H), 0)
    d       = ImageDraw.Draw(mask)

    center       = H // 2
    band_half    = int(H * 0.34)
    edge_alpha   = 60
    centre_alpha = 160

    for y in range(H):
        dist = abs(y - center)
        if dist <= band_half:
            t     = 1.0 - dist / band_half
            alpha = int(edge_alpha + (centre_alpha - edge_alpha) * t)
        else:
            alpha = edge_alpha
        d.line([(0, y), (W, y)], fill=alpha)

    base.paste(overlay, mask=mask)
    return base


# ── Card rendering ────────────────────────────────────────────────────────────

def render_card(quote: dict, bg: Image.Image, palette: dict,
                handle: str, niche: str, art_artist: str, art_title: str,
                index: int, total: int) -> Image.Image:
    img  = bg.copy().convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    pad_x      = 84
    max_text_w = W - pad_x * 2

    quote_font  = load_font("Lora-Italic.ttf", 54)
    author_font = load_font("InstrumentSerif-Regular.ttf", 32)
    book_font   = load_font("InstrumentSerif-Italic.ttf", 27)
    tag_font    = load_font("InstrumentSans-Italic.ttf", 22)
    open_font   = load_font("Lora-Italic.ttf", 110)
    credit_artist_font = load_font("InstrumentSans-Regular.ttf", 28)
    credit_title_font  = load_font("InstrumentSans-Italic.ttf", 24)
    counter_font       = load_font("InstrumentSans-Italic.ttf", 22)

    lines  = wrap_quote(quote["text"], quote_font, max_text_w, draw)
    line_h = quote_font.size + 14
    total_h = len(lines) * line_h
    center_y = H // 2
    text_top = center_y - total_h // 2

    # Opening quotation mark
    draw.text((pad_x - 8, center_y - 280), "“", font=open_font,
              fill=(*palette["rule"], 60))

    # Artwork credit, top-left — solid backdrop so artist/title stay legible
    # over busy or bright paintings (same technique as beat_the_estimate_cards'
    # kicker label: a gradient scrim isn't reliable against varying brightness).
    if art_artist and art_title:
        artist_text = art_artist.title()
        title_text  = art_title
        if len(title_text) > 42:
            title_text = title_text[:39] + "…"

        a_bbox = draw.textbbox((0, 0), artist_text, font=credit_artist_font)
        t_bbox = draw.textbbox((0, 0), title_text, font=credit_title_font)
        block_w = max(a_bbox[2] - a_bbox[0], t_bbox[2] - t_bbox[0])
        block_h = (a_bbox[3] - a_bbox[1]) + 6 + (t_bbox[3] - t_bbox[1])

        pad = 16
        draw.rectangle(
            [pad_x - pad, 48 - pad, pad_x + block_w + pad, 48 + block_h + pad],
            fill=(*palette["bg"], 210),
        )
        draw.text((pad_x, 48), artist_text, font=credit_artist_font,
                  fill=(*palette["author"], 255))
        draw.text((pad_x, 48 + (a_bbox[3] - a_bbox[1]) + 6), title_text,
                  font=credit_title_font, fill=(*palette["quote"], 220))

    # Slide counter, top-right
    counter = f"{index}/{total}"
    bbox = draw.textbbox((0, 0), counter, font=counter_font)
    cw = bbox[2] - bbox[0]
    draw.text((W - pad_x - cw, 56), counter, font=counter_font,
              fill=(*palette["tag"], 180))

    # Bottom tag
    tag_parts = [p for p in [handle, niche] if p]
    tag_text  = "  ·  ".join(tag_parts) if tag_parts else ""
    if tag_text:
        bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
        tw   = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, H - 72), tag_text, font=tag_font, fill=palette["tag"])

    # Quote lines — full text, no reveal
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=quote_font)
        lw   = bbox[2] - bbox[0]
        x    = (W - lw) // 2
        y    = text_top + i * line_h
        draw.text((x + 2, y + 3), line, font=quote_font, fill=(0, 0, 0, 120))
        draw.text((x, y), line, font=quote_font, fill=(*palette["quote"], 255))

    # Author + book
    rule_y = text_top + total_h + 36
    draw.line([(W // 2 - 50, rule_y), (W // 2 + 50, rule_y)],
              fill=(*palette["rule"], 255), width=1)

    author_text = quote["author"] if quote["author"] else "Unknown"
    bbox = draw.textbbox((0, 0), author_text, font=author_font)
    aw   = bbox[2] - bbox[0]
    ax   = (W - aw) // 2
    draw.text((ax + 1, rule_y + 15), author_text, font=author_font, fill=(0, 0, 0, 100))
    draw.text((ax, rule_y + 14), author_text, font=author_font, fill=(*palette["author"], 255))

    if quote["book"]:
        book_text = quote["book"]
        bbox = draw.textbbox((0, 0), book_text, font=book_font)
        bw   = bbox[2] - bbox[0]
        draw.text(((W - bw) // 2, rule_y + 14 + 38), book_text, font=book_font,
                  fill=(*palette["book"], 255))

    return img


def render_card_set(quotes: list[dict], arts: list[tuple[Image.Image | None, str, str]],
                    palette: dict, handle: str, niche: str, out_dir: Path) -> list[Path]:
    """Render one card per quote. `arts` is a parallel list of (art_img, artist, title)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    total = len(quotes)

    for i, (quote, (art_img, art_artist, art_title)) in enumerate(zip(quotes, arts), start=1):
        bg   = prepare_background(art_img, palette)
        card = render_card(quote, bg, palette, handle, niche, art_artist, art_title, i, total)
        path = out_dir / f"{i:02d}_quote.png"
        card.convert("RGB").save(path, "PNG")
        paths.append(path)

    return paths


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Quote card carousel generator")
    parser.add_argument("--account", default="lifequoteshere",
                        help="Account slug matching accounts/<slug>.yaml")
    parser.add_argument("--count",   type=int, default=5, help="Number of cards to render")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print chosen quotes, do nothing else")
    args = parser.parse_args()

    import account_config
    try:
        cfg = account_config.load(args.account)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    palette   = _palette(cfg)
    handle    = cfg.get("handle", "")
    niche     = cfg.get("niche", "")
    QUOTES_DB = BUSINESS_DIR / cfg.get("quotes_db", "data/quotes.db")
    ART_DB    = BUSINESS_DIR / cfg.get("art_db",    "data/art.db")

    if not QUOTES_DB.exists():
        print(f"Error: quotes database not found at {QUOTES_DB}")
        sys.exit(1)

    q_conn   = sqlite3.connect(QUOTES_DB)
    art_conn = sqlite3.connect(ART_DB)

    quotes: list[dict] = []
    seen_ids: set[int] = set()
    for _ in range(args.count):
        quote = pick_quote(q_conn)
        if not quote or quote["id"] in seen_ids:
            break
        seen_ids.add(quote["id"])
        quotes.append(quote)

    if not quotes:
        print("No unused quotes available. Run: python scraper/goodreads_scraper.py")
        q_conn.close()
        art_conn.close()
        sys.exit(1)

    print(f"\nPicked {len(quotes)} quote(s):")
    for q in quotes:
        print(f"  #{q['id']}  {q['text'][:60]}{'…' if len(q['text']) > 60 else ''}  — {q['author']}")

    if args.dry_run:
        q_conn.close()
        art_conn.close()
        return

    # ── Pick a distinct art background per card ────────────────
    arts: list[tuple[Image.Image | None, str, str]] = []
    used_urls: set[str] = set()
    for _ in quotes:
        art_result = None
        for _attempt in range(10):
            candidate = pick_art_image_url(art_conn, only_paintings=True)
            if not candidate:
                break
            if candidate[0] not in used_urls:
                art_result = candidate
                break
        if art_result:
            img_url, art_artist, art_title = art_result
            used_urls.add(img_url)
            print(f"  Art: {art_artist} — {art_title}")
            art_img = download_image(img_url)
            arts.append((art_img, art_artist, art_title))
        else:
            arts.append((None, "", ""))

    art_conn.close()

    # ── Output folder ─────────────────────────────────────────
    import reel_utils
    slug = reel_utils.make_slug(f"{quotes[0]['author']} {quotes[0]['text'][:30]}")
    folder_name = f"cards-{date.today().isoformat()}_{slug}"
    out_dir = OUTPUT_DIR / folder_name
    print(f"\n  Output: {out_dir}")

    card_paths = render_card_set(quotes, arts, palette, handle, niche, out_dir)

    meta = {
        "quotes": [
            {
                "id": q["id"], "text": q["text"], "author": q["author"], "book": q["book"],
                "art_artist": a[1], "art_title": a[2],
            }
            for q, a in zip(quotes, arts)
        ],
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    print(f"\n  {len(card_paths)} cards saved → {out_dir}")

    for quote in quotes:
        mark_quote_used(q_conn, quote["id"])
    q_conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
