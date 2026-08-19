"""
init_db.py — Who Owns What
Creates (or migrates) the SQLite database schema.
Run once to initialise, or re-run safely (IF NOT EXISTS guards).

Usage:
    python scripts/whoownswhat/init_db.py
    python scripts/whoownswhat/init_db.py --db path/to/custom.db
"""

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"


def create_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # ── ENTITIES ───────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id                TEXT PRIMARY KEY,   -- 'volkswagen', 'susanne-klatten'
            type              TEXT NOT NULL,       -- 'company' | 'person'
            country           TEXT NOT NULL,       -- 'germany', 'us', 'uk' ...
            name              TEXT NOT NULL,
            summary           TEXT,
            last_scraped      TEXT,               -- ISO-8601 datetime
            -- company fields
            ticker            TEXT,
            exchange          TEXT,
            sector            TEXT,
            headquarters      TEXT,
            founded           TEXT,
            employees         TEXT,
            revenue           TEXT,
            market_cap        TEXT,
            -- person fields
            title             TEXT,
            nationality       TEXT,
            born              TEXT,
            net_worth         TEXT,
            net_worth_rank    TEXT,
            net_worth_source  TEXT,
            net_worth_url     TEXT
        )
    """)

    # ── SHAREHOLDERS ───────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shareholders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            stake       TEXT,
            type        TEXT,
            source      TEXT,
            source_url  TEXT,
            as_of       TEXT   -- e.g. 'Q4 2023'
        )
    """)

    # ── EXECUTIVE COMPENSATION ─────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS compensation (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id         TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            fiscal_year       INTEGER,
            ceo_name          TEXT,
            ceo_title         TEXT,
            ceo_total         TEXT,
            ceo_salary        TEXT,
            ceo_equity        TEXT,
            ceo_other         TEXT,
            median_worker     TEXT,
            ceo_worker_ratio  TEXT,
            source            TEXT,
            source_url        TEXT
        )
    """)

    # ── LOBBYING ───────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lobbying (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            year        TEXT,
            amount      TEXT,
            currency    TEXT DEFAULT 'EUR',
            source      TEXT,
            source_url  TEXT
        )
    """)

    # ── POLITICAL SPENDING ─────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS political_spending (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            pac         TEXT,
            cycle       TEXT,   -- e.g. '2023', '2024'
            total       TEXT,
            currency    TEXT DEFAULT 'EUR',
            note        TEXT,
            source      TEXT,
            source_url  TEXT
        )
    """)

    # ── FINES & SETTLEMENTS ────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fines (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            year        TEXT,
            description TEXT,
            source      TEXT,
            source_url  TEXT
        )
    """)

    # ── LABOUR ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS labor (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            description TEXT,
            source      TEXT,
            source_url  TEXT
        )
    """)

    # ── COMPETITORS (companies) ────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS competitors (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            name        TEXT
        )
    """)

    # ── ASSETS (persons) ──────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            name        TEXT,
            description TEXT,
            source      TEXT,
            source_url  TEXT
        )
    """)

    # ── BOARD MEMBERSHIPS (persons) ───────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS board_memberships (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            org         TEXT,
            role        TEXT,
            source      TEXT
        )
    """)

    # ── FOUNDATIONS (persons) ─────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS foundations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            name        TEXT,
            description TEXT,
            source      TEXT,
            source_url  TEXT
        )
    """)

    # ── TIMELINE (persons) ────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS timeline (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            year        TEXT,
            event       TEXT
        )
    """)

    # ── SOURCES ───────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            title       TEXT,
            url         TEXT
        )
    """)

    # ── FACT CARDS ────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fact_cards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            country     TEXT,   -- NULL = global
            category    TEXT,
            headline    TEXT NOT NULL,
            detail      TEXT,
            source      TEXT,
            source_url  TEXT,
            active      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── SCRAPE LOG ────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scrape_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id   TEXT,
            scraper     TEXT,
            status      TEXT,   -- 'ok' | 'error' | 'no_change'
            detail      TEXT,
            ran_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── COMPANY QUEUE ─────────────────────────────────────────────
    # Tracks German companies to scrape. Populated by discover_germany.py,
    # processed daily by scrape_company_batch.py (5 per run).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_queue (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            slug          TEXT UNIQUE NOT NULL,   -- 'bayer', 'allianz'
            name          TEXT NOT NULL,           -- 'Bayer AG'
            ticker        TEXT,                    -- 'BAYN'
            index_name    TEXT,                    -- 'DAX40' | 'MDAX' | 'SDAX'
            wiki_title    TEXT,                    -- Wikipedia page title (English)
            wiki_title_de TEXT,                    -- Wikipedia page title (German)
            wikidata_qid  TEXT,                    -- Wikidata Q-ID, e.g. 'Q152006'
            status        TEXT DEFAULT 'pending',  -- 'pending' | 'scraped' | 'error' | 'skipped'
            last_attempt  TEXT,                    -- ISO-8601 datetime
            error_detail  TEXT,
            added_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    print("Schema created / verified.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise the Who Owns What SQLite database.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite database file")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        create_schema(conn)
        print(f"Database ready at: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
