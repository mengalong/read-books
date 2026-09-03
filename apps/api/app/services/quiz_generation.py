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
    QuoteEntry,
    Question,
    Quiz,
    QuizGenerationTask,
    ResourceMaterial,
)
from app.schemas import QuizGenerateRequest
from app.services.model_config import get_effective_model_configuration
from app.services.model_usage import attach_quiz_to_usage, new_usage_context
from app.services.prompt_config import get_effective_prompt_templates
from app.services.quiz_provider import (
    GeneratedQuestion,
    TrustedQuoteSource,
    compact_text,
    get_quiz_provider,
)
from app.services.question_dedup import (
    build_question_signature,
    questions_test_same_fact,
    signature_for_question,
)
from app.services.resource_types import resource_type_label
from app.services.score_allocation import (
    QUIZ_TOTAL_SCORE,
    allocate_question_scores,
    normalize_rubric_scores,
)

settings = get_settings()

THEME_SUBTYPES = {
    "classic_quotes": ["quote_speaker", "quote_context", "quote_meaning"],
    "character": [
        "quote_speaker",
        "quote_context",
        "quote_meaning",
        "character_relation",
        "character_trait",
    ],
}


def _normalized_theme_config(payload: QuizGenerateRequest) -> dict[str, Any]:
    config = payload.theme_config.model_dump()
    if payload.generation_theme == "general":
        return {}
    if not config["question_subtypes"]:
        config["question_subtypes"] = list(THEME_SUBTYPES[payload.generation_theme])
    return config


