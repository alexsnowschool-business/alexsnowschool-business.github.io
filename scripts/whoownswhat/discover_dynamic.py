"""
discover_dynamic.py — Who Owns What
Automatically discovers companies from Wikidata SPARQL and adds them to the queue.

Two modes
---------
1. Bulk discovery (default)
   Queries Wikidata for all companies headquartered in the target country that
   are listed on a major stock exchange. Results not yet in the queue are added.

2. Single-add  --add <QID | company name>
   Add one specific company. If a Wikidata Q-ID is given (e.g. Q152006) it is
   fetched directly. If a name is given, it is searched via Wikidata entity
   search and the best match is used.

Country support
---------------
  germany (default)  Q183  Frankfurt Stock Exchange / Xetra
  us                 Q30   NYSE / NASDAQ
  uk                 Q145  London Stock Exchange
  france             Q142  Euronext Paris

Each new entry is added with status='pending' and index_name='Dynamic-<Country>'.

Usage
-----
    python scripts/whoownswhat/discover_dynamic.py
    python scripts/whoownswhat/discover_dynamic.py --country germany --limit 100
    python scripts/whoownswhat/discover_dynamic.py --add Q152006
    python scripts/whoownswhat/discover_dynamic.py --add "Continental AG"
    python scripts/whoownswhat/discover_dynamic.py --dry-run
    python scripts/whoownswhat/discover_dynamic.py --stats
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
from pathlib import Path
from typing import Any

# ── SSL (same fix as scrape_company_batch.py) ─────────────────────────────
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"

# Wikidata SPARQL endpoint
SPARQL_URL = "https://query.wikidata.org/sparql"

# Wikidata entity search API
SEARCH_URL = "https://www.wikidata.org/w/api.php"

# Country → Wikidata Q-ID + relevant stock exchanges
COUNTRY_CONFIG: dict[str, dict] = {
    "germany": {
        "qid":       "Q183",
        "exchanges": ["Q185005", "Q151644"],   # Frankfurt SE, Xetra
        "label":     "Germany",
        "index_tag": "Dynamic-Germany",
    },
    "us": {
        "qid":       "Q30",
        "exchanges": ["Q13677", "Q82059"],     # NYSE, NASDAQ
        "label":     "United States",
        "index_tag": "Dynamic-US",
    },
    "uk": {
        "qid":       "Q145",
        "exchanges": ["Q170687"],              # London Stock Exchange
        "label":     "United Kingdom",
        "index_tag": "Dynamic-UK",
    },
    "france": {
        "qid":       "Q142",
        "exchanges": ["Q242503"],              # Euronext Paris
        "label":     "France",
        "index_tag": "Dynamic-France",
    },
}

_HEADERS = {
    "User-Agent": "WhoOwnsWhat/1.0 public-interest research",
    "Accept": "application/json",
}


# ── HTTP helpers ─────────────────────────────────────────────────────────

def http_get(url: str, params: dict | None = None, timeout: int = 20, retries: int = 3) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = 60 * (attempt + 1)   # 60s, 120s, 180s
                print(f"  Rate-limited (429). Waiting {wait}s before retry {attempt + 1}/{retries} …")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"Failed after {retries} retries: {url}")


# ── Slug helpers ──────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """Turn a company name into a URL-safe slug.
    'Deutsche Bank AG' → 'deutsche-bank'
    """
    # Remove legal suffixes
    suffixes = (
        r"\bAG\b", r"\bSE\b", r"\bGmbH\b", r"\bKG\b", r"\bKGaA\b",
        r"\bplc\b", r"\bInc\b", r"\bLtd\b", r"\bLLC\b", r"\bNV\b",
        r"\bSA\b", r"\bCo\b", r"\bGroup\b",
        r"&\s*Co\.\s*KGaA", r"&\s*Co\.", r"\bHolding\b",
    )
    s = name
    for suffix in suffixes:
        s = re.sub(suffix, "", s, flags=re.IGNORECASE)

    # Transliterate German umlauts
    for old, new in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"),
                     ("Ä", "ae"), ("Ö", "oe"), ("Ü", "ue")]:
        s = s.replace(old, new)

    # Lowercase, replace non-alphanumeric with hyphens, collapse
    s = re.sub(r"[^a-z0-9]+", "-", s.lower())
    return s.strip("-")


# ── Wikidata SPARQL ───────────────────────────────────────────────────────

def sparql_query(query: str) -> list[dict]:
    """Execute a SPARQL query against Wikidata and return the bindings list."""
    data = http_get(SPARQL_URL, {"query": query, "format": "json"}, timeout=60)
    return data.get("results", {}).get("bindings", [])


def build_bulk_query(country_qid: str, exchange_qids: list[str], limit: int) -> str:
    exchange_values = " ".join(f"wd:{q}" for q in exchange_qids)
    return f"""
