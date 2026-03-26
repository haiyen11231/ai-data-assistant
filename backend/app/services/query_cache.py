from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

from app.services.redis_client import (
    get_redis, serialize_json, deserialize_json, make_cache_key, 
    hash_query, TTL_QUERY_RESULT
)

logger = logging.getLogger(__name__)


class QueryResultCache:
    def __init__(self):
        self.redis = get_redis()

    def _key(self, question: str, dataset_id: str) -> str:
        query_hash = hash_query(question, dataset_id)
        return make_cache_key("query", dataset_id, query_hash)

    def get(self, question: str, dataset_id: str) -> Optional[dict]:
        try:
            key = self._key(question, dataset_id)
            data = self.redis.get(key)
            if data is None:
                return None
            result = deserialize_json(data)
            logger.info(f"Query cache HIT: {key}")
            return result
        except Exception as e:
            logger.warning(f"Query cache get failed: {e}")
            return None

    def set(
        self,
        question: str,
        dataset_id: str,
        answer: str,
        chart_b64: Optional[str] = None,
        table_rows: Optional[list] = None,
    ) -> None:
        try:
            key = self._key(question, dataset_id)
            result = {
                "answer": answer,
                "chart_b64": chart_b64,
                "table_rows": table_rows,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            data = serialize_json(result)
            self.redis.setex(key, TTL_QUERY_RESULT, data)
            logger.info(f"Query cache SET: {key}")
        except Exception as e:
            logger.warning(f"Query cache set failed: {e}")

    def invalidate_dataset(self, dataset_id: str) -> int:
        try:
            pattern = make_cache_key("query", dataset_id, "*")
            keys = self.redis.keys(pattern)
            if keys:
                deleted = self.redis.delete(*keys)
                logger.info(f"Invalidated {deleted} cached queries for dataset {dataset_id}")
                return deleted
            return 0
        except Exception as e:
            logger.warning(f"Query cache invalidation failed for {dataset_id}: {e}")
            return 0

query_cache = QueryResultCache()
