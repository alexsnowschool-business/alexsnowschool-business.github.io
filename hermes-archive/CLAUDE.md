# The Hermès Archive

Status: Live
Audience: Researchers, data scientists, ML practitioners building fashion authenticity classifiers
Brand tone: Academic archive meets luxury editorial — precise, analytical, unhurried

## Key sections
- Catalogue (`index.html`) — filterable grid of 4,287 Hermès bag listings from Vestiaire Collective and Hermès.com
- Analysis (`analysis.html`) — Chart.js visualisations + pricing analysis, sourced from `analysis.json`

## Data files
- `catalogue.json` — all item metadata (3.2 MB, ~1,639 items)
- `analysis.json` — pre-computed statistics and chart data (16 KB)

## Notes
- This is a static export of a FastAPI app originally at `data-collection-fashion/app.py`
- Images are loaded from their original CDN URLs (eBay, Vestiaire Collective, etc.) — no local images
- To update the dataset, re-run the Python scrapers and regenerate `catalogue.json` + `analysis.json`
- Both JSON files should be regenerated together when new scraping data is available
