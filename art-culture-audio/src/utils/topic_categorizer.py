"""
Topic Categorizer for BBC Audio Files
Uses Gemini AI to categorize audio files into predefined topics with caching and batching.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import google.generativeai as genai
from config import Config
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class TopicCategorizer:
    """
    AI-powered topic categorization for audio files.
    
    Features:
    - Categorizes files into predefined topics using Gemini AI
    - Persistent caching to avoid redundant API calls
    - Batch processing for efficiency
    - Retry logic for rate limit handling
    """
    
    PREDEFINED_TOPICS = [
        'History', 'Philosophy', 'Culture', 'Sociology', 
        'Economics', 'Arts', 'Literature', 'Uncategorized'
    ]
    
    def __init__(self, cache_file_path: Optional[Path] = None):
        """
        Initialize the TopicCategorizer.
        
        Args:
            cache_file_path: Path to cache file. Defaults to Config.TOPIC_CACHE_FILE
        """
        self.cache_file = cache_file_path or Config.TOPIC_CACHE_FILE
        self.categorizations: Dict[str, str] = {}
        self._load_cache()
        
        # Configure Gemini if API key is available
        if Config.GOOGLE_AI_API_KEY:
            genai.configure(api_key=Config.GOOGLE_AI_API_KEY)
            self.model = genai.GenerativeModel('gemini-flash-latest')
        else:
            self.model = None
            logger.warning("No Google AI API key - topic categorization will default to 'Uncategorized'")
    
    def _load_cache(self):
        """Load categorizations from cache file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.categorizations = json.load(f)
                logger.info(f"Loaded {len(self.categorizations)} categorizations from cache")
            except Exception as e:
                logger.error(f"Error loading cache: {e}")
                self.categorizations = {}
        else:
            logger.info("No cache file found, starting fresh")
            self.categorizations = {}
    
    def _save_cache(self):
        """Save categorizations to cache file."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.categorizations, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.categorizations)} categorizations to cache")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def _call_gemini_api(self, file_info_batch: List[Dict], retry_count: int = 3) -> Dict[str, str]:
        """
        Call Gemini API to categorize a batch of files with retry logic.
        
        Args:
            file_info_batch: List of dicts with 'title', 'description'
            retry_count: Number of retries for rate limiting
            
        Returns:
            Dict mapping titles to topics
        """
        if not self.model:
            # No API key, return all as Uncategorized
            return {info['title']: 'Uncategorized' for info in file_info_batch}
        
        # Build prompt
        topics_list = ', '.join(self.PREDEFINED_TOPICS[:-1])  # Exclude Uncategorized from list
        files_text = '\n'.join([
            f"{i+1}. Title: {info['title']}\n   Description: {info.get('description', 'N/A')[:200]}"
            for i, info in enumerate(file_info_batch)
        ])
        
        prompt = f"""Analyze these audio programme titles and descriptions, then categorize each into ONE of these topics: {topics_list}.

If a programme doesn't clearly fit any category, assign it to "Uncategorized".

Programmes:
{files_text}

Return ONLY a JSON object mapping the programme number (1, 2, 3, etc.) to its topic category.
Example format: {{"1": "History", "2": "Philosophy", "3": "Uncategorized"}}

