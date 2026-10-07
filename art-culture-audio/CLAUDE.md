# Culture & Audio Archive

Status: In Development
Audience: Researchers, students, and lifelong learners wanting to read along with BBC lectures and cultural broadcasts
Brand tone: Editorial listening room — quiet, unhurried, text-forward

## Key sections
- Library (`index.html#/`) — searchable list of episodes, filterable by listening status
- Episode detail (`index.html#/episode/<id>`) — audio player + full transcript, status tracked in `localStorage`

## Data flow
- `scripts/build_episodes_json.py` fetches episode metadata (title, description, published, audio URL)
  directly from every feed in `RSScraper.BBC_FEEDS` — no local download required — merges in any matching
  transcript from `transcripts/*_transcript.txt` / `*_transcript.json` (Whisper output), categorizes each
  episode by description via `src/utils/openrouter_categorizer.py` (OpenRouter API, cached in
  `data/topic_cache/openrouter_categorizations.json`), and writes `data/episodes.json`.
- Requires `OPENROUTER_API_KEY` in `.env` for categorization; without it every episode falls back to
  "Uncategorized".
- Run it to refresh the library: `.venv/bin/python scripts/build_episodes_json.py`
- `data/episodes.json` is the only file the frontend fetches — it is the sole exception carved out of the
  `data/*` gitignore rule (`!data/episodes.json`).
- `scripts/transcribe_daily.py` (run daily by `.github/workflows/daily-transcribe.yml`) scans every RSS feed
  for episodes without a transcript — covering both the old backlog and anything newly published — picks the
  5 oldest-published untranscribed ones, downloads each just long enough to run Whisper, deletes the audio
  again, then reuses that same fetched RSS data with `build_episodes_json.assemble_episodes()` (no second
  RSS fetch) so the new transcripts and AI topic categorization land in `data/episodes.json` together.
  `transcripts/*.txt`/`*.json` are committed (not gitignored) so this backlog persists across daily runs
  instead of re-transcribing the same episodes.

## Backend (unchanged)
- `app.py` / `src/` still hold the Gradio tool used locally to download BBC RSS episodes and run Whisper
  transcription (`src/scraper/rss_scraper.py`, `src/transcription/transcriber.py`). That tool is for content
  production, not for the public site — the static frontend only ever reads `data/episodes.json`.
- `src/utils/history_manager.py` (JSON-file based) is superseded on the frontend by `localStorage` in
  `script.js`; it's unused by the static site but still available for the Gradio tool.

## Notes
- `downloads/*.mp3` are gitignored (large binaries) and never committed. `build_episodes_json.py` instead
  points `mp3` at the BBC RSS enclosure URL (`meta["source_url"]`) when available, so the deployed GitHub
  Pages site streams audio directly from BBC's CDN rather than requiring the local file. Episodes downloaded
  without metadata (no matching `downloads/*.json`) fall back to the local `downloads/` path and are only
  playable locally.
- Roman numerals are used for in-page section ordering (I., II.) per the shared design system — do not
  switch to Arabic numerals or emoji.
