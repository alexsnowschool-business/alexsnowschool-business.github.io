import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path("data/hermes.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id                 TEXT NOT NULL,
    platform           TEXT NOT NULL,
    name               TEXT,
    brand              TEXT,
    model              TEXT,
    price              TEXT,
    price_value        REAL,
    description        TEXT,
    condition          TEXT,
    size               TEXT,
    color              TEXT,
    colors             TEXT,
    country            TEXT,
    listed_at          TEXT,
    source_url         TEXT,
    authenticity_label TEXT,
    search_query       TEXT,
    image_urls         TEXT,
    local_images       TEXT,
    scraped_at         TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (id, platform)
);
"""


def _price_value(price_str: str | None) -> float:
    if not price_str:
        return -1.0
    digits = re.sub(r"[^\d]", "", price_str)
    return float(digits) if digits else -1.0


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def item_exists(conn: sqlite3.Connection, item_id: str, platform: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM items WHERE id = ? AND platform = ?", (item_id, platform)
    ).fetchone())


def upsert_item(conn: sqlite3.Connection, product: dict) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO items (
            id, platform, name, brand, model, price, price_value,
            description, condition, size, color, colors, country,
            listed_at, source_url, authenticity_label, search_query,
            image_urls, local_images
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        product["id"],
        product.get("platform", ""),
        product.get("name"),
        product.get("brand"),
        product.get("model"),
        product.get("price"),
        _price_value(product.get("price")),
        product.get("description"),
        product.get("condition"),
        product.get("size"),
        product.get("color"),
        json.dumps(product.get("colors") or []),
        product.get("country"),
        str(product.get("listed_at") or ""),
        product.get("source_url"),
        product.get("authenticity_label"),
        product.get("search_query"),
        json.dumps(product.get("image_urls") or []),
        json.dumps(product.get("local_images") or []),
    ))
    conn.commit()


def all_items(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM items ORDER BY price_value DESC"
    ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["image_urls"]  = json.loads(d["image_urls"]  or "[]")
        d["local_images"] = json.loads(d["local_images"] or "[]")
        d["colors"]      = json.loads(d["colors"]      or "[]")
        result.append(d)
    return result
