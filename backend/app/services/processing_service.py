"""High-level pipeline that processes an uploaded file end-to-end."""
import json
import logging
from sqlalchemy.orm import Session

from app.models.file import File, FileStatus, FileType
from app.services.pdf_service import extract_pdf_text
from app.services.transcription_service import transcribe_media
from app.services.vector_service import index_pdf, index_media
from app.services.llm_service import summarize_text

logger = logging.getLogger(__name__)


def process_file(db: Session, file_id: int) -> None:
    """
    Process a file: extract text/transcribe, index, summarize.
    Updates the DB row in place.
    """
    file = db.get(File, file_id)
    if not file:
        logger.warning("process_file: file %s not found", file_id)
        return

    file.status = FileStatus.PROCESSING
    db.commit()

    try:
        if file.file_type == FileType.PDF:
            text, pages = extract_pdf_text(file.stored_path)
            file.extracted_text = text
            index_pdf(file_id=file.id, pages=pages)
        else:
            result = transcribe_media(file.stored_path)
            file.extracted_text = result["text"]
            file.duration_seconds = result["duration"]
            file.transcript_segments = json.dumps(result["segments"])
            index_media(file_id=file.id, segments=result["segments"])

        # Summarize
        if file.extracted_text:
            try:
                file.summary = summarize_text(file.extracted_text)
            except Exception as e:
                logger.exception("Summarization failed for file %s", file.id)
                file.summary = None

        file.status = FileStatus.READY
        file.error_message = None
        db.commit()
    except Exception as e:
        logger.exception("Processing failed for file %s", file_id)
        file.status = FileStatus.FAILED
        file.error_message = str(e)[:500]
        db.commit()
