"""Vector store using ChromaDB. Stores text chunks per-file with metadata."""
from __future__ import annotations
import json
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.services.transcription_service import get_openai_client


# Singleton client
_client: chromadb.ClientAPI | None = None


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_DIR,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
    return _client


def reset_client() -> None:
    """For tests."""
    global _client
    _client = None


def _collection_name(file_id: int) -> str:
    return f"file_{file_id}"


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Naive but effective character-based chunker with overlap."""
    if not text:
        return []
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate OpenAI embeddings for a list of texts, with Redis caching.

    Already-cached texts are pulled from Redis; only cache misses hit OpenAI.
    """
    if not texts:
        return []

    from app.services import redis_service  # local import to avoid cycles

    model = settings.OPENAI_EMBEDDING_MODEL
    results: list[list[float] | None] = [None] * len(texts)
    miss_indices: list[int] = []
    miss_texts: list[str] = []

    # First pass: try cache
    for i, t in enumerate(texts):
        cached = redis_service.get_cached_embedding(model, t)
        if cached is not None:
            results[i] = cached
        else:
            miss_indices.append(i)
            miss_texts.append(t)

    # Second pass: only embed misses
    if miss_texts:
        client = get_openai_client()
        response = client.embeddings.create(model=model, input=miss_texts)
        for j, item in enumerate(response.data):
            idx = miss_indices[j]
            vector = list(item.embedding)
            results[idx] = vector
            redis_service.set_cached_embedding(model, miss_texts[j], vector)

    # Type narrow: every slot is filled
    return [r for r in results if r is not None]


def index_pdf(file_id: int, pages: list[dict]) -> int:
    """Index PDF pages into Chroma. Returns number of chunks."""
    client = get_chroma_client()
    name = _collection_name(file_id)
    # Replace if exists
    try:
        client.delete_collection(name)
    except Exception:
        pass
    collection = client.create_collection(name=name)

    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    ids: list[str] = []

    counter = 0
    for page in pages:
        page_num = page["page"]
        for chunk in chunk_text(page["text"]):
            documents.append(chunk)
            metadatas.append({"type": "pdf", "page": page_num, "file_id": file_id})
            ids.append(f"{file_id}_p{page_num}_{counter}")
            counter += 1

    if not documents:
        return 0

    embeddings = embed_texts(documents)
    collection.add(
        ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas
    )
    return len(documents)


def index_media(file_id: int, segments: list[dict]) -> int:
    """Index audio/video transcript segments into Chroma."""
    client = get_chroma_client()
    name = _collection_name(file_id)
    try:
        client.delete_collection(name)
    except Exception:
        pass
    collection = client.create_collection(name=name)

    # Group segments into ~30s windows for richer context
    windows: list[dict] = []
    current_text: list[str] = []
    current_start = 0.0
    current_end = 0.0
    for seg in segments:
        if not current_text:
            current_start = seg["start"]
        current_text.append(seg["text"])
        current_end = seg["end"]
        if current_end - current_start >= 30.0:
            windows.append(
                {"start": current_start, "end": current_end, "text": " ".join(current_text)}
            )
            current_text = []
    if current_text:
        windows.append(
            {"start": current_start, "end": current_end, "text": " ".join(current_text)}
        )

    if not windows:
        return 0

    documents = [w["text"] for w in windows]
    metadatas = [
        {"type": "media", "start": w["start"], "end": w["end"], "file_id": file_id}
        for w in windows
    ]
    ids = [f"{file_id}_w{i}" for i in range(len(windows))]

    embeddings = embed_texts(documents)
    collection.add(
        ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas
    )
    return len(documents)


def search(file_id: int, query: str, k: int = 4) -> list[dict]:
    """Semantic search within a file's collection."""
    client = get_chroma_client()
    name = _collection_name(file_id)
    try:
        collection = client.get_collection(name)
    except Exception:
        return []

    query_emb = embed_texts([query])[0]
    result = collection.query(query_embeddings=[query_emb], n_results=k)

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    return [
        {"text": d, "metadata": m, "distance": dist}
        for d, m, dist in zip(docs, metas, distances)
    ]


def delete_file_index(file_id: int) -> None:
    """Remove a file's collection."""
    client = get_chroma_client()
    try:
        client.delete_collection(_collection_name(file_id))
    except Exception:
        pass
