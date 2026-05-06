"""Chat schemas."""
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.chat import MessageRole


class Citation(BaseModel):
    """Citation pointing to a chunk in a source file."""
    file_id: int
    filename: str
    snippet: str
    # For audio/video, timestamp range
    start: float | None = None
    end: float | None = None
    # For PDF, page number if available
    page: int | None = None


class MessageOut(BaseModel):
    id: int
    role: MessageRole
    content: str
    citations: list[Citation] = []
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionCreate(BaseModel):
    file_id: int | None = None
    title: str = "New chat"


class ChatSessionOut(BaseModel):
    id: int
    title: str
    file_id: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionDetail(ChatSessionOut):
    messages: list[MessageOut] = []


class AskRequest(BaseModel):
    """Ask a question, optionally scoped to a file."""
    question: str = Field(min_length=1, max_length=4000)
    file_id: int | None = None
    session_id: int | None = None
