from __future__ import annotations
import logging
import time
import uuid
from typing import Tuple

from backend.services.redis_client import get_redis, make_cache_key, TTL_RATE_LIMIT

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self):
        self.redis = get_redis()

    def _key(self, identifier: str, limit_type: str) -> str:
        return make_cache_key("rate", limit_type, identifier)

    def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        limit_type: str = "general"
    ) -> Tuple[bool, dict]:
        try:
            key = self._key(identifier, limit_type)
            now = time.time()
            window_start = now - window_seconds

            pipe = self.redis.pipeline()
            
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current entries
            pipe.zcard(key)
            
            # Add current request
            request_id = str(uuid.uuid4())
            pipe.zadd(key, {request_id: now})
            
            # Set expiry
            pipe.expire(key, window_seconds)
            
            results = pipe.execute()
            current_count = results[1]  # Result of ZCARD
            
            allowed = current_count <= limit
            remaining = max(0, limit - current_count)
            reset_time = int(now + window_seconds)

            if not allowed:
                # Remove the request we just added since it's rejected
                self.redis.zrem(key, request_id)

            info = {
                "current_count": current_count,
                "limit": limit,
                "remaining": remaining,
                "reset_time": reset_time,
            }

            return allowed, info

        except Exception as e:
            logger.error(f"Rate limit check failed for {identifier}: {e}")
            # Fail open — allow request if Redis is down
            return True, {"error": str(e)}


# Rate limit configurations
RATE_LIMITS = {
    "general": {"limit": 120, "window": 60},      # 120 req/min for general API
    "ai_query": {"limit": 10, "window": 60},      # 10 AI queries/min
    "upload": {"limit": 20, "window": 300},       # 20 uploads per 5 min
}

rate_limiter = RateLimiter()
