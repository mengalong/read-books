from __future__ import annotations

import threading
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Book, QuizGenerationTask
from app.schemas import PreGenerationResponse, QuizGenerateRequest
from app.services.quiz_generation import (
    recover_generation_tasks,
    run_generation_task,
    resolve_source_mode,
    start_generation_task,
)


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
        task_id=_task_id_for_book(book),
    )


def _task_id_for_book(book: Book) -> str | None:
    task = next(
        (
            task
            for task in book.generation_tasks
            if task.task_type == "pre_generation"
            and task.status in {"pending", "processing", "completed", "failed"}
        ),
        None,
    )
    return task.id if task else None


def begin_pre_generation(db: Session, book_id: str) -> PreGenerationStart:
    book = db.get(Book, book_id)
    if not book:
        raise ValueError("未找到这本书")
    if book.pre_generation_status in {"pending", "processing"}:
        return PreGenerationStart(pre_generation_response(book), False)
    if book.pre_generation_status == "completed" and book.pre_generation_quiz_id:
        return PreGenerationStart(pre_generation_response(book), False)

    resolve_source_mode(db, book_id)

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
        task = start_generation_task(
            db,
            book_id,
            QuizGenerateRequest(
                duration_minutes=15,
                difficulty="medium",
                single_count=5,
                multiple_count=3,
                short_count=2,
            ),
            "pre_generation",
        )
        result.response.task_id = task.id
    return result.response


def recover_pre_generation_tasks(db: Session) -> list[str]:
    return recover_generation_tasks(db, "pre_generation")


def run_pre_generation(book_id: str) -> None:
    with SessionLocal() as db:
        task = db.scalar(
            select(QuizGenerationTask)
            .where(
                QuizGenerationTask.book_id == book_id,
                QuizGenerationTask.task_type == "pre_generation",
                QuizGenerationTask.status == "pending",
            )
            .order_by(QuizGenerationTask.created_at.desc())
        )
        if not task:
            return
        run_generation_task(task.id)
