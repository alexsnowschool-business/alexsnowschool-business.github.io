# German people & company register — design draft (v0.1)

## 1. Goal

Build a system that tracks natural persons (directors, officers) linked to
German companies, using two public sources, and surfaces:

- who is connected to whom, right now
- who is connected to a company that recently went insolvent
- what sector each company operates in, in plain language

This is an MVP. Optimize for one working thread end to end, not for coverage.

## 2. Scope for v0.1

In scope:
- Two sources: Handelsregister (commercial register) and Bundesanzeiger
  (federal gazette, insolvency notices)
- One company, tracked manually to prove the pipeline, before scaling to many
- Person identity graph (basic matching: name + role + company)
- Sector classification (can start with a lookup table, not a trained model)
- REST API, three endpoints
- Frontend: search, person profile, risk dashboard

Out of scope for v0.1 (note but do not build):
- Transparenzregister integration (needs legitimate-interest access approval
  — see section 7)
- Multi-source identity resolution at scale (dedupe across 150 local courts)
- Real-time scraping (batch/polling is fine to start)

## 3. Architecture overview

```
[Handelsregister scraper]   [Bundesanzeiger scraper]
            \                       /
             \                     /
              [Processing pipeline]
                       |
                 [Data store]
                       |
                  [API layer]
                       |
                  [Frontend]
```

Processing pipeline, broken into stages:

```
raw filing text
   -> event extraction        (person_appointed / company_insolvent)
   -> person identity graph   (resolve same human across records)
   -> sector classifier       (business purpose text -> sector code)
   -> risk & status engine    (propagate insolvency to linked people)
```

## 4. Data sources

| Source | What we pull | Format | Access |
|---|---|---|---|
| Handelsregister | Company name, register number (HRB/HRA), court, officers with role and appointment date, business purpose text | HTML pages, no official API | Free search since 2022 |
| Bundesanzeiger | Insolvency notices: company name, register number, court, date filed, administrator | HTML/PDF | Public |

Scraper design notes:
- Store the raw fetched page first, parse second. Never parse-then-discard —
  a parser bug should never cost you the source data.
- Poll on a schedule (e.g. daily). No need for real-time in v0.1.
- Each scraper is a separate job with its own retry/backoff logic. A
  Bundesanzeiger outage should never block Handelsregister ingestion.

## 5. Data model

### 5.1 Event log (source of truth, append-only, never edited)

```
Event {
  id: uuid
  type: "person_appointed" | "person_departed" | "company_insolvent"
  source: "handelsregister" | "bundesanzeiger"
  source_document_id: string   // reference to raw stored document
  occurred_at: date             // date on the filing, not date we scraped it
  ingested_at: timestamp
  payload: json                 // raw extracted fields before graph resolution
}
```

### 5.2 Graph store (computed view, rebuildable from the event log)

```
Person {
  id: uuid
  name: string
  date_of_birth: date | null     // only if the source discloses it
  matched_confidence: float      // how sure we are this is one real person
}

Company {
  id: uuid
  name: string
  register_number: string        // HRB/HRA + court
  business_purpose_raw: string
  sector_code: string | null     // WZ 2008 / NACE
  sector_description: string | null
  status: "active" | "insolvent"
}

Role {
  person_id: uuid
  company_id: uuid
  role_type: "director" | "authorized_officer"  // Geschäftsführer / Prokurist
  started_at: date
  ended_at: date | null
}
```

Design rule: the graph store is a *view*. If it's ever wrong, delete it and
rebuild from the event log. Never hand-patch the graph directly.

### 5.3 Sector classification (v0.1 shortcut)

Start with a lookup table of common business-purpose phrases mapped to WZ
codes, rather than a trained classifier. Expand it as real data comes in.
Revisit build-vs-buy (third-party sector data) if the lookup table's hit
rate stays low.

## 6. API layer

Three endpoints for v0.1:

```
GET /people/:id
  -> { name, roles: [{company, role_type, started_at, ended_at}], risk_flags }

GET /companies/:id
  -> { name, register_number, sector, status, current_officers: [...] }

GET /search?q=
  -> matches across people and companies by name
```

Non-functional requirements:
- Every request logged with requester identity and timestamp. This log is
  not optional — it is how GDPR (General Data Protection Regulation)
  compliance gets demonstrated later.
- Auth: API key to start. Add scoped tokens once there's more than one
  consumer.
- Rate limiting from day one, even if generous.

## 7. Compliance note (read before building)

Person data (names, dates of birth) is regulated by default under GDPR and
BDSG (Bundesdatenschutzgesetz). Before this goes past a personal prototype:

- Define the lawful basis for storing each field.
- Support deletion on request (right to erasure) — the event-log design
  makes this harder than a normal database, since the log is append-only.
  Plan for this now: e.g. a separate encrypted-and-purgeable store for the
  handful of fields that must support erasure, referenced by ID from the log.
