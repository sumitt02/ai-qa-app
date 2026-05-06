"""Redis service tests using fakeredis."""
import time
from unittest.mock import MagicMock

import fakeredis
import pytest

from app.services import redis_service


@pytest.fixture
def fake_client(monkeypatch):
    """Inject a fakeredis client and reset state between tests."""
    redis_service.reset()
    client = fakeredis.FakeRedis(decode_responses=True)
    redis_service._client = client
    redis_service._initialized = True
    yield client
    redis_service.reset()


@pytest.fixture
def no_redis(monkeypatch):
    """Force Redis to be unavailable."""
    redis_service.reset()
    redis_service._client = None
    redis_service._initialized = True
    yield
    redis_service.reset()


# --------------------------- get_redis ---------------------------

def test_get_redis_disabled(monkeypatch):
    """Empty REDIS_URL disables Redis cleanly."""
    redis_service.reset()
    from app.core.config import settings
    monkeypatch.setattr(settings, "REDIS_URL", "")
    assert redis_service.get_redis() is None


def test_get_redis_connection_failure(monkeypatch):
    """A connection failure returns None instead of crashing."""
    redis_service.reset()
    import redis as redis_lib

    fake = MagicMock()
    fake.ping.side_effect = redis_lib.ConnectionError("nope")
    monkeypatch.setattr(redis_lib.Redis, "from_url", lambda *a, **kw: fake)

    from app.core.config import settings
    monkeypatch.setattr(settings, "REDIS_URL", "redis://nowhere:9999/0")
    assert redis_service.get_redis() is None


def test_get_redis_caches_client(fake_client):
    """Subsequent get_redis calls return the same client."""
    a = redis_service.get_redis()
    b = redis_service.get_redis()
    assert a is b


# --------------------------- embedding cache ---------------------------

def test_cache_set_and_get(fake_client):
    redis_service.set_cached_embedding("model-x", "hello", [0.1, 0.2, 0.3])
    out = redis_service.get_cached_embedding("model-x", "hello")
    assert out == [0.1, 0.2, 0.3]


def test_cache_miss(fake_client):
    assert redis_service.get_cached_embedding("model-x", "nope") is None


def test_cache_no_redis_get(no_redis):
    """get returns None silently when Redis is unavailable."""
    assert redis_service.get_cached_embedding("m", "t") is None


def test_cache_no_redis_set(no_redis):
    """set is a no-op when Redis is unavailable."""
    redis_service.set_cached_embedding("m", "t", [1.0])  # no exception


def test_cache_get_handles_redis_error(monkeypatch, fake_client):
    """Errors during get are swallowed."""
    def boom(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(fake_client, "get", boom)
    assert redis_service.get_cached_embedding("m", "t") is None


def test_cache_set_handles_redis_error(monkeypatch, fake_client):
    """Errors during set are swallowed."""
    def boom(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(fake_client, "setex", boom)
    redis_service.set_cached_embedding("m", "t", [1.0])  # no exception


def test_cache_keys_differ_per_text(fake_client):
    redis_service.set_cached_embedding("m", "alpha", [1.0])
    redis_service.set_cached_embedding("m", "beta", [2.0])
    assert redis_service.get_cached_embedding("m", "alpha") == [1.0]
    assert redis_service.get_cached_embedding("m", "beta") == [2.0]


def test_cache_keys_differ_per_model(fake_client):
    redis_service.set_cached_embedding("m1", "x", [1.0])
    redis_service.set_cached_embedding("m2", "x", [2.0])
    assert redis_service.get_cached_embedding("m1", "x") == [1.0]
    assert redis_service.get_cached_embedding("m2", "x") == [2.0]


# --------------------------- rate limiter ---------------------------

def test_rate_limit_allows_under_threshold(fake_client):
    for _ in range(5):
        redis_service.check_rate_limit("test", identity="u1", limit=5)


def test_rate_limit_blocks_over_threshold(fake_client):
    for _ in range(3):
        redis_service.check_rate_limit("test", identity="u1", limit=3)
    with pytest.raises(redis_service.RateLimitExceeded) as exc:
        redis_service.check_rate_limit("test", identity="u1", limit=3)
    assert exc.value.retry_after >= 1


def test_rate_limit_per_identity(fake_client):
    """Each identity has its own bucket."""
    for _ in range(3):
        redis_service.check_rate_limit("test", identity="u1", limit=3)
    # u1 over budget, u2 still fine
    with pytest.raises(redis_service.RateLimitExceeded):
        redis_service.check_rate_limit("test", identity="u1", limit=3)
    redis_service.check_rate_limit("test", identity="u2", limit=3)


def test_rate_limit_per_bucket(fake_client):
    """Different buckets are independent."""
    for _ in range(3):
        redis_service.check_rate_limit("ask", identity="u1", limit=3)
    redis_service.check_rate_limit("upload", identity="u1", limit=3)


def test_rate_limit_no_redis_allows(no_redis):
    """Without Redis we fail open."""
    for _ in range(100):
        redis_service.check_rate_limit("test", identity="u1", limit=1)


def test_rate_limit_handles_incr_error(monkeypatch, fake_client):
    """Errors during INCR fail open."""
    def boom(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(fake_client, "incr", boom)
    redis_service.check_rate_limit("test", identity="u1", limit=1)


def test_rate_limit_ttl_fallback(monkeypatch, fake_client):
    """If TTL lookup fails when over limit, retry_after still returned."""
    for _ in range(3):
        redis_service.check_rate_limit("test", identity="u1", limit=3)

    def boom(*a, **kw):
        raise RuntimeError("ttl down")
    monkeypatch.setattr(fake_client, "ttl", boom)

    with pytest.raises(redis_service.RateLimitExceeded) as exc:
        redis_service.check_rate_limit("test", identity="u1", limit=3)
    assert exc.value.retry_after >= 1
