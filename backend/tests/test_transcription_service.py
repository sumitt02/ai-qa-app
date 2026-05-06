"""Transcription service tests."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services import transcription_service


# --------------------------- format detection ---------------------------

def test_needs_conversion_native_formats(tmp_path):
    """Whisper-native formats don't need conversion."""
    for ext in ["mp3", "m4a", "mp4", "wav", "webm", "ogg", "flac"]:
        f = tmp_path / f"file.{ext}"
        assert transcription_service._needs_conversion(f) is False


def test_needs_conversion_video_formats(tmp_path):
    """Unsupported video formats need conversion."""
    for ext in ["mov", "mkv", "avi", "wmv"]:
        f = tmp_path / f"file.{ext}"
        assert transcription_service._needs_conversion(f) is True


def test_needs_conversion_handles_uppercase(tmp_path):
    """Extensions are case-insensitive."""
    assert transcription_service._needs_conversion(tmp_path / "X.MOV") is True
    assert transcription_service._needs_conversion(tmp_path / "X.MP3") is False


# --------------------------- transcribe (no conversion) ---------------------------

def test_transcribe_media(monkeypatch, tmp_path):
    """Transcription parses verbose_json response correctly."""
    fake_response = MagicMock()
    fake_response.model_dump.return_value = {
        "text": "Hello world this is a test",
        "duration": 12.5,
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "Hello world"},
            {"start": 5.0, "end": 12.5, "text": "this is a test"},
            {"start": 12.5, "end": 13.0, "text": "  "},
        ],
    }

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_response
    monkeypatch.setattr(transcription_service, "get_openai_client", lambda: fake_client)

    fake_media = tmp_path / "audio.mp3"
    fake_media.write_bytes(b"fake-audio-bytes")

    result = transcription_service.transcribe_media(fake_media)
    assert result["text"] == "Hello world this is a test"
    assert result["duration"] == 12.5
    assert len(result["segments"]) == 2
    assert result["segments"][0]["start"] == 0.0


def test_transcribe_media_no_segments(monkeypatch, tmp_path):
    """Missing segments key handled gracefully."""
    fake_response = MagicMock()
    fake_response.model_dump.return_value = {"text": "x", "duration": 1.0}

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_response
    monkeypatch.setattr(transcription_service, "get_openai_client", lambda: fake_client)

    fake_media = tmp_path / "audio.mp3"
    fake_media.write_bytes(b"x")

    result = transcription_service.transcribe_media(fake_media)
    assert result["segments"] == []


def test_transcribe_media_response_without_model_dump(monkeypatch, tmp_path):
    """Response without model_dump uses dict()."""
    class FakeResponse(dict):
        pass

    response = FakeResponse(text="ok", duration=2.0, segments=[])

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = response
    monkeypatch.setattr(transcription_service, "get_openai_client", lambda: fake_client)

    fake_media = tmp_path / "a.mp3"
    fake_media.write_bytes(b"x")

    result = transcription_service.transcribe_media(fake_media)
    assert result["text"] == "ok"


def test_get_openai_client():
    """The factory returns an OpenAI instance."""
    client = transcription_service.get_openai_client()
    assert client is not None


# --------------------------- conversion path ---------------------------

def test_transcribe_media_converts_unsupported_format(monkeypatch, tmp_path):
    """For .mov files, we call _convert_to_mp3 before sending to Whisper."""
    src_mov = tmp_path / "video.mov"
    src_mov.write_bytes(b"fake-mov-bytes")

    converted_mp3 = tmp_path / "converted.mp3"
    converted_mp3.write_bytes(b"fake-mp3-bytes")

    convert_called = {"called_with": None, "cleanup": False}

    def fake_convert(p):
        convert_called["called_with"] = Path(p)
        return converted_mp3

    # Track if the converted file gets opened (proxy for "was sent to whisper")
    monkeypatch.setattr(transcription_service, "_convert_to_mp3", fake_convert)

    fake_response = MagicMock()
    fake_response.model_dump.return_value = {"text": "ok", "duration": 1.0, "segments": []}
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = fake_response
    monkeypatch.setattr(transcription_service, "get_openai_client", lambda: fake_client)

    result = transcription_service.transcribe_media(src_mov)

    assert convert_called["called_with"] == src_mov
    # Converted file should be cleaned up after transcription
    assert not converted_mp3.exists()
    assert result["text"] == "ok"


