"""
Topic categorization for episodes via the OpenRouter API, based on each
episode's RSS description. Results are cached on disk (keyed by episode id)
so re-running the build only pays for newly-seen episodes.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests

from config import Config
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PREDEFINED_TOPICS = [
    'History', 'Philosophy', 'Culture', 'Sociology',
    'Economics', 'Arts', 'Literature', 'Uncategorized'
]


class OpenRouterCategorizer:
    """Categorizes episodes into PREDEFINED_TOPICS using OpenRouter, with caching."""

    def __init__(self, cache_file_path: Optional[Path] = None):
        self.cache_file = cache_file_path or (Config.TOPIC_CACHE_DIR / 'openrouter_categorizations.json')
        self.categorizations: Dict[str, str] = {}
        self._load_cache()

        if not Config.OPENROUTER_API_KEY:
            logger.warning("No OpenRouter API key (OPENROUTER_API_KEY) - categorization will default to 'Uncategorized'")

    def _load_cache(self):
        if self.cache_file.exists():
            try:
                self.categorizations = json.loads(self.cache_file.read_text(encoding="utf-8"))
                logger.info(f"Loaded {len(self.categorizations)} cached categorizations")
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Error loading cache: {e}")
                self.categorizations = {}
        else:
            self.categorizations = {}

    def _save_cache(self):
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_text(
            json.dumps(self.categorizations, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _call_openrouter(self, batch: List[Dict], retry_count: int = 3) -> Dict[str, str]:
        """Classify a batch of {'id', 'title', 'description'} dicts. Returns id -> topic."""
        if not Config.OPENROUTER_API_KEY:
            return {item['id']: 'Uncategorized' for item in batch}

        topics_list = ', '.join(PREDEFINED_TOPICS[:-1])
        items_text = '\n'.join(
            f"{i + 1}. Title: {item['title']}\n   Description: {(item.get('description') or 'N/A')[:300]}"
            for i, item in enumerate(batch)
        )

        prompt = f"""Analyze these audio programme titles and descriptions, then categorize each into ONE of these topics: {topics_list}.

If a programme doesn't clearly fit any category, assign it to "Uncategorized".

Programmes:
{items_text}

Return ONLY a JSON object mapping the programme number (1, 2, 3, etc.) to its topic category.
Example format: {{"1": "History", "2": "Philosophy", "3": "Uncategorized"}}"""

        headers = {
            "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": Config.OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }

        for attempt in range(retry_count):
            try:
                response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"].strip()

                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0].strip()

                parsed = json.loads(content)

                result = {}
                for i, item in enumerate(batch):
                    topic = parsed.get(str(i + 1), 'Uncategorized')
                    if topic not in PREDEFINED_TOPICS:
                        topic = 'Uncategorized'
                    result[item['id']] = topic
                return result

            except Exception as e:
                if attempt < retry_count - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"OpenRouter call failed (attempt {attempt + 1}/{retry_count}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"OpenRouter call failed after {retry_count} attempts: {e}")
                    return {item['id']: 'Uncategorized' for item in batch}

        return {}

    def categorize(self, episodes: List[Dict], batch_size: int = 10) -> Dict[str, str]:
        """
        Categorize episodes (each needs 'id', 'title', optionally 'description').
        Returns dict of episode id -> topic, using and updating the on-disk cache.
        """
        uncached = [ep for ep in episodes if ep['id'] not in self.categorizations]

        if not uncached:
            logger.info(f"All {len(episodes)} episodes already categorized (cache hit)")
        else:
            logger.info(f"Categorizing {len(uncached)} new episode(s) via OpenRouter ({len(episodes)} total)")
            for i in range(0, len(uncached), batch_size):
                batch = uncached[i:i + batch_size]
                logger.info(f"Batch {i // batch_size + 1}/{(len(uncached) - 1) // batch_size + 1} ({len(batch)} episodes)")
                self.categorizations.update(self._call_openrouter(batch))
                self._save_cache()
                if i + batch_size < len(uncached):
                    time.sleep(1)

        return {ep['id']: self.categorizations.get(ep['id'], 'Uncategorized') for ep in episodes}
