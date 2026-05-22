#!/usr/bin/env python3
"""
Auto-reel generator — picks the most shocking auction results from data/art.db,
downloads artwork images, and writes a ready-to-run reel folder for
reel_template/make_reel.py.

Usage (run from alexsnowschool-business/):
    python scripts/auto_reel.py                   # uses this week's scrapes
    python scripts/auto_reel.py --week 2026-05-08 # any date in the target week
    python scripts/auto_reel.py --run             # also renders the reel + captions
    python scripts/auto_reel.py --all-time        # ignore week, pick best ever
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).resolve().parent
BUSINESS_DIR  = SCRIPT_DIR.parent
DB_PATH       = BUSINESS_DIR / "data" / "art.db"
REELS_DIR     = BUSINESS_DIR / "reels"
REEL_TEMPLATE = BUSINESS_DIR / "reel_template"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_price(usd: float) -> str:
    """Format a USD price compactly: $441,000 or $13.8M."""
    if usd >= 1_000_000:
        return f"${usd / 1_000_000:.1f}M"
    return f"${usd:,.0f}"


def _pct_above(hammer: float, low: float) -> float:
    return round((hammer / low - 1) * 100, 1)


def _clean_artist(name: str) -> str:
    """Strip birth-year suffix like '(B. 1953)'."""
    return re.sub(r"\s*\([^)]+\)\s*$", "", name).strip().title()


def _week_bounds(ref_date: date) -> tuple[str, str]:
    """Return (monday, sunday) as ISO strings for the week containing ref_date."""
    monday = ref_date - timedelta(days=ref_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


# ── DB queries ─────────────────────────────────────────────────────────────────

def _query_top_lots(conn: sqlite3.Connection, week_start: str, week_end: str,
                    limit: int = 8) -> list[dict]:
    """Top outperforming lots scraped in the given week, ranked by % above estimate."""
    rows = conn.execute("""
        SELECT artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, scraped_at, auction_house, image_urls,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above,
               source_url
        FROM art_items
        WHERE sale_performance = 'above'
          AND hammer_usd IS NOT NULL
          AND estimate_low IS NOT NULL
          AND estimate_low > 0
          AND substr(scraped_at, 1, 10) BETWEEN ? AND ?
        ORDER BY pct_above DESC
        LIMIT ?
    """, (week_start, week_end, limit)).fetchall()
    return [dict(r) for r in rows]


def _query_alltime_top(conn: sqlite3.Connection, limit: int = 8) -> list[dict]:
    """All-time top outperforming lots — fallback when the week has no data."""
    rows = conn.execute("""
        SELECT artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, scraped_at, auction_house, image_urls,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above,
               source_url
        FROM art_items
        WHERE sale_performance = 'above'
          AND hammer_usd IS NOT NULL
          AND estimate_low IS NOT NULL
          AND estimate_low > 0
        ORDER BY pct_above DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


# ── Image downloading ──────────────────────────────────────────────────────────

def _download_lot_images(lot: dict, images_dir: Path, max_images: int = 8) -> list[Path]:
    """Download all unique images for a single lot. Returns list of saved paths."""
    images_dir.mkdir(parents=True, exist_ok=True)
    raw_urls = json.loads(lot.get("image_urls") or "[]")

    # Deduplicate while preserving order
    seen, urls = set(), []
    for u in raw_urls:
        if u not in seen:
            seen.add(u)
            urls.append(u)

    saved: list[Path] = []
    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=20) as client:
        for i, url in enumerate(urls[:max_images]):
            ext   = ".jpg" if "jpg" in url.lower() or "jpeg" in url.lower() else ".png"
            fname = images_dir / f"src_{i + 1:02d}{ext}"
            try:
                r = client.get(url)
                r.raise_for_status()
                fname.write_bytes(r.content)
                print(f"  ✓ {fname.name}  (image {i + 1}/{len(urls[:max_images])})")
                saved.append(fname)
            except Exception as e:
                print(f"  ✗ {url[:60]}... — {e}")

    return saved


# ── Roman numerals ────────────────────────────────────────────────────────────

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
          "XI", "XII", "XIII", "XIV", "XV", "XVI"]

def _roman(n: int) -> str:
    return _ROMAN[n] if n < len(_ROMAN) else str(n + 1)


# ── Per-frame captions ─────────────────────────────────────────────────────────

