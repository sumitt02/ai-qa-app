"""File API tests."""
import io
import json
from unittest.mock import MagicMock

import pytest

from app.api import files as files_api
from app.models.file import File, FileStatus, FileType


def _patch_processing(monkeypatch):
    """Make background processing a no-op so tests don't hit OpenAI."""
    monkeypatch.setattr(files_api, "_process_in_background", lambda fid: None)


def test_detect_file_type_pdf():
    assert files_api.detect_file_type("doc.pdf", "application/pdf") == FileType.PDF
    assert files_api.detect_file_type("doc.PDF", "") == FileType.PDF


def test_detect_file_type_audio():
    assert files_api.detect_file_type("a.mp3", "audio/mpeg") == FileType.AUDIO
    assert files_api.detect_file_type("a.wav", "") == FileType.AUDIO
    assert files_api.detect_file_type("a.m4a", "") == FileType.AUDIO


def test_detect_file_type_video():
    assert files_api.detect_file_type("v.mp4", "video/mp4") == FileType.VIDEO
    assert files_api.detect_file_type("v.mov", "") == FileType.VIDEO


def test_detect_file_type_unknown():
    assert files_api.detect_file_type("foo.exe", "application/x-msdownload") is None
    assert files_api.detect_file_type("", "") is None


def test_upload_pdf(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    pdf_bytes = b"%PDF-1.4\n%fake content\n%%EOF"
    response = client.post(
        "/api/v1/files",
        files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "test.pdf"
    assert body["file_type"] == "pdf"
    assert body["status"] == "pending"


def test_upload_audio(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    response = client.post(
        "/api/v1/files",
        files={"file": ("song.mp3", io.BytesIO(b"fake-audio"), "audio/mpeg")},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["file_type"] == "audio"


def test_upload_video(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    response = client.post(
        "/api/v1/files",
        files={"file": ("clip.mp4", io.BytesIO(b"fake-video"), "video/mp4")},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["file_type"] == "video"


def test_upload_rejects_unknown(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    response = client.post(
        "/api/v1/files",
        files={"file": ("malware.exe", io.BytesIO(b"x"), "application/x-msdownload")},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_upload_rejects_oversized(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    # Set max to tiny value
    from app.core.config import settings
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 0)  # nothing fits
    response = client.post(
        "/api/v1/files",
        files={"file": ("big.pdf", io.BytesIO(b"x" * 1024), "application/pdf")},
        headers=auth_headers,
    )
    assert response.status_code == 413


def test_upload_unauthorized(client):
    response = client.post(
        "/api/v1/files",
        files={"file": ("a.pdf", io.BytesIO(b"x"), "application/pdf")},
    )
    assert response.status_code == 401


def test_list_files_empty(client, auth_headers):
    response = client.get("/api/v1/files", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_files_after_upload(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    client.post(
        "/api/v1/files",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers=auth_headers,
    )
    response = client.get("/api/v1/files", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_file(client, auth_headers, monkeypatch, db_session):
    _patch_processing(monkeypatch)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]

    # Manually set transcript_segments to test parsing
    f = db_session.get(File, fid)
    f.transcript_segments = json.dumps([{"start": 0.0, "end": 5.0, "text": "hi"}])
    db_session.commit()

    response = client.get(f"/api/v1/files/{fid}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == fid
    assert len(body["transcript_segments"]) == 1


def test_get_file_corrupt_segments(client, auth_headers, monkeypatch, db_session):
    """Corrupt transcript JSON yields empty list, not 500."""
    _patch_processing(monkeypatch)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    f = db_session.get(File, fid)
    f.transcript_segments = "not-json"
    db_session.commit()

    response = client.get(f"/api/v1/files/{fid}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["transcript_segments"] == []


def test_get_file_not_owned(client, auth_headers, monkeypatch):
    """Other user's file is 404."""
    _patch_processing(monkeypatch)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]

    # Register a second user
    other = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "password123"},
    )
    other_token = other.json()["access_token"]
    response = client.get(
        f"/api/v1/files/{fid}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert response.status_code == 404


def test_get_nonexistent_file(client, auth_headers):
    response = client.get("/api/v1/files/99999", headers=auth_headers)
    assert response.status_code == 404


def test_delete_file(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    monkeypatch.setattr(files_api, "delete_file_index", lambda fid: None)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    response = client.delete(f"/api/v1/files/{fid}", headers=auth_headers)
    assert response.status_code == 204
    # Confirm gone
    assert client.get(f"/api/v1/files/{fid}", headers=auth_headers).status_code == 404


def test_delete_nonexistent(client, auth_headers):
    response = client.delete("/api/v1/files/99999", headers=auth_headers)
    assert response.status_code == 404


def test_stream_media_pdf_rejected(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    response = client.get(f"/api/v1/files/{fid}/media", headers=auth_headers)
    assert response.status_code == 400


def test_stream_media_success(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("a.mp3", io.BytesIO(b"audio-data"), "audio/mpeg")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    response = client.get(f"/api/v1/files/{fid}/media", headers=auth_headers)
    assert response.status_code == 200
    assert response.content == b"audio-data"


def test_stream_media_missing_on_disk(client, auth_headers, monkeypatch, db_session):
    _patch_processing(monkeypatch)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("a.mp3", io.BytesIO(b"audio"), "audio/mpeg")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    # Wipe the file off disk
    f = db_session.get(File, fid)
    from pathlib import Path
    Path(f.stored_path).unlink()
    response = client.get(f"/api/v1/files/{fid}/media", headers=auth_headers)
    assert response.status_code == 404


def test_stream_media_not_owned(client, auth_headers, monkeypatch):
    _patch_processing(monkeypatch)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("a.mp3", io.BytesIO(b"a"), "audio/mpeg")},
        headers=auth_headers,
    )
    fid = upload.json()["id"]
    other = client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "password123"},
    )
    response = client.get(
        f"/api/v1/files/{fid}/media",
        headers={"Authorization": f"Bearer {other.json()['access_token']}"},
    )
    assert response.status_code == 404


def test_background_task_runs_processing(monkeypatch, db_session):
    """The internal _process_in_background helper opens its own session."""
    called = {"id": None}

    def fake_process(db, fid):
        called["id"] = fid

    monkeypatch.setattr(files_api, "process_file", fake_process)
    files_api._process_in_background(123)
    assert called["id"] == 123
