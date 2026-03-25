from __future__ import annotations
from collections import OrderedDict
from threading import Lock
import pandas as pd

_MAX_ENTRIES = 50   # ~50 datasets in memory at once


class _LRUCache:
    def __init__(self, maxsize: int = _MAX_ENTRIES):
        self._cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self._lock = Lock()
        self._maxsize = maxsize

    def get(self, key: str) -> pd.DataFrame | None:
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def set(self, key: str, df: pd.DataFrame) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = df
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)   # evict oldest

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._cache.keys())


df_cache = _LRUCache()
