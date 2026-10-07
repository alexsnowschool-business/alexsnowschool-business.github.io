"""
Daily CI job for the Read & Listen archive:

1. Scan every feed in RSScraper.BBC_FEEDS for episodes (covers both the
   long-standing backlog and anything newly published since yesterday).
2. Transcribe up to DAILY_LIMIT episodes that don't have a transcript yet
   (oldest-published first), downloading each one only for the duration of
   the transcription pass.
3. Rebuild data/episodes.json, which also re-categorizes every episode by
   description via the OpenRouter AI categorizer.

Run: uv run python scripts/transcribe_daily.py
"""

import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.scraper.rss_scraper import RSScraper  # noqa: E402
from src.transcription.transcriber import WhisperTranscriber  # noqa: E402
from src.utils.logger import setup_logger  # noqa: E402
from config import Config  # noqa: E402

import build_episodes_json  # noqa: E402

logger = setup_logger(__name__)

DAILY_LIMIT = 20


def published_sort_key(ep: dict) -> float:
    """Oldest-first; episodes with an unparseable/missing date sort last."""
    try:
        return parsedate_to_datetime(ep.get("published", "")).timestamp()
    except (TypeError, ValueError):
        return float("inf")


def already_transcribed(title: str) -> bool:
    return (Config.TRANSCRIPTS_DIR / f"{title}_transcript.txt").exists()


def find_untranscribed(all_episodes: list) -> list:
    candidates = [ep for ep in all_episodes if not already_transcribed(ep["title"])]
    candidates.sort(key=published_sort_key)
    return candidates


def transcribe_episode(scraper: RSScraper, transcriber: WhisperTranscriber, ep: dict) -> bool:
    title = ep["title"]
    audio_path = scraper.download_audio(
        ep["audio_url"],
        title,
        metadata={
            "title": title,
            "description": ep.get("description", ""),
            "published": ep.get("published", ""),
            "source_url": ep["audio_url"],
        },
    )
    if not audio_path:
        logger.error(f"Download failed, skipping: {title}")
        return False

    try:
        transcript_path = transcriber.transcribe_and_save(audio_path)
        if not transcript_path:
            logger.error(f"Transcription failed: {title}")
        return transcript_path is not None
    finally:
        # Audio is only needed for the duration of this pass — downloads/*.mp3
        # is gitignored and not meant to accumulate in CI.
        audio_path.unlink(missing_ok=True)
        audio_path.with_suffix(".json").unlink(missing_ok=True)


def main():
    scraper = RSScraper()
    transcriber = WhisperTranscriber()

    logger.info("Scanning all BBC RSS feeds for episodes without a transcript...")
    all_episodes = build_episodes_json.fetch_episodes_from_rss(scraper)
    candidates = find_untranscribed(all_episodes)
    batch = candidates[:DAILY_LIMIT]
    logger.info(f"{len(candidates)} untranscribed episode(s) found; transcribing {len(batch)} today")

    transcribed = 0
    for i, ep in enumerate(batch, 1):
        logger.info(f"[{i}/{len(batch)}] {ep['title']}")
        if transcribe_episode(scraper, transcriber, ep):
            transcribed += 1

    logger.info(f"Transcribed {transcribed}/{len(batch)} episode(s)")

    # Reuse the RSS data already fetched above instead of hitting every feed
    # again — only transcript merging + AI categorization run from here.
    logger.info("Rebuilding data/episodes.json (includes AI topic categorization)...")
    build_episodes_json.write_episodes(build_episodes_json.assemble_episodes(all_episodes))


if __name__ == "__main__":
    main()