# Each entry: (min_pct, question, answer)
# Each entry: (min_pct, [question variants], [answer variants])
# Format vars: {artist} {title} {house} {hammer} {estimate} {pct} {n}
_HOOK_TEMPLATES = [
    (800,
     [
         "nobody priced this right.",
         "the estimate was wrong by {pct}.",
         "the room ignored the catalogue.",
     ],
     [
         "when a result moves this far, it's rarely a surprise to the buyers in the room. "
         "someone had conviction — about the artist, the moment, or both — that the estimate completely missed.",
         "the estimate is set months before the sale. "
         "by auction day, the market had already moved — what looks shocking in the catalogue is the price catching up.",
         "two collectors wanted it. neither was willing to walk away. "
         "when that happens, the estimate becomes irrelevant — the price goes wherever the last bidder stops.",
     ]),

    (500,
     [
         "the estimate was a suggestion.",
         "a {n} result doesn't happen by accident.",
         "the catalogue missed the room by {pct}.",
     ],
     [
         "estimates are set to attract interest, not predict outcomes. "
         "a gap this wide usually means two or more serious collectors decided they couldn't leave without it.",
         "this kind of outperformance signals a market shift the specialists hadn't priced in. "
         "when demand outpaces supply, the estimate stops being a ceiling and becomes a floor.",
         "the auction house put a number on it. "
         "the market put a different number on it — and the market always wins.",
     ]),

    (300,
     [
         "the catalogue got this wrong by {pct}.",
         "the specialists underestimated the room.",
         "priced for safety. sold for ambition.",
     ],
     [
         "specialists price from precedent. "
         "but when an artist's reputation shifts — or a new collector base enters — the catalogue is always the last to know.",
         "a result this far above estimate usually points to something the pre-sale research missed: a fresh buyer, a rediscovered provenance, a cultural moment.",
         "the estimate is backward-looking. "
         "the room is forward-looking. "
         "here, the room was right.",
     ]),

    (150,
     [
         "the room disagreed with the experts.",
         "the house priced it low. the room priced it right.",
         "conviction beat the catalogue.",
     ],
     [
         "auction houses price conservatively to guarantee a sale. "
         "the real number is whatever the most motivated buyer is willing to pay — and here, they were very motivated.",
         "a result this far above estimate isn't luck — it's two collectors who did their homework and arrived ready to pay.",
         "the specialists set a floor. "
         "the bidders set the ceiling. "
         "that gap is where the real market lives.",
     ]),

    (80,
     [
         "the room knew something the catalogue didn't.",
         "more buyers arrived than the estimate assumed.",
         "the market priced what the house wouldn't.",
     ],
     [
         "moderate outperformance usually means more buyers arrived than the estimate assumed. "
         "the house priced for certainty; the market priced for desire.",
         "when you see consistent outperformance in a range, it's a signal — not noise. "
         "the estimate is a floor, and the room was willing to go higher.",
         "the house sets the estimate to sell. "
         "the bidders set the price to own. "
         "those are different numbers — and the difference is the story.",
     ]),

    (40,
     [
         "priced to sell. sold for more.",
         "above estimate — the most common story in the room.",
         "the floor held. the ceiling didn't.",
     ],
     [
         "estimates are floor prices, not forecasts. "
         "the auction house sets a number to guarantee a sale — what happens above that is entirely up to the room.",
         "most lots sell above estimate. "
         "that's not a surprise — it's the system working as designed. "
         "the house prices conservatively; competition does the rest.",
         "a small overshoot is the baseline at auction. "
         "the estimate attracts bidders; the bidders set the price.",
     ]),

    (0,
     [
         "above estimate — even here.",
         "the floor held. just.",
         "sold above the low estimate.",
     ],
     [
         "small overshoots are the most consistent pattern at auction. "
         "when more buyers arrive than expected, the price moves — quietly, but reliably.",
         "even a modest result above estimate confirms demand. "
         "the house priced it right; the room agreed and went a little further.",
         "not every lot is a headline. "
         "but every lot that sells above estimate tells the same story: demand met supply, and then passed it.",
     ]),
]


