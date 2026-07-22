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
    """'MARC CHAGALL (B. 1887)' → 'Chagall', 'Roy Lichtenstein' → 'Lichtenstein'.
    Returns '' for entries that are clearly not a person (> 4 words after stripping parens)."""
    cleaned = re.sub(r"\s*\(.*?\)", "", artist).strip()
    parts = cleaned.split()
    if len(parts) > 4:
        return ""
    return parts[-1].title() if parts else artist.title()


def _clean_name(artist: str) -> str:
    """Strip birth-year suffix and title-case: 'TRACEY EMIN (B. 1963)' → 'Tracey Emin'."""
    return re.sub(r"\s*\([^)]+\)\s*$", "", artist).strip().title()


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
        WHERE sale_performance = 'above'
          AND artist IS NOT NULL
        GROUP BY artist
        HAVING lot_count >= ?
        """,
        (MIN_LOTS,),
    )

    # Deduplicate: 'MARC CHAGALL' and 'Marc Chagall' collapse to 'Chagall' key,
    # but we track the full clean name so callers get 'Marc Chagall' not 'Chagall'.
    agg: dict[str, dict] = {}
    for artist, lot_count, avg_pct, max_hammer in cur.fetchall():
        key = _canonical(artist)
        if not key:
            continue
        if key not in agg:
            agg[key] = {"lots": 0, "avg_pct": 0.0, "max_hammer": 0.0,
                        "full_name": _clean_name(artist)}
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

    # Return full names (e.g. "Tracey Emin") sorted by score so LIKE filters
    # are unambiguous — returning just "Emin" would also match "Pincemin".
    return sorted(
        (d["full_name"] for d in agg.values()),
        key=lambda name: agg[_canonical(name)]["score"],
        reverse=True,
    )


def get_rotation(db_path: Path = DB_PATH) -> list[str]:
    """Return the full artist rotation list built from art_items."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    rotation = _build_rotation(cur)
    conn.close()
    return rotation


def _unposted_above_estimate_count(cur: sqlite3.Cursor, name: str) -> int:
    """Count unposted lots for this artist where hammer beat the high estimate."""
    cur.execute(
        """
        SELECT COUNT(*) FROM art_items
        WHERE sale_performance = 'above'
          AND artist IS NOT NULL
          AND UPPER(artist) LIKE '%' || UPPER(?) || '%'
          AND id NOT IN (SELECT lot_id FROM posted_reels)
        """,
        (name,),
    )
    row = cur.fetchone()
    return row[0] if row else 0


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

    # --- Sticky campaign: keep the current artist until all their lots are posted ---
    # Find the most recently posted artist that maps to a rotation entry.
    current_campaign: str | None = None
    for db_artist, _ in all_posts:
        for name in rotation:
            if _matches(name, db_artist):
                current_campaign = name
                break
        if current_campaign:
            break

    if current_campaign and _unposted_above_estimate_count(cur, current_campaign) > 0:
        conn.close()
        return current_campaign

    # Current artist exhausted (or no history) — pick the next one via rotation.
    recent_artists = [r[0] for r in all_posts]

    # Collect the last RECENCY_WINDOW *distinct* posted artists (not rows).
    seen: list[str] = []
    for db_artist in recent_artists:
        if db_artist not in seen:
            seen.append(db_artist)
        if len(seen) >= RECENCY_WINDOW:
            break

    blocked = {
        name
        for db_artist in seen
        for name in rotation
        if _matches(name, db_artist)
    }

    # last_posted: most recent posted_at for each rotation artist (None = never posted)
    last_posted: dict[str, str | None] = {a: None for a in rotation}
    for db_artist, posted_at in all_posts:
        for name in rotation:
            if _matches(name, db_artist) and last_posted[name] is None:
                last_posted[name] = posted_at

    # Only consider artists who still have unposted above-estimate lots.
    candidates = [
        a for a in rotation
        if a not in blocked and _unposted_above_estimate_count(cur, a) > 0
    ]
    if not candidates:
        # Fall back: ignore block and lot-exhaustion filter so we always return someone.
        candidates = [a for a in rotation if a not in blocked] or rotation

    conn.close()

    # Pick whoever was posted longest ago; tiebreak by rotation rank so the
    # highest-scored never-posted artist surfaces before lower-ranked ones.
    rank_of = {a: i for i, a in enumerate(rotation)}
    return min(candidates, key=lambda a: (last_posted[a] or "1900-01-01", rank_of[a]))


if __name__ == "__main__":
    print(next_artist())
