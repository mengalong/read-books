from __future__ import annotations

import threading
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Book, ContentChunk, PdfDocument
from app.schemas import PreGenerationResponse, QuizGenerateRequest


@dataclass(frozen=True)
class PreGenerationStart:
    response: PreGenerationResponse
    should_start: bool


def pre_generation_response(book: Book) -> PreGenerationResponse:
    if book.pre_generation_status == "completed":
        message = "预生成测试已准备完成"
    elif book.pre_generation_status in {"pending", "processing"}:
        message = "正在后台生成测试，请稍候"
    elif book.pre_generation_status == "failed":
        message = book.pre_generation_error or "预生成测试失败，可以重新尝试"
    else:
        message = "预生成测试尚未开启"
    return PreGenerationResponse(
        status=book.pre_generation_status,
        message=message,
        error_message=book.pre_generation_error,
        quiz_id=book.pre_generation_quiz_id,
    )


def begin_pre_generation(db: Session, book_id: str) -> PreGenerationStart:
    book = db.get(Book, book_id)
    if not book:
        raise ValueError("未找到这本书")
    if book.pre_generation_status in {"pending", "processing"}:
        return PreGenerationStart(pre_generation_response(book), False)
    if book.pre_generation_status == "completed" and book.pre_generation_quiz_id:
        return PreGenerationStart(pre_generation_response(book), False)

    has_chunks = db.scalar(
        select(ContentChunk.id)
        .join(PdfDocument, PdfDocument.id == ContentChunk.pdf_id)
        .where(ContentChunk.book_id == book_id, PdfDocument.parse_status == "completed")
        .limit(1)
    )
    if not has_chunks:
        raise ValueError("请先上传并完成解析 PDF，再开启预生成")

    claimed = db.execute(
        update(Book)
        .where(
            Book.id == book_id,
            Book.pre_generation_status.not_in(["pending", "processing", "completed"]),
        )
        .values(
            pre_generation_enabled=True,
            pre_generation_status="pending",
            pre_generation_error=None,
            pre_generation_quiz_id=None,
        )
    )
    if claimed.rowcount != 1:
        db.rollback()
        book = db.get(Book, book_id)
        return PreGenerationStart(pre_generation_response(book), False)
    db.commit()
    book = db.get(Book, book_id)
    return PreGenerationStart(pre_generation_response(book), True)


def start_pre_generation(db: Session, book_id: str) -> PreGenerationResponse:
    result = begin_pre_generation(db, book_id)
    if result.should_start:
        threading.Thread(target=run_pre_generation, args=(book_id,), daemon=True).start()
    return result.response


def recover_pre_generation_tasks(db: Session) -> list[str]:
    book_ids = list(
        db.scalars(
            select(Book.id).where(Book.pre_generation_status.in_(["pending", "processing"]))
        ).all()
    )
    if not book_ids:
        return []
    db.execute(
        update(Book)
        .where(Book.id.in_(book_ids))
        .values(pre_generation_status="pending", pre_generation_error=None)
    )
    db.commit()
    return book_ids


def run_pre_generation(book_id: str) -> None:
    with SessionLocal() as db:
        book = db.get(Book, book_id)
        if not book or book.pre_generation_status != "pending":
            return
        book.pre_generation_status = "processing"
        db.commit()

        try:
            # Reuse the same validation, Provider selection and source-evidence path as manual tests.
            from app.routers.quizzes import _generate_quiz

            quiz = _generate_quiz(
                book_id,
                QuizGenerateRequest(
                    duration_minutes=15,
                    difficulty="medium",
                    single_count=5,
                    multiple_count=3,
                    short_count=2,
                ),
                db,
            )
            book = db.get(Book, book_id)
            book.pre_generation_status = "completed"
            book.pre_generation_quiz_id = quiz.id
            book.pre_generation_error = None
            db.commit()
        except Exception as exc:  # Background tasks must persist a visible failure state.
            db.rollback()
            book = db.get(Book, book_id)
            if not book:
                return
            book.pre_generation_status = "failed"
            book.pre_generation_error = str(getattr(exc, "detail", exc))[:500]
            db.commit()
