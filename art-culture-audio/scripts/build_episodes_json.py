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


def fetch_episodes_from_rss(scraper: RSScraper = None) -> list[dict]:
    """Fetch every episode (title/description/published/feed/audio_url) from
    all BBC_FEEDS, deduped by id. Callers that already need the raw RSS data
    (e.g. transcribe_daily.py, to find untranscribed episodes) can reuse this
    instead of hitting every feed again via assemble_episodes()."""
    scraper = scraper or RSScraper()
    episodes = []
    seen_ids = set()

    for feed_name, feed_url in scraper.list_available_feeds().items():
        for ep in scraper.get_episodes(feed_url):
            title = ep["title"]
            episode_id = slugify(title)
            if episode_id in seen_ids:
                continue
            seen_ids.add(episode_id)
            episodes.append(
                {
                    "id": episode_id,
                    "title": title,
                    "description": ep.get("description"),
                    "published": ep.get("published"),
                    "feed": feed_name,
                    "audio_url": ep.get("audio_url"),
                }
            )

    return episodes


def assemble_episodes(raw_episodes: list[dict]) -> list[dict]:
    """Merge transcripts + AI topic categorization onto already-fetched RSS
    episode data (no network RSS calls here — only transcript file reads and
    the OpenRouter categorizer, which itself skips already-cached ids)."""
    episodes = []

    for ep in raw_episodes:
        title = ep["title"]
        transcript_meta = load_json(TRANSCRIPTS_DIR / f"{title}_transcript.json")
        transcript_txt_path = TRANSCRIPTS_DIR / f"{title}_transcript.txt"
        transcript_text = (
            transcript_txt_path.read_text(encoding="utf-8")
            if transcript_txt_path.exists()
            else None
        )

        episodes.append(
            {
                "id": ep["id"],
                "title": title,
                "description": ep.get("description"),
                "published": ep.get("published"),
                "feed": ep.get("feed"),
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


def build() -> list[dict]:
    return assemble_episodes(fetch_episodes_from_rss())


def write_episodes(episodes: list[dict]):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps({"episodes": episodes}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(episodes)} episodes to {OUTPUT_FILE}")


def main():
    write_episodes(build())


if __name__ == "__main__":
    main()
