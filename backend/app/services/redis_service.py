"""Redis-backed cache and rate limiter.

Both features fail open: if Redis is unreachable, the app keeps working.
"""
from __future__ import annotations
import hashlib
import json
import logging
import time
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)


_client: redis.Redis | None = None
_initialized = False


def get_redis() -> redis.Redis | None:
    """
    Lazy singleton Redis client. Returns None if Redis is unavailable.
    Tests can override by setting `_client` directly.
    """
    global _client, _initialized
    if _initialized:
        return _client
    _initialized = True
    if not settings.REDIS_URL:
        return None
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        _client = client
    except Exception as e:
        logger.warning("Redis unavailable (%s); cache + rate-limit disabled.", e)
        _client = None
    return _client


def reset() -> None:
    """For tests."""
    global _client, _initialized
    _client = None
    _initialized = False


# --------------------------- embedding cache ---------------------------

EMBEDDING_PREFIX = "emb:"


def _embedding_key(model: str, text: str) -> str:
    """Stable cache key from (model, text)."""
    digest = hashlib.sha256(f"{model}|{text}".encode("utf-8")).hexdigest()
    return f"{EMBEDDING_PREFIX}{digest}"


def get_cached_embedding(model: str, text: str) -> list[float] | None:
    """Return a cached embedding or None."""
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(_embedding_key(model, text))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("Cache get failed: %s", e)
        return None


def set_cached_embedding(model: str, text: str, vector: list[float]) -> None:
    """Cache an embedding with TTL."""
    client = get_redis()
    if client is None:
        return
    try:
        client.setex(
            _embedding_key(model, text),
            settings.EMBEDDING_CACHE_TTL,
            json.dumps(vector),
        )
    except Exception as e:
        logger.warning("Cache set failed: %s", e)


# --------------------------- rate limiter ---------------------------

class RateLimitExceeded(Exception):
    """Raised when a caller is over their per-minute budget."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded; retry in {retry_after}s")


def check_rate_limit(bucket: str, identity: str | int, limit: int, window_seconds: int = 60) -> None:
    """
    Sliding-window-ish counter using INCR + EXPIRE.

    Raises RateLimitExceeded if the caller has exceeded `limit` requests in the
    last `window_seconds`. Fails open (allows) if Redis is down.
    """
    client = get_redis()
    if client is None:
        return  # fail open

    # Bucket the timestamp into a window. Switching windows resets the counter.
    window_id = int(time.time()) // window_seconds
    key = f"rl:{bucket}:{identity}:{window_id}"

    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds + 1)
    except Exception as e:
        logger.warning("Rate-limit check failed (%s); allowing request.", e)
        return

    if count > limit:
        # Approximate retry: time until the window flips
        try:
            ttl = client.ttl(key)
        except Exception:
            ttl = window_seconds
        retry_after = max(int(ttl), 1)
        raise RateLimitExceeded(retry_after=retry_after)
