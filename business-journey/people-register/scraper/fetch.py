"""Fetch-and-store, shared by both scrapers.

Design rule (design draft section 4): store the raw fetched page first,
parse second — a parser bug should never cost you the source data. Each
scraper gets its own retry/backoff so a Bundesanzeiger outage never blocks
Handelsregister ingestion.
"""

import time
import uuid
from pathlib import Path

import httpx

RAW_DIR = Path(__file__).parent / "data" / "raw"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 2


def fetch_and_store(url: str, source: str) -> tuple[str, str]:
    """Fetch `url` with retry/backoff and store the raw response.

    Returns (source_document_id, raw_text). source_document_id is a path
    relative to RAW_DIR, suitable for storing in events.source_document_id.
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = httpx.get(url, timeout=30, follow_redirects=True)
            response.raise_for_status()
            break
        except (httpx.HTTPError,) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_SECONDS * attempt)
    else:
        raise RuntimeError(f"Failed to fetch {url} after {MAX_ATTEMPTS} attempts") from last_error

    (RAW_DIR / source).mkdir(parents=True, exist_ok=True)
    document_id = f"{source}/{uuid.uuid4()}.html"
    (RAW_DIR / document_id).write_text(response.text, encoding="utf-8")
    return document_id, response.text


def load_raw(source_document_id: str) -> str:
    return (RAW_DIR / source_document_id).read_text(encoding="utf-8")
