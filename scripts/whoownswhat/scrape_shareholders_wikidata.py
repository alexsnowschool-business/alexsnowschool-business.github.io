"""
scrape_shareholders_wikidata.py — Who Owns What
Fetches major shareholder / ownership structure for German companies from
Wikidata SPARQL (property P127 "owned by" with P1107 "proportion" qualifier).

Covers DAX / large-cap German AGs where Wikidata editors maintain stakes.
Falls back to Wikipedia infobox `owners=` parsing when SPARQL returns nothing.

Usage:
    python scripts/whoownswhat/scrape_shareholders_wikidata.py
    python scripts/whoownswhat/scrape_shareholders_wikidata.py --dry-run
    python scripts/whoownswhat/scrape_shareholders_wikidata.py --slug volkswagen
"""

import argparse
import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"

WIKIDATA_SPARQL  = "https://query.wikidata.org/sparql"
WIKIDATA_SEARCH  = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API    = "https://en.wikipedia.org/w/api.php"
DELAY       = 2.0   # base delay between entities
SPARQL_DELAY = 5.0  # extra delay before each SPARQL call

_HEADERS = {
    "User-Agent": "WhoOwnsWhat/1.0 (public-interest research; github.com/alexsnowschool-business)",
    "Accept": "application/json",
}

# ── Wikidata QID lookup ──────────────────────────────────────────────────────

def find_qid(name: str) -> str | None:
    """Search Wikidata for the QID of a company by name."""
    params = urllib.parse.urlencode({
        "action": "wbsearchentities",
        "search": name,
        "language": "en",
        "type": "item",
        "limit": "5",
        "format": "json",
    })
    url = f"{WIKIDATA_SEARCH}?{params}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        for result in data.get("search", []):
            desc = result.get("description", "").lower()
            label = result.get("label", "").lower()
            # Prefer results that mention company / enterprise / AG
            if any(w in desc for w in ("company", "enterprise", "corporation", "german", "ag", "se")):
                return result["id"]
            if name.lower() in label:
                return result["id"]
        # Fallback: return first result
        results = data.get("search", [])
        return results[0]["id"] if results else None
    except Exception as exc:
        print(f"    QID lookup failed for '{name}': {exc}")
        return None


# ── SPARQL ownership query ───────────────────────────────────────────────────

SPARQL_TEMPLATE = """
SELECT ?owner ?ownerLabel ?share ?shareType WHERE {{
  wd:{qid} p:P127 ?stmt .
  ?stmt ps:P127 ?owner .
  OPTIONAL {{ ?stmt pq:P1107 ?share }}
  OPTIONAL {{ ?stmt pq:P518  ?shareTypeEntity .
             ?shareTypeEntity rdfs:label ?shareType FILTER(LANG(?shareType)="en") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
}}
"""


def sparql_owners(qid: str) -> list[dict]:
    """Run SPARQL with retry/backoff for 429s."""
    query = SPARQL_TEMPLATE.format(qid=qid).strip()
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    url = f"{WIKIDATA_SPARQL}?{params}"
    req = urllib.request.Request(url, headers=_HEADERS)

    for attempt in range(3):
        wait = SPARQL_DELAY * (2 ** attempt)
        time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.load(resp)
            return data.get("results", {}).get("bindings", [])
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                print(f"    SPARQL 429 (attempt {attempt+1}/3) — waiting {wait*2:.0f}s")
                time.sleep(wait * 2)
            else:
                print(f"    SPARQL failed for {qid}: {exc}")
                return []
        except Exception as exc:
            print(f"    SPARQL failed for {qid}: {exc}")
            return []
    return []


def consolidate_sparql(rows: list[dict]) -> list[dict]:
    """
    Wikidata has separate rows per share class (equity vs. voting).
    Consolidate: keep the highest % per owner; prefer equity share if both present.
    Returns list of {name, equity_pct, voting_pct}.
    """
    owners: dict[str, dict] = {}
    for row in rows:
        owner_label = row.get("ownerLabel", {}).get("value", "")
        share_raw   = row.get("share", {}).get("value")
        share_type  = row.get("shareType", {}).get("value", "").lower()
        if not owner_label or not share_raw:
            continue
        try:
            pct = round(float(share_raw) * 100, 2)
        except ValueError:
            continue
        if owner_label not in owners:
            owners[owner_label] = {"name": owner_label, "equity_pct": None, "voting_pct": None}
        if "vot" in share_type:
            owners[owner_label]["voting_pct"] = pct
        else:
            owners[owner_label]["equity_pct"] = pct

    # Filter out rows with no usable percentage
    return [v for v in owners.values() if v["equity_pct"] or v["voting_pct"]]


# ── Wikipedia infobox fallback ───────────────────────────────────────────────

