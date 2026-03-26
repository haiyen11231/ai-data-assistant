from __future__ import annotations
from collections import defaultdict
from threading import Lock
from typing import Optional
from app.models.schemas import HistoryItem, FeedbackRequest


class HistoryStore:
    def __init__(self):
        self._store: dict[str, list[HistoryItem]] = defaultdict(list)
        self._lock = Lock()

    def append(self, session_id: str, item: HistoryItem) -> None:
        with self._lock:
            self._store[session_id].append(item)

    def list_all(self, session_id: str) -> list[HistoryItem]:
        with self._lock:
            return list(self._store[session_id])

    def apply_feedback(
        self,
        session_id: str,
        feedback: FeedbackRequest,
    ) -> Optional[HistoryItem]:
        with self._lock:
            for item in self._store[session_id]:
                if item.prompt_id == feedback.prompt_id:
                    item.rating = feedback.rating
                    return item
        return None

history_store = HistoryStore()
