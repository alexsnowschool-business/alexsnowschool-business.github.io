"""
Build data/episodes.json directly from the BBC RSS feeds (no local download
needed) and merge in any transcripts already produced under transcripts/, so
the static Read & Listen site has a single data file to fetch.

Run: uv run python scripts/build_episodes_json.py
"""

import hashlib
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.scraper.rss_scraper import RSScraper  # noqa: E402
from src.utils.openrouter_categorizer import OpenRouterCategorizer  # noqa: E402

TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
OUTPUT_FILE = BASE_DIR / "data" / "episodes.json"


def slugify(title: str) -> str:
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:10]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def build() -> list[dict]:
    scraper = RSScraper()
    episodes = []
    seen_ids = set()

    for feed_name, feed_url in scraper.list_available_feeds().items():
        for ep in scraper.get_episodes(feed_url):
            title = ep["title"]
            episode_id = slugify(title)
            if episode_id in seen_ids:
                continue
            seen_ids.add(episode_id)

            transcript_meta = load_json(TRANSCRIPTS_DIR / f"{title}_transcript.json")
            transcript_txt_path = TRANSCRIPTS_DIR / f"{title}_transcript.txt"
            transcript_text = (
                transcript_txt_path.read_text(encoding="utf-8")
                if transcript_txt_path.exists()
                else None
            )

            episodes.append(
                {
                    "id": episode_id,
                    "title": title,
                    "description": ep.get("description"),
                    "published": ep.get("published"),
                    "feed": feed_name,
                    # Stream straight from the BBC RSS enclosure — no local
                    # download required, and it plays from the deployed site
                    # since downloads/*.mp3 is never committed.
                    "source_url": ep.get("audio_url"),
                    "mp3": ep.get("audio_url"),
                    "has_transcript": transcript_text is not None,
                    "transcript": transcript_text,
                    "word_count": transcript_meta.get("word_count"),
                }
            )

    episodes.sort(key=lambda e: e["title"])

    topics = OpenRouterCategorizer().categorize(episodes)
    for ep in episodes:
        ep["topic"] = topics.get(ep["id"], "Uncategorized")

    return episodes


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    episodes = build()
    OUTPUT_FILE.write_text(
        json.dumps({"episodes": episodes}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(episodes)} episodes to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
