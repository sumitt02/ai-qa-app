"""Chat routes: ask questions, manage sessions, stream responses."""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.chat import ChatSession, Message, MessageRole
from app.models.file import File, FileStatus
from app.models.user import User
from app.schemas.chat import (
    AskRequest, ChatSessionCreate, ChatSessionOut, ChatSessionDetail, MessageOut, Citation
)
from app.services.llm_service import answer_question, answer_question_stream
from app.services.redis_service import check_rate_limit

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_or_create_session(
    db: Session, user_id: int, session_id: int | None, file_id: int | None, title_hint: str
) -> ChatSession:
    """Helper: load or create a session."""
    if session_id is not None:
        sess = db.get(ChatSession, session_id)
        if sess is None or sess.user_id != user_id:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return sess
    sess = ChatSession(user_id=user_id, file_id=file_id, title=title_hint[:200] or "New chat")
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def _check_file(db: Session, file_id: int, user_id: int) -> File:
    f = db.get(File, file_id)
    if f is None or f.owner_id != user_id:
        raise HTTPException(status_code=404, detail="File not found")
    if f.status != FileStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=f"File is not ready for questions (status={f.status.value})",
        )
    return f


def _load_history(db: Session, session_id: int, limit: int = 10) -> list[dict]:
    """Load recent message history for the session."""
    msgs = db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    msgs = list(reversed(msgs))
    return [{"role": m.role.value, "content": m.content} for m in msgs]


@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionOut:
    """Create a new chat session."""
    if payload.file_id is not None:
        _check_file(db, payload.file_id, current_user.id)
    sess = ChatSession(user_id=current_user.id, file_id=payload.file_id, title=payload.title)
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return ChatSessionOut.model_validate(sess)


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatSessionOut]:
    sessions = db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    ).all()
    return [ChatSessionOut.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionDetail:
    sess = db.get(ChatSession, session_id)
    if sess is None or sess.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    messages = []
    for m in sess.messages:
        cits = []
        if m.citations:
            try:
                cits = [Citation(**c) for c in json.loads(m.citations)]
            except (json.JSONDecodeError, TypeError):
                cits = []
        messages.append(
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                citations=cits,
                created_at=m.created_at,
            )
        )
    return ChatSessionDetail(
        id=sess.id,
        title=sess.title,
        file_id=sess.file_id,
        created_at=sess.created_at,
        messages=messages,
    )


@router.post("/ask", response_model=MessageOut)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    """Ask a question and get a complete (non-streaming) answer."""
    check_rate_limit(
        bucket="ask",
        identity=current_user.id,
        limit=settings.RATE_LIMIT_ASK_PER_MINUTE,
    )

    if payload.file_id is None:
        raise HTTPException(status_code=400, detail="file_id is required")

    file = _check_file(db, payload.file_id, current_user.id)
    sess = _get_or_create_session(
        db, current_user.id, payload.session_id, payload.file_id, payload.question
    )

    # Save user message
    user_msg = Message(session_id=sess.id, role=MessageRole.USER, content=payload.question)
    db.add(user_msg)
    db.commit()

    history = _load_history(db, sess.id, limit=10)[:-1]  # exclude the just-added user msg
    answer, citations = answer_question(
        question=payload.question,
        file_id=file.id,
        filename=file.filename,
        history=history,
    )

    asst_msg = Message(
        session_id=sess.id,
        role=MessageRole.ASSISTANT,
        content=answer,
        citations=json.dumps(citations),
    )
    db.add(asst_msg)
    db.commit()
    db.refresh(asst_msg)

    return MessageOut(
        id=asst_msg.id,
        role=asst_msg.role,
        content=asst_msg.content,
        citations=[Citation(**c) for c in citations],
        created_at=asst_msg.created_at,
    )


@router.post("/ask/stream")
def ask_stream(
    payload: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Ask a question with Server-Sent Events streaming response."""
    check_rate_limit(
        bucket="ask",
        identity=current_user.id,
        limit=settings.RATE_LIMIT_ASK_PER_MINUTE,
    )

    if payload.file_id is None:
        raise HTTPException(status_code=400, detail="file_id is required")

    file = _check_file(db, payload.file_id, current_user.id)
    sess = _get_or_create_session(
        db, current_user.id, payload.session_id, payload.file_id, payload.question
    )
    user_msg = Message(session_id=sess.id, role=MessageRole.USER, content=payload.question)
    db.add(user_msg)
    db.commit()

    history = _load_history(db, sess.id, limit=10)[:-1]

    # Capture primitives — generator runs after the request handler returns
    # and SQLAlchemy instances may be detached.
    file_id_val = file.id
    file_name_val = file.filename
    sess_id_val = sess.id

    def event_generator():
        # Tell the client which session this belongs to
        yield f"event: session\ndata: {json.dumps({'session_id': sess_id_val})}\n\n"

        full_answer_parts: list[str] = []
        citations_data: list[dict] = []

        for evt in answer_question_stream(
            question=payload.question,
            file_id=file_id_val,
            filename=file_name_val,
            history=history,
        ):
            yield evt
            # Reconstruct full answer for DB
            if evt.startswith("event: token\n"):
                # Pull data line: "data: <text>\n\n"
                data_line = evt.split("data: ", 1)[1].rstrip("\n")
                full_answer_parts.append(data_line.replace("\\n", "\n"))
            elif evt.startswith("event: citations\n"):
                try:
                    json_str = evt.split("data: ", 1)[1].rstrip("\n")
                    citations_data = json.loads(json_str)
                except (IndexError, json.JSONDecodeError):
                    citations_data = []

        # Persist assistant message — open a fresh session since `db` may be closed
        from app.core.database import SessionLocal
        full_answer = "".join(full_answer_parts)
        persist_db = SessionLocal()
        try:
            asst_msg = Message(
                session_id=sess_id_val,
                role=MessageRole.ASSISTANT,
                content=full_answer,
                citations=json.dumps(citations_data),
            )
            persist_db.add(asst_msg)
            persist_db.commit()
        finally:
            persist_db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