JSON:"""
        
        for attempt in range(retry_count):
            try:
                response = self.model.generate_content(prompt)
                response_text = response.text.strip()
                
                # Extract JSON from response (handle markdown code blocks)
                if '```json' in response_text:
                    response_text = response_text.split('```json')[1].split('```')[0].strip()
                elif '```' in response_text:
                    response_text = response_text.split('```')[1].split('```')[0].strip()
                
                # Parse JSON response
                categorizations = json.loads(response_text)
                
                # Map back to titles
                result = {}
                for i, info in enumerate(file_info_batch):
                    topic = categorizations.get(str(i+1), 'Uncategorized')
                    # Validate topic is in our predefined list
                    if topic not in self.PREDEFINED_TOPICS:
                        topic = 'Uncategorized'
                    result[info['title']] = topic
                
                return result
                
            except Exception as e:
                if attempt < retry_count - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"API call failed (attempt {attempt+1}/{retry_count}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"API call failed after {retry_count} attempts: {e}")
                    # Return all as Uncategorized on failure
                    return {info['title']: 'Uncategorized' for info in file_info_batch}
        
        return {}
    
    def categorize_file(self, audio_file_path: Path, metadata: Optional[Dict] = None) -> str:
        """
        Categorize a single audio file.
        
        Args:
            audio_file_path: Path to audio file
            metadata: Optional metadata dict with 'title' and 'description'
            
        Returns:
            Topic category string
        """
        # Get metadata to extract title
        if not metadata:
            from src.utils.file_manager import FileManager
            metadata = FileManager.load_metadata(audio_file_path)
        
        title = metadata.get('title', audio_file_path.stem)
        
        # Check cache first (using title as key)
        if title in self.categorizations:
            return self.categorizations[title]
        
        # Prepare for categorization
        description = metadata.get('description', '')
        
        # Categorize using API
        file_info = [{
            'title': title,
            'description': description
        }]
        
        result = self._call_gemini_api(file_info)
        topic = result.get(title, 'Uncategorized')
        
        # Update cache (using title as key)
        self.categorizations[title] = topic
        self._save_cache()
        
        return topic
    
    def categorize_all_files(self, audio_files: List[Path], batch_size: int = 10) -> Dict[str, str]:
        """
        Categorize multiple audio files in batches.
        
        Args:
            audio_files: List of audio file paths
            batch_size: Number of files to process per API call
            
        Returns:
            Dict mapping file paths to topics
        """
        if not audio_files:
            logger.info("No audio files to categorize")
            return {}
            
        from src.utils.file_manager import FileManager
        
        # Filter out already categorized files
        # We need to check titles, not file paths, as cache stores titles
        uncategorized_files = []
        for f in audio_files:
            metadata = FileManager.load_metadata(f)
            title = metadata.get('title', f.stem)
            if title not in self.categorizations:
                uncategorized_files.append(f)
        
        if not uncategorized_files:
            logger.info(f"All {len(audio_files)} files already categorized (loaded from cache)")
            return self.categorizations
        
        logger.info(f"Categorizing {len(uncategorized_files)} new files (out of {len(audio_files)} total)")
        
        # Load metadata for uncategorized files
        from src.utils.file_manager import FileManager
        
        # Process in batches
        for i in range(0, len(uncategorized_files), batch_size):
            batch = uncategorized_files[i:i + batch_size]
            
            # Prepare batch info
            batch_info = []
            for audio_file in batch:
                metadata = FileManager.load_metadata(audio_file)
                batch_info.append({
                    'title': metadata.get('title', audio_file.stem),
                    'description': metadata.get('description', '')
                })
            
            # Categorize batch
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(uncategorized_files)-1)//batch_size + 1} ({len(batch)} files)")
            batch_results = self._call_gemini_api(batch_info)
            
            # Update cache
            self.categorizations.update(batch_results)
            
            # Save after each batch
            self._save_cache()
            
            # Small delay between batches to avoid rate limiting
            if i + batch_size < len(uncategorized_files):
                time.sleep(1)
        
        logger.info(f"Categorization complete! Total: {len(self.categorizations)} files")
        return self.categorizations
    
    def get_files_by_topic(self, topic: str) -> List[Path]:
        """
        Get all files categorized under a specific topic.
        
        Args:
            topic: Topic name
            
        Returns:
            List of file paths matching the topic
        """
        from src.utils.file_manager import FileManager
        fm = FileManager()
        
        # Get all audio files and filter by topic
        all_files = fm.list_audio_files()
        files = [
            audio_file
            for audio_file in all_files
            for title, file_topic in self.categorizations.items()
            if file_topic == topic and fm.format_display_name(audio_file) == title
        ]
        return sorted(files, key=lambda x: x.stem)
    
    def get_all_topics(self) -> List[Dict[str, any]]:
        """
        Get all topics with file counts.
        
        Returns:
            List of dicts with 'topic' and 'count' keys, sorted by count descending
        """
        topic_counts = {}
        for topic in self.PREDEFINED_TOPICS:
            count = sum(1 for t in self.categorizations.values() if t == topic)
            if count > 0:  # Only include topics with files
                topic_counts[topic] = count
        
        # Sort by count (descending), then alphabetically
        sorted_topics = sorted(
            topic_counts.items(),
            key=lambda x: (-x[1], x[0])
        )
        
        return [{'topic': topic, 'count': count} for topic, count in sorted_topics]
    
    def get_topic_for_file(self, file_path: Path) -> Optional[str]:
        """
        Get the topic for a specific file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Topic string or None if not categorized
        """
        from src.utils.file_manager import FileManager
        title = FileManager.load_metadata(file_path).get('title', file_path.stem)
        return self.categorizations.get(title)
    
    def recategorize_all(self, audio_files: List[Path], batch_size: int = 10) -> Dict[str, str]:
        """
        Force recategorization of all files (clears cache first).
        
        Args:
            audio_files: List of audio file paths
            batch_size: Number of files to process per API call
            
        Returns:
            Dict mapping file paths to topics
        """
        logger.info("Clearing cache and recategorizing all files")
        self.categorizations = {}
        return self.categorize_all_files(audio_files, batch_size)
