"""
scrape_company_batch.py — Who Owns What
Processes N companies from the company_queue each run.

Data sources (all free, no authentication required):
  1. Wikipedia REST API  — summary text, thumbnail
  2. Wikidata API        — structured facts (employees, revenue, CEO, HQ, founded)
  3. Bundestag Lobbyregister — lobbying budget (German-listed companies only)

Run by the daily CI workflow after discover_germany.py has been run at least once.

Usage:
    python scripts/whoownswhat/scrape_company_batch.py            # 5 companies
    python scripts/whoownswhat/scrape_company_batch.py --batch 10
    python scripts/whoownswhat/scrape_company_batch.py --dry-run
    python scripts/whoownswhat/scrape_company_batch.py --slug bayer  # one specific company
"""

import argparse
import json
import re
import socket
import sqlite3
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# macOS ships with an outdated SSL cert bundle; create a permissive context for local use.
# In GitHub Actions (Ubuntu), the system bundle is up-to-date and this is not needed.
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"
LOBBYREGISTER_API = "https://lobbyregister.bundestag.de/suche"

# Polite delay between API calls (seconds)
DELAY = 1.2

NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


# ── HTTP HELPERS ───────────────────────────────────────────────────────────

def http_get(url: str, timeout: int = 15) -> dict | None:
    """Fetch JSON from a URL. Returns None on error."""
    headers = {
        "User-Agent": (
            "WhoOwnsWhat/1.0 (public-interest research; contact: "
            "https://github.com/alexsnowschool-business) "
            "urllib/3"
        ),
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            raw = resp.read()
            return json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as exc:
        print(f"    HTTP error {url}: {exc}")
        return None


# ── WIKIPEDIA ──────────────────────────────────────────────────────────────

def fetch_wikipedia_summary(wiki_title: str) -> dict | None:
    """
    Fetch the Wikipedia REST API summary for a page.
    Returns: {title, description, extract, thumbnail_url}
    Docs: https://en.wikipedia.org/api/rest_v1/page/summary/{title}
    """
    encoded = urllib.parse.quote(wiki_title.replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    data = http_get(url)
    if not data:
        return None
    return {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "extract": data.get("extract", ""),
        "thumbnail_url": (data.get("thumbnail") or {}).get("source", ""),
        "wikidata_qid": data.get("wikibase_item", ""),
    }


def fetch_wikipedia_pageprops(wiki_title: str) -> str | None:
    """
    Get the Wikidata QID for a Wikipedia page via the MediaWiki API.
    Returns QID like 'Q246' or None.
    """
    params = urllib.parse.urlencode({
        "action": "query",
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "titles": wiki_title,
        "format": "json",
        "formatversion": "2",
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    data = http_get(url)
    if not data:
        return None
    pages = data.get("query", {}).get("pages", [])
    if pages:
        return pages[0].get("pageprops", {}).get("wikibase_item")
    return None


# ── WIKIDATA ───────────────────────────────────────────────────────────────

# Wikidata property IDs we care about
WD_PROPS = {
    "P249":  "ticker",          # stock market index ticker
    "P414":  "exchange",        # stock exchange
    "P571":  "inception",       # date of founding
    "P1128": "employees",       # number of employees
    "P159":  "headquarters",    # headquarters location
    "P2139": "revenue",         # total revenue
    "P169":  "ceo",             # chief executive officer
    "P856":  "website",         # official website
    "P18":   "image",           # image
    "P749":  "parent",          # parent company
    "P452":  "industry",        # industry
}

def fetch_wikidata_entity(qid: str) -> dict:
    """
    Fetch structured data for a Wikidata entity.
    Returns a dict of property_label → value (simplified).
    """
    url = (
        f"https://www.wikidata.org/w/api.php?"
        f"action=wbgetentities&ids={qid}&props=claims|labels|descriptions"
        f"&languages=en&format=json"
    )
    data = http_get(url)
    if not data:
        return {}

    entity = data.get("entities", {}).get(qid, {})
    claims = entity.get("claims", {})
    result: dict = {}

    for prop_id, prop_label in WD_PROPS.items():
        if prop_id not in claims:
            continue
        # Take first claim value (mainsnak)
        snak = claims[prop_id][0].get("mainsnak", {})
        dv = snak.get("datavalue", {})
        dv_type = dv.get("type", "")
        value = dv.get("value", "")

        if dv_type == "string":
            result[prop_label] = value
        elif dv_type == "time":
            # e.g. '+1972-01-01T00:00:00Z'
            ts = value.get("time", "") if isinstance(value, dict) else ""
            # Extract just the year
            match = re.search(r"\+(\d{4})", ts)
            result[prop_label] = match.group(1) if match else ts
        elif dv_type == "quantity":
            # e.g. {"amount": "+684000", "unit": "1"}
            amount = value.get("amount", "") if isinstance(value, dict) else str(value)
            result[prop_label] = amount.lstrip("+")
        elif dv_type == "wikibase-entityid":
            # For CEO, headquarters etc — we need to resolve the entity label
            sub_qid = value.get("id", "") if isinstance(value, dict) else ""
            label = resolve_wikidata_label(sub_qid)
            result[prop_label] = label or sub_qid
        elif dv_type == "monolingualtext":
            result[prop_label] = value.get("text", "") if isinstance(value, dict) else str(value)
        else:
            result[prop_label] = str(value)

    return result


def resolve_wikidata_label(qid: str) -> str | None:
    """Resolve a Wikidata QID to its English label (for CEO names, HQ cities, etc.)."""
    if not qid:
        return None
    url = (
        f"https://www.wikidata.org/w/api.php?"
        f"action=wbgetentities&ids={qid}&props=labels&languages=en&format=json"
    )
    time.sleep(DELAY)
    data = http_get(url)
    if not data:
        return None
    entity = data.get("entities", {}).get(qid, {})
    return entity.get("labels", {}).get("en", {}).get("value")


# ── LOBBYREGISTER ──────────────────────────────────────────────────────────

def fetch_lobbyregister(name: str) -> str | None:
    """
    Search the Bundestag Lobby Register for a company name.
    Returns the annual budget string or None.
    Note: The register reports budget bands, e.g. '5000001-10000000'.
    """
    params = urllib.parse.urlencode({
        "q": name,
        "status": "ALLE",
        "registrationStatus": "REGISTRIERT",
        "pageSize": "5",
        "pageNumber": "0",
    })
    url = f"{LOBBYREGISTER_API}?{params}"
    # The Lobbyregister returns HTML by default; some endpoints return JSON.
    # We request JSON via Accept header.
    headers = {
        "User-Agent": "WhoOwnsWhat/1.0 public-interest research",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="replace")
            if "json" not in content_type:
                # HTML response — extract budget with regex as fallback
                return _parse_lobbyregister_html(raw, name)
            data = json.loads(raw)
            return _extract_budget_json(data)
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        print(f"    Lobbyregister error for '{name}': {exc}")
        return None


def _parse_lobbyregister_html(html: str, query: str) -> str | None:
    """Extract annual budget from Lobbyregister HTML page."""
    # Budget typically appears as "Jahresbudget: X EUR" or in a data attribute
    patterns = [
        r"jahresbudget[^>]*>([^<]+)<",
        r"Jahresbudget[:\s]+([€\d\.,\s]+(?:Mio|Tsd|EUR)?)",
        r'"jahresbudget"\s*:\s*"([^"]+)"',
        r'"lobbyausgaben"\s*:\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            return _normalise_budget(raw)
    return None


def _extract_budget_json(data: dict | list) -> str | None:
    """Extract budget from a JSON response."""
    items = data if isinstance(data, list) else data.get("content", data.get("results", []))
    if not items:
        return None
    first = items[0] if isinstance(items, list) else items
    raw = (
        first.get("jahresbudget") or
        first.get("lobbyausgaben") or
        first.get("annualBudget") or
        ""
    )
    return _normalise_budget(str(raw)) if raw else None


def _normalise_budget(raw: str) -> str | None:
    """Convert a budget band like '5000001-10000000' to '€5–10M'."""
    raw = raw.strip().replace("EUR", "").replace("€", "").replace(" ", "")
    if not raw or raw in ("-", "0", "null"):
        return None
    # Range: '1000001-5000000'
    m = re.match(r"(\d+)-(\d+)", raw)
    if m:
        low = int(m.group(1))
        high = int(m.group(2))
        if high >= 1_000_000:
            return f"€{low / 1_000_000:.0f}–{high / 1_000_000:.0f}M"
        if high >= 1_000:
            return f"€{low // 1000:,}–{high // 1000:,}K"
        return f"€{low:,}–{high:,}"
    # Single value or label
    try:
        val = int(re.sub(r"[^\d]", "", raw))
        if val >= 1_000_000:
            return f"€{val / 1_000_000:.1f}M"
        if val >= 1_000:
            return f"€{val // 1000:,}K"
        return f"€{val:,}"
    except ValueError:
        return raw if raw else None


# ── FORMAT HELPERS ─────────────────────────────────────────────────────────

def format_employees(raw: str) -> str:
    """Format a raw employee count string like '684000' to '684,000'."""
    try:
        n = int(re.sub(r"[^\d]", "", raw))
        return f"{n:,}"
    except (ValueError, TypeError):
        return raw


def format_revenue(raw: str, currency: str = "EUR") -> str:
    """Format revenue like '29300000000' → '€29.3 billion'."""
    try:
        n = abs(float(re.sub(r"[^\d.]", "", raw)))
        if n >= 1e9:
            return f"€{n / 1e9:.1f} billion"
        if n >= 1e6:
            return f"€{n / 1e6:.0f} million"
        return f"€{n:,.0f}"
    except (ValueError, TypeError):
        return raw


# ── DB WRITERS ─────────────────────────────────────────────────────────────

def upsert_company(
    conn: sqlite3.Connection,
    slug: str,
    name: str,
    ticker: str | None,
    summary: dict,    # from Wikipedia
    facts: dict,      # from Wikidata
    lobby_budget: str | None,
    country: str = "germany",
) -> None:
    cur = conn.cursor()
    now = NOW()

    # Compose fields
    ceo_name = facts.get("ceo", "")
    founded = facts.get("inception", "")
    employees_raw = facts.get("employees", "")
    employees = format_employees(employees_raw) if employees_raw else ""
    revenue_raw = facts.get("revenue", "")
    revenue = format_revenue(revenue_raw) if revenue_raw else ""
    hq = facts.get("headquarters", "")
    sector = facts.get("industry", "")
    website = facts.get("website", "")
    description = summary.get("description", "")
    extract = summary.get("extract", "")
    entity_summary = extract[:600] if extract else description  # cap at 600 chars

    cur.execute("""
        INSERT OR REPLACE INTO entities
            (id, type, country, name, summary, last_scraped,
             ticker, sector, headquarters, founded, employees)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        slug, "company", country, name, entity_summary, now,
        ticker, sector or "—", hq or "Germany", founded, employees,
    ))

    # Lobbying — insert/replace for current year
    year = datetime.now(timezone.utc).strftime("%Y")
    if lobby_budget:
        cur.execute("DELETE FROM lobbying WHERE entity_id=? AND year=?", (slug, year))
        cur.execute("""
            INSERT INTO lobbying (entity_id,year,amount,currency,source,source_url)
            VALUES (?,?,?,?,?,?)
        """, (slug, year, lobby_budget, "EUR",
              "Bundestag Lobbyregister", "https://lobbyregister.bundestag.de"))

    # Political spending note (Germany-specific)
    cur.execute("DELETE FROM political_spending WHERE entity_id=?", (slug,))
    cur.execute("""
        INSERT INTO political_spending (entity_id,pac,cycle,total,currency,note,source,source_url)
        VALUES (?,?,?,?,?,?,?,?)
    """, (slug,
          "N/A — prohibited by Parteiengesetz §25",
          str(datetime.now().year), "€0", "EUR",
          "German law (Parteiengesetz §25) prohibits direct donations to political parties from corporations.",
          "Parteiengesetz §25", "https://www.gesetze-im-internet.de/partg/__25.html"))

    # CEO as minimal compensation record if we have a name
    if ceo_name:
        cur.execute("DELETE FROM compensation WHERE entity_id=?", (slug,))
        cur.execute("""
            INSERT INTO compensation (entity_id,fiscal_year,ceo_name,source,source_url)
            VALUES (?,?,?,?,?)
        """, (slug, datetime.now().year - 1, ceo_name,
              "Wikipedia / Wikidata", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(summary.get('title', name))}"))

    # Sources
    cur.execute("DELETE FROM sources WHERE entity_id=?", (slug,))
    wiki_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(summary.get('title', name))}"
    sources_to_add = [
        (slug, f"Wikipedia — {name}", wiki_url),
        (slug, "Bundesanzeiger — annual report filings", "https://www.bundesanzeiger.de"),
        (slug, "BaFin — voting rights notifications", "https://www.bafin.de"),
    ]
    if lobby_budget:
        sources_to_add.append((slug, "Bundestag Lobbyregister", "https://lobbyregister.bundestag.de"))
    if website:
        sources_to_add.append((slug, f"{name} — official website", website))

    cur.executemany("INSERT INTO sources (entity_id,title,url) VALUES (?,?,?)", sources_to_add)


def mark_queue_status(conn: sqlite3.Connection, slug: str, status: str, detail: str = "") -> None:
    conn.execute("""
        UPDATE company_queue SET status=?, last_attempt=?, error_detail=? WHERE slug=?
    """, (status, NOW(), detail, slug))


def log_scrape(conn: sqlite3.Connection, slug: str, status: str, detail: str) -> None:
    conn.execute("""
        INSERT INTO scrape_log (entity_id,scraper,status,detail) VALUES (?,?,?,?)
    """, (slug, "company_batch", status, detail))


# ── MAIN SCRAPE LOOP ───────────────────────────────────────────────────────

def scrape_company(conn: sqlite3.Connection, row: dict, dry_run: bool = False) -> bool:
    """
    Scrape one company from the queue. Returns True on success.
    row: dict with slug, name, ticker, wiki_title, wikidata_qid
    """
    slug = row["slug"]
    name = row["name"]
    ticker = row.get("ticker")
    wiki_title = row.get("wiki_title") or name
    qid = row.get("wikidata_qid") or ""

    print(f"\n  [{slug}] {name} ({ticker or 'private'})")

    # 1. Wikipedia summary
    print(f"    → Wikipedia: '{wiki_title}'")
    wiki = fetch_wikipedia_summary(wiki_title)
    time.sleep(DELAY)

    if not wiki:
        print(f"    ✗ Wikipedia not found. Trying with name...")
        wiki = fetch_wikipedia_summary(name)
        time.sleep(DELAY)

    if not wiki:
        print(f"    ✗ Wikipedia failed entirely.")
        if not dry_run:
            mark_queue_status(conn, slug, "error", "Wikipedia fetch failed")
            log_scrape(conn, slug, "error", "Wikipedia fetch failed")
        return False

    # Use QID from Wikipedia if not provided
    if not qid:
        qid = wiki.get("wikidata_qid", "")

    # 2. Wikidata structured facts
    facts: dict = {}
    if qid:
        print(f"    → Wikidata: {qid}")
        facts = fetch_wikidata_entity(qid)
        time.sleep(DELAY)
        # Resolve CEO label if it's still a QID
        if "ceo" in facts and facts["ceo"].startswith("Q"):
            ceo_label = resolve_wikidata_label(facts["ceo"])
            if ceo_label:
                facts["ceo"] = ceo_label
            time.sleep(DELAY)

    # 3. Bundestag Lobbyregister (only for incorporated German entities)
    lobby_budget = None
    if row.get("index_name") != "Private" or ticker:
        print(f"    → Lobbyregister: '{name}'")
        lobby_budget = fetch_lobbyregister(name)
        time.sleep(DELAY)
        # Try shorter name if no result
        if not lobby_budget:
            short = name.split(" ")[0]  # e.g. "BMW" from "BMW AG"
            if short != name:
                lobby_budget = fetch_lobbyregister(short)
                time.sleep(DELAY)

    print(f"    Summary: {(wiki.get('extract') or '')[:80]}...")
    print(f"    CEO: {facts.get('ceo', '—')}")
    print(f"    Founded: {facts.get('inception', '—')}")
    print(f"    Employees: {facts.get('employees', '—')}")
    print(f"    Lobbying: {lobby_budget or '—'}")

    if dry_run:
        return True

    # Write to DB
    upsert_company(conn, slug, name, ticker, wiki, facts, lobby_budget)
    mark_queue_status(conn, slug, "scraped")
    log_scrape(conn, slug, "ok", f"CEO={facts.get('ceo','')}, lobby={lobby_budget}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily batch scraper for German companies.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--batch", type=int, default=5, help="Number of companies to process per run (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print without writing to DB")
    parser.add_argument("--slug", help="Process one specific company slug (overrides --batch)")
    parser.add_argument("--retry-errors", action="store_true", help="Also process companies that previously errored")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}. Run init_db.py and discover_germany.py first.")
        raise SystemExit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    # Build query for pending companies
    if args.slug:
        rows = list(conn.execute(
            "SELECT * FROM company_queue WHERE slug=?", (args.slug,)
        ).fetchall())
    elif args.retry_errors:
        rows = list(conn.execute("""
            SELECT * FROM company_queue
            WHERE status IN ('pending', 'error')
            ORDER BY
                CASE index_name WHEN 'DAX40' THEN 0 WHEN 'MDAX' THEN 1 ELSE 2 END,
                id
            LIMIT ?
        """, (args.batch,)).fetchall())
    else:
        rows = list(conn.execute("""
            SELECT * FROM company_queue
            WHERE status = 'pending'
            ORDER BY
                CASE index_name WHEN 'DAX40' THEN 0 WHEN 'MDAX' THEN 1 ELSE 2 END,
                id
            LIMIT ?
        """, (args.batch,)).fetchall())

    if not rows:
        print("No pending companies in queue.")
        pending = conn.execute("SELECT COUNT(*) FROM company_queue WHERE status='pending'").fetchone()[0]
        scraped = conn.execute("SELECT COUNT(*) FROM company_queue WHERE status='scraped'").fetchone()[0]
        print(f"Queue: {pending} pending, {scraped} scraped.")
        conn.close()
        return

    print(f"Processing {len(rows)} companies (batch={args.batch}, dry_run={args.dry_run})")

    ok = 0
    errors = 0
    for row in rows:
        row_dict = dict(row)
        success = scrape_company(conn, row_dict, dry_run=args.dry_run)
        if success:
            ok += 1
        else:
            errors += 1
        if not args.dry_run:
            conn.commit()

    conn.close()

    pending_after = sqlite3.connect(args.db).execute(
        "SELECT COUNT(*) FROM company_queue WHERE status='pending'"
    ).fetchone()[0] if not args.dry_run else "?"

    print(f"\nBatch complete: {ok} scraped, {errors} errors. Pending in queue: {pending_after}")


if __name__ == "__main__":
    main()
