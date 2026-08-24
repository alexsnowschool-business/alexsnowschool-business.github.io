"""
scrape_institutional_holders.py — Who Owns What
Fetches institutional shareholder data from Yahoo Finance via yfinance
for all German company entities that have a stock ticker.

Data returned per company:
  - Top institutional holders (name, % held, shares, date reported)
  - Major holders summary (% held by institutions, insiders, float)

Tickers are stored in the DB as short-form (e.g. "BMW") and are mapped
to Frankfurt Xetra format by appending ".DE" (e.g. "BMW.DE").

Usage:
    python scripts/whoownswhat/scrape_institutional_holders.py
    python scripts/whoownswhat/scrape_institutional_holders.py --dry-run
    python scripts/whoownswhat/scrape_institutional_holders.py --slug bmw
    python scripts/whoownswhat/scrape_institutional_holders.py --limit 5
"""

import argparse
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"
DELAY = 1.5
SOURCE = "Yahoo Finance / yfinance"
SOURCE_URL_TEMPLATE = "https://finance.yahoo.com/quote/{ticker}/holders/"

# Some tickers need a different suffix (not .DE) or a different symbol entirely
TICKER_OVERRIDES: dict[str, str] = {
    "AIR": "AIR.PA",    # Airbus — listed on Euronext Paris
    "1COV": "1COV.DE",  # Covestro — keep as-is (already has number prefix)
}


def to_yahoo_ticker(ticker: str) -> str:
    if ticker in TICKER_OVERRIDES:
        return TICKER_OVERRIDES[ticker]
    if "." in ticker:          # already has suffix
        return ticker
    return f"{ticker}.DE"


def fmt_pct(val) -> str | None:
    try:
        return f"{float(val) * 100:.2f}%"
    except (TypeError, ValueError):
        return None


def fmt_shares(val) -> str | None:
    try:
        n = int(val)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M shares"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K shares"
        return f"{n:,} shares"
    except (TypeError, ValueError):
        return None


def scrape_ticker(yahoo_ticker: str) -> list[dict]:
    """
    Returns a list of {name, pct_held, shares, date_reported} dicts
    for the top institutional holders.
    """
    import yfinance as yf
    try:
        info = yf.Ticker(yahoo_ticker)
        ih = info.institutional_holders
        if ih is None or ih.empty:
            return []
        holders = []
        for _, row in ih.iterrows():
            name = str(row.get("Holder") or row.get("Name") or "").strip()
            if not name:
                continue
            pct_raw  = row.get("pctHeld") or row.get("% Out") or row.get("Pct Held")
            shares   = row.get("Shares") or row.get("shares")
            date_rep = row.get("Date Reported") or row.get("dateReported")
            holders.append({
                "name":          name,
                "pct_held":      fmt_pct(pct_raw),
                "shares":        fmt_shares(shares),
                "date_reported": str(date_rep)[:10] if date_rep else None,
            })
        return holders
    except Exception as exc:
        print(f"    yfinance error for {yahoo_ticker}: {exc}")
        return []


def clear_institutional_shareholders(conn: sqlite3.Connection, entity_id: str) -> None:
    conn.execute(
        "DELETE FROM shareholders WHERE entity_id=? AND source=?",
        (entity_id, SOURCE)
    )


def insert_shareholder(
    conn: sqlite3.Connection,
    entity_id: str,
    holder: dict,
    source_url: str,
    dry_run: bool,
) -> None:
    pct    = holder["pct_held"] or "—"
    shares = holder["shares"]
    stake  = f"{pct} ({shares})" if shares else pct
    as_of  = holder.get("date_reported") or "2025"

    if dry_run:
        print(f"      [DRY RUN] {holder['name']}: {stake} as of {as_of}")
        return

    conn.execute(
        """INSERT INTO shareholders (entity_id, name, stake, type, source, source_url, as_of)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (entity_id, holder["name"], stake, "Institutional", SOURCE, source_url, as_of),
    )


def scrape_entity(
    entity_id: str,
    name: str,
    ticker: str,
    dry_run: bool,
    conn: sqlite3.Connection,
) -> int:
    yahoo_ticker = to_yahoo_ticker(ticker)
    print(f"  [{entity_id}] {name} → {yahoo_ticker}")

    holders = scrape_ticker(yahoo_ticker)
    time.sleep(DELAY)

    if not holders:
        print(f"    — no institutional holder data")
        return 0

    source_url = SOURCE_URL_TEMPLATE.format(ticker=yahoo_ticker)

    if not dry_run:
        clear_institutional_shareholders(conn, entity_id)

    for h in holders:
        insert_shareholder(conn, entity_id, h, source_url, dry_run)
        if not dry_run:
            print(f"      ✓ {h['name']}: {h['pct_held']}")

    if not dry_run:
        conn.commit()

    return len(holders)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape institutional holders from Yahoo Finance for all German entities"
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--slug",  help="Only process one entity by id")
    parser.add_argument("--limit", type=int, default=0, help="Max entities to process (0 = all)")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")

    if args.slug:
        rows = conn.execute(
            "SELECT id, name, ticker FROM entities WHERE type='company' AND country='germany' AND id=? AND ticker IS NOT NULL AND ticker != ''",
            (args.slug,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, ticker FROM entities WHERE type='company' AND country='germany' AND ticker IS NOT NULL AND ticker != '' ORDER BY name"
        ).fetchall()

    if args.limit:
        rows = rows[:args.limit]

    if not rows:
        print("No entities with tickers found.")
        conn.close()
        return

    print(f"Fetching institutional holders for {len(rows)} entities...\n")
    updated = not_found = 0

    for entity_id, name, ticker in rows:
        count = scrape_entity(entity_id, name, ticker, args.dry_run, conn)
        if count:
            updated += 1
        else:
            not_found += 1

    conn.close()
    print(f"\nDone. Updated: {updated}, not found: {not_found}")


if __name__ == "__main__":
    main()
