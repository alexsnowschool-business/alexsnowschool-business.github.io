"""
scrape_lobbying_register.py — Who Owns What
Scrapes lobbying budget data from the Bundestag Lobby Register
(lobbyregister.bundestag.de) for tracked German entities.

The Register's public API endpoint:
  GET https://lobbyregister.bundestag.de/suche?q=<name>&json=1
  Returns: paginated JSON with registrant data including 'jahresbudget' (annual budget).

Updates the `lobbying` table in SQLite.
Logs results to `scrape_log`.

Usage:
    python scripts/whoownswhat/scrape_lobbying_register.py
    python scripts/whoownswhat/scrape_lobbying_register.py --db custom.db --dry-run
"""

import argparse
import json
import ssl
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"
REGISTER_API = "https://lobbyregister.bundestag.de/suche"
YEAR = datetime.now(timezone.utc).strftime("%Y")

# Map entity_id → search term(s) to try in the register
SEARCH_TERMS: dict[str, list[str]] = {
    "volkswagen":        ["Volkswagen AG"],
    "sap":               ["SAP SE"],
    "siemens":           ["Siemens AG"],
    "deutsche-telekom":  ["Deutsche Telekom AG", "Telekom Deutschland"],
    "bmw":               ["BMW AG", "Bayerische Motoren Werke"],
}


def fetch_register(name: str) -> list[dict]:
    """Fetch matching entries from the Bundestag Lobby Register public JSON endpoint."""
    params = urllib.parse.urlencode({"q": name, "json": "1"})
    url = f"{REGISTER_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "WhoOwnsWhat/1.0 public-interest research"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"    Fetch failed for '{name}': {exc}")
        return []


def extract_budget(entry: dict) -> str | None:
    """
    Extract lobbying budget from a register entry.
    The register reports a budget band, e.g. '5000001-10000000' (EUR).
    We normalise to a human-readable string like '€5–10M'.
    """
    budget_raw = entry.get("jahresbudget") or entry.get("lobbyausgaben") or ""
    if not budget_raw:
        return None

    # Band format: '<lower>-<upper>' in EUR
    try:
        parts = str(budget_raw).split("-")
        if len(parts) == 2:
            low = int(parts[0]) / 1_000_000
            high = int(parts[1]) / 1_000_000
            if high >= 1:
                return f"€{low:.0f}–{high:.0f}M"
            return f"€{int(parts[0]):,}–{int(parts[1]):,}"
        # Single value
        val = int(budget_raw)
        return f"€{val / 1_000_000:.1f}M"
    except (ValueError, TypeError):
        return str(budget_raw)


def update_lobbying(
    conn: sqlite3.Connection,
    entity_id: str,
    year: str,
    amount: str,
    dry_run: bool = False,
) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM lobbying WHERE entity_id=? AND year=?",
        (entity_id, year),
    )
    row = cur.fetchone()
    if dry_run:
        print(f"    [DRY RUN] Would {'update' if row else 'insert'} lobbying: {entity_id} {year} {amount}")
        return

    if row:
        cur.execute(
            "UPDATE lobbying SET amount=?, source=?, source_url=? WHERE id=?",
            (amount, "Bundestag Lobbyregister", "https://lobbyregister.bundestag.de", row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO lobbying (entity_id,year,amount,currency,source,source_url) VALUES (?,?,?,?,?,?)",
            (entity_id, year, amount, "EUR", "Bundestag Lobbyregister",
             "https://lobbyregister.bundestag.de"),
        )


def log_scrape(conn: sqlite3.Connection, entity_id: str, status: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO scrape_log (entity_id,scraper,status,detail) VALUES (?,?,?,?)",
        (entity_id, "lobbying_register", status, detail),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Bundestag Lobby Register for tracked German entities.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")

    updated = 0
    errors = 0

    for entity_id, terms in SEARCH_TERMS.items():
        print(f"\n  Scraping: {entity_id}")
        found = False

        for term in terms:
            results = fetch_register(term)
            time.sleep(1)  # polite delay

            if not results:
                continue

            # Take the first result that looks like a direct name match
            for entry in results if isinstance(results, list) else results.get("results", []):
                name_in_result = (
                    entry.get("name") or entry.get("registrant_name") or ""
                ).lower()
                if term.lower().split()[0] in name_in_result:
                    budget = extract_budget(entry)
                    if budget:
                        print(f"    Found: {budget} for '{term}'")
                        update_lobbying(conn, entity_id, YEAR, budget, args.dry_run)
                        log_scrape(conn, entity_id, "ok", f"Budget {budget} from term '{term}'")
                        found = True
                        updated += 1
                        break
            if found:
                break

        if not found:
            print(f"    No match found for {entity_id}")
            log_scrape(conn, entity_id, "no_change", "No matching register entry found")
            errors += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\nDone. Updated: {updated}, not found: {errors}")


if __name__ == "__main__":
    main()
