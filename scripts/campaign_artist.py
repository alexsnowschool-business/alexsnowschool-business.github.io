#!/usr/bin/env python3
"""
Print the next campaign artist based on posting history in art.db.

Usage:
    python scripts/campaign_artist.py

Builds the rotation dynamically from art_items: all artists with >= MIN_LOTS
lots, deduplicated by last name, ranked by a composite score (lot depth,
avg % over estimate, max hammer). Skips any artist that appeared in the
last RECENCY_WINDOW posts to prevent back-to-back runs.
"""

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "art.db"

MIN_LOTS = 4       # minimum lots in art_items to qualify for the rotation
RECENCY_WINDOW = 4  # skip artist if they appear in the last N posts


def _canonical(artist: str) -> str:
    """'MARC CHAGALL (B. 1887)' → 'Chagall', 'Roy Lichtenstein' → 'Lichtenstein'."""
    cleaned = re.sub(r"\s*\(.*?\)", "", artist).strip()
    parts = cleaned.split()
    return parts[-1].title() if parts else artist.title()


def _matches(rotation_name: str, db_artist: str) -> bool:
    return rotation_name.upper() in db_artist.upper()


def _build_rotation(cur: sqlite3.Cursor) -> list[str]:
    """Return artists ordered by composite score, built from art_items."""
    cur.execute(
        """
        SELECT
            artist,
            COUNT(*) AS lot_count,
            AVG(CASE WHEN estimate_low > 0
                     THEN (hammer_usd - estimate_low) / estimate_low * 100 END) AS avg_pct,
            MAX(hammer_usd) AS max_hammer
        FROM art_items
        WHERE hammer_usd > 0 AND artist IS NOT NULL
        GROUP BY artist
        HAVING lot_count >= ?
        """,
        (MIN_LOTS,),
    )

    # Deduplicate: 'MARC CHAGALL' and 'Marc Chagall' collapse to 'Chagall'.
    agg: dict[str, dict] = {}
    for artist, lot_count, avg_pct, max_hammer in cur.fetchall():
        key = _canonical(artist)
        if key not in agg:
            agg[key] = {"lots": 0, "avg_pct": 0.0, "max_hammer": 0.0}
        agg[key]["lots"] += lot_count
        agg[key]["avg_pct"] = max(agg[key]["avg_pct"], avg_pct or 0.0)
        agg[key]["max_hammer"] = max(agg[key]["max_hammer"], max_hammer or 0.0)

    # Normalise each dimension to [0, 1] then combine with weights.
    max_lots = max(d["lots"] for d in agg.values()) or 1
    max_avg = max(d["avg_pct"] for d in agg.values()) or 1
    max_ham = max(d["max_hammer"] for d in agg.values()) or 1

    for d in agg.values():
        d["score"] = (
            (d["lots"] / max_lots) * 0.4
            + (d["avg_pct"] / max_avg) * 0.4
            + (d["max_hammer"] / max_ham) * 0.2
        )

    return sorted(agg.keys(), key=lambda k: agg[k]["score"], reverse=True)


def get_rotation(db_path: Path = DB_PATH) -> list[str]:
    """Return the full artist rotation list built from art_items."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rotation = _build_rotation(cur)
    conn.close()
    return rotation


def next_artist(db_path: Path = DB_PATH) -> str:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rotation = _build_rotation(cur)

    # Fetch every post ever so we can find the true last-posted date per artist.
    cur.execute(
        """
        SELECT artist, posted_at FROM posted_reels
        ORDER BY posted_at DESC
        """,
    )
    all_posts = cur.fetchall()
    conn.close()

    recent_artists = [r[0] for r in all_posts]

    blocked = {
        name
        for db_artist in recent_artists[:RECENCY_WINDOW]
        for name in rotation
        if _matches(name, db_artist)
    }

    # last_posted: most recent posted_at for each rotation artist (None = never posted)
    last_posted: dict[str, str | None] = {a: None for a in rotation}
    for db_artist, posted_at in all_posts:
        for name in rotation:
            if _matches(name, db_artist) and last_posted[name] is None:
                last_posted[name] = posted_at

    candidates = [a for a in rotation if a not in blocked]
    if not candidates:
        candidates = rotation  # history too short to fill the window — ignore block

    # Pick whoever was posted longest ago (never-posted artists sort first).
    return min(candidates, key=lambda a: last_posted[a] or "")


if __name__ == "__main__":
    print(next_artist())
