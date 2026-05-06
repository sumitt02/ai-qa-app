"""File schemas."""
from datetime import datetime
from pydantic import BaseModel
from app.models.file import FileType, FileStatus


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class FileOut(BaseModel):
    id: int
    filename: str
    file_type: FileType
    mime_type: str
    size_bytes: int
    status: FileStatus
    error_message: str | None = None
    duration_seconds: float | None = None
    summary: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class FileDetail(FileOut):
    """File with transcript segments parsed."""
    transcript_segments: list[TranscriptSegment] = []
