"""Audio/video transcription using OpenAI Whisper.

Whisper accepts: flac, m4a, mp3, mp4, mpeg, mpga, oga, ogg, wav, webm
For unsupported formats (e.g. .mov, .mkv), we use ffmpeg to extract audio as .mp3 first.
"""
from __future__ import annotations
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


# Formats Whisper accepts directly (lowercase, no leading dot)
WHISPER_NATIVE_FORMATS = {
    "flac", "m4a", "mp3", "mp4", "mpeg", "mpga", "oga", "ogg", "wav", "webm"
}


def get_openai_client() -> OpenAI:
    """Build an OpenAI client. Separated so tests can mock it."""
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _has_ffmpeg() -> bool:
    """Check if ffmpeg is available on the system."""
    return shutil.which("ffmpeg") is not None


def _convert_to_mp3(src: Path) -> Path:
    """
    Use ffmpeg to extract audio from src into a temporary .mp3 file.
    Returns the path to the converted file (caller is responsible for cleanup).
    Raises RuntimeError if ffmpeg is missing or conversion fails.
    """
    if not _has_ffmpeg():
        raise RuntimeError(
            "ffmpeg not available; cannot convert this file format. "
            "Install ffmpeg or upload a Whisper-supported format "
            "(mp3, m4a, mp4, wav, webm, flac, ogg, mpeg)."
        )

    out_fd, out_path_str = tempfile.mkstemp(suffix=".mp3", prefix="whisper_")
    os.close(out_fd)
    out_path = Path(out_path_str)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(src),
        "-vn",
        "-acodec", "libmp3lame",
        "-ab", "128k",
        "-ar", "44100",
        str(out_path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
    except subprocess.TimeoutExpired:
        out_path.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg conversion timed out (>10 min)")

    if result.returncode != 0:
        out_path.unlink(missing_ok=True)
        stderr_tail = "\n".join((result.stderr or "").splitlines()[-5:])
        raise RuntimeError(f"ffmpeg failed: {stderr_tail or 'unknown error'}")

    if not out_path.exists() or out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg produced an empty output file")

    return out_path


def _needs_conversion(file_path: Path) -> bool:
    """True if Whisper won't accept this file's extension directly."""
    ext = file_path.suffix.lower().lstrip(".")
    return ext not in WHISPER_NATIVE_FORMATS


def transcribe_media(file_path: str | Path) -> dict[str, Any]:
    """
    Transcribe an audio/video file with Whisper.

    Automatically converts unsupported video containers (e.g. .mov, .mkv)
    to .mp3 via ffmpeg before sending to Whisper.

    Returns a dict with:
        - text: full transcript
        - duration: seconds (float)
        - segments: list of {start, end, text}
    """
    src = Path(file_path)
    converted: Path | None = None

    try:
        if _needs_conversion(src):
            logger.info("Converting %s to mp3 for Whisper", src.name)
            converted = _convert_to_mp3(src)
            target = converted
        else:
            target = src

        client = get_openai_client()
        with target.open("rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=settings.OPENAI_TRANSCRIPTION_MODEL,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
    finally:
        if converted is not None:
            converted.unlink(missing_ok=True)

    data = response.model_dump() if hasattr(response, "model_dump") else dict(response)

    segments_raw = data.get("segments") or []
    segments = [
        {
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "text": (seg.get("text") or "").strip(),
        }
        for seg in segments_raw
        if (seg.get("text") or "").strip()
    ]

    return {
        "text": data.get("text", "") or "",
        "duration": float(data.get("duration", 0.0) or 0.0),
        "segments": segments,
    }