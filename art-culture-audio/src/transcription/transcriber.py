"""
Audio transcription using OpenAI Whisper (FREE, runs locally).
No API key required - completely free and open-source.
"""

import whisper
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
from config import Config
from src.utils.logger import setup_logger
from src.utils.file_manager import FileManager

logger = setup_logger(__name__)

class WhisperTranscriber:
    """
    Local audio transcription using OpenAI Whisper.
    
    Model sizes (speed vs accuracy trade-off):
    - tiny: Fastest, least accurate (~1GB RAM)
    - base: Fast, good for most use cases (~1GB RAM)
    - small: Balanced (~2GB RAM)
    - medium: High accuracy (~5GB RAM)
    - large: Best accuracy, slowest (~10GB RAM)
    """
    
    def __init__(self, model_size: str = None):
        """
        Initialize Whisper transcriber.
        
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
        """
        self.model_size = model_size or Config.WHISPER_MODEL_SIZE
        self.model = None
        self.file_manager = FileManager()
        logger.info(f"Initialized WhisperTranscriber with model: {self.model_size}")
    
    def load_model(self):
        """Load Whisper model (lazy loading)"""
        if self.model is None:
            logger.info(f"Loading Whisper model '{self.model_size}'... (this may take a moment)")
            self.model = whisper.load_model(self.model_size)
            logger.info("Model loaded successfully")
    
    def transcribe_audio(self, audio_path: Path, language: str = 'en') -> Dict:
        """
        Transcribe audio file to text.
        
        Args:
            audio_path: Path to audio file
            language: Language code (default: 'en' for English)
        
        Returns:
            Dictionary with transcript text and metadata
        """
        audio_path = Path(audio_path)
        
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return None
        
        # Load model if not already loaded
        self.load_model()
        
        logger.info(f"Transcribing: {audio_path.name}")
        start_time = datetime.now()
        
        try:
            # Transcribe with Whisper
            result = self.model.transcribe(
                str(audio_path),
                language=language,
                verbose=False
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Transcription completed in {duration:.1f} seconds")
            
            transcript_data = {
                'text': result['text'].strip(),
                'language': result.get('language', language),
                'segments': result.get('segments', []),
                'audio_file': str(audio_path),
                'model': self.model_size,
                'transcription_time': duration,
                'timestamp': datetime.now().isoformat(),
            }
            
            return transcript_data
            
        except Exception as e:
            logger.error(f"Error transcribing {audio_path}: {e}")
            return None
    
    def save_transcript(self, transcript_data: Dict, output_path: Optional[Path] = None) -> Path:
        """
        Save transcript to text file.
        
        Args:
            transcript_data: Transcript data from transcribe_audio()
            output_path: Optional custom output path
        
        Returns:
            Path to saved transcript file
        """
        if output_path is None:
            # Generate output path based on audio filename
            audio_path = Path(transcript_data['audio_file'])
            output_path = Config.TRANSCRIPTS_DIR / f"{audio_path.stem}_transcript.txt"
        
        # Save transcript text
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(transcript_data['text'])
        
        logger.info(f"Saved transcript to: {output_path}")
        
        # Save metadata
        metadata = {
            'audio_file': transcript_data['audio_file'],
            'model': transcript_data['model'],
            'language': transcript_data['language'],
            'transcription_time': transcript_data['transcription_time'],
            'timestamp': transcript_data['timestamp'],
            'word_count': len(transcript_data['text'].split()),
        }
        self.file_manager.save_metadata(output_path, metadata)
        
        return output_path
    
    def transcribe_and_save(self, audio_path: Path, language: str = 'en') -> Optional[Path]:
        """
        Transcribe audio and save to file (convenience method).
        
        Args:
            audio_path: Path to audio file
            language: Language code
        
        Returns:
            Path to transcript file or None if failed
        """
        transcript_data = self.transcribe_audio(audio_path, language)
        if transcript_data:
            return self.save_transcript(transcript_data)
        return None
    
    def batch_transcribe(self, audio_files: list, language: str = 'en') -> list:
        """
        Transcribe multiple audio files.
        
        Args:
            audio_files: List of audio file paths
            language: Language code
        
        Returns:
            List of transcript file paths
        """
        logger.info(f"Starting batch transcription of {len(audio_files)} files")
        transcripts = []
        
        for i, audio_path in enumerate(audio_files, 1):
            logger.info(f"Processing file {i}/{len(audio_files)}: {Path(audio_path).name}")
            transcript_path = self.transcribe_and_save(audio_path, language)
            if transcript_path:
                transcripts.append(transcript_path)
        
        logger.info(f"Batch transcription complete: {len(transcripts)} successful")
        return transcripts
