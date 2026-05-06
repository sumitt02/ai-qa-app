"""PDF text extraction."""
from pathlib import Path
from pypdf import PdfReader


def extract_pdf_text(file_path: str | Path) -> tuple[str, list[dict]]:
    """
    Extract text from a PDF.

    Returns:
        (full_text, pages) where pages is a list of {"page": int, "text": str}
    """
    reader = PdfReader(str(file_path))
    pages: list[dict] = []
    chunks: list[str] = []

    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        if text:
            pages.append({"page": i, "text": text})
            chunks.append(text)

    return "\n\n".join(chunks), pages
