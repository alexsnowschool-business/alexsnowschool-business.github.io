"""
Generate biographical profiles for stub artists using the Claude API.

Fetches artists that exist in art_items but have no artist_profiles entry,
calls Claude in batches to generate structured profiles, and upserts them
directly into data/art.db.

Usage:
    uv run python scripts/enrich_artist_bios.py            # all stubs
    uv run python scripts/enrich_artist_bios.py --limit 10
    uv run python scripts/enrich_artist_bios.py --dry-run
"""

import argparse
import json
import re
import sys
import time

import anthropic

from scraper.art_db import connect, upsert_artist_profile

_STRIP_DATES = re.compile(
    r"\s*\((?:b\.\s*\d{4}|B\.\s*\d{4}|\d{4}\s*[-–]\s*(?:\d{4}|present)|\d{4})\)\s*$",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """\
You are an art historian writing for an auction research platform.
For each artist supplied, return a JSON array of profile objects.
Each object must have exactly these fields:

{
  "name_key": "ARTIST NAME UPPERCASED AS GIVEN",
  "display_name": "Properly Cased Name",
  "dates": "YYYY–YYYY  or  b. YYYY",
  "nationality": "Nationality adjective, e.g. American",
  "movement": "Primary Movement · Secondary if relevant",
  "movement_id": "lowercase-hyphenated-slug",
  "bio": "Two or three paragraph scholarly essay. Editorial, precise, historically grounded. No bullet points.",
  "famous_works": [
    {"title": "Work Title", "year": "YYYY", "notes": "One sentence contextualising significance."},
    {"title": "Work Title", "year": "YYYY", "notes": "..."},
    {"title": "Work Title", "year": "YYYY", "notes": "..."}
  ],
  "lesser_known_works": [
    {"title": "Work Title", "year": "YYYY", "notes": "One sentence."},
    {"title": "Work Title", "year": "YYYY", "notes": "..."}
  ]
}

movement_id slugs to use: abstract-expressionism, pop-art, modernism, contemporary,
impressionism, minimalism, conceptual, surrealism, neo-expressionism, photography,
sculpture, street-art, colour-field, fluxus, expressionism, cubism, dada,
post-impressionism, performance, installation. Choose the best fit.

Provide 3–4 famous_works and 2–3 lesser_known_works per artist.
Return ONLY the JSON array — no markdown fences, no commentary.\
"""


def get_stub_artists(conn) -> list[str]:
    """Return normalised name_keys for artists in art_items without a profile."""
    rows = conn.execute(
        "SELECT DISTINCT artist FROM art_items WHERE artist IS NOT NULL"
    ).fetchall()
    all_names = set()
    for (name,) in rows:
        key = _STRIP_DATES.sub("", name).upper().strip()
        if key:
            all_names.add(key)

    profiled = {row[0] for row in conn.execute("SELECT name_key FROM artist_profiles")}
    return sorted(all_names - profiled)


def generate_profiles(client: anthropic.Anthropic, name_keys: list[str]) -> list[dict]:
    names_block = "\n".join(f"- {k}" for k in name_keys)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Generate profiles for:\n{names_block}"}],
    )
    text = msg.content[0].text.strip()
    # Strip accidental markdown fences
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich stub artist bios via Claude API")
    parser.add_argument("--limit",      type=int, default=None, help="Max artists to process")
    parser.add_argument("--batch-size", type=int, default=5,    help="Artists per API call (default 5)")
    parser.add_argument("--dry-run",    action="store_true",    help="Print profiles, do not save")
    args = parser.parse_args()

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment

    with connect() as conn:
        stubs = get_stub_artists(conn)

        if not stubs:
            print("All artists already have profiles — nothing to do.")
            return

        if args.limit:
            stubs = stubs[: args.limit]

        total = len(stubs)
        print(f"{total} stub artist{'s' if total != 1 else ''} to enrich "
              f"(batch size {args.batch_size})…\n")

        done = 0
        errors = 0
        for i in range(0, total, args.batch_size):
            batch = stubs[i : i + args.batch_size]
            batch_num = i // args.batch_size + 1
            total_batches = (total + args.batch_size - 1) // args.batch_size
            print(f"  [{batch_num}/{total_batches}] {', '.join(k.title() for k in batch)}")

            try:
                profiles = generate_profiles(client, batch)
            except Exception as exc:
                print(f"    ERROR: {exc}", file=sys.stderr)
                errors += 1
                continue

            for profile in profiles:
                if args.dry_run:
                    print(json.dumps(profile, indent=2, ensure_ascii=False))
                else:
                    upsert_artist_profile(conn, profile)
                done += 1

            if i + args.batch_size < total:
                time.sleep(0.3)

        print(f"\nDone — {done} profiles {'printed' if args.dry_run else 'saved'}."
              + (f"  {errors} batch error(s)." if errors else ""))


if __name__ == "__main__":
    main()
