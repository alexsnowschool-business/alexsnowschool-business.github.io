# Culture & Audio Archive

Status: In Development
Audience: Researchers, students, and lifelong learners wanting to read along with BBC lectures and cultural broadcasts
Brand tone: Editorial listening room — quiet, unhurried, text-forward

## Key sections
- Library (`index.html#/`) — searchable list of episodes, filterable by listening status
- Episode detail (`index.html#/episode/<id>`) — audio player + full transcript, status tracked in `localStorage`
- History (`index.html#/history`) — episodes with any progress, newest-activity first

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
  N oldest-published untranscribed ones (`TRANSCRIBE_DAILY_LIMIT` env var, default 5, configurable per-run via
  the workflow's `daily_limit` input), downloads each just long enough to run Whisper, deletes the audio
  again, then reuses that same fetched RSS data with `build_episodes_json.assemble_episodes()` (no second
  RSS fetch) so the new transcripts and AI topic categorization land in `data/episodes.json` together.
  `transcripts/*.txt`/`*.json` are committed (not gitignored) so this backlog persists across daily runs
  instead of re-transcribing the same episodes.

## Listening status (local vs. synced)
- "Unheard"/"In Progress" and the `lastAccessed`/`accessCount` tracking are purely local — stored in each
  browser's `localStorage` (`audioArchiveHistory`), never leave the device, and don't sync anywhere.
- "Completed" can also come from `data/completed.json` (`{ "<episode id>": { title, completed_at } }`),
  which the frontend fetches alongside `episodes.json` and treats as authoritative — `getStatus()` checks it
  before falling back to the local status. This is the cross-device sync path: since this is a single-user
  personal site (no accounts/auth), rather than adding a hosted backend, completing an episode on any device
  syncs to others by manually running the `.github/workflows/mark-completed.yml` workflow_dispatch with the
  episode's exact title (the episode page has a "Copy Title" button for this) — it calls
  `scripts/mark_completed.py`, which hashes the title with the same `slugify()` used for episode ids and
  commits the update. `data/completed.json` is the other exception carved out of the `data/*` gitignore rule.
- The in-page "Mark as Read" button only ever writes to local `localStorage` — it does not trigger the
  workflow — so a device will show "Completed" immediately for itself, but other devices only pick it up
  after the GitHub Action runs and the page is reloaded.

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
