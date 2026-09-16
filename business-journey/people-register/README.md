# People & Company Register (v0.1)

Local-only MVP implementing `../people-register-design-draft.md`. No deploy
target yet — everything runs via Docker Compose on your own machine.

## Prerequisites

- Docker Desktop (or Docker Engine + the Compose plugin), v24+
- Docker Compose v2 (`docker compose`, not the old standalone `docker-compose`)

## Install & run

```bash
cd business-journey/people-register
cp env.example .env        # then edit .env: set POSTGRES_PASSWORD and API_KEY

docker compose build
docker compose up -d postgres
docker compose run --rm api python manage_db.py init   # create schema

docker compose up -d api frontend
```

- API: http://localhost:8000/docs
- Frontend: http://localhost:3000

## Running the scraper

The scraper is not started by `docker compose up` — it's a one-off job
(`profiles: [tools]` in `docker-compose.yml`), matching the "no real-time
scraping" decision in the design draft:

```bash
docker compose run --rm scraper python scrape_one.py --company "Example GmbH"
```

**Current real-data status** (verified live 2026-09-16):
- Insolvency-notice search and Handelsregister company search both work
  against the real sites — see the module docstrings in
  `scraper/bundesanzeiger.py` and `scraper/handelsregister.py` for the exact
  session/form handshake each needs.
- One correction to the design draft: insolvency notices are published at
  `neu.insolvenzbekanntmachungen.de`, not bundesanzeiger.de.
- Not yet implemented: officer/appointment extraction (Handelsregister
  doesn't expose it in the search results — it's in a separate generated
  document) and the insolvency notice's full publication text/administrator
  name (a JSF ajax popup not yet cracked). Both are documented as `TODO`s in
  their respective modules. Until officer extraction exists, the graph view
  will show companies but no linked people.
- Both sites throttle repeated automated requests within a short window
  (expect occasional `RemoteProtocolError`/connection drops if you run the
  scraper many times in quick succession — this is the site, not a bug).

Raw fetched pages are stored under `/app/data/raw/<source>/<uuid>.html`
inside the `raw_data` named Docker volume before parsing (design draft
section 4: store raw first, parse second). A named volume is used instead
of a host bind mount because macOS blocks Docker's access to `~/Documents`
by default; inspect stored files with
`docker compose run --rm scraper ls -R data/raw` if needed.

## Project layout

```
people-register/
├── docker-compose.yml
├── env.example              # copy to .env
├── db/
│   └── schema.py             # event log + graph view tables (section 5)
├── api/                      # FastAPI: GET /people/:id, /companies/:id, /search, /risk
├── scraper/                  # Handelsregister + Bundesanzeiger scrapers, pipeline
└── frontend/                 # React (Vite): search, person profile, risk dashboard
```

## Notes

- `GET /risk` isn't one of the 3 endpoints listed in the design draft's API
  section — added because the risk-dashboard screen (section 8) needs a way
  to list people linked to insolvent companies.
- Every API request is logged (requester `apikey`, path, status, timestamp)
  per the design draft's GDPR-accountability requirement (section 6).
- The graph view (`people`/`companies`/`roles`) is rebuilt from the event
  log on every scrape run (`pipeline.rebuild_graph`) — never hand-edit those
  tables directly.
