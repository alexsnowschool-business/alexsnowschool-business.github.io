"""
File management utilities for organizing downloads, transcripts, and metadata.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from config import Config
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class FileManager:
    """Manages file operations for audio files and transcripts"""
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename by removing invalid characters.
        
        Args:
            filename: Original filename
        
        Returns:
            Sanitized filename
        """
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()
    
    @staticmethod
    def format_display_name(filepath: Path) -> str:
        """
        Format filename for display by removing extension and cleaning up.
        
        Args:
            filepath: Path to file
        
        Returns:
            Cleaned display name (e.g., "Maurice Merleau Ponty" instead of "Maurice-Merleau-Ponty.mp3")
        """
        # Get filename without extension
        name = filepath.stem
        
        # Remove '_transcript' suffix if present
        if name.endswith('_transcript'):
            name = name[:-11]  # len('_transcript') = 11
        
        # Replace hyphens and underscores with spaces
        name = name.replace('-', ' ').replace('_', ' ')
        
        # Clean up multiple spaces
        name = ' '.join(name.split())
        
        return name
    
    @staticmethod
    def get_file_hash(filepath: Path) -> str:
        """
        Calculate MD5 hash of a file.
        
        Args:
            filepath: Path to file
        
        Returns:
            MD5 hash string
        """
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    @staticmethod
    def save_metadata(filepath: Path, metadata: Dict[str, Any]):
        """
        Save metadata as JSON file alongside the main file.
        
        Args:
            filepath: Path to main file
            metadata: Dictionary of metadata
        """
        metadata_path = filepath.with_suffix('.json')
        metadata['file_hash'] = FileManager.get_file_hash(filepath)
        metadata['created_at'] = datetime.now().isoformat()
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved metadata to {metadata_path}")
    
    @staticmethod
    def load_metadata(filepath: Path) -> Dict[str, Any]:
        """
        Load metadata from JSON file.
        
        Args:
            filepath: Path to main file
        
        Returns:
            Metadata dictionary or empty dict if not found
        """
        metadata_path = filepath.with_suffix('.json')
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    @staticmethod
    def list_audio_files() -> list:
        """
        List all audio files in downloads directory.
        
        Returns:
            List of audio file paths
        """
        audio_extensions = ['.mp3', '.m4a', '.wav', '.ogg', '.flac']
        audio_files = []
        
        for ext in audio_extensions:
            audio_files.extend(Config.DOWNLOADS_DIR.glob(f'*{ext}'))
        
        return sorted(audio_files)
    
    @staticmethod
    def list_audio_files_sorted_by_date() -> list:
        """
        List all audio files sorted by published date (from metadata).
        Falls back to file modification time if no metadata available.
        
        Returns:
            List of audio file paths sorted by date (newest first)
        """
        from datetime import datetime
        
        audio_files = FileManager.list_audio_files()
        
        # Create list of (file, date) tuples
        files_with_dates = []
        for audio_file in audio_files:
            metadata = FileManager.load_metadata(audio_file)
            
            # Try to get published date from metadata
            date_str = metadata.get('published', '')
            
            try:
                # Try parsing various date formats
                if date_str:
                    # Common RSS date formats
                    for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d']:
                        try:
                            date_obj = datetime.strptime(date_str.strip(), fmt)
                            # Convert to timezone-naive to avoid comparison issues
                            if date_obj.tzinfo is not None:
                                date_obj = date_obj.replace(tzinfo=None)
                            break
                        except ValueError:
                            continue
                    else:
                        # If no format matched, use file modification time
                        date_obj = datetime.fromtimestamp(audio_file.stat().st_mtime)
                else:
                    # No published date in metadata, use file modification time
                    date_obj = datetime.fromtimestamp(audio_file.stat().st_mtime)
            except Exception:
                # Fallback to file modification time
                date_obj = datetime.fromtimestamp(audio_file.stat().st_mtime)
            
            files_with_dates.append((audio_file, date_obj))
        
        # Sort by date (newest first)
        files_with_dates.sort(key=lambda x: x[1], reverse=True)
        
        # Return just the file paths
        return [f[0] for f in files_with_dates]
    
    @staticmethod
    def list_audio_files_sorted_by_topic() -> list:
        """
        List all audio files grouped by similar topics using AI.
        Uses Google Gemini API to analyze titles and descriptions.
        
        Returns:
            List of audio file paths sorted by topic similarity
        """
        import google.generativeai as genai
        from config import Config
        
        audio_files = FileManager.list_audio_files()
        
        if not audio_files:
            return []
        
        # If no API key, fall back to date sorting
        if not Config.GOOGLE_AI_API_KEY:
            logger.warning("No Google AI API key - falling back to date sorting")
            return FileManager.list_audio_files_sorted_by_date()
        
        try:
            # Configure Gemini
            genai.configure(api_key=Config.GOOGLE_AI_API_KEY)
            model = genai.GenerativeModel('gemini-pro')
            
            # Collect file info
            file_info = []
            for audio_file in audio_files:
                metadata = FileManager.load_metadata(audio_file)
                title = metadata.get('title', audio_file.stem)
                description = metadata.get('description', '')[:200]  # Limit description length
                
                file_info.append({
                    'path': audio_file,
                    'title': title,
                    'description': description
                })
            
            # Build prompt for AI clustering
            titles_list = "\n".join([f"{i+1}. {info['title']}" for i, info in enumerate(file_info)])
            
            prompt = f"""Analyze these audio programme titles and group them by similar topics. Return ONLY a comma-separated list of numbers representing the order, grouping similar topics together.

Titles:
{titles_list}

Instructions:
- Group similar topics together (e.g., philosophy, science, history, politics)
- Within each topic group, maintain chronological or logical order
- Return ONLY numbers separated by commas (e.g., "3,7,1,5,2,4,6")
- No explanations, just the number sequence

Order:"""
            
            # Get AI response
            response = model.generate_content(prompt)
            order_str = response.text.strip()
            
            # Parse the order
            try:
                order_indices = [int(x.strip()) - 1 for x in order_str.split(',')]
                
                # Validate indices
                if len(order_indices) == len(file_info) and all(0 <= i < len(file_info) for i in order_indices):
                    # Reorder files based on AI suggestion
                    sorted_files = [file_info[i]['path'] for i in order_indices]
                    logger.info(f"Successfully sorted {len(sorted_files)} files by topic using AI")
                    return sorted_files
                else:
                    logger.warning("AI returned invalid order - falling back to date sorting")
                    return FileManager.list_audio_files_sorted_by_date()
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse AI response: {e} - falling back to date sorting")
                return FileManager.list_audio_files_sorted_by_date()
                
        except Exception as e:
            logger.error(f"Error in AI topic sorting: {e} - falling back to date sorting")
            return FileManager.list_audio_files_sorted_by_date()
    
    @staticmethod
    def list_transcripts() -> list:
        """
        List all transcript files.
        
        Returns:
            List of transcript file paths
        """
        return sorted(Config.TRANSCRIPTS_DIR.glob('*.txt'))