def _split_phrases(text: str) -> list[str]:
    """Split answer text into sentence fragments for phrase-by-phrase reveal."""
    import re
    parts = re.split(r'(?<=\.) ', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _hook_caption(lot: dict, pct: float) -> tuple[str, str]:
    """Return (question, answer) — randomly selected from per-tier variants."""
    import random
    mult     = round(pct / 100 + 1, 1)
    artist   = _clean_artist(lot.get("artist") or "Unknown")
    title    = (lot.get("title") or "Untitled")[:40]
    house    = (lot.get("auction_house") or "the auction house")
    hammer   = _fmt_price(lot["hammer_usd"])
    est_low  = lot["estimate_low"]
    est_high = lot.get("estimate_high") or est_low
    estimate = f"{_fmt_price(est_low)}–{_fmt_price(est_high)}"

    fmt = dict(
        n=f"{mult:.0f}×",
        artist=artist,
        title=title,
        house=house,
        hammer=hammer,
        estimate=estimate,
        pct=f"{pct:,.0f}%",
    )

    for threshold, q_variants, a_variants in _HOOK_TEMPLATES:
        if pct >= threshold:
            question = random.choice(q_variants).format(**fmt)
            answer   = random.choice(a_variants).format(**fmt)
            return question, answer

    return "the hammer price tells the real story.", "follow the data."


def _build_reveal_sequence(lot: dict, tag_base: str) -> list[dict]:
    """5-frame progressive reveal for a single lot — targets ~25s total.

    Frames:
      1 — estimate line (price reveal starts immediately)
      2 — + sold price
      3 — full data box (+ % above estimate)
      4 — question appears large below the data (no answer yet)
      5 — question shrinks to label, answer dominates in large serif
    """
    hammer        = lot["hammer_usd"]
    est_low       = lot["estimate_low"]
    est_high      = lot.get("estimate_high") or est_low
    pct           = _pct_above(hammer, est_low)
    artist_name   = _clean_artist(lot.get("artist") or "Unknown")
    painting_title = (lot.get("title") or "Untitled")

    tag   = f"{tag_base}  ·  lot I"
    E     = f"estimate: {_fmt_price(est_low)}–{_fmt_price(est_high)}"
    S     = f"sold: {_fmt_price(hammer)}."
    P     = f"+{pct:,.0f}% above estimate."

    question, answer = _hook_caption(lot, pct)
    phrases = _split_phrases(answer)

    def _data(line1="", line2="", line3="", q=None, a="", hold=4.0):
        return {
            "show_caption":  bool(line1 or line2 or line3),
            "tag":           tag,
            "line1":         line1,
            "line2":         line2,
            "line3":         line3,
            "hook_question": q,
            "hook_answer":   a,
            "upper_artist":  artist_name,
            "upper_title":   painting_title,
            "hold_seconds":  hold,
        }

    frames = [
        # 1 — estimate lands
        _data(line1=E),
        # 2 — sold price reveals
        _data(line1=E, line2=S),
        # 3 — outperformance % completes the data box
        _data(line1=E, line2=S, line3=P),
        # 4 — question appears large (no answer yet)
        _data(line1=E, line2=S, line3=P, q=question, hold=4.0),
    ]

    # Phrase-by-phrase answer reveal: each sentence fragment appears in sequence
    for j in range(len(phrases)):
        partial = " ".join(phrases[:j + 1])
        hold = 2.5 if j < len(phrases) - 1 else 6.0
        frames.append(_data(line1=E, line2=S, line3=P, q=question, a=partial, hold=hold))

    return frames


# ── Config generation ──────────────────────────────────────────────────────────

def _generate_config(hook_lot: dict, week_label: str, all_time: bool, reveal: list[dict] | None = None) -> str:
    artist    = _clean_artist(hook_lot.get("artist") or "Unknown")
    title     = (hook_lot.get("title") or "Untitled")[:50]
    hammer    = hook_lot["hammer_usd"]
    est_low   = hook_lot["estimate_low"]
    est_high  = hook_lot.get("estimate_high") or est_low
    pct       = _pct_above(hammer, est_low)
    house     = hook_lot.get("auction_house") or "Auction House"
    sale_name = (hook_lot.get("sale_name") or "Contemporary Sale")[:40]
    scraped   = (hook_lot.get("scraped_at") or "")[:10]

    est_str    = f"estimate: {_fmt_price(est_low)}–{_fmt_price(est_high)}"
    sold_str   = f"sold: {_fmt_price(hammer)}."
    pct_str    = f"+{pct:,.0f}% above estimate."

    tag_line   = "@thehammerprice  ·  weekly results" if not all_time else "@thehammerprice  ·  auction data"
    house_upper = house.upper()
    sale_upper  = sale_name.upper()

    caption_full_line1 = f"the auction house said {_fmt_price(est_low)}. the room said {_fmt_price(hammer)}."
    caption_full_line2 = (
        f"{artist}'s '{title}' — +{pct:,.0f}% above the low estimate. "
        f"this is what happens when the data knows something the catalogue doesn't."
    )
    personal_note = (
        "51% of lots at the major houses sell above estimate. "
        "that's not randomness — it's a pattern, and it's exploitable."
    )
    engagement_hook = (
        "what's the biggest auction surprise you've ever seen? "
        "drop the lot in the comments #thehammerprice #artmarket #auctionresults"
    )

    lines = [
        '"""',
        "╔══════════════════════════════════════════════════════════════╗",
        f"║  REEL CONFIG — auto-generated for week {week_label}",
        f"║  Hook lot: {artist} — {title[:30]}",
        "║  Generated by scripts/auto_reel.py",
        "╚══════════════════════════════════════════════════════════════╝",
        '"""',
        "",
        "CONFIG = {",
        "    # ── Caption — The Shock Number ────────────────────────────",
        f'    "caption_tag":    "{tag_line}",',
        f'    "caption_line1":  "{est_str}",',
        f'    "caption_line2":  "{sold_str}",',
        f'    "caption_line3":  "{pct_str}",',
        "",
        "    # ── Location metadata ─────────────────────────────────────",
        f'    "location_coords": "{house_upper}",',
        f'    "location_name":   "{sale_upper}",',
        f'    "location_season": "{scraped[:4]}  ·  SALE RESULT",',
        '    "frame_label":     "@thehammerprice",',
        "",
        "    # ── Style ─────────────────────────────────────────────────",
        '    "vibe":             "auction_editorial",',
        '    "caption_position": "center",',
        "",
        "    # ── Font overrides ─────────────────────────────────────────",
        '    "fonts_override": {',
        '        "serif_lg":   ("InstrumentSerif-Regular.ttf", 82),',
        '        "serif_med":  ("InstrumentSerif-Italic.ttf",  58),',
        '        "italic_med": ("InstrumentSerif-Italic.ttf",  40),',
        '        "mono":       ("IBMPlexMono-Regular.ttf",      17),',
        '        "mono_sm":    ("IBMPlexMono-Regular.ttf",      14),',
        "    },",
        "",
        "    # ── Per-line colours ──────────────────────────────────────",
        "    \"color_line1\": (210, 200, 178),",
        "    \"color_line2\": (201, 168, 76),",
        "    \"color_line3\": (230, 215, 175),",
        "",
        "    \"caption_all_frames\": False,",
        "",
        "    # ── Pacing — 3fps, ~25s (5 frames × 4s + 4 × 0.5s fade) ───",
        "    \"fps\":          3,",
        "    \"hold_seconds\": 4.0,",
        "    \"fade_seconds\": 0.5,",
        "",
        "    # ── Captions metadata ─────────────────────────────────────",
        '    "topic":          "culture",',
        f'    "location":       "{house}",',
        f'    "season":         "{scraped[:4]}",',
        '    "caption_full":   (',
        f'        "{caption_full_line1}\\n\\n"',
        f'        "{caption_full_line2}"',
        "    ),",
        '    "caption_hero":   "they priced it wrong",',
        f'    "personal_note":  "{personal_note}",',
        f'    "engagement_hook": "{engagement_hook}",',
    ]

    # ── per_frame_captions (reveal sequence) ─────────────────
    if reveal:
        lines.append("")
        lines.append("    # ── Progressive reveal — one entry per frame ─────────────")
        lines.append("    \"per_frame_captions\": [")
        for fc in reveal:
            lines.append("        {")
            for key, val in fc.items():
                lines.append(f'            {repr(key)}: {repr(val)},')
            lines.append("        },")
        lines.append("    ],")

    lines.append("}")
    return "\n".join(lines) + "\n"


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-generate a reel from weekly art auction data")
    parser.add_argument("--week",      default=None, help="ISO date in target week (default: today)")
    parser.add_argument("--all-time",  action="store_true", help="Use all-time top lots instead of weekly")
    parser.add_argument("--run",       action="store_true", help="Run make_reel.py + make_captions.py after generation")
    parser.add_argument("--top-n",     type=int, default=8, help="Max lots to query (default: 8)")
    parser.add_argument("--lot-index", type=int, default=0, help="Which lot to use (0 = top, 1 = 2nd, etc.)")
    args = parser.parse_args()

    # ── Resolve week ───────────────────────────────────────────
    ref_date   = date.fromisoformat(args.week) if args.week else date.today()
    week_start, week_end = _week_bounds(ref_date)
    week_label = f"{week_start} / {week_end}"
    reel_slug  = f"weekly-{week_start}"

    print("═" * 60)
    print("  AUTO-REEL GENERATOR — The Hammer Price")
    if args.all_time:
        print("  Mode: all-time top outperformers")
    else:
        print(f"  Week: {week_label}")
    print("═" * 60)

    if not DB_PATH.exists():
        print(f"✗ Database not found: {DB_PATH}")
        sys.exit(1)

    # ── Query lots ─────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    top_n = max(args.top_n, args.lot_index + 1)
    if args.all_time:
        lots = _query_alltime_top(conn, limit=top_n)
        reel_slug = f"weekly-{date.today().isoformat()}-alltime"
    else:
        lots = _query_top_lots(conn, week_start, week_end, limit=top_n)
        if not lots:
            print(f"\n  No data found for week {week_label}.")
            print("  Falling back to all-time top outperformers.\n")
            lots = _query_alltime_top(conn, limit=top_n)
            reel_slug = f"weekly-{week_start}-fallback"
    conn.close()

    if not lots:
        print("✗ No suitable lots found in database.")
        sys.exit(1)

    if args.lot_index >= len(lots):
        print(f"✗ --lot-index {args.lot_index} out of range (only {len(lots)} lots found)")
        sys.exit(1)

    if args.lot_index > 0:
        reel_slug = reel_slug.replace("alltime", f"alltime-lot{args.lot_index + 1}")
        reel_slug = reel_slug.replace("fallback", f"fallback-lot{args.lot_index + 1}")
        if "alltime" not in reel_slug and "fallback" not in reel_slug:
            reel_slug += f"-lot{args.lot_index + 1}"

    hook = lots[args.lot_index]
    artist = _clean_artist(hook.get("artist") or "Unknown")
    print(f"\n▸ Hook lot: {artist} — {hook.get('title', 'Untitled')[:50]}")
    print(f"  Estimate: {_fmt_price(hook['estimate_low'])}–{_fmt_price(hook.get('estimate_high') or hook['estimate_low'])}")
    print(f"  Hammer:   {_fmt_price(hook['hammer_usd'])}")
    print(f"  Result:   +{_pct_above(hook['hammer_usd'], hook['estimate_low']):,.0f}% above estimate")
    print(f"  House:    {hook.get('auction_house')}")

    # ── Create reel folder ─────────────────────────────────────
    reel_dir   = REELS_DIR / reel_slug
    images_dir = reel_dir / "images"
    output_dir = reel_dir / "output"

    reel_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n▸ Reel folder: {reel_dir}")

    # ── Download all images of the single hook lot ─────────────
    print(f"\n▸ Downloading images for hook lot...")
    src_images = _download_lot_images(hook, reel_dir / "_src", max_images=8)

    if not src_images:
        print("✗ No images downloaded — cannot generate reel.")
        sys.exit(1)

    # ── Build reveal sequence (7 frames) ──────────────────────
    tag_base = "@thehammerprice  ·  weekly results" if not args.all_time else "@thehammerprice  ·  auction data"
    reveal = _build_reveal_sequence(hook, tag_base)

    # Map each reveal frame to an image file (cycle through available sources)
    import shutil
    for i, _ in enumerate(reveal):
        src  = src_images[i % len(src_images)]
        dest = images_dir / f"frame_{i + 1:02d}{src.suffix}"
        shutil.copy2(src, dest)
    n_images = len(reveal)
    print(f"  {len(src_images)} source image(s) → {n_images} frames")

    # ── Write reel_config.py ───────────────────────────────────
    config_path = reel_dir / "reel_config.py"
    config_src  = _generate_config(hook, week_label, args.all_time, reveal=reveal)
    config_path.write_text(config_src)
    print(f"\n▸ Config written: {config_path}")

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  READY TO RENDER")
    print(f"  Reel folder: reels/{reel_slug}/")
    print(f"  Frames: {n_images} (progressive reveal)")
    print()
    print("  To render:")
    print(f"    cd ../reel-automation")
    print(f"    python reel_template/make_reel.py reels/{reel_slug}")
    print(f"    python reel_template/make_captions.py reels/{reel_slug}")
    print("═" * 60)

    # ── Optionally run ─────────────────────────────────────────
    if args.run:
        reel_automation = REEL_TEMPLATE.parent
        print("\n▸ Running make_reel.py...")
        r1 = subprocess.run(
            [sys.executable, str(REEL_TEMPLATE / "make_reel.py"), str(reel_dir)],
            cwd=str(reel_automation),
        )
        if r1.returncode == 0:
            print("\n▸ Running make_captions.py...")
            subprocess.run(
                [sys.executable, str(REEL_TEMPLATE / "make_captions.py"), str(reel_dir)],
                cwd=str(reel_automation),
            )


if __name__ == "__main__":
    main()
