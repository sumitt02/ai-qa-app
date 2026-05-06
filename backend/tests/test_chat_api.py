"""Chat API tests."""
import io
import json
from unittest.mock import MagicMock

import pytest

from app.api import files as files_api, chat as chat_api
from app.models.file import File, FileStatus, FileType


@pytest.fixture
def ready_file(client, auth_headers, monkeypatch, db_session):
    """Upload a file and mark it READY without running real processing."""
    monkeypatch.setattr(files_api, "_process_in_background", lambda fid: None)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    f = db_session.get(File, fid)
    f.status = FileStatus.READY
    db_session.commit()
    return fid


def test_create_session_no_file(client, auth_headers):
    response = client.post(
        "/api/v1/chat/sessions",
        json={"title": "My chat"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["title"] == "My chat"


def test_create_session_with_file(client, auth_headers, ready_file):
    response = client.post(
        "/api/v1/chat/sessions",
        json={"file_id": ready_file, "title": "About doc"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["file_id"] == ready_file


def test_create_session_unready_file(client, auth_headers, monkeypatch):
    monkeypatch.setattr(files_api, "_process_in_background", lambda fid: None)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("d.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    response = client.post(
        "/api/v1/chat/sessions", json={"file_id": fid}, headers=auth_headers
    )
    assert response.status_code == 409


def test_list_sessions(client, auth_headers):
    client.post("/api/v1/chat/sessions", json={"title": "A"}, headers=auth_headers)
    client.post("/api/v1/chat/sessions", json={"title": "B"}, headers=auth_headers)
    response = client.get("/api/v1/chat/sessions", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_session_with_messages(client, auth_headers, ready_file, monkeypatch):
    """Ask a question, then fetch the session and check messages + citations."""
    monkeypatch.setattr(
        chat_api,
        "answer_question",
        lambda **kw: ("The answer.", [
            {"file_id": ready_file, "filename": "doc.pdf", "snippet": "ctx", "page": 1, "start": None, "end": None}
        ]),
    )
    ask = client.post(
        "/api/v1/chat/ask",
        json={"question": "what?", "file_id": ready_file},
        headers=auth_headers,
    )
    assert ask.status_code == 200, ask.text

    sessions = client.get("/api/v1/chat/sessions", headers=auth_headers).json()
    sid = sessions[0]["id"]
    detail = client.get(f"/api/v1/chat/sessions/{sid}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["messages"]) == 2  # user + assistant
    assert body["messages"][1]["role"] == "assistant"
    assert body["messages"][1]["citations"][0]["page"] == 1


def test_get_session_corrupt_citations(client, auth_headers, ready_file, monkeypatch, db_session):
    monkeypatch.setattr(
        chat_api, "answer_question", lambda **kw: ("ok", [])
    )
    client.post(
        "/api/v1/chat/ask",
        json={"question": "x", "file_id": ready_file},
        headers=auth_headers,
    )
    sessions = client.get("/api/v1/chat/sessions", headers=auth_headers).json()
    sid = sessions[0]["id"]

    # Corrupt one message's citation field
    from app.models.chat import Message
    msg = db_session.query(Message).filter(Message.session_id == sid).first()
    msg.citations = "not-json"
    db_session.commit()

    detail = client.get(f"/api/v1/chat/sessions/{sid}", headers=auth_headers)
    assert detail.status_code == 200


def test_get_session_not_found(client, auth_headers):
    response = client.get("/api/v1/chat/sessions/99999", headers=auth_headers)
    assert response.status_code == 404


def test_get_session_not_owned(client, auth_headers):
    s1 = client.post("/api/v1/chat/sessions", json={}, headers=auth_headers).json()
    other = client.post(
        "/api/v1/auth/register", json={"email": "z@x.com", "password": "password123"}
    )
    response = client.get(
        f"/api/v1/chat/sessions/{s1['id']}",
        headers={"Authorization": f"Bearer {other.json()['access_token']}"},
    )
    assert response.status_code == 404


def test_ask_requires_file_id(client, auth_headers):
    response = client.post(
        "/api/v1/chat/ask",
        json={"question": "what?"},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_ask_unready_file(client, auth_headers, monkeypatch):
    monkeypatch.setattr(files_api, "_process_in_background", lambda fid: None)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("d.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    response = client.post(
        "/api/v1/chat/ask",
        json={"question": "x", "file_id": fid},
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_ask_creates_session(client, auth_headers, ready_file, monkeypatch):
    monkeypatch.setattr(
        chat_api, "answer_question", lambda **kw: ("answer text", [])
    )
    response = client.post(
        "/api/v1/chat/ask",
        json={"question": "Why?", "file_id": ready_file},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "answer text"
    assert body["role"] == "assistant"


def test_ask_existing_session(client, auth_headers, ready_file, monkeypatch):
    monkeypatch.setattr(chat_api, "answer_question", lambda **kw: ("a", []))
    sess = client.post(
        "/api/v1/chat/sessions",
        json={"file_id": ready_file, "title": "S"},
        headers=auth_headers,
    ).json()
    response = client.post(
        "/api/v1/chat/ask",
        json={"question": "q1", "file_id": ready_file, "session_id": sess["id"]},
        headers=auth_headers,
    )
    assert response.status_code == 200


def test_ask_invalid_session(client, auth_headers, ready_file, monkeypatch):
    monkeypatch.setattr(chat_api, "answer_question", lambda **kw: ("a", []))
    response = client.post(
        "/api/v1/chat/ask",
        json={"question": "q1", "file_id": ready_file, "session_id": 99999},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_ask_uses_history(client, auth_headers, ready_file, monkeypatch):
    """Second question reuses session history."""
    captured = {"history": None}

    def fake_answer(**kwargs):
        captured["history"] = kwargs.get("history")
        return "a", []

    monkeypatch.setattr(chat_api, "answer_question", fake_answer)

    first = client.post(
        "/api/v1/chat/ask",
        json={"question": "first", "file_id": ready_file},
        headers=auth_headers,
    )
    sid = client.get("/api/v1/chat/sessions", headers=auth_headers).json()[0]["id"]
    client.post(
        "/api/v1/chat/ask",
        json={"question": "second", "file_id": ready_file, "session_id": sid},
        headers=auth_headers,
    )
    # On second call, history should contain at least the previous exchange
    assert captured["history"] is not None
    contents = [h["content"] for h in captured["history"]]
    assert "first" in contents


def test_ask_stream(client, auth_headers, ready_file, monkeypatch):
    """Streaming endpoint emits SSE events."""
    def fake_stream(**kw):
        yield "event: citations\ndata: []\n\n"
        yield "event: token\ndata: Hello\n\n"
        yield "event: token\ndata:  world\n\n"
        yield "event: done\ndata: ok\n\n"

    monkeypatch.setattr(chat_api, "answer_question_stream", fake_stream)

    response = client.post(
        "/api/v1/chat/ask/stream",
        json={"question": "stream me", "file_id": ready_file},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: session" in body
    assert "event: citations" in body
    assert "event: token" in body
    assert "event: done" in body


def test_ask_stream_requires_file(client, auth_headers):
    response = client.post(
        "/api/v1/chat/ask/stream",
        json={"question": "x"},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_ask_stream_persists_message(client, auth_headers, ready_file, monkeypatch, db_session):
    """After streaming completes, the assistant message is saved."""
    def fake_stream(**kw):
        yield "event: citations\ndata: []\n\n"
        yield "event: token\ndata: hello\n\n"
        yield "event: done\ndata: ok\n\n"

    monkeypatch.setattr(chat_api, "answer_question_stream", fake_stream)

    response = client.post(
        "/api/v1/chat/ask/stream",
        json={"question": "q", "file_id": ready_file},
        headers=auth_headers,
    )
    assert response.status_code == 200
    # consume the stream
    _ = response.text

    sid = client.get("/api/v1/chat/sessions", headers=auth_headers).json()[0]["id"]
    detail = client.get(f"/api/v1/chat/sessions/{sid}", headers=auth_headers).json()
    assistant_messages = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert len(assistant_messages) == 1
    assert "hello" in assistant_messages[0]["content"]


def test_ask_stream_handles_bad_citations_event(client, auth_headers, ready_file, monkeypatch):
    """Malformed citations data doesn't crash."""
    def fake_stream(**kw):
        yield "event: citations\ndata: not-json\n\n"
        yield "event: done\ndata: ok\n\n"

    monkeypatch.setattr(chat_api, "answer_question_stream", fake_stream)

    response = client.post(
        "/api/v1/chat/ask/stream",
        json={"question": "q", "file_id": ready_file},
        headers=auth_headers,
    )
    assert response.status_code == 200
    _ = response.text  # don't crash
