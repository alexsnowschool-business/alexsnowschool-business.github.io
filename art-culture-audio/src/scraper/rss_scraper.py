"""
RSS Feed scraper for BBC podcasts.
Downloads audio files from BBC podcast RSS feeds.
"""

import feedparser
import requests
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm
from config import Config
from src.utils.logger import setup_logger
from src.utils.file_manager import FileManager

logger = setup_logger(__name__)

class RSScraper:
    """Scraper for BBC podcast RSS feeds"""
    
    # Popular BBC podcast RSS feeds
    BBC_FEEDS = {
        'reith_lectures': 'https://podcasts.files.bbci.co.uk/p02p8xh7.rss',
        'in_our_time': 'https://podcasts.files.bbci.co.uk/p01f0vzr.rss',
        'in_our_time_history': 'https://podcasts.files.bbci.co.uk/p01gyd7j.rss',
        'the_documentary': 'https://podcasts.files.bbci.co.uk/p02nq0lx.rss',
        'analysis': 'https://podcasts.files.bbci.co.uk/b006r4vz.rss',
        'thinking_allowed': 'https://podcasts.files.bbci.co.uk/b006qy05.rss',
        'more_or_less': 'https://podcasts.files.bbci.co.uk/p02nrss1.rss',
    }
    
    def __init__(self):
        self.downloads_dir = Config.DOWNLOADS_DIR
        self.file_manager = FileManager()
    
    def parse_feed(self, feed_url: str) -> Dict:
        """
        Parse an RSS feed and extract episode information.
        
        Args:
            feed_url: URL of the RSS feed
        
        Returns:
            Parsed feed data
        """
        logger.info(f"Parsing RSS feed: {feed_url}")
        try:
            response = requests.get(feed_url, timeout=2)
            response.raise_for_status()
            logger.info(f"Successfully fetched feed: {feed_url}")
        except requests.RequestException as e:
            logger.error(f"Error fetching feed: {e}")
            return None

        feed = feedparser.parse(response.content)

        if feed.bozo:
            logger.error(f"Error parsing feed: {feed.bozo_exception}")
            return None
        
        logger.info(f"Found {len(feed.entries)} episodes in feed: {feed.feed.get('title', 'Unknown')}")
        return feed
    
    def get_episodes(self, feed_url: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Get episode information from RSS feed.
        
        Args:
            feed_url: URL of the RSS feed
            limit: Maximum number of episodes to return
        
        Returns:
            List of episode dictionaries
        """
        feed = self.parse_feed(feed_url)
        if not feed:
            return []
        
        episodes = []
        entries = feed.entries[:limit] if limit else feed.entries
        
        for entry in entries:
            # Find audio enclosure
            audio_url = None
            for link in entry.get('links', []):
                if link.get('type', '').startswith('audio/'):
                    audio_url = link.get('href')
                    break
            
            # Fallback to enclosures
            if not audio_url and entry.get('enclosures'):
                audio_url = entry.enclosures[0].get('href')
            
            if audio_url:
                episode = {
                    'title': entry.get('title', 'Unknown'),
                    'description': entry.get('summary', ''),
                    'published': entry.get('published', ''),
                    'audio_url': audio_url,
                    'duration': entry.get('itunes_duration', ''),
                }
                episodes.append(episode)
        
        logger.info(f"Found {len(episodes)} episodes with audio")
        return episodes
    
    def download_audio(self, url: str, filename: str, metadata: Dict = None) -> Optional[Path]:
        """
        Download audio file from URL.
        
        Args:
            url: Audio file URL
            filename: Destination filename
            metadata: Optional metadata to save
        
        Returns:
            Path to downloaded file or None if failed
        """
        try:
            # Sanitize filename
            filename = self.file_manager.sanitize_filename(filename)
            if not filename.endswith('.mp3'):
                filename += '.mp3'
            
            filepath = self.downloads_dir / filename
            
            # Skip if already exists
            if filepath.exists():
                logger.info(f"File already exists: {filepath.name}")
                return filepath
            
            # Download with progress bar
            logger.info(f"Downloading: {filename}")
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(filepath, 'wb') as f:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=filename) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            
            logger.info(f"Downloaded: {filepath}")
            
            # Save metadata
            if metadata:
                self.file_manager.save_metadata(filepath, metadata)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return None
    
    def download_episodes(self, feed_url: str, limit: Optional[int] = None) -> List[Path]:
        """
        Download episodes from RSS feed.
        
        Args:
            feed_url: URL of the RSS feed
            limit: Maximum number of episodes to download
        
        Returns:
            List of downloaded file paths
        """
        episodes = self.get_episodes(feed_url, limit)
        downloaded_files = []
        
        for i, episode in enumerate(episodes, 1):
            logger.info(f"Processing episode {i}/{len(episodes)}: {episode['title']}")
            
            filename = f"{episode['title']}"
            metadata = {
                'title': episode['title'],
                'description': episode['description'],
                'published': episode['published'],
                'source_url': episode['audio_url'],
                'feed_url': feed_url,
            }
            
            filepath = self.download_audio(episode['audio_url'], filename, metadata)
            if filepath:
                downloaded_files.append(filepath)
        
        logger.info(f"Downloaded {len(downloaded_files)} episodes")
        return downloaded_files
    
    def list_available_feeds(self) -> Dict[str, str]:
        """
        Get list of predefined BBC feeds.
        
        Returns:
            Dictionary of feed names and URLs
        """
        return self.BBC_FEEDS
