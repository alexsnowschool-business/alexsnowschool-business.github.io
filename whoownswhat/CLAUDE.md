# Who Owns What

Status: In Development
Audience: General public — journalists, researchers, curious individuals who want to understand corporate power without hours of research
Brand tone: Journalistic, authoritative, plainspoken. "Every claim has a source." No spin, no partisan framing.
Country focus: Germany (Phase I) — DAX 40 companies and top billionaires. Expanding by country.

## Key Sections
- Landing: Country selector hero, search bar, daily fact cards, featured entities grid, methodology
- company.html: Shareholders, executive compensation, lobbying, political spending, fines, labour, competitors, sources
- person.html: Net worth, major assets, board memberships, foundations, political spending, timeline, sources

## Data Architecture
- **SQLite database**: `data/whoownswhat.db` — source of truth
- **data.js**: JavaScript export generated from SQLite by `scripts/whoownswhat/export_data_js.py`
- **Daily scraper CI**: `.github/workflows/whoownswhat-update.yml` runs scrapers + exports data.js
- Frontend is a static site (no backend needed): all rendering is client-side from data.js

## German-Specific Sources
- **Bundesanzeiger** (bundesanzeiger.de) — mandatory annual report filings
- **BaFin** (bafin.de) — voting rights notifications, regulatory actions
- **Handelsregister** (handelsregister.de) — company registry, Gesellschafterliste
- **Bundestag Lobbyregister** (lobbyregister.bundestag.de) — mandatory since Jan 2022
- **Manager Magazin Reichenliste** — German billionaires list
- **Statista** — German statistics platform
- **Parteiengesetz §25** — corporate party donation law context

## Rules for Claude
- Never add unsourced data. If a source URL is uncertain, use the base domain (e.g. `https://www.bundesanzeiger.de`) rather than a broken deep link.
- All monetary figures should note currency (EUR/CHF/USD) and the year of the data.
- German law context: corporations cannot donate to political parties (Parteiengesetz §25) — always note this in politicalSpending blocks.
- Lobbying figures from the Bundestag Lobbyregister are self-reported annual budgets, not verified expenditures.
- Keep co-determination (Mitbestimmung) context accurate: Mitbestimmungsgesetz 1976 requires 50% employee supervisory board representation for firms with >2,000 employees in Germany.
