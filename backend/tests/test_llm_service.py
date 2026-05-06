"""LLM service tests with mocked OpenAI."""
import json
from unittest.mock import MagicMock

import pytest

from app.services import llm_service


@pytest.fixture
def fake_chunks():
    return [
        {
            "text": "The quick brown fox jumps over the lazy dog.",
            "metadata": {"type": "pdf", "page": 1, "file_id": 1},
            "distance": 0.1,
        },
        {
            "text": "Machine learning models require training data.",
            "metadata": {"type": "media", "start": 12.0, "end": 25.0, "file_id": 1},
            "distance": 0.2,
        },
    ]


def test_format_context_pdf_and_media(fake_chunks):
    out = llm_service._format_context(fake_chunks)
    assert "page 1" in out
    assert "12.0s-25.0s" in out
    assert "fox" in out
    assert "Machine learning" in out


def test_format_context_unknown_type():
    chunks = [{"text": "x", "metadata": {}, "distance": 0.0}]
    out = llm_service._format_context(chunks)
    assert "[chunk 1]" in out


def test_build_citations_truncates(fake_chunks):
    long_chunks = [
        {"text": "A" * 500, "metadata": {"type": "pdf", "page": 3}},
    ]
    cits = llm_service.build_citations(long_chunks, "doc.pdf", file_id=7)
    assert cits[0]["snippet"].endswith("...")
    assert cits[0]["filename"] == "doc.pdf"
    assert cits[0]["page"] == 3
    assert cits[0]["file_id"] == 7


def test_build_citations_short_snippet():
    cits = llm_service.build_citations(
        [{"text": "short", "metadata": {"type": "media", "start": 1.0, "end": 2.0}}],
        "vid.mp4",
        file_id=8,
    )
    assert not cits[0]["snippet"].endswith("...")
    assert cits[0]["start"] == 1.0
    assert cits[0]["end"] == 2.0


def test_answer_question_uses_search_and_llm(monkeypatch, fake_chunks):
    monkeypatch.setattr(llm_service, "search", lambda **kw: fake_chunks)

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="The fox jumped."))]
    )
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)

    answer, citations = llm_service.answer_question(
        question="What did the fox do?",
        file_id=1,
        filename="doc.pdf",
    )
    assert answer == "The fox jumped."
    assert len(citations) == 2
    fake_client.chat.completions.create.assert_called_once()


def test_answer_question_no_results(monkeypatch):
    monkeypatch.setattr(llm_service, "search", lambda **kw: [])
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="I don't know."))]
    )
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)

    answer, cits = llm_service.answer_question(
        question="?", file_id=99, filename="x"
    )
    assert answer == "I don't know."
    assert cits == []


def test_answer_question_with_history(monkeypatch, fake_chunks):
    monkeypatch.setattr(llm_service, "search", lambda **kw: fake_chunks)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))]
    )
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)

    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    answer, _ = llm_service.answer_question(
        question="another", file_id=1, filename="d.pdf", history=history
    )
    # Verify history made it into the messages
    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    msgs = call_kwargs["messages"]
    assert any(m["content"] == "hi" for m in msgs)


def test_answer_question_none_content(monkeypatch, fake_chunks):
    monkeypatch.setattr(llm_service, "search", lambda **kw: fake_chunks)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=None))]
    )
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)
    answer, _ = llm_service.answer_question(question="?", file_id=1, filename="d")
    assert answer == ""


def test_answer_question_stream(monkeypatch, fake_chunks):
    monkeypatch.setattr(llm_service, "search", lambda **kw: fake_chunks)

    # Build fake stream chunks
    def make_chunk(text):
        return MagicMock(choices=[MagicMock(delta=MagicMock(content=text))])

    stream_chunks = [make_chunk("Hello"), make_chunk(" world"), make_chunk(None), make_chunk("!")]

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter(stream_chunks)
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)

    events = list(
        llm_service.answer_question_stream(
            question="hi", file_id=1, filename="d.pdf"
        )
    )
    # First event must be citations
    assert events[0].startswith("event: citations\n")
    # Should have token events
    token_events = [e for e in events if e.startswith("event: token\n")]
    assert len(token_events) == 3  # None content was skipped
    # Final event is done
    assert events[-1].startswith("event: done\n")


def test_answer_question_stream_handles_bad_chunk(monkeypatch, fake_chunks):
    """Stream chunks without choices/delta don't crash."""
    monkeypatch.setattr(llm_service, "search", lambda **kw: fake_chunks)

    bad_chunk = MagicMock()
    bad_chunk.choices = []  # IndexError when accessed

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter([bad_chunk])
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)

    events = list(
        llm_service.answer_question_stream(question="x", file_id=1, filename="f")
    )
    # Survives and emits citations + done
    assert any(e.startswith("event: citations\n") for e in events)
    assert any(e.startswith("event: done\n") for e in events)


def test_answer_stream_escapes_newlines(monkeypatch, fake_chunks):
    monkeypatch.setattr(llm_service, "search", lambda **kw: fake_chunks)

    def make_chunk(text):
        return MagicMock(choices=[MagicMock(delta=MagicMock(content=text))])

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter([make_chunk("line1\nline2")])
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)

    events = list(
        llm_service.answer_question_stream(question="?", file_id=1, filename="f")
    )
    token_events = [e for e in events if e.startswith("event: token\n")]
    # Newlines escaped to \n in data
    assert "line1\\nline2" in token_events[0]


def test_summarize_text(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="A short summary."))]
    )
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)

    out = llm_service.summarize_text("Some long text about things." * 50)
    assert out == "A short summary."


def test_summarize_empty_text(monkeypatch):
    """Empty input returns empty string without calling OpenAI."""
    fake_client = MagicMock()
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)
    assert llm_service.summarize_text("") == ""
    assert llm_service.summarize_text("   ") == ""
    fake_client.chat.completions.create.assert_not_called()


def test_summarize_truncates_input(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=None))]
    )
    monkeypatch.setattr(llm_service, "get_openai_client", lambda: fake_client)

    out = llm_service.summarize_text("x" * 50000, max_chars=100)
    # None content -> empty
    assert out == ""
    sent = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert len(sent) == 100
