"""Tests for rate-limit integration in routes + 429 response."""
import io

import fakeredis
import pytest

from app.services import redis_service
from app.api import files as files_api, chat as chat_api
from app.models.file import File, FileStatus


@pytest.fixture
def redis_on(monkeypatch):
    """Activate fakeredis for rate-limit tests."""
    redis_service.reset()
    client = fakeredis.FakeRedis(decode_responses=True)
    redis_service._client = client
    redis_service._initialized = True
    yield client
    redis_service.reset()


@pytest.fixture
def small_limits(monkeypatch):
    """Make rate limits tiny so tests are fast."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "RATE_LIMIT_ASK_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_UPLOAD_PER_MINUTE", 2)


def test_upload_rate_limit_returns_429(client, auth_headers, monkeypatch, redis_on, small_limits):
    """3rd upload in a window returns 429 with Retry-After."""
    monkeypatch.setattr(files_api, "_process_in_background", lambda fid: None)

    for _ in range(2):
        r = client.post(
            "/api/v1/files",
            files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            headers=auth_headers,
        )
        assert r.status_code == 201

    r = client.post(
        "/api/v1/files",
        files={"file": ("c.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    assert int(r.headers["Retry-After"]) >= 1


def test_ask_rate_limit_returns_429(client, auth_headers, monkeypatch, redis_on, small_limits):
    """3rd ask in a window returns 429."""
    monkeypatch.setattr(files_api, "_process_in_background", lambda fid: None)
    monkeypatch.setattr(chat_api, "answer_question", lambda **kw: ("ok", []))

    # Upload + mark ready
    upload = client.post(
        "/api/v1/files",
        files={"file": ("d.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    # Mark file ready directly via session
    from tests.conftest import TestingSessionLocal
    db = TestingSessionLocal()
    f = db.get(File, fid)
    f.status = FileStatus.READY
    db.commit()
    db.close()

    for _ in range(2):
        r = client.post(
            "/api/v1/chat/ask",
            json={"question": "q?", "file_id": fid},
            headers=auth_headers,
        )
        assert r.status_code == 200

    r = client.post(
        "/api/v1/chat/ask",
        json={"question": "q?", "file_id": fid},
        headers=auth_headers,
    )
    assert r.status_code == 429


def test_no_rate_limit_when_redis_off(client, auth_headers, monkeypatch, small_limits):
    """When Redis is off (default in tests), no rate limit applies."""
    redis_service.reset()
    redis_service._client = None
    redis_service._initialized = True
    monkeypatch.setattr(files_api, "_process_in_background", lambda fid: None)

    # Upload more than the limit — all succeed
    for _ in range(5):
        r = client.post(
            "/api/v1/files",
            files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            headers=auth_headers,
        )
        assert r.status_code == 201
