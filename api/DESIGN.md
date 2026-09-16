# Auction Data API — Design Document

Status: Draft
Owner: Alex Snow

## 1. Goal

Expose the auction lot data already collected by `scraper/` (Christie's, Sotheby's,
Ketterer Kunst, Artprice, etc. → `data/art.db`) as a versioned REST API, shaped like
ARTDAI's (`docs.artd.ai`) so the contract is familiar and swappable: artist-scoped
lots/analytics/index endpoints, dictionary lookups, apikey auth, pagination.

Not a fork of ARTDAI's data — this serves only data this project has scraped itself.

## 2. Non-goals (v1)

- No write endpoints (read-only API; ingestion stays in `scraper/` + CI).
- No live currency conversion API — FX via a small daily-refreshed rate table.
- No horizontal scaling / managed Postgres — SQLite is enough at current data volume.
- No public self-serve signup — API keys issued manually.

## 3. Architecture

```
api/
├── DESIGN.md
├── main.py            # FastAPI app, route registration, exception handlers
├── deps.py             # apikey auth dependency, DB connection dependency
├── models.py           # Pydantic schemas shared with scraper/sync (Lot, Pagination, Error)
├── routers/
│   ├── artists.py       # /v1/artists, /v1/artist/{artist_id}/lots|analytics|index
│   ├── sales.py         # /v1/sales, /v1/sales/{sale_id}/lots
│   └── dictionaries.py  # /v1/auction_houses, /v1/categories
├── queries.py           # all SQL against data/art.db (read-only)
├── ratelimit.py          # slowapi config + 429 headers
└── cache.py             # TTL cache for dictionary endpoints
```

FastAPI is the framework choice: it generates `/docs`, `/redoc`, and `/openapi.json`
automatically from route + Pydantic definitions — the same mechanism ARTDAI's own
docs site is built on, so "similar to artd.ai" comes largely for free.

Runs as its own long-lived process (`uvicorn api.main:app`), separate from the
cron-style scripts in `scripts/`. This is the first component in the repo that is a
service rather than a script — needs its own deploy target (Fly.io/Render/VPS),
not GitHub Actions.

## 4. Data layer

- Source of truth stays `data/art.db` (SQLite), written by `scraper/art_db.py`.
- API is read-only against the same file; sync `sqlite3` queries run fine in
  FastAPI's threadpool at current data volume.
- `artist_profiles.name_key` (existing slug) is reused as the `artist_id` path
  param — no new ID scheme needed.
- Revisit SQLite only if write-contention between scrapers and API requests
  becomes measurable (not expected at current scale).

## 5. Endpoint contract (mirrors ARTDAI's shape)

| Endpoint | Backing query | Notes |
|---|---|---|
| `GET /v1/artists?term=` | `LIKE` on `artist_profiles.display_name` | dictionary lookup, ≤5 matches |
| `GET /v1/artist/{artist_id}/lots` | `art_items` filtered by artist, paginated | filters: auction_house, date range, price range, medium |
| `GET /v1/artist/{artist_id}/analytics` | aggregate over filtered `art_items` | avg/median hammer, sell-through % |
| `GET /v1/artist/{artist_id}/index` | trend of `hammer_usd` over time | future — index methodology TBD |
| `GET /v1/auction_houses` | `SELECT DISTINCT auction_house` | cached |
| `GET /v1/categories` | `SELECT DISTINCT medium_category` | cached |
| `GET /v1/sales` | grouped by `sale_name` + `sale_date` | |
| `GET /v1/sales/{sale_id}/lots` | `art_items` filtered by sale | |

Shared `Lot` Pydantic model reused by both the API response and `sync.py` (the
ARTDAI-ingestion side, if built) so the two don't silently drift on field shape.

## 6. Auth

- `apikey` header, checked via FastAPI `APIKeyHeader` dependency.
- Keys stored in a small `api_keys` table with a `scopes` column
  (e.g. `lots:read`, `analytics:read`) from day one — even with a single key —
  so a partner can later be handed a scoped key without a schema migration.

## 7. Rate limiting & errors

- `slowapi` for per-key rate limits; `429` responses carry
  `X-RateLimit-Limit-Hour` / `X-RateLimit-Remaining-Hour` / `RateLimit-Reset`,
  matching ARTDAI's headers.
- Error body shape matches ARTDAI exactly: `{"message": "..."}` on 400/401/403/429.
  Keeping this contract-compatible means anything written against ARTDAI's error
  handling works against this API unchanged.

## 8. Currency

- `user_currency` query param supported via a static FX-rate table refreshed
  daily (source: `yfinance`, already a project dependency) rather than a
  live conversion call per request.
- `hammer_usd` (already stored on every lot) is the base for conversion.

## 9. Caching

- Dictionary endpoints (`auction_houses`, `categories`) are near-static —
  in-process TTL cache (`cachetools`) avoids hitting SQLite on every filtered
  query that first looks up an ID.

## 10. Versioning

- `/v1/...` prefix from the first commit, even pre-launch — cheap now, painful
  to retrofit once anything (a script, an MCP tool, a partner) depends on an
  unversioned path.

## 11. New dependencies

| Package | Purpose | Already in `pyproject.toml`? |
|---|---|---|
| `fastapi` | API framework | No — new |
| `uvicorn` | ASGI server | No — new |
| `slowapi` | rate limiting | No — new |
| `cachetools` | TTL cache for dictionaries | No — new |
| `python-dotenv`, `httpx` | config / testing | Yes |

## 12. Open questions

- Hosting target for the long-lived process (Fly.io / Render / existing VPS)?
- Is `/v1/artist/{artist_id}/index` (market index growth) worth building for v1,
  or defer until there's a concrete consumer?
- Any external consumers planned yet, or is v1 solely for internal MCP/agent use?

## 13. Reference

- ARTDAI API docs (design reference for this contract): https://docs.artd.ai/#tag/lots/GET/v1/artist/{artist_id}/lots
- ARTDAI OpenAPI spec (fetched for endpoint/schema detail): https://docs.artd.ai/openapi.json
