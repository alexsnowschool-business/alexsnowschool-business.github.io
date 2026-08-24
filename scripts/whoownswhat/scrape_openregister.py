"""
scrape_openregister.py — Who Owns What
Enriches German company entities using the OpenRegister API
(openregister.de) — free plan: 500 credits/month.

Credit budget per run:
  - Autocomplete ID lookup:  1 credit  (cached after first find — never repeated)
  - Company details:        10 credits (only fetched when data is missing)

Monthly breakdown at 500 credits:
  - ID lookups for all 61 companies: ~61 credits (one-time)
  - Company details for ~43 per month: ~430 credits
  → Comfortably within 500/month free tier.

Fields populated from OpenRegister:
  entities.sector        ← WZ2025 industry classification
  entities.headquarters  ← city from registered address
  entities.founded       ← incorporated_at date (YYYY-MM-DD)
  entities.employees     ← latest indicator value
  entities.revenue       ← latest indicator value (EUR)

Also stores management/directors in scrape_log for reference.

Usage:
    OPENREGISTER_API_KEY=xxx python scripts/whoownswhat/scrape_openregister.py
    python scripts/whoownswhat/scrape_openregister.py --dry-run
    python scripts/whoownswhat/scrape_openregister.py --slug volkswagen
    python scripts/whoownswhat/scrape_openregister.py --limit 10
"""

import argparse
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_DB  = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"
API_BASE    = "https://api.openregister.de/v1"
DELAY       = 1.5   # seconds between API calls
MAX_PER_RUN = 45    # hard cap to avoid over-spending credits in one run

# ── Auth ─────────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    key = os.environ.get("OPENREGISTER_API_KEY", "").strip()
    if not key:
        raise SystemExit("OPENREGISTER_API_KEY env var not set")
    return key


def make_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "WhoOwnsWhat/1.0 public-interest research",
    }


# ── DB helpers ────────────────────────────────────────────────────────────────

