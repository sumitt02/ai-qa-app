"""LLM service: RAG-based question answering and summarization."""
from __future__ import annotations
import json
from typing import AsyncGenerator, Iterable

from app.core.config import settings
from app.services.transcription_service import get_openai_client
from app.services.vector_service import search


SYSTEM_PROMPT = """You are a precise assistant that answers questions strictly from the provided context.

Rules:
- Only use information from the CONTEXT below. If the answer is not in the context, say you don't know based on the document.
- Be concise but complete. Quote short phrases from the context when helpful.
- Never invent timestamps, page numbers, or facts.
"""


def _format_context(chunks: list[dict]) -> str:
    """Format retrieved chunks for the LLM."""
    lines: list[str] = []
    for i, c in enumerate(chunks, start=1):
        meta = c.get("metadata", {}) or {}
        if meta.get("type") == "media":
            tag = f"[chunk {i}, {meta.get('start', 0):.1f}s-{meta.get('end', 0):.1f}s]"
        elif meta.get("type") == "pdf":
            tag = f"[chunk {i}, page {meta.get('page', '?')}]"
        else:
            tag = f"[chunk {i}]"
        lines.append(f"{tag}\n{c['text']}")
    return "\n\n".join(lines)


def build_citations(chunks: list[dict], filename: str, file_id: int) -> list[dict]:
    """Build citation objects from retrieved chunks."""
    citations: list[dict] = []
    for c in chunks:
        meta = c.get("metadata", {}) or {}
        snippet = c["text"][:200] + ("..." if len(c["text"]) > 200 else "")
        citation = {
            "file_id": file_id,
            "filename": filename,
            "snippet": snippet,
            "start": meta.get("start"),
            "end": meta.get("end"),
            "page": meta.get("page"),
        }
        citations.append(citation)
    return citations


def answer_question(
    question: str,
    file_id: int,
    filename: str,
    history: list[dict] | None = None,
    k: int = 4,
) -> tuple[str, list[dict]]:
    """
    Non-streaming RAG answer.
    Returns (answer_text, citations).
    """
    chunks = search(file_id=file_id, query=question, k=k)
    context = _format_context(chunks) if chunks else "(no relevant context found)"
    citations = build_citations(chunks, filename, file_id)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append(
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"}
    )

    client = get_openai_client()
    response = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=messages,
        temperature=0.2,
    )
    answer = response.choices[0].message.content or ""
    return answer, citations


def answer_question_stream(
    question: str,
    file_id: int,
    filename: str,
    history: list[dict] | None = None,
    k: int = 4,
) -> Iterable[str]:
    """
    Streaming RAG. Yields SSE-formatted lines:
        event: token  -> data: <text>
        event: citations -> data: <json>
        event: done -> data: ok
    """
    chunks = search(file_id=file_id, query=question, k=k)
    context = _format_context(chunks) if chunks else "(no relevant context found)"
    citations = build_citations(chunks, filename, file_id)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append(
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"}
    )

    client = get_openai_client()
    stream = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=messages,
        temperature=0.2,
        stream=True,
    )

    # Send citations first so the UI can show sources immediately
    yield f"event: citations\ndata: {json.dumps(citations)}\n\n"

    for chunk in stream:
        try:
            delta = chunk.choices[0].delta.content
        except (AttributeError, IndexError):
            delta = None
        if delta:
            # SSE: escape newlines within data
            safe = delta.replace("\n", "\\n")
            yield f"event: token\ndata: {safe}\n\n"

    yield "event: done\ndata: ok\n\n"


def summarize_text(text: str, max_chars: int = 12000) -> str:
    """Summarize text. Truncates very long inputs."""
    if not text or not text.strip():
        return ""
    truncated = text[:max_chars]
    client = get_openai_client()
    response = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "Write a clear, concise summary in 4-7 sentences. Focus on key points and main takeaways.",
            },
            {"role": "user", "content": truncated},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content or ""
