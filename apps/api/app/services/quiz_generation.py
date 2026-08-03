from __future__ import annotations

import threading
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import (
    Book,
    ContentChunk,
    PdfDocument,
    Question,
    Quiz,
    QuizGenerationTask,
)
from app.schemas import QuizGenerateRequest
from app.services.model_config import get_effective_model_configuration
from app.services.model_usage import attach_quiz_to_usage, new_usage_context
from app.services.prompt_config import get_effective_prompt_templates
from app.services.quiz_provider import get_quiz_provider

settings = get_settings()


def resolve_source_mode(db: Session, book_id: str) -> str:
    completed_chunk = db.scalar(
        select(ContentChunk.id)
        .join(PdfDocument, PdfDocument.id == ContentChunk.pdf_id)
        .where(ContentChunk.book_id == book_id, PdfDocument.parse_status == "completed")
        .limit(1)
    )
    if completed_chunk:
        return "pdf"

    has_pdf = db.scalar(select(PdfDocument.id).where(PdfDocument.book_id == book_id).limit(1))
    if has_pdf:
        raise ValueError("已有 PDF，但尚未完成解析；请等待解析完成或检查解析失败原因")

    configuration = get_effective_model_configuration(db, settings)
    if configuration.provider_mode == "mock":
        raise ValueError("没有 PDF 时需要启用已配置的大模型，当前模拟接口不支持书籍知识出题")
    return "model_knowledge"


def validate_generation_request(
    db: Session, book_id: str, payload: QuizGenerateRequest, task_type: str
) -> Book:
    book = db.get(Book, book_id)
    if not book:
        raise ValueError("未找到这本书")
    if payload.single_count + payload.multiple_count + payload.short_count == 0:
        raise ValueError("至少需要选择一种题型")
    if payload.page_start and payload.page_end and payload.page_start > payload.page_end:
        raise ValueError("起始页不能晚于结束页")
    active = db.scalar(
        select(QuizGenerationTask.id).where(
            QuizGenerationTask.book_id == book_id,
            QuizGenerationTask.status.in_(["pending", "processing"]),
        )
    )
    if active:
        raise ValueError("该书已有出题任务正在进行，请等待本次任务完成")
    if task_type == "manual_quiz_generation" and book.pre_generation_status in {
        "pending",
        "processing",
    }:
        raise ValueError("该书正在后台预生成测试，请等待本次任务完成")
    source_mode = resolve_source_mode(db, book_id)
    if source_mode == "model_knowledge" and (payload.page_start or payload.page_end):
        raise ValueError("没有 PDF 时不能指定页码范围")
    return book