def wikipedia_owners(name: str) -> list[dict]:
    """
    Fetch the Wikipedia infobox `owners=` field for a company.
    Returns list of {name, stake_text}.
    """
    params = urllib.parse.urlencode({
        "action": "query",
        "titles": name,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "rvsection": "0",
        "format": "json",
    })
    url = f"{WIKIPEDIA_API}?{params}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        pages = data.get("query", {}).get("pages", {})
        wikitext = ""
        for page in pages.values():
            wikitext = page.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
            break
        return parse_infobox_owners(wikitext)
    except Exception as exc:
        print(f"    Wikipedia fallback failed for '{name}': {exc}")
        return []


def parse_infobox_owners(wikitext: str) -> list[dict]:
    """Extract owners from {{Infobox}} wikitext owners= field."""
    m = re.search(r"\|\s*owners?\s*=\s*(.+?)(?=\n\s*\||\n\s*\}\})", wikitext, re.DOTALL | re.IGNORECASE)
    if not m:
        return []
    raw = m.group(1).strip()
    # Strip wiki markup
    raw = re.sub(r"\{\{[^}]+\}\}", " ", raw)
    raw = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"'{2,}", "", raw)

    owners = []
    # Extract name + percentage pairs
    # Pattern: "Name X%" or "Name: X%" or "Name (X%)"
    chunks = re.split(r"[•·\n|]+", raw)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        pct_m = re.search(r"([\d.]+)\s*%", chunk)
        if not pct_m:
            continue
        pct = float(pct_m.group(1))
        name = re.sub(r"[\d.]+\s*%.*", "", chunk).strip().rstrip(":(),")
        name = re.sub(r"\s+", " ", name).strip()
        if name and pct > 0:
            owners.append({"name": name, "equity_pct": pct, "voting_pct": None})
    return owners


# ── DB helpers ───────────────────────────────────────────────────────────────

def clear_scraped_shareholders(conn: sqlite3.Connection, entity_id: str) -> None:
    """Remove shareholders previously scraped by this script (keep manually seeded ones)."""
    conn.execute(
        "DELETE FROM shareholders WHERE entity_id=? AND source LIKE '%Wikidata%'",
        (entity_id,)
    )


def insert_shareholder(
    conn: sqlite3.Connection,
    entity_id: str,
    name: str,
    equity_pct: float | None,
    voting_pct: float | None,
    source: str,
    source_url: str,
    dry_run: bool,
) -> None:
    parts = []
    if equity_pct is not None:
        parts.append(f"{equity_pct}% equity")
    if voting_pct is not None:
        parts.append(f"{voting_pct}% voting")
    stake = " / ".join(parts) if parts else "—"

    if dry_run:
        print(f"      [DRY RUN] {name}: {stake}")
        return

    conn.execute(
        """INSERT INTO shareholders (entity_id, name, stake, type, source, source_url, as_of)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (entity_id, name, stake, "Strategic/Institutional", source, source_url, "2025"),
    )


# ── Per-entity scrape ────────────────────────────────────────────────────────

def scrape_entity(entity_id: str, name: str, dry_run: bool, conn: sqlite3.Connection) -> int:
    print(f"  [{entity_id}] {name}")

    # 1. Find Wikidata QID
    qid = find_qid(name)
    time.sleep(DELAY)
    if not qid:
        print(f"    — QID not found")
        return 0

    # 2. SPARQL ownership query
    rows = sparql_owners(qid)
    time.sleep(DELAY)
    owners = consolidate_sparql(rows)

    source     = "Wikidata (P127)"
    source_url = f"https://www.wikidata.org/wiki/{qid}"

    # 3. Wikipedia fallback if SPARQL returned nothing
    if not owners:
        print(f"    SPARQL empty — trying Wikipedia infobox")
        owners = wikipedia_owners(name)
        time.sleep(DELAY)
        source     = "Wikipedia infobox"
        source_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(name.replace(' ', '_'))}"

    if not owners:
        print(f"    — no ownership data found")
        return 0

    # 4. Write to DB
    if not dry_run:
        clear_scraped_shareholders(conn, entity_id)

    for o in owners:
        insert_shareholder(
            conn, entity_id,
            o["name"], o.get("equity_pct"), o.get("voting_pct"),
            source, source_url, dry_run,
        )
        if not dry_run:
            print(f"      ✓ {o['name']}: {o.get('equity_pct') or o.get('voting_pct')}%")

    if not dry_run:
        conn.commit()

    return len(owners)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape shareholder structure from Wikidata for German entities")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--slug", help="Only process one entity by id")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")

    if args.slug:
        rows = conn.execute(
            "SELECT id, name FROM entities WHERE type='company' AND country='germany' AND id=?",
            (args.slug,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name FROM entities WHERE type='company' AND country='germany' ORDER BY name"
        ).fetchall()

    if not rows:
        print("No entities found.")
        conn.close()
        return

    print(f"Scraping shareholder data for {len(rows)} entities...\n")
    updated = not_found = 0

    for entity_id, name in rows:
        count = scrape_entity(entity_id, name, args.dry_run, conn)
        if count:
            updated += 1
        else:
            not_found += 1

    conn.close()
    print(f"\nDone. Updated: {updated}, not found: {not_found}")


if __name__ == "__main__":
    main()
