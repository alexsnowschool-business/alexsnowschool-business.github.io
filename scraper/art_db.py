"""
Separate SQLite database for art auction lots — isolated from the fashion/hermes dataset.
DB lives at data/art.db; schema is art_items only.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/art.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS art_items (
    id               TEXT NOT NULL,
    auction_house    TEXT NOT NULL,
    artist           TEXT,
    title            TEXT,
    medium           TEXT,
    medium_category  TEXT,
    dimensions       TEXT,
    year_created     TEXT,
    lot_number       TEXT,
    sale_name        TEXT,
    sale_date        TEXT,
    estimate_low     REAL,
    estimate_high    REAL,
    hammer_price     REAL,
    currency         TEXT DEFAULT 'USD',
    hammer_usd       REAL,
    sale_performance TEXT,
    provenance       TEXT,
    description      TEXT,
    image_urls       TEXT DEFAULT '[]',
    source_url       TEXT,
    scraped_at       TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (id, auction_house)
);

CREATE TABLE IF NOT EXISTS artist_profiles (
    name_key           TEXT PRIMARY KEY,
    display_name       TEXT NOT NULL,
    dates              TEXT,
    nationality        TEXT,
    movement           TEXT,
    movement_id        TEXT,
    bio                TEXT,
    famous_works       TEXT DEFAULT '[]',
    lesser_known_works TEXT DEFAULT '[]',
    updated_at         TEXT DEFAULT (datetime('now'))
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def lot_exists(conn: sqlite3.Connection, lot_id: str, auction_house: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM art_items WHERE id = ? AND auction_house = ?",
        (lot_id, auction_house),
    ).fetchone())


def _sale_performance(hammer: float | None, low: float | None, high: float | None) -> str:
    """Classify how the hammer price compared to the pre-sale estimate."""
    if not hammer or not low or not high:
        return "unknown"
    if hammer > high:
        return "above"
    if hammer >= low:
        return "within"
    return "below"


def upsert_lot(conn: sqlite3.Connection, lot: dict) -> None:
    hammer = lot.get("hammer_price")
    low    = lot.get("estimate_low")
    high   = lot.get("estimate_high")
    perf   = _sale_performance(hammer, low, high)
    conn.execute("""
        INSERT OR IGNORE INTO art_items (
            id, auction_house, artist, title, medium, medium_category,
            dimensions, year_created, lot_number, sale_name, sale_date,
            estimate_low, estimate_high, hammer_price, currency, hammer_usd,
            sale_performance, provenance, description, image_urls, source_url
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
    """, (
        lot["id"],
        lot.get("auction_house", ""),
        lot.get("artist"),
        lot.get("title"),
        lot.get("medium"),
        lot.get("medium_category"),
        lot.get("dimensions"),
        lot.get("year_created"),
        lot.get("lot_number"),
        lot.get("sale_name"),
        lot.get("sale_date"),
        low,
        high,
        hammer,
        lot.get("currency", "USD"),
        lot.get("hammer_usd") or hammer,
        perf,
        lot.get("provenance"),
        lot.get("description"),
        json.dumps(lot.get("image_urls") or []),
        lot.get("source_url"),
    ))
    conn.commit()


def upsert_artist_profile(conn: sqlite3.Connection, profile: dict) -> None:
    conn.execute("""
        INSERT INTO artist_profiles (
            name_key, display_name, dates, nationality, movement, movement_id,
            bio, famous_works, lesser_known_works, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(name_key) DO UPDATE SET
            display_name       = excluded.display_name,
            dates              = excluded.dates,
            nationality        = excluded.nationality,
            movement           = excluded.movement,
            movement_id        = excluded.movement_id,
            bio                = excluded.bio,
            famous_works       = excluded.famous_works,
            lesser_known_works = excluded.lesser_known_works,
            updated_at         = excluded.updated_at
    """, (
        profile["name_key"],
        profile["display_name"],
        profile.get("dates"),
        profile.get("nationality"),
        profile.get("movement"),
        profile.get("movement_id"),
        profile.get("bio"),
        json.dumps(profile.get("famous_works") or []),
        json.dumps(profile.get("lesser_known_works") or []),
    ))
    conn.commit()


def all_artist_profiles(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute("SELECT * FROM artist_profiles").fetchall()
    result = {}
    for row in rows:
        d = dict(row)
        d["famous_works"]       = json.loads(d.get("famous_works") or "[]")
        d["lesser_known_works"] = json.loads(d.get("lesser_known_works") or "[]")
        result[d["name_key"]] = d
    return result


def all_lots(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM art_items ORDER BY hammer_usd DESC NULLS LAST"
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["image_urls"] = json.loads(d.get("image_urls") or "[]")
        result.append(d)
    return result
