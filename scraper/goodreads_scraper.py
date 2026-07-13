#!/usr/bin/env python3
"""
Scrape quotes from goodreads.com/quotes and store in an account's quotes.db.

Usage:
    python scripts/goodreads_scraper.py                         # scrape lifequoteshere (default)
    python scripts/goodreads_scraper.py --account stoicdaily    # scrape a different account
    python scripts/goodreads_scraper.py --tags books reading    # override tags
    python scripts/goodreads_scraper.py --pages 5               # pages per tag (default 3)
    python scripts/goodreads_scraper.py --list                  # show stored quotes
"""

import argparse
import sqlite3
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BUSINESS_DIR / "scripts"))

DEFAULT_TAGS = [
    "books", "reading", "life", "wisdom", "love", "inspirational",
]

BASE_URL = "https://www.goodreads.com/quotes/tag/{tag}?page={page}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Database ──────────────────────────────────────────────────────────────────

def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            text        TEXT NOT NULL,
            author      TEXT NOT NULL DEFAULT '',
            book        TEXT NOT NULL DEFAULT '',
            tags        TEXT NOT NULL DEFAULT '',
            url         TEXT NOT NULL DEFAULT '',
            scraped_at  TEXT NOT NULL,
            used_at     TEXT
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_quotes_text ON quotes(text)")
    conn.commit()
    return conn


MAX_CHARS = 150  # quotes longer than this won't fit the centre frame cleanly

def insert_quote(conn: sqlite3.Connection, text: str, author: str, book: str,
                  tags: str, url: str) -> bool:
    """Insert quote; returns True if new, False if duplicate or too long."""
    if len(text) > MAX_CHARS:
        return False
    try:
        conn.execute(
            "INSERT INTO quotes (text, author, book, tags, url, scraped_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (text, author, book, tags, url, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape_page(client: httpx.Client, tag: str, page: int) -> list[dict]:
    url = BASE_URL.format(tag=tag, page=page)
    try:
        r = client.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  HTTP error on {url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    for block in soup.select(".quote"):
        text_el   = block.select_one(".quoteText")
        author_el = block.select_one(".authorOrTitle")
        book_el   = block.select_one(".quoteText .authorOrTitle ~ .authorOrTitle")

        if not text_el:
            continue

        # Extract quote text — strip the leading/trailing curly quotes
        raw = text_el.get_text(separator=" ", strip=True)
        # Goodreads wraps in “...” or similar; strip leading/trailing punctuation
        raw = raw.replace("“", "").replace("”", "")
        # Remove the attribution tail that sometimes bleeds in (― Author, Book)
        if "―" in raw:
            raw = raw[:raw.index("―")].strip()
        elif "―" in raw:
            raw = raw[:raw.index("―")].strip()
        text = raw.strip().strip('"').strip()

        author = ""
        book   = ""
        if author_el:
            parts = [s.strip() for s in author_el.get_text(",").split(",") if s.strip()]
            if parts:
                author = parts[0].strip("―").strip()
            if len(parts) > 1:
                book = parts[1].strip()

        # Collect all tags on this quote
        quote_tags = [a.get_text(strip=True) for a in block.select(".greyText a")]

        results.append({
            "text":   text,
            "author": author,
            "book":   book,
            "tags":   ", ".join(quote_tags) if quote_tags else tag,
            "url":    str(r.url),
        })

    return results


def scrape_tag(client: httpx.Client, conn: sqlite3.Connection,
               tag: str, pages: int) -> tuple[int, int]:
    new_total = 0
    dup_total = 0
    for page in range(1, pages + 1):
        quotes = scrape_page(client, tag, page)
        if not quotes:
            print(f"  [{tag}] page {page}: no quotes found, stopping")
            break
        for q in quotes:
            if q["text"]:
                added = insert_quote(conn, q["text"], q["author"], q["book"],
                                     q["tags"], q["url"])
                if added:
                    new_total += 1
                else:
                    dup_total += 1
        print(f"  [{tag}] page {page}: {len(quotes)} quotes "
              f"({sum(1 for q in quotes if q['text'])} valid)")
        delay = random.uniform(1.5, 3.0)
        time.sleep(delay)
    return new_total, dup_total


# ── CLI ───────────────────────────────────────────────────────────────────────

def cmd_list(conn: sqlite3.Connection, limit: int = 20):
    rows = conn.execute(
        "SELECT id, author, book, substr(text,1,80), used_at FROM quotes "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    print(f"\n{'ID':>4}  {'Author':<25} {'Book':<30} {'Preview':<55} {'Used'}")
    print("-" * 120)
    for row in rows:
        used = "✓" if row[4] else ""
        print(f"{row[0]:>4}  {row[1]:<25} {row[2]:<30} {row[3]:<55} {used}")
    total = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
    unused = conn.execute("SELECT COUNT(*) FROM quotes WHERE used_at IS NULL").fetchone()[0]
    print(f"\nTotal: {total}  |  Unused: {unused}")


def main():
    parser = argparse.ArgumentParser(description="Goodreads quote scraper")
    parser.add_argument("--account", default="lifequoteshere",
                        help="Account slug matching accounts/<slug>.yaml")
    parser.add_argument("--tags",  nargs="+", default=None,
                        help="Override Goodreads tag slugs (default: from account config)")
    parser.add_argument("--pages", type=int, default=3,
                        help="Pages to scrape per tag (default 3, ~30 quotes/page)")
    parser.add_argument("--list",  action="store_true", help="Show stored quotes")
    args = parser.parse_args()

    import account_config
    try:
        cfg = account_config.load(args.account)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    DB_PATH = BUSINESS_DIR / cfg.get("quotes_db", "data/quotes.db")
    tags    = args.tags or cfg.get("scrape_tags", DEFAULT_TAGS)

    conn = init_db(DB_PATH)

    if args.list:
        cmd_list(conn)
        return

    print(f"Account: {args.account}  |  DB: {DB_PATH}")
    print(f"Scraping {len(tags)} tags ({args.pages} pages each): {', '.join(tags)}\n")

    grand_new = 0
    grand_dup = 0

    with httpx.Client() as client:
        for tag in tags:
            print(f"\n=== Tag: {tag} ===")
            new, dup = scrape_tag(client, conn, tag, args.pages)
            grand_new += new
            grand_dup += dup
            print(f"  → {new} new, {dup} duplicates")

    conn.close()
    print(f"\nDone. Total new: {grand_new} | Duplicates skipped: {grand_dup}")


if __name__ == "__main__":
    main()
