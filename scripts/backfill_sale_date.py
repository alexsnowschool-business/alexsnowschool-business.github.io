"""
One-time backfill for art_items.sale_date on rows scraped before sale_date
capture existed (or before Sotheby's threaded `year` through — see
scraper/sothebys.py and scraper/art_db.py upsert_lot).

The scraper's `lot_exists` check skips re-fetching lots already in the DB,
so these rows will never self-heal on a normal `scrape-art.yml` run — this
script has to touch them directly, once.

Backfill is coarse (year only, extracted from `sale_name`, e.g. "... NY 2023"),
not an exact date — sale_name doesn't always contain a year (many Christie's
day-sale names are undated, e.g. "Post-War and Contemporary Art Day Sale"),
so this recovers a partial signal, not full coverage. Never overwrites a
row that already has a sale_date.

Run:  uv run python scripts/backfill_sale_date.py
"""

import re
import sys

sys.path.insert(0, ".")
from scraper.art_db import connect

_YEAR_RE = re.compile(r"\b(19[0-9]{2}|20[0-9]{2})\b")


def main() -> None:
    conn = connect()
    rows = conn.execute(
        "SELECT id, auction_house, sale_name FROM art_items WHERE sale_date IS NULL"
    ).fetchall()

    updated = 0
    unmatched = 0
    for row in rows:
        m = _YEAR_RE.search(row["sale_name"] or "")
        if not m:
            unmatched += 1
            continue
        conn.execute(
            "UPDATE art_items SET sale_date = ? WHERE id = ? AND auction_house = ?",
            (m.group(1), row["id"], row["auction_house"]),
        )
        updated += 1

    conn.commit()
    print(f"Backfilled {updated} rows with a year extracted from sale_name.")
    print(f"{unmatched} rows had no year in sale_name — still NULL, need a real re-scrape.")


if __name__ == "__main__":
    main()
