"""
scrape_lobbying_register.py — Who Owns What
Fetches lobbying budget data from the Bundestag Lobby Register
(lobbyregister.bundestag.de) for all tracked German entities.

Endpoint strategy (tries in order):
  1. JSON API with Accept + XHR headers: GET /suche?q=<name>&pageSize=5
  2. HTML page parse — extract jahresbudget via regex
  Falls through silently if no data found.

Entity list is loaded dynamically from the DB (all German company entities),
not hardcoded — so new companies added by the batch scraper are covered.

Usage:
    python scripts/whoownswhat/scrape_lobbying_register.py
    python scripts/whoownswhat/scrape_lobbying_register.py --db custom.db --dry-run
    python scripts/whoownswhat/scrape_lobbying_register.py --slug volkswagen
"""

import argparse
import json
import re
import sqlite3
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"
REGISTER_BASE    = "https://www.lobbyregister.bundestag.de"
REGISTER_SEARCH  = f"{REGISTER_BASE}/suche"
REGISTER_API     = f"{REGISTER_BASE}/sucheJson"   # open-data JSON endpoint
YEAR = datetime.now(timezone.utc).strftime("%Y")
DELAY = 1.5

_HEADERS = {
    "User-Agent": "WhoOwnsWhat/1.0 public-interest research",
    "Accept": "application/json",
}


def fetch_json(name: str) -> list[dict]:
    """Fetch JSON results from the open-data /sucheJson endpoint."""
    params = urllib.parse.urlencode({
        "q": name,
        "sort": "RELEVANCE_DESC",
    })
    url = f"{REGISTER_API}?{params}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            raw = resp.read().strip()
            if not raw:
                return []
            data = json.loads(raw)
            return data.get("results", [])
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        print(f"    Fetch failed for '{name}': {exc}")
        return []


def extract_budget_from_json(entries: list[dict], entity_name: str) -> tuple[str, str] | tuple[None, None]:
    """
    Extract lobbying financial expenses from the best-matching entry.
    Returns (budget_string, details_page_url) or (None, None).
    New schema: result.financialExpenses.financialExpensesEuro.{from, to}
    """
    name_lower = entity_name.lower()

    def _parse_entry(entry: dict) -> tuple[str, str] | tuple[None, None]:
        fe = entry.get("financialExpenses", {})
        band = fe.get("financialExpensesEuro", {})
        lo = band.get("from")
        hi = band.get("to")
        if lo is None or hi is None:
            return None, None
        budget = normalise_budget(f"{lo}-{hi}")
        url = (
            entry.get("registerEntryDetails", {}).get("detailsPageUrl")
            or REGISTER_SEARCH
        )
        return budget, url

    # First pass: prefer a name match
    for entry in entries:
        identity = entry.get("lobbyistIdentity", {})
        reg_name = identity.get("name", "").lower()
        if entity_name and reg_name and name_lower not in reg_name and reg_name not in name_lower:
            continue
        budget, url = _parse_entry(entry)
        if budget:
            return budget, url

    # Second pass: accept any result
    for entry in entries:
        budget, url = _parse_entry(entry)
        if budget:
            return budget, url

    return None, None


def normalise_budget(raw: str) -> str | None:
    """
    Convert a band or scalar euro amount into a human-readable string.
    Lobbyregister bands are narrow (~€10K), so tight ranges collapse to a
    single midpoint value: '2300001-2310000' → '€2.3M'.
    Wide ranges display as '€5–10M'.
    """
    raw = raw.strip().replace("EUR", "").replace("€", "").replace(" ", "").replace(".", "")
    if not raw or raw in ("-", "0", "null", "keine"):
        return None
    m = re.match(r"^(\d+)-(\d+)$", raw)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
        if low == 0 and high == 0:
            return None
        # Tight band (register uses ~10K steps): collapse to midpoint
        if high - low < 500_000:
            mid = (low + high) / 2
            if mid >= 1_000_000:
                return f"€{mid / 1_000_000:.1f}M".replace(".0M", "M")
            if mid >= 1_000:
                return f"€{mid / 1000:.0f}K"
            return f"€{mid:,.0f}"
        # Wide band: show range
        if high >= 1_000_000:
            return f"€{low // 1_000_000}–{high // 1_000_000}M"
        if high >= 1_000:
            return f"€{low // 1000:,}–{high // 1000:,}K"
        return f"€{low:,}–{high:,}"
    try:
        val = int(re.sub(r"[^\d]", "", raw))
        if val == 0:
            return None
        if val >= 1_000_000:
            return f"€{val / 1_000_000:.1f}M".replace(".0M", "M")
        if val >= 1_000:
            return f"€{val // 1000:,}K"
        return f"€{val:,}"
    except ValueError:
        return raw if raw else None


