#!/usr/bin/env python3
"""
Recurring "Beat the Estimate" Substack roundup for @thehammerprice.

Picks the lots that cleared their low estimate by the widest margin among
recently-scraped rows, generates AI commentary, and saves a ready-to-paste
markdown draft. Distinct from substack_post.py (which is a single-lot deep
dive) — this is the multi-lot data column described in
research-docs/analytics-roadmap.md.

`sale_date` coverage is still partial/coarse (see analytics-roadmap.md), so
"this week's" cohort is defined by `scraped_at` — when the lot entered the
database — rather than the actual auction date. That lines up with how the
pipeline actually runs (scrape-art.yml, twice weekly) even though it's not
the same as "sold this week".

Usage:
    python scripts/beat_the_estimate.py --list             # preview candidates
    python scripts/beat_the_estimate.py --run              # generate + save draft
    python scripts/beat_the_estimate.py --run --top-n 8 --days 10
"""

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent

load_dotenv(BUSINESS_DIR / ".env", override=False)

DB_PATH    = BUSINESS_DIR / "data" / "art.db"
OUTPUT_DIR = BUSINESS_DIR / "output" / "substack"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS beat_the_estimate_posts (
    lot_id    TEXT PRIMARY KEY,
    posted_at TEXT DEFAULT (datetime('now'))
);
"""


def _fmt(usd: float) -> str:
    return f"${usd:,.0f}"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _candidates(conn: sqlite3.Connection, days: int, top_n: int) -> list[dict]:
    """
    Top outperformers among lots scraped in the last `days` days, excluding
    lots already featured in a previous roundup. Widens the window once if
    that yields nothing (a scrape didn't land, or every recent lot was
    already featured) rather than shipping an empty post.
    """
    query = """
        SELECT id, artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, auction_house, image_urls, source_url,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above
        FROM art_items
        WHERE hammer_usd IS NOT NULL AND estimate_low > 0
          AND artist IS NOT NULL AND artist != ''
          AND scraped_at >= datetime('now', ?)
          AND id NOT IN (SELECT lot_id FROM beat_the_estimate_posts)
        ORDER BY pct_above DESC
        LIMIT ?
    """
    rows = conn.execute(query, (f"-{days} days", top_n)).fetchall()
    if not rows and days < 30:
        return _candidates(conn, days=30, top_n=top_n)
    return [dict(r) for r in rows]


def _list_candidates(days: int, top_n: int) -> None:
    conn = _connect()
    lots = _candidates(conn, days, top_n)
    conn.close()

    if not lots:
        print("No unfeatured candidates found — every recent overperformer has already run.")
        return

    print(f"\n{'ID':<36}  {'Artist':<28}  {'Title':<30}  {'Hammer':>12}  {'%':>6}")
    print("-" * 120)
    for lot in lots:
        print(
            f"{lot['id']:<36}  {(lot['artist'] or '')[:27]:<28}  "
            f"{(lot['title'] or '')[:29]:<30}  {_fmt(lot['hammer_usd']):>12}  "
            f"{lot['pct_above']:>5.0f}%"
        )


def _render_markdown(lots: list[dict], sections: dict) -> str:
    title    = sections.get("title") or f"Beat the Estimate — {date.today().isoformat()}"
    subtitle = sections.get("subtitle", "")
    blurbs   = sections.get("blurbs") or [""] * len(lots)

    lines = [
        f"# {title}",
        "",
        f"*{subtitle}*" if subtitle else "",
        "",
        "---",
        "",
        sections.get("intro", ""),
        "",
        "---",
        "",
    ]

    for i, (lot, blurb) in enumerate(zip(lots, blurbs), start=1):
        hammer   = _fmt(lot["hammer_usd"])
        est_low  = _fmt(lot["estimate_low"])
        est_high = _fmt(lot.get("estimate_high") or lot["estimate_low"])
        house    = lot.get("auction_house", "")
        sale     = lot.get("sale_name", "")
        source   = lot.get("source_url", "")

        lines += [
            f"## {i}. {lot.get('artist', 'Unknown')} — {lot.get('title', 'Untitled')}",
            "",
            f"**{house}**" + (f" · {sale}" if sale else "") + "  ",
            f"Estimate: {est_low}–{est_high} · Hammer: **{hammer}** ({lot['pct_above']:.0f}% above low estimate)",
            "",
            blurb,
            "",
            f"*[View lot]({source})*" if source else "",
            "",
        ]

    lines += [
        "---",
        "",
        sections.get("closing", ""),
        "",
        "---",
        "",
        "*Data: auction house results pages, aggregated in The Hammer Price database.*",
    ]

    return "\n".join(l for l in lines if l is not None)


def _mark_posted(conn: sqlite3.Connection, lots: list[dict]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO beat_the_estimate_posts (lot_id) VALUES (?)",
        [(lot["id"],) for lot in lots],
    )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a 'Beat the Estimate' Substack roundup.")
    parser.add_argument("--list",  action="store_true", help="Preview candidates without generating a draft")
    parser.add_argument("--run",   action="store_true", help="Generate the draft and record featured lots")
    parser.add_argument("--top-n", type=int, default=5, help="Number of lots to feature (default: 5)")
    parser.add_argument("--days",  type=int, default=7,  help="Lookback window in days by scraped_at (default: 7)")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    if not args.list and not args.run:
        parser.error("Specify --list to preview or --run to generate a draft.")

    if args.list:
        _list_candidates(args.days, args.top_n)
        return

    conn = _connect()
    lots = _candidates(conn, args.days, args.top_n)
    if not lots:
        print("No unfeatured candidates found — nothing to generate.")
        conn.close()
        return

    print(f"\n▸ Generating 'Beat the Estimate' roundup for {len(lots)} lots:")
    for lot in lots:
        print(f"  {lot['artist']} — \"{lot['title']}\"  {_fmt(lot['hammer_usd'])}  ({lot['pct_above']:.0f}% above)")

    try:
        from ai_content import generate_beat_the_estimate_post
    except ImportError:
        print("✗ Could not import ai_content — run from the project root.")
        conn.close()
        sys.exit(1)

    print("\n▸ Generating content sections...")
    sections = generate_beat_the_estimate_post(lots)

    if not sections:
        print("✗ Content generation failed — check OPENROUTER_API_KEY in .env.")
        conn.close()
        sys.exit(1)

    print(f"  ✓ Title: {sections['title']}")

    draft_md = _render_markdown(lots, sections)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}-beat-the-estimate.md"
    out_path.write_text(draft_md, encoding="utf-8")

    _mark_posted(conn, lots)
    conn.close()

    print(f"\n✓ Draft saved → {out_path}")
    print("  Open and review, then paste into Substack editor (supports markdown).")


if __name__ == "__main__":
    main()
