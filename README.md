# alexsnowschool-business.github.io

[![Daily Scrape](https://github.com/alexsnowschool-business/alexsnowschool-business.github.io/actions/workflows/scrape.yml/badge.svg)](https://github.com/alexsnowschool-business/alexsnowschool-business.github.io/actions/workflows/scrape.yml)

Two things in one repo: a static portfolio site and an automated data/content pipeline.

## Ventures

| Directory | Status | Description |
|---|---|---|
| `provenance/` | Live | Heritage luxury resale platform |
| `studentroadtogermany/` | In Development | Myanmar → Germany study consultation |

## Automation Workflows

| Workflow | Schedule | What it does |
|---|---|---|
| `scrape.yml` | Daily midnight UTC | Scrapes Hermès, eBay, Vinted, Vestiaire → `data/hermes.db`; rebuilds `hermes-archive/catalogue.json` |
| `scrape-art.yml` | Weekly | Scrapes auction lots → `data/art.db` |
| `weekly-reel.yml` | Tue–Sat 11:00 UTC | Generates "The Hammer Price" reel, posts to Instagram/TikTok/LinkedIn/YouTube, drafts Substack post |
| `hermes-reel.yml` | Scheduled | Generates Hermès product reel, posts to Buffer |
| `substack-post.yml` | On demand | Publishes a Substack draft for a given lot ID |
| `static.yml` | On push / triggered | Deploys site to GitHub Pages |

## Structure

```
/
├── index.html                   ← Root dashboard
├── provenance/                  ← Venture: luxury resale
├── studentroadtogermany/        ← Venture: study consultation
├── scripts/                     ← Python automation (reel gen, posting, scrape helpers)
├── scraper/                     ← Scraper modules (hermes, ebay, vinted, vestiaire)
├── data/                        ← SQLite databases (hermes.db, art.db)
├── hermes-archive/              ← catalogue.json + analysis.json (built by scrape)
├── art-archive/                 ← Art lot data
├── reels/                       ← Generated reel folders (weekly-*, hermes-*)
├── output/substack/             ← Generated Substack drafts
├── reel_template/               ← Assets for reel generation
└── pyproject.toml               ← Python deps (managed with uv)
```

## Running Locally

```bash
python3 -m http.server 3001
# open http://localhost:3001
```

No build step. Plain HTML/CSS/JS.

## Python Setup

```bash
uv sync
uv run python scripts/auto_reel.py --help
```

Secrets for CI (eBay, ElevenLabs, OpenRouter, Buffer, YouTube) live in GitHub Actions secrets — not needed for local site dev.