def resolve_source_mode(
    db: Session, book_id: str, payload: QuizGenerateRequest | None = None
) -> str:
    book = db.get(Book, book_id)
    if not book:
        raise ValueError("未找到这本书")

    if payload is not None and payload.generation_theme != "general":
        return "material"

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
    if payload.generation_theme != "general":
        config = _normalized_theme_config(payload)
        material_ids = config["material_ids"]
        character_names = config["character_names"]
        question_subtypes = set(config["question_subtypes"])
        if not material_ids:
            raise ValueError("经典台词或角色专题至少需要选择一份可信资料")
        if payload.generation_theme == "character" and not character_names:
            raise ValueError("角色专题至少需要选择一个已确认角色")
        unsupported = question_subtypes - set(THEME_SUBTYPES[payload.generation_theme])
        if unsupported:
            raise ValueError("所选考察角度不适用于当前专题")
        material_count = db.scalar(
            select(func.count(ResourceMaterial.id)).where(
                ResourceMaterial.book_id == book_id,
                ResourceMaterial.id.in_(material_ids),
                ResourceMaterial.parse_status.in_(["needs_review", "completed"]),
            )
        ) or 0
        if material_count != len(set(material_ids)):
            raise ValueError("部分可信资料不存在、尚未解析完成或不属于当前资源")
        quote_filters = [
            QuoteEntry.book_id == book_id,
            QuoteEntry.material_id.in_(material_ids),
            QuoteEntry.review_status == "confirmed",
            QuoteEntry.enabled_for_generation.is_(True),
        ]
        if character_names:
            quote_filters.append(QuoteEntry.speaker.in_(character_names))
        available_quotes = db.scalar(
            select(func.count(QuoteEntry.id)).where(*quote_filters)
        ) or 0
        total_questions = payload.single_count + payload.multiple_count + payload.short_count
        if available_quotes < total_questions:
            raise ValueError(
                f"符合专题范围的可信台词只有 {available_quotes} 条，至少需要 {total_questions} 条"
            )
        if question_subtypes == {"quote_speaker"}:
            if payload.multiple_count or payload.short_count:
                raise ValueError("台词说话人角度只支持单选题，请增加其他考察角度或调整题型")
            speaker_quotes = db.scalar(
                select(func.count(QuoteEntry.id)).where(
                    *quote_filters,
                    QuoteEntry.speaker.is_not(None),
                )
            ) or 0
            if speaker_quotes < payload.single_count:
                raise ValueError("已确认说话人的台词数量不足，不能生成所需的说话人题")
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
    source_mode = resolve_source_mode(db, book_id, payload)
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
    source_mode = resolve_source_mode(db, book_id, payload)
    theme_config = _normalized_theme_config(payload)
    task = QuizGenerationTask(
        book_id=book_id,
        created_by_user_id=created_by_user_id,
        task_type=task_type,
        status="pending",
        source_mode=source_mode,
        generation_theme=payload.generation_theme,
        theme_config=theme_config,
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


def _get_quote_sources(
    db: Session,
    book_id: str,
    theme_config: dict[str, Any],
) -> list[TrustedQuoteSource]:
    material_ids = [str(value) for value in theme_config.get("material_ids", [])]
    character_names = [str(value) for value in theme_config.get("character_names", [])]
    filters = [
        QuoteEntry.book_id == book_id,
        QuoteEntry.material_id.in_(material_ids),
        QuoteEntry.review_status == "confirmed",
        QuoteEntry.enabled_for_generation.is_(True),
    ]
    if character_names:
        filters.append(QuoteEntry.speaker.in_(character_names))
    rows = db.execute(
        select(QuoteEntry, ResourceMaterial)
        .join(ResourceMaterial, ResourceMaterial.id == QuoteEntry.material_id)
        .where(*filters)
        .order_by(
            QuoteEntry.material_id,
            QuoteEntry.episode_number,
            QuoteEntry.start_ms,
            QuoteEntry.created_at,
        )
    ).all()
    return [
        TrustedQuoteSource(
            id=quote.id,
            material_id=material.id,
            file_name=material.file_name,
            material_type=material.material_type,
            content=quote.quote_text,
            source_segment_ids=list(quote.source_segment_ids or []),
            speaker=quote.speaker,
            context=quote.context,
            page_number=quote.page_number,
            season_number=quote.season_number,
            episode_number=quote.episode_number,
            start_ms=quote.start_ms,
            end_ms=quote.end_ms,
        )
        for quote, material in rows
    ]


def _theme_requirements(generation_theme: str, theme_config: dict[str, Any]) -> str:
    if generation_theme == "general":
        return "围绕资源整体内容出题，不限定角色或台词专题。"
    characters = "、".join(theme_config.get("character_names", [])) or "全部已确认角色"
    subtypes = "、".join(theme_config.get("question_subtypes", []))
    if generation_theme == "classic_quotes":
        return (
            f"仅围绕可信资料中的经典台词出题；角色范围：{characters}；"
            f"允许的考察角度：{subtypes}。逐字台词必须原样出现在题干中。"
        )
    return (
        f"仅围绕角色 {characters} 出题；允许的考察角度：{subtypes}。"
        "涉及逐字台词时必须原样引用可信资料。"
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


def _recent_quote_ids(db: Session, book_id: str) -> set[str]:
    recent_rows = db.scalars(
        select(Question.quote_entry_ids)
        .join(Quiz, Quiz.id == Question.quiz_id)
        .where(Quiz.book_id == book_id)
        .order_by(Quiz.created_at.desc())
        .limit(80)
    ).all()
    return {quote_id for row in recent_rows for quote_id in (row or [])}


def _normalize_question_text(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def _prepare_generated_question(question: GeneratedQuestion) -> GeneratedQuestion:
    signature = build_question_signature(question)
    question.fact_key = str(signature["fact_key"])
    question.fact_claim = str(signature["fact_claim"])
    question.semantic_signature = signature
    return question


def _question_exclusion_payload(
    question: Any, role: str = "same_type_reference"
) -> dict[str, object]:
    semantic_signature = signature_for_question(question)
    payload: dict[str, object] = {
        "role": role,
        "position": getattr(question, "position", None),
        "question_type": getattr(question, "question_type", ""),
        "prompt": compact_text(question.prompt, 140),
        "knowledge_point": compact_text(question.knowledge_point, 60),
        "source_chunk_ids": list(getattr(question, "source_chunk_ids", None) or []),
        "quote_entry_ids": list(getattr(question, "quote_entry_ids", None) or []),
        "question_subtype": str(getattr(question, "question_subtype", "general")),
        "semantic_signature": semantic_signature,
        "fact_key": semantic_signature["fact_key"],
        "fact_claim": semantic_signature["fact_claim"],
    }
    if question.question_type == "short" and question.reference_answer:
        payload["reference_answer"] = compact_text(question.reference_answer, 120)
    return payload


def _generated_question_exclusion_payload(question: GeneratedQuestion) -> dict[str, object]:
    _prepare_generated_question(question)
    payload: dict[str, object] = {
        "role": "rejected_candidate",
        "question_type": question.question_type,
        "prompt": compact_text(question.prompt, 140),
        "knowledge_point": compact_text(question.knowledge_point, 60),
        "source_chunk_ids": list(question.source_chunk_ids or []),
        "quote_entry_ids": list(question.quote_entry_ids or []),
        "question_subtype": question.question_subtype,
        "semantic_signature": question.semantic_signature,
        "fact_key": question.fact_key,
        "fact_claim": question.fact_claim,
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
    candidate: GeneratedQuestion,
    siblings: list[Any],
    recent_candidates: list[GeneratedQuestion],
) -> bool:
    _prepare_generated_question(candidate)
    if any(questions_test_same_fact(candidate, sibling) for sibling in siblings):
        return True
    if any(questions_test_same_fact(candidate, previous) for previous in recent_candidates):
        return True
    candidate_prompt = _normalize_question_text(candidate.prompt)
    candidate_knowledge = _normalize_question_text(candidate.knowledge_point)
    candidate_sources = set(candidate.source_chunk_ids or [])
    candidate_quotes = set(candidate.quote_entry_ids or [])
    for question in siblings:
        question_sources = set(getattr(question, "source_chunk_ids", None) or [])
        question_quotes = set(getattr(question, "quote_entry_ids", None) or [])
        if candidate_sources and question_sources and candidate_sources & question_sources:
            return True
        if candidate_quotes and question_quotes and candidate_quotes & question_quotes:
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
    theme_config = dict(quiz.theme_config or {})
    if quiz.source_mode == "material":
        all_sources = _get_quote_sources(db, quiz.book_id, theme_config)
        if not all_sources:
            raise ValueError("没有可用于重出题的可信台词，资料可能已删除或停用")
        blocked_source_ids = {
            quote_id
            for sibling in same_type_questions
            for quote_id in (sibling.quote_entry_ids or [])
        }
        preferred_sources = [
            source for source in all_sources if source.id not in blocked_source_ids
        ]
        chunks = preferred_sources or all_sources
        recent_chunk_ids = set() if preferred_sources else blocked_source_ids
        file_names = {}
    else:
        all_chunks = _get_chunks(db, quiz.book_id)
        if quiz.source_mode == "pdf" and not all_chunks:
            raise ValueError("没有可用于出题的 PDF 原文")
        blocked_source_ids = {
            chunk_id
            for sibling in same_type_questions
            for chunk_id in (sibling.source_chunk_ids or [])
        }
        preferred_chunks = [
            chunk for chunk in all_chunks if chunk.id not in blocked_source_ids
        ]
        chunks = preferred_chunks or all_chunks
        recent_chunk_ids = set() if preferred_chunks else blocked_source_ids
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
            generation_theme=quiz.generation_theme,
            theme_requirements=_theme_requirements(quiz.generation_theme, theme_config),
            allowed_question_subtypes=list(theme_config.get("question_subtypes", [])),
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
        _prepare_generated_question(item)
        question.source_chunk_ids = item.source_chunk_ids
        question.question_subtype = item.question_subtype
        question.quote_entry_ids = item.quote_entry_ids
        question.source_segment_ids = item.source_segment_ids
        question.fact_key = item.fact_key
        question.fact_claim = item.fact_claim
        question.semantic_signature = item.semantic_signature
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
    generation_theme: str = "general",
    theme_config: dict[str, Any] | None = None,
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
    theme_config = dict(theme_config or {})
    if source_mode == "material":
        all_sources = _get_quote_sources(db, book_id, theme_config)
        if not all_sources:
            raise ValueError("没有可用于重出题的可信台词，资料可能已删除或停用")
        blocked_source_ids = {
            quote_id
            for sibling in same_type_questions
            for quote_id in (getattr(sibling, "quote_entry_ids", None) or [])
        }
        preferred_sources = [
            source for source in all_sources if source.id not in blocked_source_ids
        ]
        chunks = preferred_sources or all_sources
        recent_chunk_ids = set() if preferred_sources else blocked_source_ids
        file_names = {}
    else:
        all_chunks = _get_chunks(db, book_id)
        if source_mode == "pdf" and not all_chunks:
            raise ValueError("没有可用于出题的 PDF 原文")
        blocked_source_ids = {
            chunk_id
            for sibling in same_type_questions
            for chunk_id in (getattr(sibling, "source_chunk_ids", None) or [])
        }
        preferred_chunks = [
            chunk for chunk in all_chunks if chunk.id not in blocked_source_ids
        ]
        chunks = preferred_chunks or all_chunks
        recent_chunk_ids = set() if preferred_chunks else blocked_source_ids
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
            generation_theme=generation_theme,
            theme_requirements=_theme_requirements(generation_theme, theme_config),
            allowed_question_subtypes=list(theme_config.get("question_subtypes", [])),
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
        _prepare_generated_question(item)
        next_question["source_chunk_ids"] = item.source_chunk_ids
        next_question["question_subtype"] = item.question_subtype
        next_question["quote_entry_ids"] = item.quote_entry_ids
        next_question["source_segment_ids"] = item.source_segment_ids
        next_question["fact_key"] = item.fact_key
        next_question["fact_claim"] = item.fact_claim
        next_question["semantic_signature"] = item.semantic_signature
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
            "正在准备原文片段"
            if task.source_mode == "pdf"
            else (
                "正在准备可信台词"
                if task.source_mode == "material"
                else "正在准备资源信息"
            )
        )
        db.commit()

        try:
            book = db.get(Book, task.book_id)
            if not book:
                raise RuntimeError("未找到这本书")
            theme_config = dict(task.theme_config or {})
            if task.source_mode == "material":
                chunks = _get_quote_sources(db, task.book_id, theme_config)
                if len(chunks) < task.total_questions:
                    raise RuntimeError("符合专题范围的可信台词数量不足")
                file_names = {}
                recent_chunk_ids = _recent_quote_ids(db, task.book_id)
            else:
                chunks = _get_chunks(db, task.book_id, task.page_start, task.page_end)
                if task.source_mode == "pdf" and not chunks:
                    raise RuntimeError("没有可用于出题的 PDF 原文")
                file_names = _chunk_file_names(db, chunks)
                recent_chunk_ids = _recent_chunk_ids(db, task.book_id)
            generation_number = db.scalar(
                select(func.count(Quiz.id)).where(Quiz.book_id == task.book_id)
            ) or 0
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
            generated: list[GeneratedQuestion] = []
            rejected_candidates: list[GeneratedQuestion] = []
            for position, question_type in enumerate(_question_types(task), start=1):
                task.current_question_position = position
                task.current_phase = f"正在生成第 {position} / {task.total_questions} 道{question_type_label(question_type)}"
                db.commit()
                item: GeneratedQuestion | None = None
                for attempt in range(3):
                    result = provider.generate_questions(
                        chunks=chunks,
                        file_names=file_names,
                        single_count=1 if question_type == "single" else 0,
                        multiple_count=1 if question_type == "multiple" else 0,
                        short_count=1 if question_type == "short" else 0,
                        difficulty=task.difficulty,
                        generation_number=generation_number + position - 1 + attempt,
                        recent_chunk_ids=recent_chunk_ids,
                        duration_minutes=task.duration_minutes,
                        book_title=book.title,
                        author=book.author,
                        resource_type=book.resource_type,
                        source_mode=task.source_mode,
                        question_exclusions=[
                            *(_question_exclusion_payload(item) for item in generated),
                            *(
                                _generated_question_exclusion_payload(item)
                                for item in rejected_candidates
                            ),
                        ],
                        regeneration_guidance=(
                            f"本次是第 {position} 道题，必须考察一个尚未出现的独立事实。"
                            "仅更换题干措辞、题型或选项顺序不算新事实。"
                            + (f"这是第 {attempt + 1} 次尝试，请避开已列出的事实。" if attempt else "")
                        ),
                        generation_theme=task.generation_theme,
                        theme_requirements=_theme_requirements(
                            task.generation_theme, theme_config
                        ),
                        allowed_question_subtypes=list(
                            theme_config.get("question_subtypes", [])
                        ),
                    )
                    if len(result) != 1:
                        raise RuntimeError(f"第 {position} 道题生成结果数量不正确")
                    candidate = _prepare_generated_question(result[0])
                    if _is_duplicate_question(candidate, generated, rejected_candidates):
                        rejected_candidates.append(candidate)
                        task.current_phase = f"第 {position} 道题与已有事实重复，正在重新生成"
                        db.commit()
                        continue
                    item = candidate
                    break
                if item is None:
                    raise RuntimeError(
                        f"第 {position} 道题连续重复已有事实，当前资料中可区分的独立事实不足；请降低题量或扩大出题范围"
                    )
                generated.append(item)
                recent_chunk_ids.update(item.source_chunk_ids)
                recent_chunk_ids.update(item.quote_entry_ids)
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

            theme_label = {
                "classic_quotes": "经典台词专题",
                "character": "角色专题",
            }.get(task.generation_theme, "复习试卷")
            quiz = Quiz(
                book_id=task.book_id,
                title=f"第 {generation_number + 1} 套{theme_label}",
                difficulty=task.difficulty,
                duration_minutes=task.duration_minutes,
                status="ready",
                source_mode=task.source_mode,
                generation_theme=task.generation_theme,
                theme_config=theme_config,
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
                        question_subtype=item.question_subtype,
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
                        quote_entry_ids=item.quote_entry_ids,
                        source_segment_ids=item.source_segment_ids,
                        fact_key=item.fact_key,
                        fact_claim=item.fact_claim,
                        semantic_signature=item.semantic_signature,
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
