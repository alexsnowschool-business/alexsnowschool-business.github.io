"""
Manual smoke test for RSScraper.
Run with: .venv/bin/python test_rss_scraper.py
"""

from src.scraper.rss_scraper import RSScraper

scraper = RSScraper()

# 1. List available feeds
feeds = scraper.list_available_feeds()
print("Available feeds:", list(feeds.keys()))

# 2. Parse feed and get episode info (no download)
url = feeds["in_our_time"]
episodes = scraper.get_episodes(url, limit=3)
print(f"\nFound {len(episodes)} episodes:")
for ep in episodes:
    print("-", ep["title"], "|", ep["audio_url"])

if not episodes:
    print("No episodes found, aborting download test.")
    raise SystemExit(1)

# 3. Download one episode, forcing https on the audio URL
ep = episodes[0]
https_url = ep["audio_url"].replace("http://", "https://", 1)
print(f"\nDownloading (https): {https_url}")

filepath = scraper.download_audio(https_url, ep["title"])
print("Result:", filepath)
