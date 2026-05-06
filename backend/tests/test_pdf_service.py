"""PDF service tests."""
from pathlib import Path
from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.services.pdf_service import extract_pdf_text


def _make_pdf(tmp_path: Path, pages_text: list[str]) -> Path:
    """Create a real PDF using pypdf so we can extract text reliably."""
    # pypdf's PdfWriter doesn't easily write text; use reportlab if available else fallback
    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        # Build a minimal PDF using a string we know pypdf can parse.
        # Skip actual text extraction validation — test on empty page instead.
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        path = tmp_path / "blank.pdf"
        with path.open("wb") as f:
            writer.write(f)
        return path

    path = tmp_path / "test.pdf"
    c = canvas.Canvas(str(path))
    for text in pages_text:
        c.drawString(100, 750, text)
        c.showPage()
    c.save()
    return path


def test_extract_blank_pdf(tmp_path):
    """Blank PDFs return empty result without errors."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    path = tmp_path / "blank.pdf"
    with path.open("wb") as f:
        writer.write(f)

    text, pages = extract_pdf_text(path)
    assert text == ""
    assert pages == []


def test_extract_with_text(tmp_path):
    """If reportlab is available, verify text extraction."""
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    path = tmp_path / "real.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(100, 750, "Hello world page one")
    c.showPage()
    c.drawString(100, 750, "Second page content")
    c.showPage()
    c.save()

    text, pages = extract_pdf_text(path)
    assert "Hello" in text or "world" in text
    assert len(pages) >= 1
    for p in pages:
        assert "page" in p
        assert "text" in p


def test_extract_handles_corrupt_page(tmp_path, monkeypatch):
    """If a page raises on extract_text, we skip it."""
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    path = tmp_path / "ok.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(100, 750, "good page")
    c.showPage()
    c.save()

    # Patch the method to raise
    from pypdf import PageObject
    original = PageObject.extract_text

    call_count = {"n": 0}

    def boom(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated corrupt page")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", boom)

    text, pages = extract_pdf_text(path)
    # Doesn't crash
    assert isinstance(text, str)
    assert isinstance(pages, list)
