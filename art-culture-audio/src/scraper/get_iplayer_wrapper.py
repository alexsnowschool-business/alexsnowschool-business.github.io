"""
Wrapper for get_iplayer command-line tool.
Provides Python interface to download BBC programmes.
"""

import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional
from config import Config
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class GetIPlayerWrapper:
    """Wrapper for get_iplayer CLI tool"""
    
    def __init__(self):
        self.downloads_dir = Config.DOWNLOADS_DIR
        self.check_installation()
    
    def check_installation(self) -> bool:
        """
        Check if get_iplayer is installed.
        
        Returns:
            True if installed, False otherwise
        """
        try:
            result = subprocess.run(
                ['get_iplayer', '--help'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info("get_iplayer is installed")
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.warning("get_iplayer is not installed or not in PATH")
            logger.info("Install from: https://github.com/get-iplayer/get_iplayer")
            return False
        
        return False
    
    def search(self, query: str, programme_type: str = 'radio') -> List[Dict]:
        """
        Search for programmes.
        
        Args:
            query: Search query
            programme_type: Type of programme ('radio' or 'tv')
        
        Returns:
            List of programme dictionaries
        """
        try:
            cmd = [
                'get_iplayer',
                '--type', programme_type,
                query,
                '--listformat', '<pid>|<name>|<episode>|<desc>',
            ]
            
            logger.info(f"Searching for: {query}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            programmes = []
            for line in result.stdout.split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 4:
                        programmes.append({
                            'pid': parts[0].strip(),
                            'name': parts[1].strip(),
                            'episode': parts[2].strip(),
                            'description': parts[3].strip(),
                        })
            
            logger.info(f"Found {len(programmes)} programmes")
            return programmes
            
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []
    
    def download(self, pid: str, output_dir: Optional[Path] = None) -> bool:
        """
        Download a programme by PID.
        
        Args:
            pid: Programme ID
            output_dir: Output directory (defaults to Config.DOWNLOADS_DIR)
        
        Returns:
            True if successful, False otherwise
        """
        if output_dir is None:
            output_dir = self.downloads_dir
        
        try:
            cmd = [
                'get_iplayer',
                '--pid', pid,
                '--output', str(output_dir),
                '--radiomode', 'best',
            ]
            
            logger.info(f"Downloading PID: {pid}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                logger.info(f"Successfully downloaded PID: {pid}")
                return True
            else:
                logger.error(f"Download failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading: {e}")
            return False
    
    def download_by_url(self, url: str) -> bool:
        """
        Download a programme by BBC URL.
        
        Args:
            url: BBC programme URL
        
        Returns:
            True if successful, False otherwise
        """
        try:
            cmd = [
                'get_iplayer',
                '--url', url,
                '--output', str(self.downloads_dir),
                '--radiomode', 'best',
            ]
            
            logger.info(f"Downloading from URL: {url}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode == 0:
                logger.info(f"Successfully downloaded from URL")
                return True
            else:
                logger.error(f"Download failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading: {e}")
            return False
    
    def refresh_cache(self) -> bool:
        """
        Refresh get_iplayer cache.
        
        Returns:
            True if successful
        """
        try:
            logger.info("Refreshing get_iplayer cache...")
            result = subprocess.run(
                ['get_iplayer', '--refresh'],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                logger.info("Cache refreshed successfully")
                return True
            else:
                logger.error(f"Cache refresh failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error refreshing cache: {e}")
            return False
