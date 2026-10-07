"""
Configuration management for BBC Audio Scraper system.
Loads environment variables and provides centralized config access.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Central configuration class"""
    
    # Base directories
    BASE_DIR = Path(__file__).parent
    DOWNLOADS_DIR = BASE_DIR / os.getenv('DOWNLOADS_DIR', 'downloads')
    TRANSCRIPTS_DIR = BASE_DIR / os.getenv('TRANSCRIPTS_DIR', 'transcripts')
    PDF_DIR = BASE_DIR / os.getenv('PDF_DIR', 'pdfs')
    HISTORY_DIR = BASE_DIR / os.getenv('HISTORY_DIR', 'data/history')
    TOPIC_CACHE_DIR = BASE_DIR / os.getenv('TOPIC_CACHE_DIR', 'data/topic_cache')
    TOPIC_CACHE_FILE = TOPIC_CACHE_DIR / 'topic_categorizations.json'

    # API Keys
    GOOGLE_AI_API_KEY = os.getenv('GOOGLE_AI_API_KEY', '')
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
    OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'openai/gpt-4o-mini')

    # Whisper Settings (local transcription)
    WHISPER_MODEL_SIZE = os.getenv('WHISPER_MODEL_SIZE', 'base')  # tiny, base, small, medium, large

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Google AI Settings
    GOOGLE_MODEL = os.getenv('GOOGLE_MODEL', 'gemini-flash-latest')  # Free tier model - latest stable Gemini Flash
    TEMPERATURE = 0.7
    MAX_TOKENS = 2048

    # Topic Categorization Settings
    PREDEFINED_TOPICS = ['History', 'Philosophy', 'Culture', 'Sociology', 'Economics', 'Arts', 'Literature', 'Uncategorized']
    
    @classmethod
    def ensure_directories(cls):
        """Create necessary directories if they don't exist"""
        cls.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        cls.TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        cls.PDF_DIR.mkdir(parents=True, exist_ok=True)
        cls.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        cls.TOPIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls):
        """Validate configuration"""
        cls.ensure_directories()
        return True

# Initialize on import
Config.validate()
