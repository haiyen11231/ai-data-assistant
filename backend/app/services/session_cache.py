from __future__ import annotations
import logging
from typing import Optional, List
from datetime import datetime, timezone

from app.services.redis_client import (
    get_redis, serialize_json, deserialize_json, 
    make_cache_key, TTL_METADATA, TTL_SESSION
)

logger = logging.getLogger(__name__)


class SessionCache:
    def __init__(self):
        self.redis = get_redis()

    def set_session(self, session_id: str, session_data: dict) -> None:
        try:
            key = make_cache_key("session", session_id)
            data = serialize_json(session_data)
            self.redis.setex(key, TTL_SESSION, data)
        except Exception as e:
            logger.warning(f"Session cache set failed: {e}")

    def get_session(self, session_id: str) -> Optional[dict]:
        try:
            key = make_cache_key("session", session_id)
            data = self.redis.get(key)
            return deserialize_json(data) if data else None
        except Exception as e:
            logger.warning(f"Session cache get failed: {e}")
            return None

    def set_dataset_meta(self, dataset_id: str, metadata: dict) -> None:
        try:
            key = make_cache_key("meta", dataset_id)
            # Add cache timestamp
            metadata["cached_at"] = datetime.now(timezone.utc).isoformat()
            data = serialize_json(metadata)
            self.redis.setex(key, TTL_METADATA, data)
        except Exception as e:
            logger.warning(f"Dataset metadata cache set failed: {e}")

    def get_dataset_meta(self, dataset_id: str) -> Optional[dict]:
        try:
            key = make_cache_key("meta", dataset_id)
            data = self.redis.get(key)
            return deserialize_json(data) if data else None
        except Exception as e:
            logger.warning(f"Dataset metadata cache get failed: {e}")
            return None

    def invalidate_dataset_meta(self, dataset_id: str) -> None:
        try:
            key = make_cache_key("meta", dataset_id)
            self.redis.delete(key)
        except Exception as e:
            logger.warning(f"Dataset metadata cache invalidation failed: {e}")

    def warm_session_cache(self, session_id: str, datasets: List[dict]) -> None:
        try:
            session_data = {
                "session_id": session_id,
                "dataset_count": len(datasets),
                "last_upload": datetime.now(timezone.utc).isoformat(),
            }
            self.set_session(session_id, session_data)
            
            # Cache each dataset metadata
            for dataset in datasets:
                self.set_dataset_meta(dataset["dataset_id"], dataset)
                
        except Exception as e:
            logger.warning(f"Session cache warming failed: {e}")

session_cache = SessionCache()
