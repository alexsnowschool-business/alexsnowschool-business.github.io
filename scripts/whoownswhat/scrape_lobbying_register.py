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
REGISTER_BASE = "https://www.lobbyregister.bundestag.de"
REGISTER_API  = f"{REGISTER_BASE}/suche"
YEAR = datetime.now(timezone.utc).strftime("%Y")
DELAY = 1.5

_HEADERS_JSON = {
    "User-Agent": "WhoOwnsWhat/1.0 public-interest research",
    "Accept": "application/json, text/json",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": REGISTER_API,
}
_HEADERS_HTML = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "de,en;q=0.5",
}


def fetch_json(name: str) -> list[dict]:
    """Try to get JSON results from the register search API."""
    params = urllib.parse.urlencode({
        "q": name,
        "pageSize": "5",
        "pageNumber": "0",
        "status": "ALLE",
    })
    url = f"{REGISTER_API}?{params}"
    req = urllib.request.Request(url, headers=_HEADERS_JSON)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if not raw:
                return []
            if "json" not in content_type.lower():
                return []
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            return data.get("content", data.get("results", data.get("items", [])))
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        print(f"    JSON fetch failed for '{name}': {exc}")
        return []


def fetch_html(name: str) -> str:
    """Fetch the HTML search page as fallback."""
    params = urllib.parse.urlencode({"q": name})
    url = f"{REGISTER_API}?{params}"
    req = urllib.request.Request(url, headers=_HEADERS_HTML)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        print(f"    HTML fetch failed for '{name}': {exc}")
        return ""


def parse_budget_from_html(html: str) -> str | None:
    """Extract annual budget from lobbyregister HTML page."""
    patterns = [
        r'"jahresbudget"\s*:\s*"([^"]+)"',
        r'"lobbyausgaben"\s*:\s*"([^"]+)"',
        r'jahresbudget[^>]*>([^<]+)<',
        r'Jahresbudget[:\s]+([€\d\.\,\s]+(?:Mio|Tsd|EUR)?)',
        r'(\d{4,9})-(\d{4,9})',   # raw band like 1000001-5000000
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            return normalise_budget(m.group(1).strip())
    return None


def extract_budget_from_json(entries: list[dict]) -> str | None:
    """Extract and normalise the budget from the first matching JSON entry."""
    for entry in entries:
        raw = (
            entry.get("jahresbudget") or
            entry.get("lobbyausgaben") or
            entry.get("annualBudget") or
            entry.get("budget") or ""
        )
        if raw:
            return normalise_budget(str(raw))
    return None


def normalise_budget(raw: str) -> str | None:
    """Convert '5000001-10000000' → '€5–10M', '29000000' → '€29M'."""
    raw = raw.strip().replace("EUR", "").replace("€", "").replace(" ", "").replace(".", "")
    if not raw or raw in ("-", "0", "null", "keine"):
        return None
    m = re.match(r"^(\d+)-(\d+)$", raw)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
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
            return f"€{val // 1_000_000}M"
        if val >= 1_000:
            return f"€{val // 1000:,}K"
        return f"€{val:,}"
    except ValueError:
        return raw if raw else None


def scrape_entity(entity_id: str, name: str) -> str | None:
    """
    Attempt to find a lobbying budget for an entity. Returns budget string or None.
    Strategy: JSON API → HTML parse → try shorter name variant.
    """
    # Build search terms: full name + first token (e.g. "BMW" from "BMW AG")
    terms = [name]
    first_token = name.split()[0]
    if first_token != name and len(first_token) >= 3:
        terms.append(first_token)

    for term in terms:
        # 1. JSON API
        entries = fetch_json(term)
        time.sleep(DELAY)
        if entries:
            budget = extract_budget_from_json(entries)
            if budget:
                return budget

        # 2. HTML fallback
        html = fetch_html(term)
        time.sleep(DELAY)
        if html:
            budget = parse_budget_from_html(html)
            if budget:
                return budget

    return None


def update_lobbying(
    conn: sqlite3.Connection,
    entity_id: str,
    amount: str,
    dry_run: bool = False,
) -> None:
    if dry_run:
        print(f"    [DRY RUN] Would upsert: {entity_id} {YEAR} {amount}")
        return
    cur = conn.cursor()
    cur.execute("SELECT id FROM lobbying WHERE entity_id=? AND year=?", (entity_id, YEAR))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE lobbying SET amount=?, source=?, source_url=? WHERE id=?",
            (amount, "Bundestag Lobbyregister", REGISTER_BASE, row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO lobbying (entity_id,year,amount,currency,source,source_url) VALUES (?,?,?,?,?,?)",
            (entity_id, YEAR, amount, "EUR", "Bundestag Lobbyregister", REGISTER_BASE),
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
        budget = scrape_entity(entity_id, name)

        if budget:
            print(f"    ✓ {budget}")
            update_lobbying(conn, entity_id, budget, args.dry_run)
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
