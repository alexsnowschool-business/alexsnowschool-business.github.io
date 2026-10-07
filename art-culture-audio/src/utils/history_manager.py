"""
History management for tracking listening/reading progress.
Stores user's content consumption history and provides statistics.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from config import Config
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class HistoryManager:
    """Manages listening and reading history for audio content"""
    
    def __init__(self):
        """Initialize history manager"""
        self.history_file = Config.HISTORY_DIR / "listening_history.json"
        self.history = self._load_history()
    
    def _load_history(self) -> Dict:
        """
        Load history from JSON file.
        
        Returns:
            Dictionary of history records
        """
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading history: {e}")
                return {}
        return {}
    
    def _save_history(self):
        """Save history to JSON file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
            logger.info("History saved successfully")
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    def mark_as_accessed(self, content_name: str):
        """
        Mark content as accessed (started listening/reading).
        
        Args:
            content_name: Name of the content
        """
        now = datetime.now().isoformat()
        
        if content_name not in self.history:
            # First time accessing
            self.history[content_name] = {
                'status': 'in_progress',
                'first_accessed': now,
                'last_accessed': now,
                'access_count': 1
            }
            logger.info(f"Marked '{content_name}' as accessed (new)")
        else:
            # Update existing record
            self.history[content_name]['last_accessed'] = now
            self.history[content_name]['access_count'] = self.history[content_name].get('access_count', 0) + 1
            # If it was completed, keep it completed
            if self.history[content_name]['status'] != 'completed':
                self.history[content_name]['status'] = 'in_progress'
            logger.info(f"Updated access for '{content_name}'")
        
        self._save_history()
    
    def mark_as_completed(self, content_name: str):
        """
        Mark content as completed.
        
        Args:
            content_name: Name of the content
        """
        now = datetime.now().isoformat()
        
        if content_name not in self.history:
            # First time, mark as completed
            self.history[content_name] = {
                'status': 'completed',
                'first_accessed': now,
                'last_accessed': now,
                'completed_at': now,
                'access_count': 1
            }
        else:
            # Update existing record
            self.history[content_name]['status'] = 'completed'
            self.history[content_name]['completed_at'] = now
            self.history[content_name]['last_accessed'] = now
        
        logger.info(f"Marked '{content_name}' as completed")
        self._save_history()
    
    def get_history(self, status_filter: Optional[str] = None) -> List[Dict]:
        """
        Get history records, optionally filtered by status.
        
        Args:
            status_filter: Optional status to filter by ('in_progress', 'completed', None for all)
        
        Returns:
            List of history records with content names
        """
        records = []
        for content_name, data in self.history.items():
            if status_filter is None or data.get('status') == status_filter:
                record = {'content_name': content_name, **data}
                records.append(record)
        
        # Sort by last accessed (most recent first)
        records.sort(key=lambda x: x.get('last_accessed', ''), reverse=True)
        return records
    
    def get_status(self, content_name: str) -> str:
        """
        Get status of a specific content.
        
        Args:
            content_name: Name of the content
        
        Returns:
            Status string: 'not_started', 'in_progress', or 'completed'
        """
        if content_name not in self.history:
            return 'not_started'
        return self.history[content_name].get('status', 'not_started')
    
    def get_statistics(self) -> Dict:
        """
        Get summary statistics about listening history.
        
        Returns:
            Dictionary with statistics
        """
        total = len(self.history)
        completed = sum(1 for data in self.history.values() if data.get('status') == 'completed')
        in_progress = sum(1 for data in self.history.values() if data.get('status') == 'in_progress')
        
        completion_rate = (completed / total * 100) if total > 0 else 0
        
        return {
            'total_content': total,
            'completed': completed,
            'in_progress': in_progress,
            'not_started': 0,  # We only track accessed content
            'completion_rate': round(completion_rate, 1)
        }
    
    def get_completed_content_names(self) -> set:
        """
        Get set of all completed content names.
        
        Returns:
            Set of content names that have been marked as completed
        """
        return {
            content_name
            for content_name, data in self.history.items()
            if data.get('status') == 'completed'
        }

    
    def clear_history(self):
        """Clear all history"""
        self.history = {}
        self._save_history()
        logger.info("Cleared all history")
    
    def delete_record(self, content_name: str):
        """
        Delete a specific history record.
        
        Args:
            content_name: Name of the content to remove
        """
        if content_name in self.history:
            del self.history[content_name]
            self._save_history()
            logger.info(f"Deleted history for '{content_name}'")
