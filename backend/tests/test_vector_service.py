"""Vector service tests."""
from unittest.mock import MagicMock, patch

import pytest

from app.services import vector_service


@pytest.fixture(autouse=True)
def isolate_chroma(tmp_path, monkeypatch):
    """Use a fresh per-test Chroma directory."""
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    # Reset any cached client
    vector_service.reset_client()
    # Patch settings cache too
    from app.core import config as cfg
    cfg.get_settings.cache_clear()
    yield
    vector_service.reset_client()


def _fake_embeddings(texts):
    """Return deterministic 4-d embeddings from text length."""
    return [[float(len(t) % 7), 1.0, 2.0, float(i)] for i, t in enumerate(texts)]


@pytest.fixture
def mock_embed(monkeypatch):
    monkeypatch.setattr(vector_service, "embed_texts", _fake_embeddings)


def test_chunk_text_short():
    result = vector_service.chunk_text("hello", chunk_size=100)
    assert result == ["hello"]


def test_chunk_text_long():
    text = "a" * 1000
    chunks = vector_service.chunk_text(text, chunk_size=200, overlap=50)
    assert len(chunks) > 1
    # Check overlap
    assert chunks[0][-50:] == chunks[1][:50]


def test_chunk_text_empty():
    assert vector_service.chunk_text("") == []
    assert vector_service.chunk_text("   ") == []


def test_index_pdf_empty(mock_embed):
    """Empty pages list returns 0."""
    n = vector_service.index_pdf(file_id=1, pages=[])
    assert n == 0


def test_index_pdf_creates_collection(mock_embed):
    pages = [
        {"page": 1, "text": "First page about cats and dogs."},
        {"page": 2, "text": "Second page about machine learning."},
    ]
    n = vector_service.index_pdf(file_id=1, pages=pages)
    assert n == 2


def test_index_pdf_replaces_existing(mock_embed):
    pages_v1 = [{"page": 1, "text": "version one"}]
    pages_v2 = [{"page": 1, "text": "version two replacement"}]
    n1 = vector_service.index_pdf(file_id=2, pages=pages_v1)
    n2 = vector_service.index_pdf(file_id=2, pages=pages_v2)
    assert n1 == 1
    assert n2 == 1


def test_index_media_groups_segments(mock_embed):
    segments = [
        {"start": 0.0, "end": 10.0, "text": "first part"},
        {"start": 10.0, "end": 20.0, "text": "second part"},
        {"start": 20.0, "end": 35.0, "text": "third part crosses 30s"},
        {"start": 35.0, "end": 40.0, "text": "fourth part"},
    ]
    n = vector_service.index_media(file_id=3, segments=segments)
    assert n >= 1


def test_index_media_empty(mock_embed):
    assert vector_service.index_media(file_id=4, segments=[]) == 0


def test_search_returns_results(mock_embed):
    pages = [
        {"page": 1, "text": "Photosynthesis converts light to energy in plants."},
        {"page": 2, "text": "Mitochondria are the powerhouse of the cell."},
    ]
    vector_service.index_pdf(file_id=10, pages=pages)
    results = vector_service.search(file_id=10, query="energy", k=2)
    assert isinstance(results, list)
    assert len(results) > 0
    assert "text" in results[0]
    assert "metadata" in results[0]


def test_search_missing_collection(mock_embed):
    results = vector_service.search(file_id=99999, query="anything", k=2)
    assert results == []


def test_delete_file_index(mock_embed):
    pages = [{"page": 1, "text": "to be deleted"}]
    vector_service.index_pdf(file_id=11, pages=pages)
    vector_service.delete_file_index(file_id=11)
    results = vector_service.search(file_id=11, query="anything")
    assert results == []


def test_delete_nonexistent(mock_embed):
    """Deleting a nonexistent index doesn't raise."""
    vector_service.delete_file_index(file_id=88888)


def test_embed_texts_empty():
    """Empty list returns [] without API call."""
    assert vector_service.embed_texts([]) == []


def test_embed_texts_calls_openai(monkeypatch):
    """When given texts, embed_texts hits the OpenAI client."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.data = [
        MagicMock(embedding=[0.1, 0.2, 0.3]),
        MagicMock(embedding=[0.4, 0.5, 0.6]),
    ]
    fake_client.embeddings.create.return_value = fake_response
    monkeypatch.setattr(vector_service, "get_openai_client", lambda: fake_client)
    # Force cache miss for both
    from app.services import redis_service
    monkeypatch.setattr(redis_service, "get_cached_embedding", lambda m, t: None)
    monkeypatch.setattr(redis_service, "set_cached_embedding", lambda m, t, v: None)

    out = vector_service.embed_texts(["a", "b"])
    assert out == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    fake_client.embeddings.create.assert_called_once()


def test_embed_texts_uses_cache(monkeypatch):
    """Cache hits skip the OpenAI call."""
    from app.services import redis_service

    cache: dict[str, list[float]] = {
        "alpha": [9.0, 9.0],
        "beta": [8.0, 8.0],
    }
    monkeypatch.setattr(
        redis_service, "get_cached_embedding",
        lambda model, text: cache.get(text),
    )
    set_calls: list[tuple] = []
    monkeypatch.setattr(
        redis_service, "set_cached_embedding",
        lambda m, t, v: set_calls.append((t, v)),
    )

    fake_client = MagicMock()
    monkeypatch.setattr(vector_service, "get_openai_client", lambda: fake_client)

    out = vector_service.embed_texts(["alpha", "beta"])
    assert out == [[9.0, 9.0], [8.0, 8.0]]
    fake_client.embeddings.create.assert_not_called()
    assert set_calls == []  # nothing new to cache


def test_embed_texts_partial_cache(monkeypatch):
    """Mix of hits and misses: only misses go to OpenAI; misses get cached."""
    from app.services import redis_service

    cache: dict[str, list[float]] = {"hit": [1.0]}
    monkeypatch.setattr(
        redis_service, "get_cached_embedding",
        lambda model, text: cache.get(text),
    )
    set_calls: list[tuple] = []
    monkeypatch.setattr(
        redis_service, "set_cached_embedding",
        lambda m, t, v: set_calls.append((t, v)),
    )

    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.data = [MagicMock(embedding=[2.0])]  # only one miss
    fake_client.embeddings.create.return_value = fake_response
    monkeypatch.setattr(vector_service, "get_openai_client", lambda: fake_client)

    out = vector_service.embed_texts(["hit", "miss"])
    assert out == [[1.0], [2.0]]
    # Only miss text was sent to OpenAI
    sent = fake_client.embeddings.create.call_args.kwargs["input"]
    assert sent == ["miss"]
    # Only miss was cached
    assert set_calls == [("miss", [2.0])]
