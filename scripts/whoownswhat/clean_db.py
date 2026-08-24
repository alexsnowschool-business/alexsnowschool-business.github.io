"""
clean_db.py — Who Owns What
Cleans up placeholder and boilerplate data from whoownswhat.db.

Operations:
  1. Delete all political_spending rows (all are Parteiengesetz §25 boilerplate)
  2. Normalise sector "—" → NULL
  3. Normalise headquarters "Germany" (bare country, no city) → NULL
  4. Clear empty-string market_cap / employees / founded fields → NULL

Usage:
    python scripts/whoownswhat/clean_db.py
    python scripts/whoownswhat/clean_db.py --dry-run
"""

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"


def run_cleanup(conn: sqlite3.Connection, dry_run: bool = False) -> None:
    cur = conn.cursor()
    results = {}

    # ── 1. Political spending table ──────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM political_spending")
    count = cur.fetchone()[0]
    results["political_spending deleted"] = count
    if not dry_run:
        cur.execute("DELETE FROM political_spending")

    # ── 2. Sector "—" → NULL ────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM entities WHERE sector = '—'")
    count = cur.fetchone()[0]
    results["sector '—' → NULL"] = count
    if not dry_run:
        cur.execute("UPDATE entities SET sector = NULL WHERE sector = '—'")

    # ── 3. Headquarters bare "Germany" → NULL ───────────────────────────────
    cur.execute("SELECT COUNT(*) FROM entities WHERE headquarters = 'Germany'")
    count = cur.fetchone()[0]
    results["headquarters 'Germany' → NULL"] = count
    if not dry_run:
        cur.execute("UPDATE entities SET headquarters = NULL WHERE headquarters = 'Germany'")

    # ── 4. Empty-string scalar fields → NULL ────────────────────────────────
    for field in ("market_cap", "employees", "founded"):
        try:
            cur.execute(f"SELECT COUNT(*) FROM entities WHERE {field} = ''")
            count = cur.fetchone()[0]
            results[f"{field} '' → NULL"] = count
            if not dry_run:
                cur.execute(f"UPDATE entities SET {field} = NULL WHERE {field} = ''")
        except sqlite3.OperationalError:
            pass  # column may not exist

    # ── Report ───────────────────────────────────────────────────────────────
    tag = "[DRY RUN] " if dry_run else ""
    for key, val in results.items():
        print(f"  {tag}{key}: {val} rows")

    if not dry_run:
        conn.commit()
        print("\nCleanup committed.")
    else:
        print("\nDry run — no changes written.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean placeholder data from whoownswhat.db")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    print(f"Cleaning {args.db}\n")
    run_cleanup(conn, dry_run=args.dry_run)
    conn.close()


if __name__ == "__main__":
    main()
