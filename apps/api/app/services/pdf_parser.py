import re
import logging
from pathlib import Path

import fitz
from sqlalchemy import delete

from app.database import SessionLocal
from app.models import ContentChunk, PdfDocument

MIN_EXTRACTED_CHARS = 200
MAX_CHUNK_CHARS = 1_200
logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def chunk_page_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                paragraph[start : start + max_chars]
                for start in range(0, len(paragraph), max_chars)
            )
            continue

        candidate = f"{current}\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)
    return chunks


def parse_pdf_document(pdf_id: str) -> None:
    with SessionLocal() as db:
        pdf = db.get(PdfDocument, pdf_id)
        if not pdf:
            return

        pdf.parse_status = "processing"
        pdf.error_message = None
        db.commit()

        try:
            parsed: list[tuple[int, str]] = []
            with fitz.open(pdf.file_path) as document:
                if document.needs_pass and not document.authenticate(""):
                    raise ValueError("PDF 受密码保护，首版无法读取其原文")
                page_count = document.page_count
                for page_index, page in enumerate(document):
                    text = normalize_text(page.get_text("text"))
                    parsed.extend(
                        (page_index + 1, chunk) for chunk in chunk_page_text(text) if chunk
                    )

            total_chars = sum(len(content) for _, content in parsed)
            if total_chars < MIN_EXTRACTED_CHARS:
                raise ValueError("PDF 可提取文字过少，文件可能是扫描版，首版暂不支持 OCR")

            db.execute(delete(ContentChunk).where(ContentChunk.pdf_id == pdf.id))
            for sequence, (page_number, content) in enumerate(parsed, start=1):
                db.add(
                    ContentChunk(
                        book_id=pdf.book_id,
                        pdf_id=pdf.id,
                        page_number=page_number,
                        sequence=sequence,
                        content=content,
                        char_count=len(content),
                    )
                )

            pdf.page_count = page_count
            pdf.chunk_count = len(parsed)
            pdf.parse_status = "completed"
            db.commit()
        except Exception as exc:
            logger.exception("PDF 解析失败: %s", pdf_id)
            db.rollback()
            failed_pdf = db.get(PdfDocument, pdf_id)
            if failed_pdf:
                failed_pdf.parse_status = "failed"
                failed_pdf.error_message = str(exc) or "PDF 解析失败"
                db.commit()
