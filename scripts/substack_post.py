#!/usr/bin/env python3
"""
On-demand Substack post generator for @thehammerprice.

Pulls a lot from art.db, generates work analysis + art history via AI,
and saves a ready-to-paste markdown draft.

Usage:
    python scripts/substack_post.py --lot-id <id>
    python scripts/substack_post.py --list          # show top lots with their IDs
    python scripts/substack_post.py --lot-id <id> --output-dir path/to/dir
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


def _fmt(usd: float) -> str:
    return f"${usd:,.0f}"


def _fetch_lot(lot_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("""
        SELECT id, artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, auction_house, image_urls, source_url,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above
        FROM art_items
        WHERE id = ?
    """, (lot_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _list_lots(limit: int = 20) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, artist, title, hammer_usd, estimate_low, auction_house, sale_date,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above
        FROM art_items
        WHERE hammer_usd IS NOT NULL AND estimate_low > 0
        ORDER BY pct_above DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    print(f"\n{'ID':<36}  {'Artist':<28}  {'Title':<30}  {'Hammer':>12}  {'%':>6}  Sale Date")
    print("-" * 125)
    for r in rows:
        print(
            f"{r['id']:<36}  {(r['artist'] or '')[:27]:<28}  "
            f"{(r['title'] or '')[:29]:<30}  {_fmt(r['hammer_usd']):>12}  "
            f"{r['pct_above']:>5.0f}%  {r['sale_date'] or ''}"
        )


def _render_markdown(lot: dict, sections: dict) -> str:
    hammer   = _fmt(lot["hammer_usd"])
    est_low  = _fmt(lot["estimate_low"])
    est_high = _fmt(lot.get("estimate_high") or lot["estimate_low"])
    pct      = lot.get("pct_above", 0)
    house    = lot.get("auction_house", "")
    sale     = lot.get("sale_name", "")
    sale_date = lot.get("sale_date", "")
    source   = lot.get("source_url", "")

    title    = sections.get("title") or f"{lot.get('artist', 'Unknown')}: {lot.get('title', 'Untitled')}"
    subtitle = sections.get("subtitle", "")

    lines = [
        f"# {title}",
        f"",
        f"*{subtitle}*" if subtitle else "",
        f"",
        f"---",
        f"",
        f"**{house}**" + (f" · {sale}" if sale else "") + (f" · {sale_date}" if sale_date else "") + "  ",
        f"Estimate: {est_low}–{est_high} · Hammer: **{hammer}** ({pct:.0f}% above low estimate)",
        f"",
        f"---",
        f"",
        f"## The Work",
        f"",
        sections.get("work_analysis", ""),
        f"",
        f"---",
        f"",
        f"## The Artist",
        f"",
        sections.get("art_history", ""),
        f"",
        f"---",
        f"",
        f"*Data: {house}. Lot: [{lot.get('id', '')}]({source}).*" if source else
        f"*Data: {house}.*",
    ]

    return "\n".join(l for l in lines if l is not None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Substack post for an auction lot.")
    parser.add_argument("--lot-id",    help="Lot ID from art.db")
    parser.add_argument("--list",      action="store_true", help="List top lots and their IDs")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Where to save the draft")
    args = parser.parse_args()

    if args.list:
        _list_lots()
        return

    if not args.lot_id:
        parser.error("Provide --lot-id <id> or use --list to browse available lots.")

    lot = _fetch_lot(args.lot_id)
    if not lot:
        print(f"✗ Lot '{args.lot_id}' not found in art.db.")
        sys.exit(1)

    print(f"\n▸ Generating Substack post for:")
    print(f"  {lot.get('artist')} — \"{lot.get('title')}\"")
    print(f"  {_fmt(lot['hammer_usd'])}  ({lot.get('pct_above', 0):.0f}% above estimate)  ·  {lot.get('auction_house')}")

    try:
        from ai_content import generate_substack_post
    except ImportError:
        print("✗ Could not import ai_content — run from the project root.")
        sys.exit(1)

    print("\n▸ Generating content sections...")
    sections = generate_substack_post(lot)

    if not sections:
        print("✗ Content generation failed — check OPENROUTER_API_KEY in .env.")
        sys.exit(1)

    print(f"  ✓ Title:             {sections['title']}")
    print(f"  ✓ Subtitle:          {sections['subtitle'][:80]}...")
    print(f"  ✓ Work analysis:     {len(sections['work_analysis'])} chars")
    print(f"  ✓ Art history:       {len(sections['art_history'])} chars")

    draft_md = _render_markdown(lot, sections)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    artist_slug  = (lot.get("artist") or "unknown").lower().replace(" ", "-").replace("/", "-")[:30]
    title_slug   = (lot.get("title") or "untitled").lower().replace(" ", "-").replace("/", "-")[:40]
    slug         = f"{artist_slug}-{title_slug}"
    filename     = f"{date.today().isoformat()}-{slug}.md"
    out_path  = out_dir / filename

    out_path.write_text(draft_md, encoding="utf-8")
    print(f"\n✓ Draft saved → {out_path}")
    print(f"\n  Open and review, then paste into Substack editor (supports markdown).")


if __name__ == "__main__":
    main()
