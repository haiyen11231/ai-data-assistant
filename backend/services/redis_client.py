from __future__ import annotations
import hashlib
import json
import pickle
import os
import uuid
from typing import Any, Optional

import pandas as pd
import redis
from redis.connection import ConnectionPool

# Environment configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD") 

_pool: Optional[ConnectionPool] = None
_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _pool, _client
    if _client is None:
        _pool = ConnectionPool.from_url(
            REDIS_URL,
            password=REDIS_PASSWORD,
            max_connections=50,
            retry_on_timeout=True,
            socket_keepalive=True,
            socket_keepalive_options={},
            health_check_interval=10,
        )
        _client = redis.Redis(connection_pool=_pool, decode_responses=False)
    return _client


def ping() -> bool:
    try:
        return get_redis().ping()
    except Exception:
        return False

def serialize_df(df: pd.DataFrame) -> bytes:
    return pickle.dumps(df)


def deserialize_df(data: bytes) -> pd.DataFrame:
    return pickle.loads(data)


def serialize_json(obj: Any) -> bytes:
    return json.dumps(obj, separators=(',', ':')).encode('utf-8')


def deserialize_json(data: bytes) -> Any:
    return json.loads(data.decode('utf-8'))


def make_cache_key(*parts: str) -> str:
    return ":".join(str(p) for p in parts)


def hash_query(question: str, dataset_id: str) -> str:
    content = f"{question.strip().lower()}|{dataset_id}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# TTL constants (seconds) 
TTL_DATAFRAME = 24 * 3600      # 24 hours
TTL_QUERY_RESULT = 7 * 24 * 3600   # 7 days
TTL_METADATA = 3600             # 1 hour
TTL_SESSION = 30 * 24 * 3600    # 30 days
TTL_RATE_LIMIT = 60             # 1 minute
