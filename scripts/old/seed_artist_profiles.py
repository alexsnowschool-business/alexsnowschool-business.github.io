"""
Seed artist_profiles table in data/art.db from scripts/artist_profiles.json.

Run once (or whenever the JSON is updated):
    uv run python scripts/seed_artist_profiles.py

The JSON file stays as the editable source; this imports it into SQLite
so build_research_json.py can query everything from a single DB.
"""

import json
from pathlib import Path

from scraper.art_db import connect, upsert_artist_profile

PROFILES_PATH = Path("scripts/artist_profiles.json")


if __name__ == "__main__":
    profiles = json.loads(PROFILES_PATH.read_text())
    print(f"Seeding {len(profiles)} artist profiles into data/art.db…")
    with connect() as conn:
        for name_key, data in profiles.items():
            upsert_artist_profile(conn, {"name_key": name_key, **data})
    print("Done.")
