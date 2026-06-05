"""
Import profiles from data/staged_profiles.json into data/art.db.

Only inserts artists that exist in art_items (no orphaned profiles).
Skips artists that already have a profile unless --force is passed.

Usage:
    uv run python scripts/import_staged_profiles.py
    uv run python scripts/import_staged_profiles.py --force   # overwrite existing
    uv run python scripts/import_staged_profiles.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

STAGED_PATH = Path("data/staged_profiles.json")

sys.path.insert(0, ".")
from scraper.art_db import connect, upsert_artist_profile


def normalize(name: str) -> str:
    import re
    _STRIP = re.compile(
        r"\s*\((?:b\.\s*\d{4}|B\.\s*\d{4}|\d{4}\s*[-–]\s*(?:\d{4}|present)|\d{4})\)\s*$",
        re.IGNORECASE,
    )
    return _STRIP.sub("", name).upper().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force",   action="store_true", help="Overwrite existing profiles")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted")
    args = parser.parse_args()

    profiles = json.loads(STAGED_PATH.read_text())
    print(f"Loaded {len(profiles)} staged profiles from {STAGED_PATH}")

    with connect() as conn:
        # Artists in art_items
        known = {
            normalize(row[0])
            for row in conn.execute("SELECT DISTINCT artist FROM art_items WHERE artist IS NOT NULL")
        }
        # Already profiled
        profiled = {
            row[0] for row in conn.execute("SELECT name_key FROM artist_profiles")
        }

        inserted = skipped = not_in_db = 0
        for p in profiles:
            key = p.get("name_key", "").upper().strip()
            if not key or not p.get("bio"):
                continue
            p["name_key"] = key  # ensure DB stores uppercase key
            if key not in known:
                print(f"  SKIP (not in art_items): {key}")
                not_in_db += 1
                continue
            if key in profiled and not args.force:
                print(f"  SKIP (already profiled): {key}")
                skipped += 1
                continue
            if args.dry_run:
                print(f"  WOULD INSERT: {key}")
            else:
                upsert_artist_profile(conn, p)
                print(f"  INSERTED: {key}")
            inserted += 1

    print(f"\nDone — {inserted} {'would be ' if args.dry_run else ''}inserted, "
          f"{skipped} skipped (existing), {not_in_db} not in DB.")


if __name__ == "__main__":
    main()
