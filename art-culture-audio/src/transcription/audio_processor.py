"""
Audio processing utilities for format conversion and preprocessing.
"""

from pydub import AudioSegment
from pathlib import Path
from typing import Optional
from config import Config
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

class AudioProcessor:
    """Audio preprocessing and format conversion utilities"""
    
    @staticmethod
    def convert_to_wav(input_path: Path, output_path: Optional[Path] = None) -> Path:
        """
        Convert audio file to WAV format.
        
        Args:
            input_path: Input audio file path
            output_path: Optional output path (defaults to same name with .wav)
        
        Returns:
            Path to converted WAV file
        """
        input_path = Path(input_path)
        
        if output_path is None:
            output_path = input_path.with_suffix('.wav')
        
        logger.info(f"Converting {input_path.name} to WAV format")
        
        try:
            audio = AudioSegment.from_file(str(input_path))
            audio.export(str(output_path), format='wav')
            logger.info(f"Converted to: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error converting audio: {e}")
            raise
    
    @staticmethod
    def get_audio_duration(audio_path: Path) -> float:
        """
        Get duration of audio file in seconds.
        
        Args:
            audio_path: Path to audio file
        
        Returns:
            Duration in seconds
        """
        try:
            audio = AudioSegment.from_file(str(audio_path))
            duration = len(audio) / 1000.0  # Convert ms to seconds
            return duration
        except Exception as e:
            logger.error(f"Error getting audio duration: {e}")
            return 0.0
    
    @staticmethod
    def normalize_audio(input_path: Path, output_path: Optional[Path] = None) -> Path:
        """
        Normalize audio volume.
        
        Args:
            input_path: Input audio file path
            output_path: Optional output path
        
        Returns:
            Path to normalized audio file
        """
        input_path = Path(input_path)
        
        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_normalized{input_path.suffix}"
        
        logger.info(f"Normalizing audio: {input_path.name}")
        
        try:
            audio = AudioSegment.from_file(str(input_path))
            normalized = audio.normalize()
            normalized.export(str(output_path), format=input_path.suffix[1:])
            logger.info(f"Normalized audio saved to: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error normalizing audio: {e}")
            raise
    
    @staticmethod
    def split_audio(input_path: Path, chunk_length_ms: int = 600000) -> list:
        """
        Split long audio file into chunks.
        
        Args:
            input_path: Input audio file path
            chunk_length_ms: Chunk length in milliseconds (default: 10 minutes)
        
        Returns:
            List of chunk file paths
        """
        input_path = Path(input_path)
        logger.info(f"Splitting audio: {input_path.name}")
        
        try:
            audio = AudioSegment.from_file(str(input_path))
            chunks = []
            
            for i, start in enumerate(range(0, len(audio), chunk_length_ms)):
                chunk = audio[start:start + chunk_length_ms]
                chunk_path = input_path.parent / f"{input_path.stem}_chunk{i+1}{input_path.suffix}"
                chunk.export(str(chunk_path), format=input_path.suffix[1:])
                chunks.append(chunk_path)
                logger.info(f"Created chunk {i+1}: {chunk_path.name}")
            
            logger.info(f"Split into {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Error splitting audio: {e}")
            raise
