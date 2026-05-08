# Art Research

Status: Live
Audience: Art students, researchers, collectors, and ML practitioners studying auction market dynamics
Brand tone: Academic archive meets fine-art editorial — intellectual, precise, historically grounded

## Key sections
- Hero — Dataset statistics (300 lots, 198 artists, $141k median, Christie's)
- Part I: Art History Timeline — 12 moments from 35,000 BCE to present
- Part II: Four Philosophical Frameworks — Kant, Benjamin, Greenberg, Bourdieu
- Part III: Artist Profiles — 25 artists from the Christie's dataset with movement, bio, auction performance
- Part IV: The Auction as Social Structure — market analysis via the frameworks
- Archive links — to art-archive/index.html and art-archive/analysis.html

## Data source
All auction figures are from the Christie's dataset in `data/art.db` (300 lots, scraped via `scraper/christies.py`)

## Artist filter
Movement filter buttons on the artist grid:
- all / abstract-expressionism / pop-art / modernism / contemporary / impressionism
- Controlled by `data-movement` attribute on each `.artist-card`

## Notes
- No external data fetches — all content is static HTML
- Add artists by duplicating `.artist-card` blocks with appropriate `data-movement` attribute
- Movement filter logic is in `script.js`