def create_generation_task(
    db: Session,
    book_id: str,
    payload: QuizGenerateRequest,
    task_type: str,
    *,
    created_by_user_id: str | None = None,
) -> QuizGenerationTask:
    validate_generation_request(db, book_id, payload, task_type)
    source_mode = resolve_source_mode(db, book_id)
    task = QuizGenerationTask(
        book_id=book_id,
        created_by_user_id=created_by_user_id,
        task_type=task_type,
        status="pending",
        source_mode=source_mode,
        total_questions=payload.single_count + payload.multiple_count + payload.short_count,
        current_phase="等待开始",
        difficulty=payload.difficulty,
        duration_minutes=payload.duration_minutes,
        single_count=payload.single_count,
        multiple_count=payload.multiple_count,
        short_count=payload.short_count,
        page_start=payload.page_start,
        page_end=payload.page_end,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def start_generation_task(
    db: Session,
    book_id: str,
    payload: QuizGenerateRequest,
    task_type: str,
    *,
    created_by_user_id: str | None = None,
) -> QuizGenerationTask:
    task = create_generation_task(
        db,
        book_id,
        payload,
        task_type,
        created_by_user_id=created_by_user_id,
    )
    threading.Thread(target=run_generation_task, args=(task.id,), daemon=True).start()
    return task


def recover_generation_tasks(db: Session, task_type: str | None = None) -> list[str]:
    conditions = [QuizGenerationTask.status.in_(["pending", "processing"])]
    if task_type:
        conditions.append(QuizGenerationTask.task_type == task_type)
    tasks = list(
        db.scalars(
            select(QuizGenerationTask).where(*conditions)
        ).all()
    )
    if not tasks:
        return []
    pre_generation_book_ids = {
        task.book_id for task in tasks if task.task_type == "pre_generation"
    }
    for task in tasks:
        task.status = "pending"
        task.current_phase = "等待服务恢复"
    if pre_generation_book_ids:
        books = db.scalars(select(Book).where(Book.id.in_(pre_generation_book_ids))).all()
        for book in books:
            book.pre_generation_status = "pending"
            book.pre_generation_error = None
    db.commit()
    return [task.id for task in tasks]


def _get_chunks(db: Session, task: QuizGenerationTask) -> list[ContentChunk]:
    statement = (
        select(ContentChunk)
        .join(PdfDocument, PdfDocument.id == ContentChunk.pdf_id)
        .where(ContentChunk.book_id == task.book_id, PdfDocument.parse_status == "completed")
        .order_by(ContentChunk.page_number, ContentChunk.sequence)
    )
    if task.page_start:
        statement = statement.where(ContentChunk.page_number >= task.page_start)
    if task.page_end:
        statement = statement.where(ContentChunk.page_number <= task.page_end)
    return list(db.scalars(statement).all())


def _recent_chunk_ids(db: Session, book_id: str) -> set[str]:
    recent_rows = db.scalars(
        select(Question.source_chunk_ids)
        .join(Quiz, Quiz.id == Question.quiz_id)
        .where(Quiz.book_id == book_id)
        .order_by(Quiz.created_at.desc())
        .limit(40)
    ).all()
    return {chunk_id for row in recent_rows for chunk_id in (row or [])}


def _question_types(task: QuizGenerationTask) -> Iterable[str]:
    for question_type, count in (
        ("single", task.single_count),
        ("multiple", task.multiple_count),
        ("short", task.short_count),
    ):
        yield from (question_type for _ in range(count))


def _set_task_failure(db: Session, task_id: str, error: Exception) -> None:
    db.rollback()
    task = db.get(QuizGenerationTask, task_id)
    if not task:
        return
    task.status = "failed"
    task.current_phase = "生成失败"
    task.error_message = str(getattr(error, "detail", error))[:1_000]
    db.commit()
    if task.task_type == "pre_generation":
        book = db.get(Book, task.book_id)
        if book:
            book.pre_generation_status = "failed"
            book.pre_generation_error = task.error_message
            book.pre_generation_quiz_id = None
            db.commit()


def run_generation_task(task_id: str) -> None:
    with SessionLocal() as db:
        task = db.get(QuizGenerationTask, task_id)
        if not task or task.status not in {"pending", "processing"}:
            return
        task.status = "processing"
        task.current_phase = (
            "正在准备原文片段" if task.source_mode == "pdf" else "正在准备书籍信息"
        )
        db.commit()

        try:
            book = db.get(Book, task.book_id)
            chunks = _get_chunks(db, task)
            if not book:
                raise RuntimeError("未找到这本书")
            if task.source_mode == "pdf" and not chunks:
                raise RuntimeError("没有可用于出题的 PDF 原文")
            file_names = dict(
                db.execute(
                    select(PdfDocument.id, PdfDocument.file_name).where(
                        PdfDocument.id.in_({chunk.pdf_id for chunk in chunks})
                    )
                ).all()
            )
            generation_number = db.scalar(
                select(func.count(Quiz.id)).where(Quiz.book_id == task.book_id)
            ) or 0
            recent_chunk_ids = _recent_chunk_ids(db, task.book_id)
            usage_context = new_usage_context(
                task.task_type,
                f"《{book.title}》后台预出题"
                if task.task_type == "pre_generation"
                else f"《{book.title}》生成复习试卷",
                book_id=book.id,
            )
            provider = get_quiz_provider(
                settings,
                get_effective_model_configuration(db, settings),
                get_effective_prompt_templates(db),
                usage_context,
            )
            generated = []
            for position, question_type in enumerate(_question_types(task), start=1):
                task.current_question_position = position
                task.current_phase = f"正在生成第 {position} / {task.total_questions} 道{question_type_label(question_type)}"
                db.commit()
                result = provider.generate_questions(
                    chunks=chunks,
                    file_names=file_names,
                    single_count=1 if question_type == "single" else 0,
                    multiple_count=1 if question_type == "multiple" else 0,
                    short_count=1 if question_type == "short" else 0,
                    difficulty=task.difficulty,
                    generation_number=generation_number + position - 1,
                    recent_chunk_ids=recent_chunk_ids,
                    duration_minutes=task.duration_minutes,
                    book_title=book.title,
                    author=book.author,
                    source_mode=task.source_mode,
                )
                if len(result) != 1:
                    raise RuntimeError(f"第 {position} 道题生成结果数量不正确")
                item = result[0]
                generated.append(item)
                recent_chunk_ids.update(item.source_chunk_ids)
                task.completed_questions = position
                task.current_phase = f"已完成第 {position} / {task.total_questions} 道题"
                db.commit()

            quiz = Quiz(
                book_id=task.book_id,
                title=f"第 {generation_number + 1} 套复习试卷",
                difficulty=task.difficulty,
                duration_minutes=task.duration_minutes,
                status="ready",
                source_mode=task.source_mode,
                max_score=sum(item.max_score for item in generated),
                generation_task_id=task.id,
            )
            db.add(quiz)
            db.flush()
            for position, item in enumerate(generated, start=1):
                db.add(
                    Question(
                        quiz_id=quiz.id,
                        position=position,
                        question_type=item.question_type,
                        prompt=item.prompt,
                        options=item.options,
                        correct_answers=item.correct_answers,
                        explanation=item.explanation,
                        knowledge_point=item.knowledge_point,
                        difficulty=task.difficulty,
                        estimated_seconds=item.estimated_seconds,
                        reference_answer=item.reference_answer,
                        grading_rubric=item.grading_rubric,
                        source_chunk_ids=item.source_chunk_ids,
                        source_evidence=item.source_evidence,
                        max_score=item.max_score,
                    )
                )
            db.commit()
            attach_quiz_to_usage(usage_context.task_id, quiz.id)
            task = db.get(QuizGenerationTask, task.id)
            task.status = "completed"
            task.quiz_id = quiz.id
            task.current_phase = "全部题目已生成"
            task.current_question_position = task.total_questions
            db.commit()
            if task.task_type == "pre_generation":
                book = db.get(Book, task.book_id)
                book.pre_generation_status = "completed"
                book.pre_generation_quiz_id = quiz.id
                book.pre_generation_error = None
                db.commit()
        except Exception as exc:
            _set_task_failure(db, task_id, exc)


def question_type_label(question_type: str) -> str:
    return {"single": "单选题", "multiple": "多选题", "short": "问答题"}.get(
        question_type, "题目"
    )
