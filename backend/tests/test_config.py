"""Settings tests."""
from app.core.config import Settings


def test_cors_origins_list():
    s = Settings(CORS_ORIGINS="http://a.com, http://b.com ,http://c.com,")
    assert s.cors_origins_list == ["http://a.com", "http://b.com", "http://c.com"]


def test_cors_origins_empty():
    s = Settings(CORS_ORIGINS="")
    assert s.cors_origins_list == []
