from __future__ import annotations

import copy
import re
import threading
from types import SimpleNamespace
from typing import Any, Iterable

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
from app.services.quiz_provider import GeneratedQuestion, compact_text, get_quiz_provider
from app.services.resource_types import resource_type_label
from app.services.score_allocation import (
    QUIZ_TOTAL_SCORE,
    allocate_question_scores,
    normalize_rubric_scores,
)

settings = get_settings()


def resolve_source_mode(db: Session, book_id: str) -> str:
    book = db.get(Book, book_id)
    if not book:
        raise ValueError("未找到这本书")

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
        label = resource_type_label(book.resource_type)
        raise ValueError(f"没有 PDF 时需要启用已配置的大模型，当前模拟接口不支持{label}知识出题")
    if book.resource_type != "book" and book.model_knowledge_supported is not True:
        label = resource_type_label(book.resource_type)
        raise ValueError(f"该{label}尚未通过模型真实内容测试，不能依赖模型知识出题")
    if book.resource_type == "book" and book.model_knowledge_supported is False:
        label = resource_type_label(book.resource_type)
        raise ValueError(f"该{label}尚未通过模型真实内容测试，不能依赖模型知识出题")
    return "model_knowledge"


def validate_generation_request(
    db: Session, book_id: str, payload: QuizGenerateRequest, task_type: str
) -> Book:
    book = db.get(Book, book_id)
    if not book:
        raise ValueError("未找到这本书")
    if book.shelf_status != "active":
        raise ValueError("这本书已下架，请恢复后再生成试卷")
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


def _get_chunks(
    db: Session, book_id: str, page_start: int | None = None, page_end: int | None = None
) -> list[ContentChunk]:
    statement = (
        select(ContentChunk)
        .join(PdfDocument, PdfDocument.id == ContentChunk.pdf_id)
        .where(ContentChunk.book_id == book_id, PdfDocument.parse_status == "completed")
        .order_by(ContentChunk.page_number, ContentChunk.sequence)
    )
    if page_start:
        statement = statement.where(ContentChunk.page_number >= page_start)
    if page_end:
        statement = statement.where(ContentChunk.page_number <= page_end)
    return list(db.scalars(statement).all())


def _chunk_file_names(db: Session, chunks: list[ContentChunk]) -> dict[str, str]:
    if not chunks:
        return {}
    return dict(
        db.execute(
            select(PdfDocument.id, PdfDocument.file_name).where(
                PdfDocument.id.in_({chunk.pdf_id for chunk in chunks})
            )
        ).all()
    )


def _recent_chunk_ids(db: Session, book_id: str) -> set[str]:
    recent_rows = db.scalars(
        select(Question.source_chunk_ids)
        .join(Quiz, Quiz.id == Question.quiz_id)
        .where(Quiz.book_id == book_id)
        .order_by(Quiz.created_at.desc())
        .limit(40)
    ).all()
    return {chunk_id for row in recent_rows for chunk_id in (row or [])}


def _normalize_question_text(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def _question_exclusion_payload(question: Question, role: str = "same_type_reference") -> dict[str, object]:
    payload: dict[str, object] = {
        "role": role,
        "position": question.position,
        "question_type": question.question_type,
        "prompt": compact_text(question.prompt, 140),
        "knowledge_point": compact_text(question.knowledge_point, 60),
        "source_chunk_ids": list(getattr(question, "source_chunk_ids", None) or []),
    }
    if question.question_type == "short" and question.reference_answer:
        payload["reference_answer"] = compact_text(question.reference_answer, 120)
    return payload


def _generated_question_exclusion_payload(question: GeneratedQuestion) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": "rejected_candidate",
        "question_type": question.question_type,
        "prompt": compact_text(question.prompt, 140),
        "knowledge_point": compact_text(question.knowledge_point, 60),
        "source_chunk_ids": list(question.source_chunk_ids or []),
    }
    if question.question_type == "short" and question.reference_answer:
        payload["reference_answer"] = compact_text(question.reference_answer, 120)
    return payload


def _build_regeneration_guidance(quiz: Quiz, question: Question, attempt: int) -> str:
    guidance = (
        f"本次是《{quiz.book.title}》第 {question.position} 题的"
        f"{question_type_label(question.question_type)}重出，请确保新题与同类题目在题干、知识点和原文依据上都不同，"
        "优先换用不同的原文片段和不同的提问角度。"
    )
    if attempt > 0:
        guidance += f" 这是第 {attempt + 1} 次尝试，请进一步拉开差异。"
    return guidance


def _build_snapshot_regeneration_guidance(book_title: str, question: Any, attempt: int) -> str:
    guidance = (
        f"本次是《{book_title}》第 {question.position} 题的"
        f"{question_type_label(str(getattr(question, 'question_type', 'single')))}重出，请确保新题与同类题目在题干、知识点和原文依据上都不同，"
        "优先换用不同的原文片段和不同的提问角度。"
    )
    if attempt > 0:
        guidance += f" 这是第 {attempt + 1} 次尝试，请进一步拉开差异。"
    return guidance


