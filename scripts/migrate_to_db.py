"""
One-time migration: import all existing data/*/metadata/*.json files into
the SQLite database, then remove the JSON files from disk.

Run from the repo root:
    uv run python scripts/migrate_to_db.py
"""

import json
from pathlib import Path

from scraper.db import connect, upsert_item

SOURCES = [
    Path("data/vestiaire/metadata"),
    Path("data/hermes/metadata"),
]


def main() -> None:
    conn = connect()
    total = skipped = 0

    for meta_dir in SOURCES:
        if not meta_dir.exists():
            continue
        files = sorted(meta_dir.glob("*.json"))
        print(f"{meta_dir}: {len(files)} files")
        for f in files:
            try:
                product = json.loads(f.read_text())
                if not product.get("id"):
                    product["id"] = product.get("sku", "")
                if not product.get("id") or not product.get("platform"):
                    skipped += 1
                    continue
                upsert_item(conn, product)
                total += 1
            except Exception as e:
                print(f"  skip {f.name}: {e}")
                skipped += 1

    conn.close()
    print(f"\nMigrated {total} items ({skipped} skipped) → data/hermes.db")


if __name__ == "__main__":
    main()