def ensure_openregister_id_column(conn: sqlite3.Connection) -> None:
    """Add openregister_id column if it doesn't exist yet (idempotent)."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(entities)").fetchall()]
    if "openregister_id" not in cols:
        conn.execute("ALTER TABLE entities ADD COLUMN openregister_id TEXT")
        conn.commit()


def get_cached_or_id(conn: sqlite3.Connection, entity_id: str) -> str | None:
    row = conn.execute(
        "SELECT openregister_id FROM entities WHERE id=?", (entity_id,)
    ).fetchone()
    return row[0] if row and row[0] else None


def save_openregister_id(conn: sqlite3.Connection, entity_id: str, or_id: str) -> None:
    conn.execute(
        "UPDATE entities SET openregister_id=? WHERE id=?", (or_id, entity_id)
    )
    conn.commit()


def needs_enrichment(conn: sqlite3.Connection, entity_id: str) -> bool:
    """Return True if any of sector / headquarters / founded / employees is NULL."""
    row = conn.execute(
        """SELECT sector, headquarters, founded, employees
           FROM entities WHERE id=?""",
        (entity_id,)
    ).fetchone()
    if not row:
        return False
    return any(v is None for v in row)


# ── API calls ─────────────────────────────────────────────────────────────────

def api_get(path: str, headers: dict) -> dict | None:
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 402:
            raise SystemExit("OpenRegister: out of credits (402). Stopping to preserve budget.")
        if exc.code == 429:
            print(f"    Rate limited (429) — waiting 60s")
            time.sleep(60)
            return None
        print(f"    HTTP {exc.code} for {path}")
        return None
    except Exception as exc:
        print(f"    Request failed for {path}: {exc}")
        return None


def autocomplete(name: str, headers: dict) -> str | None:
    """Find OpenRegister company ID via autocomplete (1 credit). Returns first active match."""
    params = urllib.parse.urlencode({"query": name})
    url = f"{API_BASE}/autocomplete/company?{params}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 402:
            raise SystemExit("OpenRegister: out of credits (402). Stopping.")
        print(f"    Autocomplete HTTP {exc.code} for '{name}'")
        return None
    except Exception as exc:
        print(f"    Autocomplete failed for '{name}': {exc}")
        return None

    results = data if isinstance(data, list) else data.get("results", [])
    # Prefer active German company whose name matches
    name_lower = name.lower()
    for r in results:
        r_name = (r.get("name") or "").lower()
        if r.get("active") and (name_lower in r_name or r_name in name_lower):
            return r.get("company_id")
    # Fallback: first result
    return results[0].get("company_id") if results else None


def fetch_company_details(or_id: str, headers: dict) -> dict | None:
    return api_get(f"/company/{urllib.parse.quote(or_id)}", headers)


def fetch_financials(or_id: str, headers: dict) -> dict | None:
    return api_get(f"/company/{urllib.parse.quote(or_id)}/financials", headers)


# ── Data extraction ───────────────────────────────────────────────────────────

def extract_sector(data: dict) -> str | None:
    """Extract WZ2025 industry description from company data."""
    codes = data.get("industry_codes") or []
    for code in codes:
        # Prefer English label, fall back to German
        label = code.get("label_en") or code.get("label_de") or code.get("label")
        if label:
            return label.strip()
    # Fall back to purpose field (truncate to ~80 chars)
    purpose = data.get("purpose") or (data.get("purposes") or [{}])
    if isinstance(purpose, list) and purpose:
        purpose = purpose[0].get("purpose", "")
    if isinstance(purpose, str) and purpose:
        return purpose[:80].rstrip()
    return None


def extract_headquarters(data: dict) -> str | None:
    """Extract city from registered address."""
    addr = data.get("address") or {}
    if isinstance(addr, list) and addr:
        addr = addr[0]
    city    = addr.get("city") or ""
    country = addr.get("country") or ""
    if city and city.lower() not in ("germany", "deutschland"):
        return city.strip()
    return None


def extract_founded(data: dict) -> str | None:
    raw = data.get("incorporated_at") or ""
    if raw:
        return str(raw)[:10]  # YYYY-MM-DD → YYYY
    return None


def extract_employees_revenue(indicators: list) -> tuple[str | None, str | None]:
    """Return (employees, revenue) from the latest indicators entry."""
    if not indicators:
        return None, None
    latest = indicators[0]  # sorted latest-first by API
    emp = latest.get("employees")
    rev = latest.get("revenue")   # value in cents
    emp_str = f"{int(emp):,}" if emp else None
    rev_str = None
    if rev:
        eur = int(rev) / 100
        if eur >= 1_000_000_000:
            rev_str = f"€{eur / 1_000_000_000:.1f}B".replace(".0B", "B")
        elif eur >= 1_000_000:
            rev_str = f"€{eur / 1_000_000:.0f}M"
        else:
            rev_str = f"€{eur:,.0f}"
    return emp_str, rev_str


# ── Per-entity scrape ─────────────────────────────────────────────────────────

def scrape_entity(
    entity_id: str,
    name: str,
    headers: dict,
    conn: sqlite3.Connection,
    dry_run: bool,
) -> bool:
    """Returns True if any data was written."""
    print(f"  [{entity_id}] {name}")

    # 1. Get or find OpenRegister ID (1 credit if not cached)
    or_id = get_cached_or_id(conn, entity_id)
    if not or_id:
        or_id = autocomplete(name, headers)
        time.sleep(DELAY)
        if not or_id:
            print(f"    — not found in OpenRegister")
            return False
        print(f"    ID: {or_id}")
        if not dry_run:
            save_openregister_id(conn, entity_id, or_id)
    else:
        print(f"    ID cached: {or_id}")

    # 2. Skip if all key fields already populated
    if not needs_enrichment(conn, entity_id):
        print(f"    — already fully enriched, skipping")
        return False

    # 3. Fetch company details (10 credits)
    data = fetch_company_details(or_id, headers)
    time.sleep(DELAY)
    if not data:
        print(f"    — company details fetch failed")
        return False

    sector   = extract_sector(data)
    hq       = extract_headquarters(data)
    founded  = extract_founded(data)

    # 4. Fetch financials for employees + revenue (10 credits)
    fin_data  = fetch_financials(or_id, headers)
    time.sleep(DELAY)
    indicators = (fin_data or {}).get("indicators", [])
    employees, revenue = extract_employees_revenue(indicators)

    # 5. Report / write
    updates = {k: v for k, v in {
        "sector":       sector,
        "headquarters": hq,
        "founded":      founded,
        "employees":    employees,
        "revenue":      revenue,
    }.items() if v}

    if not updates:
        print(f"    — no new data extracted")
        return False

    for k, v in updates.items():
        print(f"    ✓ {k}: {v}")

    if not dry_run:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(
            f"UPDATE entities SET {set_clause} WHERE id=?",
            (*updates.values(), entity_id)
        )
        conn.commit()

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich German company data from OpenRegister API"
    )
    parser.add_argument("--db",      default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--slug",    help="Only process one entity by id")
    parser.add_argument("--limit",   type=int, default=MAX_PER_RUN,
                        help=f"Max entities to process (default {MAX_PER_RUN})")
    args = parser.parse_args()

    api_key = get_api_key()
    headers = make_headers(api_key)

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_openregister_id_column(conn)

    if args.slug:
        rows = conn.execute(
            "SELECT id, name FROM entities WHERE type='company' AND country='germany' AND id=?",
            (args.slug,)
        ).fetchall()
    else:
        # Prioritise: no OR ID yet first (need ID lookup cheaply), then missing data
        rows = conn.execute(
            """SELECT id, name FROM entities
               WHERE type='company' AND country='germany'
               ORDER BY
                 CASE WHEN openregister_id IS NULL THEN 0 ELSE 1 END,
                 CASE WHEN sector IS NULL THEN 0 ELSE 1 END,
                 name"""
        ).fetchall()

    rows = rows[:args.limit]

    if not rows:
        print("No entities found.")
        conn.close()
        return

    print(f"Enriching {len(rows)} entities from OpenRegister...\n")
    enriched = skipped = 0

    for entity_id, name in rows:
        result = scrape_entity(entity_id, name, headers, conn, args.dry_run)
        if result:
            enriched += 1
        else:
            skipped += 1

    conn.close()
    print(f"\nDone. Enriched: {enriched}, skipped/not found: {skipped}")


if __name__ == "__main__":
    main()
