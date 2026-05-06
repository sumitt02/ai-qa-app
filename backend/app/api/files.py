"""File upload, management, and media streaming routes."""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, BackgroundTasks, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db, SessionLocal
from app.models.file import File, FileType, FileStatus
from app.models.user import User
from app.schemas.file import FileOut, FileDetail, TranscriptSegment
from app.services.processing_service import process_file
from app.services.vector_service import delete_file_index
from app.services.redis_service import check_rate_limit

router = APIRouter(prefix="/files", tags=["files"])


# Map content-types and extensions to FileType
PDF_TYPES = {"application/pdf"}
AUDIO_TYPES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/mp4", "audio/m4a", "audio/x-m4a", "audio/webm", "audio/ogg"}
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/mpeg"}

PDF_EXTS = {".pdf"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".webm", ".ogg"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".mpeg", ".mpg"}


def detect_file_type(filename: str, content_type: str) -> FileType | None:
    ext = Path(filename).suffix.lower()
    ct = (content_type or "").lower()
    if ct in PDF_TYPES or ext in PDF_EXTS:
        return FileType.PDF
    if ct in AUDIO_TYPES or ext in AUDIO_EXTS:
        return FileType.AUDIO
    if ct in VIDEO_TYPES or ext in VIDEO_EXTS:
        return FileType.VIDEO
    return None


def _process_in_background(file_id: int) -> None:
    """Run processing with its own DB session."""
    db = SessionLocal()
    try:
        process_file(db, file_id)
    finally:
        db.close()


@router.post("", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileOut:
    """Upload a PDF, audio, or video file."""
    check_rate_limit(
        bucket="upload",
        identity=current_user.id,
        limit=settings.RATE_LIMIT_UPLOAD_PER_MINUTE,
    )

    file_type = detect_file_type(file.filename or "", file.content_type or "")
    if file_type is None:
        raise HTTPException(status_code=400, detail="Unsupported file type. Allowed: PDF, audio, video.")

    # Save to disk
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = upload_dir / stored_name

    size = 0
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    with stored_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                out.close()
                stored_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File too large (max {settings.MAX_UPLOAD_SIZE_MB} MB)")
            out.write(chunk)

    db_file = File(
        owner_id=current_user.id,
        filename=file.filename or stored_name,
        stored_path=str(stored_path),
        file_type=file_type,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        status=FileStatus.PENDING,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    background_tasks.add_task(_process_in_background, db_file.id)
    return FileOut.model_validate(db_file)


@router.get("", response_model=list[FileOut])
def list_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FileOut]:
    """List the current user's files."""
    files = db.scalars(
        select(File).where(File.owner_id == current_user.id).order_by(File.created_at.desc())
    ).all()
    return [FileOut.model_validate(f) for f in files]


@router.get("/{file_id}", response_model=FileDetail)
def get_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileDetail:
    """Get a single file with its transcript segments."""
    f = db.get(File, file_id)
    if f is None or f.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="File not found")
    segments: list[TranscriptSegment] = []
    if f.transcript_segments:
        try:
            raw = json.loads(f.transcript_segments)
            segments = [TranscriptSegment(**s) for s in raw]
        except (json.JSONDecodeError, TypeError):
            segments = []
    base = FileOut.model_validate(f).model_dump()
    return FileDetail(**base, transcript_segments=segments)


@router.delete("/{file_id}")
def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete a file and its index."""
    f = db.get(File, file_id)
    if f is None or f.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="File not found")

    # Delete physical file
    try:
        Path(f.stored_path).unlink(missing_ok=True)
    except Exception:
        pass

    delete_file_index(file_id)
    db.delete(f)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{file_id}/media")
def stream_media(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream the raw audio/video file (used by frontend <audio>/<video>)."""
    f = db.get(File, file_id)
    if f is None or f.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="File not found")
    if f.file_type == FileType.PDF:
        raise HTTPException(status_code=400, detail="File is a PDF, not media")
    path = Path(f.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path=str(path), media_type=f.mime_type, filename=f.filename)
