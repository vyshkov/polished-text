"""History management for recent dictation transcriptions and text corrections."""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from .config import HISTORY_FILE


class HistoryManager:
    """Manages persistent history of recent dictations and corrections."""

    def __init__(self, file_path: Optional[Path] = None, max_items: int = 20):
        self.file_path = file_path or HISTORY_FILE
        self.max_items = max_items
        self._items: List[Dict] = []
        self.load()

    def load(self):
        """Load history items from disk."""
        if not self.file_path.exists():
            self._items = []
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._items = data[: self.max_items]
                else:
                    self._items = []
        except Exception:
            self._items = []

    def save(self):
        """Save history items to disk."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._items, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, text: str, kind: str = "dictation"):
        """Add a new item to the history.

        :param text: The transcribed or corrected text.
        :param kind: 'dictation' or 'correction'.
        """
        text = text.strip()
        if not text:
            return

        # Avoid exact consecutive duplicate
        if self._items and self._items[0].get("text") == text and self._items[0].get("kind") == kind:
            self._items[0]["timestamp"] = time.time()
            self.save()
            return

        item = {
            "text": text,
            "kind": kind,
            "timestamp": time.time(),
        }

        self._items.insert(0, item)
        self._items = self._items[: self.max_items]
        self.save()

    def get_recent(self, limit: int = 5) -> List[Dict]:
        """Return the most recent history items up to limit."""
        return self._items[:limit]

    def clear(self):
        """Clear all history items."""
        self._items = []
        self.save()
