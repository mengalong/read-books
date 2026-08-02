import re
import logging
import json
import subprocess
from pathlib import Path

import fitz
from sqlalchemy import delete

from app.database import SessionLocal
from app.models import ContentChunk, PdfDocument
from app.config import get_settings

MIN_EXTRACTED_CHARS = 200
MAX_CHUNK_CHARS = 1_200
MIN_READABLE_PAGE_RATIO = 0.1
logger = logging.getLogger(__name__)
settings = get_settings()


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


def is_readable_page(text: str) -> bool:
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return cjk_count >= 20 or latin_count >= max(20, len(text) // 4)


def extract_with_ocr(file_path: str) -> list[tuple[int, str]]:
    if not settings.ocr_enabled:
        raise ValueError("PDF 原文编码无法可靠读取，且 OCR 解析未启用")
    if not settings.ocr_script.exists():
        raise ValueError("PDF 原文编码无法可靠读取，当前环境没有 OCR 解析脚本")

    result = subprocess.run(
        [settings.ocr_command, str(settings.ocr_script), file_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=settings.ocr_script.parent.parent,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "未知错误"
        raise ValueError(f"PDF OCR 解析失败：{detail}")

    pages: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = normalize_text(str(item.get("text", "")))
        if text:
            pages.append((int(item["page"]), text))
    if not pages or sum(len(text) for _, text in pages) < MIN_EXTRACTED_CHARS:
        raise ValueError("PDF OCR 未识别出足够的文字，暂时无法生成可靠题目")
    return pages


def parse_pdf_document(pdf_id: str) -> None:
    with SessionLocal() as db:
        pdf = db.get(PdfDocument, pdf_id)
        if not pdf:
            return

        pdf.parse_status = "processing"
        pdf.error_message = None
        db.commit()

        try:
            direct_pages: list[tuple[int, str]] = []
            page_count = 0
            permissions = 0
            with fitz.open(pdf.file_path) as document:
                if document.needs_pass and not document.authenticate(""):
                    raise ValueError("PDF 受密码保护，首版无法读取其原文")
                page_count = document.page_count
                permissions = document.permissions
                for page_index, page in enumerate(document):
                    text = normalize_text(page.get_text("text"))
                    direct_pages.append((page_index + 1, text))

            readable_page_count = sum(is_readable_page(text) for _, text in direct_pages)
            required_readable_pages = (
                1 if page_count < 10 else max(3, int(page_count * MIN_READABLE_PAGE_RATIO))
            )
            direct_is_usable = (
                bool(permissions & fitz.PDF_PERM_COPY)
                and sum(len(text) for _, text in direct_pages) >= MIN_EXTRACTED_CHARS
                and readable_page_count >= required_readable_pages
            )
            pages = direct_pages if direct_is_usable else extract_with_ocr(pdf.file_path)
            parsed = [
                (page_number, chunk)
                for page_number, text in pages
                for chunk in chunk_page_text(text)
                if chunk
            ]
            if not parsed:
                raise ValueError("PDF 未提取出足够的文字，暂时无法生成可靠题目")

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