- Do not integrate Transparenzregister data without first securing
  "legitimate interest" (berechtigtes Interesse) access, a legal
  prerequisite, not a technical one.

## 8. Frontend (v0.1)

Three screens only:

1. **Search** — one input, results split into people and companies.
2. **Person profile** — name, current and past roles, a risk flag if linked
   to an insolvent company.
3. **Risk dashboard** — list of people currently linked to a company with
   status `insolvent`.

## 9. Suggested tech stack (adjust to your own preference)

- Scrapers: Python (requests/httpx + BeautifulSoup), scheduled via cron or a
  lightweight job runner
- Processing pipeline: Python, run as a batch job initially — no need for
  streaming infrastructure at this scale
- Data store: Postgres for both the event log (one table, append-only) and
  the graph view (a few normalized tables) — a dedicated graph database is
  not justified at v0.1 scale
- API: FastAPI or a small Node/Express service
- Frontend: React, plain REST calls, no need for GraphQL yet

## 10. Local setup & running (Docker Compose, v0.1)

v0.1 runs locally only — no deploy target yet (see open question in section 12).
Docker Compose keeps Postgres, the API, and the frontend reproducible on any
machine without installing Postgres/Node/Python versions by hand.

### Prerequisites

- Docker Desktop (or Docker Engine + the Compose plugin), v24+
- Docker Compose v2 (invoked as `docker compose`, not the old standalone
  `docker-compose` v1 binary)
- Optional, only needed to run scraper/pipeline scripts outside a container
  for debugging: Python 3.11+ and `uv` (or `pip`)

### Services (`docker-compose.yml`)

| Service | Role | Notes |
|---|---|---|
| `postgres` | Event log + graph view tables (section 5) | Postgres 16, named volume for persistence across restarts |
| `api` | FastAPI app served via `uvicorn` | built from `api/Dockerfile`, `depends_on: postgres`, exposes `8000` |
| `frontend` | React app (search / person profile / risk dashboard) | Vite dev server locally, `depends_on: api`, exposes `3000` |
| `scraper` | Handelsregister + Bundesanzeiger scraper and processing pipeline | not long-running — invoked on demand via `docker compose run scraper ...` or a host cron entry, not `docker compose up` |

### Required libraries/tools by component

Scrapers & processing pipeline (Python):
- `httpx` — HTTP fetching, with retry/backoff per source (section 4)
- `beautifulsoup4` — HTML parsing
- `psycopg[binary]` — Postgres driver
- `python-dotenv` — local env/config loading

API (Python):
- `fastapi`
- `uvicorn`
- `psycopg[binary]`
- `python-dotenv`

Frontend (Node):
- `react`, `react-dom`
- `vite` — dev server and build tool

### Install & run steps

1. Copy `.env.example` to `.env` and fill in Postgres credentials and the API
   key used by the frontend/scraper to call the API.
2. `docker compose build`
3. `docker compose up -d postgres`
4. Initialize the schema (event log + graph view tables from section 5):
   `docker compose run --rm api python manage_db.py init`
5. `docker compose up -d api frontend`
6. Run the scraper once, for the single tracked company (per the build order
   in section 11): `docker compose run --rm scraper python scrape_one.py --company "<name>"`
7. Open the frontend at `http://localhost:3000` and the API docs at
   `http://localhost:8000/docs`.

### Notes

- Services talk to Postgres over the Docker Compose network by name
  (`postgres:5432`) — no need to expose the Postgres port to the host unless
  inspecting the DB directly with a local client.
- Keeping `scraper` as a manual/cron-invoked one-off container (rather than
  an always-running service) matches the "no real-time scraping" decision in
  section 2.

## 11. Build order (bottom-up thread first)

1. Scrape one real Bundesanzeiger insolvency notice. Store it raw.
2. Parse it into one `company_insolvent` event by hand-written rules.
3. Scrape the matching Handelsregister entry for that same company. Extract
   its officers into `person_appointed` events.
4. Build the graph view from those events. Confirm one person shows up
   linked to one insolvent company.
5. Wire `GET /people/:id` to return that one real result.
6. Build the search screen and person profile screen against that one
   result.
7. Only then: scale the scrapers to more companies.

Get step 6 working before touching step 7. A single correct thread end to
end is worth more than five half-built layers.

## 12. Open questions for the next design pass

- How many companies/persons is v1 expected to cover? (Affects whether
  Postgres alone is enough, or whether a dedicated identity-matching
  service is needed sooner.)
- Who are the consumers of the API — internal tools only, or external
  paying customers? (Affects auth design and the compliance bar.)
- Is Transparenzregister access (legitimate interest) being pursued in
  parallel, or is beneficial-ownership data out of scope indefinitely?
