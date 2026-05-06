"""Processing pipeline tests."""
import json
from unittest.mock import MagicMock

import pytest

from app.models.file import File, FileStatus, FileType
from app.models.user import User
from app.services import processing_service


def _make_user(db) -> User:
    user = User(email="proc@test.com", hashed_password="x", full_name="P")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_file(db, user, file_type, path="/fake/path"):
    f = File(
        owner_id=user.id,
        filename=f"test.{file_type.value}",
        stored_path=path,
        file_type=file_type,
        mime_type="application/octet-stream",
        size_bytes=100,
        status=FileStatus.PENDING,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def test_process_pdf_success(db_session, monkeypatch):
    user = _make_user(db_session)
    file = _make_file(db_session, user, FileType.PDF)

    monkeypatch.setattr(
        processing_service, "extract_pdf_text",
        lambda p: ("page1 content", [{"page": 1, "text": "page1 content"}]),
    )
    monkeypatch.setattr(processing_service, "index_pdf", lambda **kw: 1)
    monkeypatch.setattr(processing_service, "summarize_text", lambda t: "summary")

    processing_service.process_file(db_session, file.id)
    db_session.refresh(file)
    assert file.status == FileStatus.READY
    assert file.summary == "summary"
    assert file.extracted_text == "page1 content"


def test_process_audio_success(db_session, monkeypatch):
    user = _make_user(db_session)
    file = _make_file(db_session, user, FileType.AUDIO)

    monkeypatch.setattr(
        processing_service, "transcribe_media",
        lambda p: {
            "text": "spoken words",
            "duration": 30.0,
            "segments": [{"start": 0.0, "end": 30.0, "text": "spoken words"}],
        },
    )
    monkeypatch.setattr(processing_service, "index_media", lambda **kw: 1)
    monkeypatch.setattr(processing_service, "summarize_text", lambda t: "audio summary")

    processing_service.process_file(db_session, file.id)
    db_session.refresh(file)
    assert file.status == FileStatus.READY
    assert file.duration_seconds == 30.0
    assert file.summary == "audio summary"
    parsed = json.loads(file.transcript_segments)
    assert parsed[0]["text"] == "spoken words"


def test_process_video_success(db_session, monkeypatch):
    user = _make_user(db_session)
    file = _make_file(db_session, user, FileType.VIDEO)

    monkeypatch.setattr(
        processing_service, "transcribe_media",
        lambda p: {"text": "v", "duration": 5.0, "segments": []},
    )
    monkeypatch.setattr(processing_service, "index_media", lambda **kw: 0)
    monkeypatch.setattr(processing_service, "summarize_text", lambda t: "video summary")

    processing_service.process_file(db_session, file.id)
    db_session.refresh(file)
    assert file.status == FileStatus.READY


def test_process_failure_marks_failed(db_session, monkeypatch):
    user = _make_user(db_session)
    file = _make_file(db_session, user, FileType.PDF)

    def boom(*a, **kw):
        raise RuntimeError("PDF parse failed")

    monkeypatch.setattr(processing_service, "extract_pdf_text", boom)

    processing_service.process_file(db_session, file.id)
    db_session.refresh(file)
    assert file.status == FileStatus.FAILED
    assert "PDF parse failed" in (file.error_message or "")


def test_process_summarization_failure_does_not_fail_whole(db_session, monkeypatch):
    """If summarization fails, file is still READY."""
    user = _make_user(db_session)
    file = _make_file(db_session, user, FileType.PDF)

    monkeypatch.setattr(
        processing_service, "extract_pdf_text",
        lambda p: ("text", [{"page": 1, "text": "text"}]),
    )
    monkeypatch.setattr(processing_service, "index_pdf", lambda **kw: 1)

    def boom_summary(*a, **kw):
        raise RuntimeError("openai down")

    monkeypatch.setattr(processing_service, "summarize_text", boom_summary)

    processing_service.process_file(db_session, file.id)
    db_session.refresh(file)
    assert file.status == FileStatus.READY
    assert file.summary is None


def test_process_missing_file(db_session):
    """Calling with non-existent id is a noop."""
    processing_service.process_file(db_session, 99999)


def test_process_no_extracted_text_skips_summary(db_session, monkeypatch):
    """If extraction yields empty text, summary stays None."""
    user = _make_user(db_session)
    file = _make_file(db_session, user, FileType.PDF)

    monkeypatch.setattr(processing_service, "extract_pdf_text", lambda p: ("", []))
    monkeypatch.setattr(processing_service, "index_pdf", lambda **kw: 0)
    summarize_called = {"yes": False}

    def fake_summarize(*a, **kw):
        summarize_called["yes"] = True
        return "x"

    monkeypatch.setattr(processing_service, "summarize_text", fake_summarize)

    processing_service.process_file(db_session, file.id)
    db_session.refresh(file)
    assert file.status == FileStatus.READY
    assert summarize_called["yes"] is False
