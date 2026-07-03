# Art Data → Analytics Product Roadmap

Context: the weekly `scrape-art.yml` pipeline into `data/art.db` was built to feed
reel/social content ("The Hammer Price"). It's also the raw material for a
higher-margin product: recurring auction-market analytics sold to
collectors/advisors/family offices, in the vein of Artprice/ArtTactic but
narrower and cheaper to run. This doc tracks what's real in the data today,
what was fixed, and what's next.

## Current data snapshot (as of this audit)

- `art_items`: 2,625 lots, 1,052 distinct artists, 2 auction houses (Christie's
  1,797 / Sotheby's 828). Mostly Post-War/Contemporary and Impressionist/Modern
  **Day Sales**, not just blue-chip evening headliners.
- `sale_performance` already computed per lot on insert: 1,215 `above` estimate,
  912 `within`, 489 `below`, 3 `unknown`.
- `artist_profiles`: 330 of 1,052 artists enriched with bios.
- `posted_reels`: 91 lots turned into content so far.
- `art-archive/analysis.json` (built by `scripts/build_art_json.py`) already
  computes `top_outperformers` and `sale_performance` breakdowns — the "beat
  the estimate" signal exists, it's just never been published as its own
  content pillar, only folded into reel selection.

## Bug found + fixed: `sale_date` was NULL on every row

Root cause, not a scraping gap:

1. `scraper/sothebys.py` `_parse_lot()` hardcoded `sale_date: None`, even
   though the auction `year` (from the `/en/buy/auction/{year}/{slug}` URL)
   was already available in the calling scope and just never threaded through.
2. `scraper/art_db.py` `upsert_lot()` used `INSERT OR IGNORE` — once a lot
   row exists, later scraper improvements (like a working `sale_date` regex)
   never backfill it, because the insert is silently skipped on conflict.
3. Compounding that: both scrapers' `lot_exists()` check skips re-fetching
   lots already in the DB, so even fixing (1) and (2) wouldn't self-heal
   existing rows on a normal weekly run — they needed a direct one-time
   backfill.

**Fixed:**
- `scraper/art_db.py`: `upsert_lot()` now does a real `INSERT ... ON CONFLICT
  DO UPDATE`, so future scraper fixes propagate to existing rows if they're
  ever reprocessed. `sale_date` specifically uses `COALESCE(excluded, existing)`
  so a scrape that fails to find a date doesn't blank out one already known.
- `scraper/sothebys.py`: `_parse_lot()` now takes `year` and sets `sale_date`
  to it. **Coarse — year only**, not an exact date; Sotheby's GraphQL lot list
  doesn't expose a per-lot date without an extra request per lot (a possible
  future improvement, not done here to avoid adding untested request volume
  to the scraper).
- `scripts/backfill_sale_date.py` (new, one-time): extracts a year from
  `sale_name` text (e.g. "Contemporary Evening Auction, NY 2023") for existing
  NULL rows. **Run once, already run locally**: backfilled 628 of 2,625 rows.
  The remaining 1,997 have no year in `sale_name` at all (e.g. undated day-sale
  names like "Post-War and Contemporary Art Day Sale") and need a real
  re-scrape to resolve — this script cannot invent a date that isn't present
  anywhere in the stored data.
- Verified: `year_timeline` in `analysis.json` went from empty to a real
  4-year series (2023–2026) after the backfill + rebuild.

**Still open / not attempted here:**
- `scraper/christies.py` has a `"sale_date"` regex against the raw page body
  that is marked "best effort" in its own comment — worth checking against a
  live page fetch next time the weekly scrape runs, to see if it's actually
  matching or silently failing (no network access available in this session
  to verify against the live site).
- Sotheby's per-lot exact date would require one extra request per lot or a
  GraphQL field addition — worth doing once the coarse year-level data proves
  useful enough to justify the added request volume.

## Next: turn existing signal into a content/product pillar (no new scraping)

`sale_performance` + `top_outperformers` already exist in `analysis.json`.
Nothing new needs to be scraped to ship this:

- A recurring "Beat the Estimate" post/reel: which artists/lots are running
  hot vs. cold relative to auction-house estimates this week, pulled straight
  from `top_outperformers`.
- With `sale_date` now populated (even partially), a real trend line by
  house/artist/medium over time becomes possible — feeds a "quarterly index"
  piece, which is a more defensible product angle than one-off lot highlights.
- Free tier: reels/social as now. Paid tier (Substack, since `substack_post.py`
  already exists): the underlying index numbers / downloadable breakdown.
- Framing discipline: publish *data and trend analysis*, never buy/sell
  recommendations — that keeps this outside BaFin's Anlageberatung licensing
  in Germany.

## Next: the actual moat — extend scraping downmarket + into Europe

Christie's/Sotheby's evening and day sales are already covered extensively by
Artnet/Artprice/financial press — good for reel virality (everyone recognizes
a $54M Kusama), bad for a paid-data moat since there's no information
advantage over free coverage.

The differentiated move: add regional European auction houses that
Artprice-tier coverage under-serves relative to what they charge for it —
concretely, houses reachable without spoken German (scraping/parsing a
results page is not the same skill as negotiating in German):

- Van Ham (Köln)
- Lempertz (Köln)
- Ketterer Kunst (Munich)
- Grisebach (Berlin)

`scraper/artprice.py` already exists in the repo (currently commented out of
`scrape-art.yml`) — checked it: it scrapes Artprice's public `/sales/futures`
page for *upcoming* lots (highlights across major houses, no hammer price yet
since the sale hasn't happened), not broader historical coverage. Different
purpose from the Van Ham/Lempertz/Ketterer idea above — worth re-enabling on
its own merits (upcoming-sale previews are good "what to watch this week"
content), but it doesn't reduce the work needed for European day-sale
coverage.

This is the multi-week build, not a same-session fix — scoping it (site
structure, rate limits, whether Playwright vs. plain httpx is needed per site)
is the next concrete task once the "Beat the Estimate" content pillar is
shipped and validated with the existing audience.
