from __future__ import annotations
import logging
from typing import Optional

import pandas as pd

from app.services.redis_client import (
    get_redis, serialize_df, deserialize_df, make_cache_key, TTL_DATAFRAME
)

logger = logging.getLogger(__name__)


class DataFrameCache:
    def __init__(self):
        self.redis = get_redis()

    def _key(self, dataset_id: str) -> str:
        return make_cache_key("df", dataset_id)

    def get(self, dataset_id: str) -> Optional[pd.DataFrame]:
        try:
            key = self._key(dataset_id)
            data = self.redis.get(key)
            if data is None:
                return None
            return deserialize_df(data)
        except Exception as e:
            logger.warning(f"DataFrame cache get failed for {dataset_id}: {e}")
            return None

    def set(self, dataset_id: str, df: pd.DataFrame) -> None:
        try:
            key = self._key(dataset_id)
            data = serialize_df(df)
            self.redis.setex(key, TTL_DATAFRAME, data)
        except Exception as e:
            logger.warning(f"DataFrame cache set failed for {dataset_id}: {e}")

    def delete(self, dataset_id: str) -> None:
        try:
            key = self._key(dataset_id)
            self.redis.delete(key)
        except Exception as e:
            logger.warning(f"DataFrame cache delete failed for {dataset_id}: {e}")

    def exists(self, dataset_id: str) -> bool:
        try:
            key = self._key(dataset_id)
            return self.redis.exists(key) > 0
        except Exception:
            return False

    def keys(self) -> list[str]:
        try:
            pattern = make_cache_key("df", "*")
            keys = self.redis.keys(pattern)
            return [k.decode().split(":", 2)[-1] for k in keys]
        except Exception:
            return []

df_cache = DataFrameCache()