def _is_duplicate_question(
    candidate: GeneratedQuestion, siblings: list[Question], recent_candidates: list[GeneratedQuestion]
) -> bool:
    candidate_prompt = _normalize_question_text(candidate.prompt)
    candidate_knowledge = _normalize_question_text(candidate.knowledge_point)
    candidate_sources = set(candidate.source_chunk_ids or [])
    for question in siblings:
        question_sources = set(getattr(question, "source_chunk_ids", None) or [])
        if candidate_sources and question_sources and candidate_sources & question_sources:
            return True
        if candidate_prompt and candidate_prompt == _normalize_question_text(question.prompt):
            return True
        if candidate_knowledge and candidate_knowledge == _normalize_question_text(
            question.knowledge_point
        ):
            return True
    for previous in recent_candidates:
        if candidate_prompt and candidate_prompt == _normalize_question_text(previous.prompt):
            return True
        if candidate_knowledge and candidate_knowledge == _normalize_question_text(
            previous.knowledge_point
        ):
            return True
    return False


def regenerate_quiz_question(
    db: Session, quiz: Quiz, question: Question, *, user_id: str | None = None
) -> Question:
    same_type_questions = [
        item
        for item in quiz.questions
        if item.id != question.id and item.question_type == question.question_type
    ]
    comparison_questions = [question, *same_type_questions]
    all_chunks = _get_chunks(db, quiz.book_id)
    if quiz.source_mode == "pdf" and not all_chunks:
        raise ValueError("没有可用于出题的 PDF 原文")

    blocked_chunk_ids = {
        chunk_id
        for sibling in same_type_questions
        for chunk_id in (sibling.source_chunk_ids or [])
    }
    preferred_chunks = [chunk for chunk in all_chunks if chunk.id not in blocked_chunk_ids]
    chunks = preferred_chunks or all_chunks
    recent_chunk_ids = set() if preferred_chunks else blocked_chunk_ids
    file_names = _chunk_file_names(db, chunks)
    base_generation_number = db.scalar(
        select(func.count(Quiz.id)).where(Quiz.book_id == quiz.book_id)
    ) or 0
    provider = get_quiz_provider(
        settings,
        get_effective_model_configuration(db, settings),
        get_effective_prompt_templates(db),
        new_usage_context(
            "question_regeneration",
            f"《{quiz.book.title}》重出第 {question.position} 题",
            book_id=quiz.book_id,
            quiz_id=quiz.id,
            user_id=user_id,
            workspace_id=quiz.book.workspace_id,
        ),
    )
    question_exclusions = [
        _question_exclusion_payload(question, role="current_question"),
        *(_question_exclusion_payload(item) for item in same_type_questions),
    ]
    rejected_candidates: list[GeneratedQuestion] = []
    question_type_counts = {"single": 0, "multiple": 0, "short": 0}
    question_type_counts[question.question_type] = 1

    for attempt in range(3):
        result = provider.generate_questions(
            chunks=chunks,
            file_names=file_names,
            single_count=question_type_counts["single"],
            multiple_count=question_type_counts["multiple"],
            short_count=question_type_counts["short"],
            difficulty=quiz.difficulty,
            generation_number=base_generation_number + question.position + attempt,
            recent_chunk_ids=recent_chunk_ids,
            duration_minutes=quiz.duration_minutes,
            book_title=quiz.book.title,
            author=quiz.book.author,
            resource_type=quiz.book.resource_type,
            source_mode=quiz.source_mode,
            question_exclusions=[
                *question_exclusions,
                *(
                    _generated_question_exclusion_payload(item)
                    for item in rejected_candidates
                ),
            ],
            regeneration_guidance=_build_regeneration_guidance(quiz, question, attempt),
        )
        if len(result) != 1:
            raise RuntimeError("重出结果数量不正确")
        item = result[0]
        if item.question_type != question.question_type:
            raise RuntimeError("重出结果题型不正确")
        if _is_duplicate_question(item, comparison_questions, rejected_candidates):
            rejected_candidates.append(item)
            continue

        question.prompt = item.prompt
        question.options = item.options
        question.correct_answers = item.correct_answers
        question.explanation = item.explanation
        question.knowledge_point = item.knowledge_point
        question.difficulty = quiz.difficulty
        question.estimated_seconds = item.estimated_seconds
        question.reference_answer = item.reference_answer
        question.grading_rubric = (
            normalize_rubric_scores(item.grading_rubric, question.max_score)
            if item.question_type == "short"
            else item.grading_rubric
        )
        question.source_chunk_ids = item.source_chunk_ids
        question.source_evidence = item.source_evidence
        db.commit()
        db.refresh(question)
        return question

    raise ValueError("重出失败，请先调整同类题目或原文来源后再试")


