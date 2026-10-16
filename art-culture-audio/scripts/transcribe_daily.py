"""
Daily CI job for the Read & Listen archive:

1. Scan every feed in RSScraper.BBC_FEEDS for episodes (covers both the
   long-standing backlog and anything newly published since yesterday).
2. Transcribe up to DAILY_LIMIT episodes that don't have a transcript yet
   (oldest-published first), downloading each one only for the duration of
   the transcription pass. If TRANSCRIBE_EPISODE_TITLE is set (see
   .github/workflows/daily-transcribe.yml's workflow_dispatch input), only
   that one episode (exact title match, transcribed even if already done) is
   processed instead of the daily batch.
3. Rebuild data/episodes.json, which also re-categorizes every episode by
   description via the OpenRouter AI categorizer.

DAILY_LIMIT is configurable via the TRANSCRIBE_DAILY_LIMIT env var, defaulting
to 5.

Run: uv run python scripts/transcribe_daily.py
"""

import json
import os
import sys
from datetime import datetime, timezone
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

DAILY_LIMIT = int(os.getenv("TRANSCRIBE_DAILY_LIMIT", "5"))
EPISODE_TITLE = os.getenv("TRANSCRIBE_EPISODE_TITLE", "").strip()
MANIFEST_FILE = BASE_DIR / "data" / "transcribed.json"


def published_sort_key(ep: dict) -> float:
    """Oldest-first; episodes with an unparseable/missing date sort last."""
    try:
        return parsedate_to_datetime(ep.get("published", "")).timestamp()
    except (TypeError, ValueError):
        return float("inf")


def load_manifest(all_episodes: list) -> dict:
    """Episode id -> {title, transcribed_at}. Keyed by the stable episode id
    (md5 of the title), never by a filename. Transcripts already on disk are
    folded in on every run, so the first run backfills the manifest."""
    try:
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    for ep in all_episodes:
        if ep["id"] not in manifest and build_episodes_json.transcript_path(ep["title"]).exists():
            manifest[ep["id"]] = {"title": ep["title"], "transcribed_at": None}
    return manifest


def save_manifest(manifest: dict):
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_FILE.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def find_untranscribed(all_episodes: list, manifest: dict) -> list:
    candidates = [ep for ep in all_episodes if ep["id"] not in manifest]
    candidates.sort(key=published_sort_key)
    return candidates


def find_by_title(all_episodes: list, title: str) -> dict | None:
    needle = title.strip().lower()
    return next((ep for ep in all_episodes if ep["title"].strip().lower() == needle), None)


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

    logger.info("Scanning all BBC RSS feeds for episodes...")
    all_episodes = build_episodes_json.fetch_episodes_from_rss(scraper)

    manifest = load_manifest(all_episodes)

    if EPISODE_TITLE:
        episode = find_by_title(all_episodes, EPISODE_TITLE)
        if episode is None:
            logger.error(f"No episode found matching title: {EPISODE_TITLE!r}")
            sys.exit(1)
        batch = [episode]
        logger.info(f"Transcribing requested episode: {episode['title']}")
    else:
        candidates = find_untranscribed(all_episodes, manifest)
        batch = candidates[:DAILY_LIMIT]
        logger.info(f"{len(candidates)} untranscribed episode(s) found; transcribing {len(batch)} today")

    transcribed_titles = []
    for i, ep in enumerate(batch, 1):
        logger.info(f"[{i}/{len(batch)}] {ep['title']}")
        if transcribe_episode(scraper, transcriber, ep):
            transcribed_titles.append(ep["title"])
            manifest[ep["id"]] = {
                "title": ep["title"],
                "transcribed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_manifest(manifest)  # persist per episode so a crash keeps progress

    save_manifest(manifest)  # also persists the backfill when nothing was transcribed
    logger.info(f"Transcribed {len(transcribed_titles)}/{len(batch)} episode(s)")

    # Consumed by .github/workflows/daily-transcribe.yml to list the
    # transcribed episode titles in the commit message; not committed itself.
    titles_file = BASE_DIR / ".transcribed_titles.txt"
    titles_file.write_text(
        "\n".join(transcribed_titles), encoding="utf-8"
    )

    # Reuse the RSS data already fetched above instead of hitting every feed
    # again — only transcript merging + AI categorization run from here.
    logger.info("Rebuilding data/episodes.json (includes AI topic categorization)...")
    build_episodes_json.write_episodes(build_episodes_json.assemble_episodes(all_episodes))


if __name__ == "__main__":
    main()