def scrape_entity(entity_id: str, name: str) -> tuple[str, str] | tuple[None, None]:
    """
    Attempt to find a lobbying budget for an entity.
    Returns (budget_string, details_page_url) or (None, None).
    Strategy: try full name, then first token (e.g. "BMW" from "BMW AG").
    """
    terms = [name]
    first_token = name.split()[0]
    if first_token != name and len(first_token) >= 3:
        terms.append(first_token)

    for term in terms:
        entries = fetch_json(term)
        time.sleep(DELAY)
        if entries:
            budget, url = extract_budget_from_json(entries, name)
            if budget:
                return budget, url

    return None, None


def update_lobbying(
    conn: sqlite3.Connection,
    entity_id: str,
    amount: str,
    source_url: str,
    dry_run: bool = False,
) -> None:
    if dry_run:
        print(f"    [DRY RUN] Would upsert: {entity_id} {YEAR} {amount} → {source_url}")
        return
    cur = conn.cursor()
    cur.execute("SELECT id FROM lobbying WHERE entity_id=? AND year=?", (entity_id, YEAR))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE lobbying SET amount=?, source=?, source_url=? WHERE id=?",
            (amount, "Bundestag Lobbyregister", source_url, row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO lobbying (entity_id,year,amount,currency,source,source_url) VALUES (?,?,?,?,?,?)",
            (entity_id, YEAR, amount, "EUR", "Bundestag Lobbyregister", source_url),
        )


def log_scrape(conn: sqlite3.Connection, entity_id: str, status: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO scrape_log (entity_id,scraper,status,detail) VALUES (?,?,?,?)",
        (entity_id, "lobbying_register", status, detail),
    )


def load_entities(conn: sqlite3.Connection, slug_filter: str | None = None) -> list[tuple[str, str]]:
    """Load German company entities from the DB. Returns [(id, name), ...]."""
    if slug_filter:
        rows = conn.execute(
            "SELECT id, name FROM entities WHERE type='company' AND country='germany' AND id=?",
            (slug_filter,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name FROM entities WHERE type='company' AND country='germany' ORDER BY name"
        ).fetchall()
    return [(r[0], r[1]) for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh lobbying budgets from Bundestag Lobby Register for all German entities."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--slug", help="Only process one entity by slug/id")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")

    entities = load_entities(conn, slug_filter=args.slug)
    if not entities:
        print("No German company entities found in DB. Run scrape_company_batch.py first.")
        conn.close()
        return

    print(f"Refreshing lobbying data for {len(entities)} entities...\n")

    updated = 0
    not_found = 0

    for entity_id, name in entities:
        print(f"  [{entity_id}] {name}")
        budget, url = scrape_entity(entity_id, name)

        if budget:
            print(f"    ✓ {budget}  ({url})")
            update_lobbying(conn, entity_id, budget, url, args.dry_run)
            log_scrape(conn, entity_id, "ok", f"Budget: {budget}")
            updated += 1
        else:
            print(f"    — not found")
            log_scrape(conn, entity_id, "no_change", "No budget data found")
            not_found += 1

        if not args.dry_run:
            conn.commit()

    conn.close()
    print(f"\nDone. Updated: {updated}, not found: {not_found}")


if __name__ == "__main__":
    main()