def regenerate_snapshot_question(
    db: Session,
    *,
    book_id: str,
    book_title: str,
    author: str,
    resource_type: str,
    source_mode: str,
    difficulty: str,
    duration_minutes: int,
    workspace_id: str | None = None,
    quiz_id: str | None = None,
    exam_share_id: str | None = None,
    current_question: dict[str, object],
    sibling_questions: list[dict[str, object]],
    user_id: str | None = None,
    generation_number: int = 0,
) -> dict[str, object]:
    current = SimpleNamespace(**current_question)
    same_type_questions = [
        SimpleNamespace(**item)
        for item in sibling_questions
        if str(item.get("id")) != str(current_question.get("id"))
        and item.get("question_type") == current_question.get("question_type")
    ]
    comparison_questions = [current, *same_type_questions]
    all_chunks = _get_chunks(db, book_id)
    if source_mode == "pdf" and not all_chunks:
        raise ValueError("没有可用于出题的 PDF 原文")

    blocked_chunk_ids = {
        chunk_id
        for sibling in same_type_questions
        for chunk_id in (getattr(sibling, "source_chunk_ids", None) or [])
    }
    preferred_chunks = [chunk for chunk in all_chunks if chunk.id not in blocked_chunk_ids]
    chunks = preferred_chunks or all_chunks
    recent_chunk_ids = set() if preferred_chunks else blocked_chunk_ids
    file_names = _chunk_file_names(db, chunks)
    provider = get_quiz_provider(
        settings,
        get_effective_model_configuration(db, settings),
        get_effective_prompt_templates(db),
        new_usage_context(
            "question_regeneration",
            f"《{book_title}》重出第 {current.position} 题",
            book_id=book_id,
            quiz_id=quiz_id,
            user_id=user_id,
            workspace_id=workspace_id,
            exam_share_id=exam_share_id,
        ),
    )
    question_exclusions = [
        _question_exclusion_payload(current, role="current_question"),
        *(_question_exclusion_payload(item) for item in same_type_questions),
    ]
    rejected_candidates: list[GeneratedQuestion] = []
    question_type_counts = {"single": 0, "multiple": 0, "short": 0}
    question_type_counts[str(current.question_type)] = 1

    for attempt in range(3):
        result = provider.generate_questions(
            chunks=chunks,
            file_names=file_names,
            single_count=question_type_counts["single"],
            multiple_count=question_type_counts["multiple"],
            short_count=question_type_counts["short"],
            difficulty=difficulty,
            generation_number=generation_number + current.position + attempt,
            recent_chunk_ids=recent_chunk_ids,
            duration_minutes=duration_minutes,
            book_title=book_title,
            author=author,
            resource_type=resource_type,
            source_mode=source_mode,
            question_exclusions=[
                *question_exclusions,
                *(
                    _generated_question_exclusion_payload(item)
                    for item in rejected_candidates
                ),
            ],
            regeneration_guidance=_build_snapshot_regeneration_guidance(
                book_title, current, attempt
            ),
        )
        if len(result) != 1:
            raise RuntimeError("重出结果数量不正确")
        item = result[0]
        if item.question_type != current.question_type:
            raise RuntimeError("重出结果题型不正确")
        if _is_duplicate_question(item, comparison_questions, rejected_candidates):
            rejected_candidates.append(item)
            continue

        next_question = copy.deepcopy(current_question)
        next_question["prompt"] = item.prompt
        next_question["options"] = item.options
        next_question["correct_answers"] = item.correct_answers
        next_question["explanation"] = item.explanation
        next_question["knowledge_point"] = item.knowledge_point
        next_question["difficulty"] = difficulty
        next_question["estimated_seconds"] = item.estimated_seconds
        next_question["reference_answer"] = item.reference_answer
        next_question["grading_rubric"] = (
            normalize_rubric_scores(item.grading_rubric, float(current_question.get("max_score") or 0))
            if item.question_type == "short"
            else item.grading_rubric
        )
        next_question["source_chunk_ids"] = item.source_chunk_ids
        next_question["source_evidence"] = item.source_evidence
        return next_question

    raise ValueError("重出失败，请先调整同类题目或原文来源后再试")


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
            "正在准备原文片段" if task.source_mode == "pdf" else "正在准备资源信息"
        )
        db.commit()

        try:
            book = db.get(Book, task.book_id)
            chunks = _get_chunks(db, task.book_id, task.page_start, task.page_end)
            if not book:
                raise RuntimeError("未找到这本书")
            if task.source_mode == "pdf" and not chunks:
                raise RuntimeError("没有可用于出题的 PDF 原文")
            file_names = _chunk_file_names(db, chunks)
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
                user_id=task.created_by_user_id,
                workspace_id=book.workspace_id,
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
                    resource_type=book.resource_type,
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

            allocated_scores = allocate_question_scores(
                item.question_type for item in generated
            )
            for item, max_score in zip(generated, allocated_scores, strict=True):
                item.max_score = max_score
                if item.question_type == "short":
                    item.grading_rubric = normalize_rubric_scores(
                        item.grading_rubric, max_score
                    )

            quiz = Quiz(
                book_id=task.book_id,
                title=f"第 {generation_number + 1} 套复习试卷",
                difficulty=task.difficulty,
                duration_minutes=task.duration_minutes,
                status="ready",
                source_mode=task.source_mode,
                max_score=QUIZ_TOTAL_SCORE,
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