def test_transcribe_media_cleans_up_on_whisper_failure(monkeypatch, tmp_path):
    """If Whisper raises, the converted temp file is still deleted."""
    src_mov = tmp_path / "video.mov"
    src_mov.write_bytes(b"fake")

    converted_mp3 = tmp_path / "leak_check.mp3"
    converted_mp3.write_bytes(b"fake-mp3")

    monkeypatch.setattr(transcription_service, "_convert_to_mp3", lambda p: converted_mp3)

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.side_effect = RuntimeError("Whisper down")
    monkeypatch.setattr(transcription_service, "get_openai_client", lambda: fake_client)

    with pytest.raises(RuntimeError):
        transcription_service.transcribe_media(src_mov)

    assert not converted_mp3.exists()


# --------------------------- _convert_to_mp3 / ffmpeg ---------------------------

def test_convert_to_mp3_no_ffmpeg(monkeypatch, tmp_path):
    """When ffmpeg is missing, we raise a clear error."""
    monkeypatch.setattr(transcription_service, "_has_ffmpeg", lambda: False)
    src = tmp_path / "x.mov"
    src.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="ffmpeg not available"):
        transcription_service._convert_to_mp3(src)


def test_convert_to_mp3_success(monkeypatch, tmp_path):
    """Successful ffmpeg run produces an output file."""
    monkeypatch.setattr(transcription_service, "_has_ffmpeg", lambda: True)

    def fake_run(cmd, capture_output, text, timeout):
        # Pull the output path from the cmd (last arg)
        out_path = Path(cmd[-1])
        out_path.write_bytes(b"fake mp3 content")
        return MagicMock(returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    src = tmp_path / "video.mov"
    src.write_bytes(b"fake-mov")

    out = transcription_service._convert_to_mp3(src)
    assert out.exists()
    assert out.suffix == ".mp3"
    assert out.read_bytes() == b"fake mp3 content"
    out.unlink()


def test_convert_to_mp3_ffmpeg_failure(monkeypatch, tmp_path):
    """Non-zero ffmpeg return code raises RuntimeError with stderr."""
    monkeypatch.setattr(transcription_service, "_has_ffmpeg", lambda: True)

    def fake_run(cmd, capture_output, text, timeout):
        return MagicMock(returncode=1, stderr="line1\nline2\nbad codec\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    src = tmp_path / "x.mov"
    src.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        transcription_service._convert_to_mp3(src)


def test_convert_to_mp3_timeout(monkeypatch, tmp_path):
    """Subprocess timeout raises RuntimeError."""
    monkeypatch.setattr(transcription_service, "_has_ffmpeg", lambda: True)

    def fake_run(cmd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    src = tmp_path / "x.mov"
    src.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="timed out"):
        transcription_service._convert_to_mp3(src)


def test_convert_to_mp3_empty_output(monkeypatch, tmp_path):
    """If ffmpeg succeeds but produces no/empty output, raise."""
    monkeypatch.setattr(transcription_service, "_has_ffmpeg", lambda: True)

    def fake_run(cmd, capture_output, text, timeout):
        # Don't write any output file
        return MagicMock(returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    src = tmp_path / "x.mov"
    src.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="empty output file"):
        transcription_service._convert_to_mp3(src)


def test_has_ffmpeg_uses_shutil_which(monkeypatch):
    """_has_ffmpeg returns True when shutil.which finds it."""
    import shutil as shutil_mod
    monkeypatch.setattr(shutil_mod, "which", lambda name: "/usr/bin/ffmpeg")
    assert transcription_service._has_ffmpeg() is True

    monkeypatch.setattr(shutil_mod, "which", lambda name: None)
    assert transcription_service._has_ffmpeg() is False