SELECT DISTINCT ?company ?companyLabel ?ticker ?qid WHERE {{
  VALUES ?exchange {{ {exchange_values} }}
  ?company wdt:P414 ?exchange .
  ?company wdt:P17 wd:{country_qid} .
  OPTIONAL {{ ?company wdt:P249 ?ticker }}
  BIND(STRAFTER(STR(?company), "entity/") AS ?qid)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
ORDER BY ?companyLabel
LIMIT {limit}
"""


def fetch_entity_by_qid(qid: str) -> dict | None:
    """Fetch a single Wikidata entity and return a normalised dict."""
    data = http_get("https://www.wikidata.org/w/api.php", {
        "action": "wbgetentities",
        "ids":    qid,
        "props":  "labels|claims|sitelinks",
        "languages": "en|de",
        "format": "json",
    })
    entity = data.get("entities", {}).get(qid)
    if not entity or "missing" in entity:
        return None
    return entity


def entity_label(entity: dict, lang: str = "en") -> str:
    return entity.get("labels", {}).get(lang, {}).get("value", "")


def entity_claim_value(entity: dict, prop: str) -> str | None:
    """Return the first string/monolingual/external-id value for a property claim."""
    claims = entity.get("claims", {}).get(prop, [])
    if not claims:
        return None
    snak = claims[0].get("mainsnak", {})
    dv = snak.get("datavalue", {})
    if dv.get("type") == "string":
        return dv.get("value")
    if dv.get("type") == "monolingualtext":
        return dv["value"].get("text")
    if dv.get("type") == "wikibase-entityid":
        return dv["value"].get("id")
    return None


def search_entity(name: str, type_: str = "item", limit: int = 5) -> list[dict]:
    """Search Wikidata for entities matching a name."""
    data = http_get(SEARCH_URL, {
        "action": "wbsearchentities",
        "search": name,
        "language": "en",
        "type": type_,
        "limit": limit,
        "format": "json",
    })
    return data.get("search", [])


def sitelink_title(entity: dict, wiki: str) -> str | None:
    return entity.get("sitelinks", {}).get(wiki, {}).get("title")


# ── Queue helpers ─────────────────────────────────────────────────────────

def existing_slugs(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT slug FROM company_queue").fetchall()
    return {r[0] for r in rows}


def existing_qids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT wikidata_qid FROM company_queue WHERE wikidata_qid IS NOT NULL").fetchall()
    return {r[0] for r in rows}


def insert_company(
    conn: sqlite3.Connection,
    slug: str,
    name: str,
    ticker: str | None,
    index_name: str,
    wiki_title: str | None,
    wiki_title_de: str | None,
    qid: str | None,
    dry_run: bool = False,
) -> bool:
    """Insert into queue; return True if inserted (False if already exists)."""
    if dry_run:
        print(f"    [DRY RUN] Would add: {slug} ({name}) [{index_name}] {qid or ''}")
        return True
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO company_queue
            (slug, name, ticker, index_name, wiki_title, wiki_title_de, wikidata_qid)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (slug, name, ticker, index_name, wiki_title, wiki_title_de, qid))
    conn.commit()
    return bool(cur.rowcount)


# ── Mode: bulk discovery ──────────────────────────────────────────────────

def run_bulk(conn: sqlite3.Connection, country: str, limit: int, dry_run: bool) -> None:
    cfg = COUNTRY_CONFIG[country]
    print(f"\nDiscovering companies — {cfg['label']} (exchanges: {cfg['exchanges']}) …")

    query = build_bulk_query(cfg["qid"], cfg["exchanges"], limit)

    try:
        bindings = sparql_query(query)
    except Exception as exc:
        print(f"  SPARQL query failed: {exc}")
        return

    print(f"  Wikidata returned {len(bindings)} results")

    known_qids = existing_qids(conn)
    known_slugs = existing_slugs(conn)

    added = 0
    dupes = 0

    for b in bindings:
        qid       = b.get("qid", {}).get("value", "")
        label     = b.get("companyLabel", {}).get("value", "")
        ticker    = b.get("ticker", {}).get("value")

        if not label or not qid:
            continue
        if qid in known_qids:
            dupes += 1
            continue

        slug = slugify(label)
        if slug in known_slugs:
            # Try adding QID suffix to avoid collision
            slug = f"{slug}-{qid.lower()}"

        ok = insert_company(
            conn, slug, label, ticker,
            cfg["index_tag"], None, None, qid, dry_run=dry_run,
        )
        if ok:
            print(f"  + {slug:40s}  {label}")
            known_qids.add(qid)
            known_slugs.add(slug)
            added += 1
        else:
            dupes += 1

        time.sleep(0.05)   # gentle rate limit

    print(f"\nDone. Added: {added}, already in queue: {dupes}")


# ── Mode: single add ──────────────────────────────────────────────────────

def run_single_add(conn: sqlite3.Connection, query: str, country: str, dry_run: bool) -> None:
    cfg = COUNTRY_CONFIG[country]
    known_qids = existing_qids(conn)

    # Is it a QID?
    if re.match(r"^Q\d+$", query.strip(), re.IGNORECASE):
        qid = query.strip().upper()
        print(f"\nFetching entity {qid} from Wikidata …")
        entity = fetch_entity_by_qid(qid)
        if not entity:
            print(f"  Entity {qid} not found.")
            return
        candidates = [(qid, entity)]
    else:
        print(f"\nSearching Wikidata for '{query}' …")
        results = search_entity(query, limit=5)
        if not results:
            print("  No results found.")
            return
        # Skip results with no label (Wikidata API can return stub entities)
        results = [r for r in results if r.get("label", "").strip()]
        if not results:
            print("  No labelled results found.")
            return
        # Pick the best match: prefer exact name match, else first result
        best = None
        for r in results:
            if r.get("label", "").lower() == query.lower():
                best = r
                break
        if not best:
            best = results[0]
        print(f"  Best match: {best['label']} ({best['id']}) — {best.get('description', '')}")
        entity = fetch_entity_by_qid(best["id"])
        if not entity:
            print("  Could not fetch entity.")
            return
        candidates = [(best["id"], entity)]

    for qid, entity in candidates:
        if qid in known_qids:
            print(f"  {qid} is already in the queue.")
            continue

        name_en = entity_label(entity, "en")
        name_de = entity_label(entity, "de")
        ticker  = entity_claim_value(entity, "P249")   # stock exchange ticker
        wiki_en = sitelink_title(entity, "enwiki")
        wiki_de = sitelink_title(entity, "dewiki")
        slug    = slugify(name_en or name_de)

        known_slugs = existing_slugs(conn)
        if slug in known_slugs:
            slug = f"{slug}-{qid.lower()}"

        print(f"  Adding: {slug} | {name_en} | ticker={ticker} | {qid}")
        ok = insert_company(
            conn, slug, name_en or name_de, ticker,
            cfg["index_tag"], wiki_en, wiki_de, qid, dry_run=dry_run,
        )
        if ok:
            print("  ✓ Added to queue.")
        else:
            print("  Already present (slug collision).")


# ── main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dynamically discover companies from Wikidata and add them to the queue."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument(
        "--country", default="germany", choices=list(COUNTRY_CONFIG),
        help="Target country (default: germany)"
    )
    parser.add_argument(
        "--limit", type=int, default=200,
        help="Max SPARQL results in bulk mode (default: 200)"
    )
    parser.add_argument(
        "--add", metavar="QID_OR_NAME",
        help="Add a single company by Wikidata QID (e.g. Q152006) or name"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}. Run init_db.py first.")
        raise SystemExit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        if args.stats:
            from discover_germany import print_stats
            print_stats(conn)
        elif args.add:
            run_single_add(conn, args.add, args.country, args.dry_run)
        else:
            run_bulk(conn, args.country, args.limit, args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
