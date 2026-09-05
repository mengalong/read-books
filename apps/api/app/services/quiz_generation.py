from __future__ import annotations

import copy
import re
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import (
    Book,
    ContentChunk,
    ModelUsageRecord,
    PdfDocument,
    PlotEvent,
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
    TrustedPlotSource,
    compact_text,
    get_quiz_provider,
    parse_json_object,
)
from app.services.material_understanding import get_understanding_context
from app.services.question_dedup import (
    question_keywords,
    questions_test_same_fact,
    refresh_question_signature,
    signature_for_question,
)
from app.services.resource_types import resource_type_label
from app.services.score_allocation import (
    QUIZ_TOTAL_SCORE,
    allocate_question_scores,
    normalize_rubric_scores,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

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

# The complete historical set is still loaded for the server-side duplicate guard. Only a
# small, relevant fact summary is sent to the model so prompt size does not grow with every
# quiz ever generated for a book.
HISTORICAL_FACT_PROMPT_LIMIT = 10
HISTORICAL_FACT_PROMPT_CHAR_BUDGET = 6_000


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
    confirmed_quote = db.scalar(
        select(QuoteEntry.id)
        .where(
            QuoteEntry.book_id == book_id,
            QuoteEntry.review_status == "confirmed",
            QuoteEntry.enabled_for_generation.is_(True),
        )
        .limit(1)
    )
    confirmed_plot = db.scalar(
        select(PlotEvent.id).where(
            PlotEvent.book_id == book_id,
            PlotEvent.review_status == "confirmed",
            PlotEvent.enabled_for_generation.is_(True),
        ).limit(1)
    )
    # A resource can be comprehensive even when it has no PDF. Plot summaries and
    # trusted dialogue must therefore enter the same combined strategy as PDF-backed
    # resources instead of letting the dialogue source win by fallback order.
    if confirmed_quote and confirmed_plot:
        return "combined"
    if completed_chunk and (confirmed_quote or confirmed_plot):
        return "combined"
    if completed_chunk:
        return "pdf"
    if confirmed_quote:
        return "material"
    if confirmed_plot:
        return "plot"

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
    if source_mode in {"material", "plot", "model_knowledge"} and (payload.page_start or payload.page_end):
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
    task.question_states = _initial_question_states(task)
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


def resume_generation_task(db: Session, task_id: str) -> QuizGenerationTask:
    task = db.get(QuizGenerationTask, task_id)
    if task is None:
        raise ValueError("未找到这次出题任务")
    if task.status not in {"awaiting_intervention", "failed"}:
        raise ValueError("当前出题任务不需要人工恢复")
    task.status = "pending"
    task.error_message = None
    task.current_phase = "等待继续出题"
    db.commit()
    threading.Thread(target=run_generation_task, args=(task.id,), daemon=True).start()
    db.refresh(task)
    return task


def _task_was_cancelled(db: Session, task_id: str) -> bool:
    """Read cancellation state from a fresh query while a worker is calling the model."""
    status = db.scalar(
        select(QuizGenerationTask.status)
        .where(QuizGenerationTask.id == task_id)
        .execution_options(populate_existing=True)
    )
    return status in {None, "cancelled"}


def cancel_generation_task(db: Session, task_id: str) -> QuizGenerationTask:
    task = db.get(QuizGenerationTask, task_id)
    if task is None:
        raise ValueError("未找到这次出题任务")
    if task.status == "completed":
        raise ValueError("已经完成的出题任务不能终止")
    if task.status == "cancelled":
        return task
    task.status = "cancelled"
    task.current_phase = "已手动终止"
    task.error_message = "出题任务已由用户手动终止"
    if task.task_type == "pre_generation":
        book = db.get(Book, task.book_id)
        if book:
            book.pre_generation_status = "failed"
            book.pre_generation_error = task.error_message
            book.pre_generation_quiz_id = None
    db.commit()
    db.refresh(task)
    return task


def delete_generation_task(db: Session, task_id: str) -> None:
    task = db.get(QuizGenerationTask, task_id)
    if task is None:
        raise ValueError("未找到这次出题任务")
    if task.status in {"pending", "processing"}:
        raise ValueError("进行中的任务请先手动终止，再删除任务")
    book = db.get(Book, task.book_id)
    if task.task_type == "pre_generation" and book:
        book.pre_generation_enabled = False
        book.pre_generation_status = "disabled"
        book.pre_generation_error = None
        book.pre_generation_quiz_id = None
    if task.quiz_id:
        quiz = db.get(Quiz, task.quiz_id)
        if quiz and quiz.generation_task_id == task.id:
            quiz.generation_task_id = None
    db.execute(delete(ModelUsageRecord).where(ModelUsageRecord.task_id == task.id))
    db.delete(task)
    db.commit()


def apply_generation_intervention(
    db: Session,
    task_id: str,
    position: int,
    *,
    action: str,
    question_payload: dict[str, Any] | None = None,
) -> QuizGenerationTask:
    task = db.get(QuizGenerationTask, task_id)
    if task is None:
        raise ValueError("未找到这次出题任务")
    if task.status == "cancelled":
        raise ValueError("已终止的出题任务不能继续人工处理")
    if task.status == "completed":
        raise ValueError("已经完成的出题任务不能继续人工处理")
    if task.status not in {"pending", "processing", "awaiting_intervention", "failed"}:
        raise ValueError("当前出题任务不支持人工介入")
    was_running = task.status in {"pending", "processing"}
    if was_running and action in {"retry", "replace"}:
        raise ValueError("进行中的任务只能人工调整或确认题目，不能重试或换题")
    states = copy.deepcopy(task.question_states or _initial_question_states(task))
    if position < 1 or position > len(states):
        raise ValueError("未找到需要处理的题目")
    state = states[position - 1]
    if action == "accept":
        if not isinstance(state.get("question"), dict):
            raise ValueError("当前题目没有可确认的草稿，请先人工编辑或重新出题")
        state["status"] = "confirmed"
    elif action in {"retry", "replace"}:
        state["status"] = "pending"
        state["error_message"] = None
        if action == "replace" and isinstance(state.get("question"), dict):
            state.setdefault("rejected_questions", []).append(state["question"])
            state["question"] = None
    elif action == "edit":
        if not question_payload:
            raise ValueError("人工调整需要提供题目内容")
        current = dict(state.get("question") or {})
        current.update(question_payload)
        current["question_type"] = state.get("question_type")
        if not str(current.get("prompt") or "").strip():
            raise ValueError("题干不能为空")
        current.setdefault("options", [])
        current.setdefault("correct_answers", [])
        current.setdefault("explanation", "")
        current.setdefault("knowledge_point", "人工调整")
        current.setdefault("estimated_seconds", 45)
        current.setdefault("reference_answer", None)
        current.setdefault("grading_rubric", [])
        current.setdefault("source_chunk_ids", [])
        current.setdefault("source_evidence", [])
        current.setdefault("quote_entry_ids", [])
        current.setdefault("plot_event_ids", [])
        current.setdefault("source_segment_ids", [])
        current.setdefault("fact_key", "")
        current.setdefault("fact_claim", current["prompt"])
        current.setdefault("semantic_signature", {})
        current.setdefault("max_score", 0)
        state["question"] = current
        state["status"] = "confirmed"
    else:
        raise ValueError("不支持的人工介入动作")
    state["error_message"] = None
    state["updated_at"] = utc_now().isoformat()
    task.question_states = states
    task.completed_questions = sum(
        _finalized_state_status(current.get("status")) for current in states
    )
    if was_running and action in {"edit", "accept"}:
        task.status = "processing"
        task.error_message = None
        task.current_phase = f"已人工更新第 {position} 道题，继续生成其余题目"
    else:
        task.status = "pending"
        task.error_message = None
        task.current_phase = f"等待继续处理第 {position} 道题"
    db.commit()
    if not was_running:
        threading.Thread(target=run_generation_task, args=(task.id,), daemon=True).start()
    db.refresh(task)
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


MODEL_KNOWLEDGE_MATERIAL_MIN_MATCHES = 1  # 3+ char n-gram overlaps are already high-precision


def _get_all_confirmed_quote_sources(db: Session, book_id: str) -> list[TrustedQuoteSource]:
    """Return every confirmed, generation-enabled quote for a book regardless of theme scope."""
    rows = db.execute(
        select(QuoteEntry, ResourceMaterial)
        .join(ResourceMaterial, ResourceMaterial.id == QuoteEntry.material_id)
        .where(
            QuoteEntry.book_id == book_id,
            QuoteEntry.review_status == "confirmed",
            QuoteEntry.enabled_for_generation.is_(True),
        )
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


def _get_plot_sources(db: Session, book_id: str) -> list[TrustedPlotSource]:
    rows = db.execute(
        select(PlotEvent, ResourceMaterial)
        .join(ResourceMaterial, ResourceMaterial.id == PlotEvent.material_id)
        .where(
            PlotEvent.book_id == book_id,
            PlotEvent.review_status == "confirmed",
            PlotEvent.enabled_for_generation.is_(True),
            PlotEvent.question_usable == "true",
        )
        .order_by(
            PlotEvent.season_number,
            PlotEvent.episode_number,
            PlotEvent.sequence,
            PlotEvent.created_at,
        )
    ).all()
    return [
        TrustedPlotSource(
            id=event.id,
            event_id=event.event_id,
            material_id=material.id,
            file_name=material.file_name,
            material_type=material.material_type,
            content="；".join(
                value
                for value in (
                    event.summary,
                    event.cause,
                    event.action,
                    event.result,
                    event.future_impact,
                )
                if value
            ),
            summary=event.summary,
            level=event.level,
            season_number=event.season_number,
            episode_number=event.episode_number,
            sequence=event.sequence,
            title=event.title,
            cause=event.cause,
            action=event.action,
            result=event.result,
            future_impact=event.future_impact,
            characters=list(event.characters or []),
            relationship_changes=list(event.relationship_changes or []),
            conflict_tags=list(event.conflict_tags or []),
            theme_tags=list(event.theme_tags or []),
            importance=event.importance,
            source_refs=list(event.source_refs or []),
            confidence=event.confidence,
        )
        for event, material in rows
    ]


def _matching_quote_sources_for_question(
    sources: list[TrustedQuoteSource], question: Any
) -> list[TrustedQuoteSource]:
    """Pick confirmed quotes relevant to a single question via a keyword pre-filter.

    This lets a question regenerated after new trusted material was uploaded reuse that
    material even when it falls outside the quiz's original theme scope, without sending
    the model every confirmed quote in the book.
    """
    signature = signature_for_question(question)
    keywords = question_keywords(
        getattr(question, "knowledge_point", None),
        getattr(question, "prompt", None),
        signature.get("fact_subject"),
        signature.get("fact_claim"),
        signature.get("fact_context"),
    )
    if not keywords:
        return []
    scored: list[tuple[int, TrustedQuoteSource]] = []
    for source in sources:
        source_keywords = question_keywords(source.content, source.speaker, source.context)
        overlap = len(keywords & source_keywords)
        if overlap:
            scored.append((overlap, source))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [source for _, source in scored[:20]]


def _background_context_for_chunks(
    db: Session, book_id: str, chunks: list[ContentChunk | TrustedQuoteSource | TrustedPlotSource]
) -> str:
    episode_numbers = {
        chunk.episode_number
        for chunk in chunks
        if isinstance(chunk, (TrustedQuoteSource, TrustedPlotSource))
        and chunk.episode_number is not None
    }
    return get_understanding_context(db, book_id, episode_numbers=episode_numbers or None)


def _combined_sources(
    db: Session,
    book_id: str,
    page_start: int | None = None,
    page_end: int | None = None,
) -> tuple[list[ContentChunk | TrustedQuoteSource | TrustedPlotSource], dict[str, str]]:
    pdf_chunks = _get_chunks(db, book_id, page_start, page_end)
    quote_sources = _get_all_confirmed_quote_sources(db, book_id)
    plot_sources = _get_plot_sources(db, book_id)
    if not pdf_chunks and not quote_sources and not plot_sources:
        return [], {}
    return [*pdf_chunks, *quote_sources, *plot_sources], _chunk_file_names(db, pdf_chunks)


def _theme_requirements(generation_theme: str, theme_config: dict[str, Any]) -> str:
    if generation_theme == "general":
        return "围绕资源整体内容出题，不限定角色或台词专题。"
    characters = "、".join(theme_config.get("character_names", [])) or "全部已确认角色"
    subtypes = "、".join(theme_config.get("question_subtypes", []))
    if generation_theme == "classic_quotes":
        return (
            f"仅围绕可信资料中的经典台词出题；角色范围：{characters}；"
            f"允许的考察角度：{subtypes}。题目可以逐字引用台词，也可以自然转述或描述台词所表达的情境；"
            "quote_entry_ids 只用于来源追溯。对话场景只考察语境、人物处境和事件背景，不考精确集数、时间点或出处位置。"
        )
    return (
        f"仅围绕角色 {characters} 出题；允许的考察角度：{subtypes}。"
        "涉及台词时可以逐字引用、自然转述或概括含义；必须能从对应可信资料推出，不考精确集数、时间点或出处位置。"
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


def _recent_plot_ids(db: Session, book_id: str) -> set[str]:
    recent_rows = db.scalars(
        select(Question.plot_event_ids)
        .join(Quiz, Quiz.id == Question.quiz_id)
        .where(Quiz.book_id == book_id)
        .order_by(Quiz.created_at.desc())
        .limit(80)
    ).all()
    return {event_id for row in recent_rows for event_id in (row or [])}


def _historical_questions(db: Session, book_id: str) -> list[Question]:
    questions = list(
        db.scalars(
            select(Question)
            .join(Quiz, Quiz.id == Question.quiz_id)
            .where(Quiz.book_id == book_id)
            .order_by(Quiz.created_at.desc(), Question.position)
        ).all()
    )
    for question in questions:
        if not question.fact_key or not question.fact_claim or not question.semantic_signature:
            refresh_question_signature(question)
    return questions


def _exclusion_relevance_text(chunks: Iterable[Any], *, limit: int = 24) -> str:
    """Build a bounded keyword context for selecting model-side history."""
    parts: list[str] = []
    for chunk in list(chunks)[:limit]:
        parts.extend(
            str(value)
            for value in (
                getattr(chunk, "content", ""),
                getattr(chunk, "speaker", ""),
                getattr(chunk, "context", ""),
            )
            if value
        )
    return compact_text(" ".join(parts), 8_000)


def _compact_exclusions(
    questions: Iterable[Any],
    *,
    role: str | None = None,
    relevance_text: str = "",
    limit: int = HISTORICAL_FACT_PROMPT_LIMIT,
    char_budget: int = HISTORICAL_FACT_PROMPT_CHAR_BUDGET,
) -> list[dict[str, object]]:
    """Return compact, relevant fact summaries for the model prompt.

    This is intentionally separate from `_is_duplicate_question`, which continues to
    compare against the complete historical question set in the API process.
    """
    entries: list[tuple[int, int, dict[str, object]]] = []
    seen_fact_keys: set[str] = set()
    relevance_tokens = question_keywords(relevance_text)
    for index, question in enumerate(questions):
        signature = signature_for_question(question)
        fact_key = str(signature["fact_key"])
        if fact_key and fact_key in seen_fact_keys:
            continue
        if fact_key:
            seen_fact_keys.add(fact_key)
        payload = _question_exclusion_payload(question, role=role or "historical_question")
        payload_tokens = question_keywords(
            payload.get("fact_claim"),
            payload.get("fact_subject"),
            payload.get("fact_relation"),
            payload.get("fact_context"),
            payload.get("answer_signature"),
        )
        entries.append((len(relevance_tokens & payload_tokens), index, payload))
    entries.sort(key=lambda item: (-item[0], item[1]))
    exclusions: list[dict[str, object]] = []
    used_chars = 2
    for _score, _order, payload in entries:
        if len(exclusions) >= limit:
            break
        serialized_size = len(str(payload))
        if exclusions and used_chars + serialized_size > char_budget:
            continue
        exclusions.append(payload)
        used_chars += serialized_size
    return exclusions


def _historical_question_exclusions(
    questions: list[Question], relevance_text: str = ""
) -> list[dict[str, object]]:
    return _compact_exclusions(questions, relevance_text=relevance_text)


def _normalize_question_text(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def _prepare_generated_question(question: GeneratedQuestion) -> GeneratedQuestion:
    refresh_question_signature(question)
    return question


def _question_exclusion_payload(
    question: Any, role: str = "same_type_reference"
) -> dict[str, object]:
    semantic_signature = signature_for_question(question)
    return {
        "role": role,
        "position": getattr(question, "position", None),
        "question_type": getattr(question, "question_type", ""),
        "question_subtype": str(getattr(question, "question_subtype", "general")),
        "fact_claim": compact_text(str(semantic_signature.get("fact_claim", "")), 180),
        "fact_subject": compact_text(str(semantic_signature.get("fact_subject", "")), 80),
        "fact_relation": compact_text(str(semantic_signature.get("fact_relation", "")), 80),
        "fact_context": compact_text(str(semantic_signature.get("fact_context", "")), 120),
        "answer_signature": [
            compact_text(str(value), 60)
            for value in list(semantic_signature.get("answer_signature") or [])[:4]
        ],
    }


def _generated_question_exclusion_payload(question: GeneratedQuestion) -> dict[str, object]:
    _prepare_generated_question(question)
    return _question_exclusion_payload(question, role="rejected_candidate")


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
    historical_questions: list[Any] | None = None,
) -> bool:
    _prepare_generated_question(candidate)
    if any(
        questions_test_same_fact(candidate, historical)
        for historical in (historical_questions or [])
    ):
        return True
    if any(questions_test_same_fact(candidate, sibling) for sibling in siblings):
        return True
    if any(questions_test_same_fact(candidate, previous) for previous in recent_candidates):
        return True
    candidate_prompt = _normalize_question_text(candidate.prompt)
    candidate_knowledge = _normalize_question_text(candidate.knowledge_point)
    candidate_sources = set(candidate.source_chunk_ids or [])
    candidate_quotes = set(candidate.quote_entry_ids or [])
    candidate_plots = set(candidate.plot_event_ids or [])
    for question in siblings:
        question_sources = set(getattr(question, "source_chunk_ids", None) or [])
        question_quotes = set(getattr(question, "quote_entry_ids", None) or [])
        question_plots = set(getattr(question, "plot_event_ids", None) or [])
        if candidate_sources and question_sources and candidate_sources & question_sources:
            return True
        if candidate_quotes and question_quotes and candidate_quotes & question_quotes:
            return True
        if candidate_plots and question_plots and candidate_plots & question_plots:
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
    all_other_questions = [item for item in quiz.questions if item.id != question.id]
    same_type_questions = [
        item
        for item in all_other_questions
        if item.question_type == question.question_type
    ]
    comparison_questions = [question, *all_other_questions]
    theme_config = dict(quiz.theme_config or {})
    effective_source_mode = quiz.source_mode
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
    elif quiz.source_mode in {"plot", "combined"}:
        all_sources, file_names = (
            (_get_plot_sources(db, quiz.book_id), {})
            if quiz.source_mode == "plot"
            else _combined_sources(db, quiz.book_id)
        )
        if not all_sources:
            raise ValueError("没有可用于重出题的剧情或可信资料，资料可能已删除或停用")
        blocked_source_ids = {
            source_id
            for sibling in same_type_questions
            for source_id in (
                (sibling.source_chunk_ids or [])
                + (sibling.quote_entry_ids or [])
                + (sibling.plot_event_ids or [])
            )
        }
        preferred_sources = [source for source in all_sources if source.id not in blocked_source_ids]
        chunks = preferred_sources or all_sources
        recent_chunk_ids = set() if preferred_sources else blocked_source_ids
    else:
        matched_sources = _matching_quote_sources_for_question(
            _get_all_confirmed_quote_sources(db, quiz.book_id), question
        )
        if len(matched_sources) >= MODEL_KNOWLEDGE_MATERIAL_MIN_MATCHES:
            effective_source_mode = "material"
            blocked_source_ids = {
                quote_id
                for sibling in same_type_questions
                for quote_id in (sibling.quote_entry_ids or [])
            }
            preferred_sources = [
                source for source in matched_sources if source.id not in blocked_source_ids
            ]
            chunks = preferred_sources or matched_sources
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
            question_position=question.position,
        ),
    )
    question_exclusions = [
        _question_exclusion_payload(question, role="current_question"),
        *(_question_exclusion_payload(item) for item in all_other_questions),
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
            source_mode=effective_source_mode,
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
            background_context=_background_context_for_chunks(db, quiz.book_id, chunks),
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
        question.plot_event_ids = item.plot_event_ids
        question.source_segment_ids = item.source_segment_ids
        question.fact_key = item.fact_key
        question.fact_claim = item.fact_claim
        question.semantic_signature = item.semantic_signature
        question.source_evidence = item.source_evidence
        question.source_mode = (
            effective_source_mode if effective_source_mode != quiz.source_mode else None
        )
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
    all_other_questions = [
        SimpleNamespace(**item)
        for item in sibling_questions
        if str(item.get("id")) != str(current_question.get("id"))
    ]
    same_type_questions = [
        item
        for item in all_other_questions
        if item.question_type == current_question.get("question_type")
    ]
    comparison_questions = [current, *all_other_questions]
    theme_config = dict(theme_config or {})
    effective_source_mode = source_mode
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
        matched_sources = _matching_quote_sources_for_question(
            _get_all_confirmed_quote_sources(db, book_id), current
        )
        if len(matched_sources) >= MODEL_KNOWLEDGE_MATERIAL_MIN_MATCHES:
            effective_source_mode = "material"
            blocked_source_ids = {
                quote_id
                for sibling in same_type_questions
                for quote_id in (getattr(sibling, "quote_entry_ids", None) or [])
            }
            preferred_sources = [
                source for source in matched_sources if source.id not in blocked_source_ids
            ]
            chunks = preferred_sources or matched_sources
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
            question_position=current.position,
        ),
    )
    question_exclusions = [
        _question_exclusion_payload(current, role="current_question"),
        *(_question_exclusion_payload(item) for item in all_other_questions),
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
            source_mode=effective_source_mode,
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
            background_context=_background_context_for_chunks(db, book_id, chunks),
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
        next_question["plot_event_ids"] = item.plot_event_ids
        next_question["source_segment_ids"] = item.source_segment_ids
        next_question["fact_key"] = item.fact_key
        next_question["fact_claim"] = item.fact_claim
        next_question["semantic_signature"] = item.semantic_signature
        next_question["source_evidence"] = item.source_evidence
        next_question["source_mode"] = (
            effective_source_mode if effective_source_mode != source_mode else None
        )
        return next_question

    raise ValueError("重出失败，请先调整同类题目或原文来源后再试")


def _question_types(task: QuizGenerationTask) -> Iterable[str]:
    for question_type, count in (
        ("single", task.single_count),
        ("multiple", task.multiple_count),
        ("short", task.short_count),
    ):
        yield from (question_type for _ in range(count))


def _source_focus_for_question(
    source_mode: str,
    chunks: list[ContentChunk | TrustedQuoteSource | TrustedPlotSource],
    position: int,
    total_questions: int,
) -> str:
    """Allocate general-comprehension questions across content and dialogue sources."""
    has_dialogue = any(isinstance(chunk, TrustedQuoteSource) for chunk in chunks)
    has_content = any(isinstance(chunk, (ContentChunk, TrustedPlotSource)) for chunk in chunks)
    if not (has_dialogue and has_content):
        return "dialogue" if has_dialogue else "content"
    content_count = max(1, round(total_questions * 0.7))
    dialogue_count = max(1, round(total_questions * 0.2))
    if position <= content_count:
        return "content"
    if position <= content_count + dialogue_count:
        return "dialogue"
    return "integrated"


def _initial_question_states(task: QuizGenerationTask) -> list[dict[str, Any]]:
    return [
        {
            "position": position,
            "question_type": question_type,
            "status": "pending",
            "attempts": 0,
            "error_message": None,
            "question": None,
            "updated_at": utc_now().isoformat(),
        }
        for position, question_type in enumerate(_question_types(task), start=1)
    ]


def _generated_question_from_state(value: dict[str, Any]) -> GeneratedQuestion:
    fields = {
        "question_type": str(value.get("question_type") or "single"),
        "prompt": str(value.get("prompt") or ""),
        "options": list(value.get("options") or []),
        "correct_answers": list(value.get("correct_answers") or []),
        "explanation": str(value.get("explanation") or ""),
        "knowledge_point": str(value.get("knowledge_point") or ""),
        "estimated_seconds": int(value.get("estimated_seconds") or 0),
        "reference_answer": value.get("reference_answer"),
        "grading_rubric": list(value.get("grading_rubric") or []),
        "source_chunk_ids": list(value.get("source_chunk_ids") or []),
        "source_evidence": list(value.get("source_evidence") or []),
        "max_score": float(value.get("max_score") or 0),
        "question_subtype": str(value.get("question_subtype") or "general"),
        "quote_entry_ids": list(value.get("quote_entry_ids") or []),
        "plot_event_ids": list(value.get("plot_event_ids") or []),
        "source_segment_ids": list(value.get("source_segment_ids") or []),
        "fact_key": str(value.get("fact_key") or ""),
        "fact_claim": str(value.get("fact_claim") or ""),
        "semantic_signature": dict(value.get("semantic_signature") or {}),
        "validation_warnings": list(value.get("validation_warnings") or []),
    }
    return GeneratedQuestion(**fields)


def _state_question_payload(question: GeneratedQuestion) -> dict[str, Any]:
    return asdict(question)


def _finalized_state_status(value: str | None) -> bool:
    return value in {"ready", "confirmed"}


def _set_task_failure(db: Session, task_id: str, error: Exception) -> None:
    db.rollback()
    task = db.get(QuizGenerationTask, task_id)
    if not task:
        return
    db.refresh(task)
    if task.status == "cancelled":
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


def _latest_model_draft(
    db: Session, task_id: str, position: int, question_type: str
) -> dict[str, Any] | None:
    """Recover the raw question fields when structural/source validation rejects a call."""
    record = db.scalar(
        select(ModelUsageRecord)
        .where(
            ModelUsageRecord.task_id == task_id,
            ModelUsageRecord.question_position == position,
        )
        .order_by(ModelUsageRecord.created_at.desc(), ModelUsageRecord.call_number.desc())
    )
    if record is None or not record.model_response:
        return None
    try:
        payload = parse_json_object(record.model_response)
    except (RuntimeError, ValueError, TypeError):
        return None
    questions = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(questions, list) or not questions or not isinstance(questions[0], dict):
        return None
    draft = dict(questions[0])
    draft["question_type"] = question_type
    draft.setdefault("options", [])
    draft.setdefault("correct_answers", [])
    draft.setdefault("explanation", "")
    draft.setdefault("knowledge_point", "人工调整")
    draft.setdefault("estimated_seconds", 45)
    draft.setdefault("reference_answer", None)
    draft.setdefault("grading_rubric", [])
    draft.setdefault("source_chunk_ids", [])
    draft.setdefault("quote_entry_ids", [])
    draft.setdefault("plot_event_ids", [])
    draft.setdefault("source_segment_ids", [])
    draft.setdefault("source_evidence", [])
    draft.setdefault("fact_key", "")
    draft.setdefault("fact_claim", draft.get("prompt", ""))
    draft.setdefault("semantic_signature", {})
    draft.setdefault("max_score", 0)
    return draft


def run_generation_task(task_id: str) -> None:
    with SessionLocal() as db:
        task = db.get(QuizGenerationTask, task_id)
        if not task or task.status not in {"pending", "processing"}:
            return
        if _task_was_cancelled(db, task_id):
            return
        task.status = "processing"
        task.current_phase = (
            "正在准备原文片段"
            if task.source_mode == "pdf"
            else (
                "正在准备可信台词"
                if task.source_mode == "material"
                else (
                    "正在准备综合剧情与台词来源"
                    if task.source_mode == "combined"
                    else "正在准备资源信息"
                )
            )
        )
        db.commit()

        try:
            book = db.get(Book, task.book_id)
            if not book:
                raise RuntimeError("未找到这本书")
            theme_config = dict(task.theme_config or {})
            if task.source_mode == "material":
                chunks = (
                    _get_all_confirmed_quote_sources(db, task.book_id)
                    if task.generation_theme == "general"
                    else _get_quote_sources(db, task.book_id, theme_config)
                )
                if len(chunks) < task.total_questions:
                    raise RuntimeError("符合专题范围的可信台词数量不足")
                file_names = {}
                recent_chunk_ids = _recent_quote_ids(db, task.book_id)
            elif task.source_mode == "plot":
                chunks = _get_plot_sources(db, task.book_id)
                if len(chunks) < task.total_questions:
                    raise RuntimeError("符合条件的已确认剧情事件数量不足")
                file_names = {}
                recent_chunk_ids = _recent_plot_ids(db, task.book_id)
            elif task.source_mode == "combined":
                chunks, file_names = _combined_sources(
                    db, task.book_id, task.page_start, task.page_end
                )
                if not chunks:
                    raise RuntimeError("没有可用于综合出题的可信 PDF、剧情或台词资料")
                recent_chunk_ids = (
                    _recent_chunk_ids(db, task.book_id)
                    | _recent_quote_ids(db, task.book_id)
                    | _recent_plot_ids(db, task.book_id)
                )
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
                task_id=task.id,
            )
            provider = get_quiz_provider(
                settings,
                get_effective_model_configuration(db, settings),
                get_effective_prompt_templates(db),
                usage_context,
            )
            question_states = copy.deepcopy(
                task.question_states or _initial_question_states(task)
            )
            if len(question_states) != task.total_questions:
                question_states = _initial_question_states(task)
            task.question_states = question_states
            db.commit()
            historical_questions = _historical_questions(db, task.book_id)
            historical_exclusions = _historical_question_exclusions(
                historical_questions,
                " ".join(
                    [
                        _exclusion_relevance_text(chunks),
                        task.generation_theme,
                        " ".join(_question_types(task)),
                    ]
                ),
            )
            background_context = _background_context_for_chunks(db, task.book_id, chunks)
            generated = [
                _generated_question_from_state(state["question"])
                for state in question_states
                if _finalized_state_status(state.get("status")) and state.get("question")
            ]
            rejected_candidates = [
                _generated_question_from_state(rejected)
                for state in question_states
                for rejected in state.get("rejected_questions", [])
                if isinstance(rejected, dict)
            ]
            for position, question_type in enumerate(_question_types(task), start=1):
                if _task_was_cancelled(db, task_id):
                    return
                db.refresh(task)
                question_states = copy.deepcopy(
                    task.question_states or _initial_question_states(task)
                )
                generated = [
                    _generated_question_from_state(state["question"])
                    for state in question_states
                    if _finalized_state_status(state.get("status")) and state.get("question")
                ]
                rejected_candidates = [
                    _generated_question_from_state(rejected)
                    for state in question_states
                    for rejected in state.get("rejected_questions", [])
                    if isinstance(rejected, dict)
                ]
                state = question_states[position - 1]
                if _finalized_state_status(state.get("status")) and state.get("question"):
                    continue
                task.current_question_position = position
                state["source_focus"] = _source_focus_for_question(
                    task.source_mode, chunks, position, task.total_questions
                )
                task.current_phase = f"正在生成第 {position} / {task.total_questions} 道{question_type_label(question_type)}"
                state["status"] = "generating"
                state["error_message"] = None
                state["updated_at"] = utc_now().isoformat()
                task.question_states = copy.deepcopy(question_states)
                db.commit()
                item: GeneratedQuestion | None = None
                last_candidate: GeneratedQuestion | None = None
                state_was_updated_while_generating = False
                for attempt in range(3):
                    if _task_was_cancelled(db, task_id):
                        return
                    provider.set_question_position(position)
                    state["attempts"] = int(state.get("attempts") or 0) + 1
                    task.question_states = copy.deepcopy(question_states)
                    task.current_phase = (
                        f"正在调用模型生成第 {position} / {task.total_questions} 道题"
                        f"（第 {state['attempts']} 次）"
                    )
                    db.commit()
                    try:
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
                                *historical_exclusions,
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
                            background_context=background_context,
                            source_focus=_source_focus_for_question(
                                task.source_mode,
                                chunks,
                                position,
                                task.total_questions,
                            ),
                        )
                        if _task_was_cancelled(db, task_id):
                            return
                        db.refresh(task)
                        latest_states = copy.deepcopy(
                            task.question_states or _initial_question_states(task)
                        )
                        latest_state = latest_states[position - 1]
                        if (
                            _finalized_state_status(latest_state.get("status"))
                            and latest_state.get("question")
                        ):
                            question_states = latest_states
                            generated = [
                                _generated_question_from_state(current["question"])
                                for current in question_states
                                if _finalized_state_status(current.get("status"))
                                and current.get("question")
                            ]
                            rejected_candidates = [
                                _generated_question_from_state(rejected)
                                for current in question_states
                                for rejected in current.get("rejected_questions", [])
                                if isinstance(rejected, dict)
                            ]
                            state_was_updated_while_generating = True
                            item = _generated_question_from_state(latest_state["question"])
                            break
                        if len(result) != 1:
                            raise RuntimeError(f"第 {position} 道题生成结果数量不正确")
                        candidate = _prepare_generated_question(result[0])
                    except Exception as exc:
                        if _task_was_cancelled(db, task_id):
                            return
                        state["question"] = _latest_model_draft(
                            db, task_id, position, question_type
                        )
                        state["status"] = "awaiting_intervention"
                        state["error_message"] = str(exc)[:1_000]
                        state["updated_at"] = utc_now().isoformat()
                        task.status = "awaiting_intervention"
                        task.current_phase = f"第 {position} 道题需要人工处理"
                        task.error_message = state["error_message"]
                        task.question_states = copy.deepcopy(question_states)
                        db.commit()
                        return
                    last_candidate = candidate
                    if _is_duplicate_question(
                        candidate,
                        generated,
                        rejected_candidates,
                        historical_questions,
                    ):
                        rejected_candidates.append(candidate)
                        task.current_phase = f"第 {position} 道题与已有事实重复，正在重新生成"
                        task.question_states = copy.deepcopy(question_states)
                        db.commit()
                        continue
                    item = candidate
                    break
                if item is None:
                    if _task_was_cancelled(db, task_id):
                        return
                    state["status"] = "awaiting_intervention"
                    state["question"] = (
                        _state_question_payload(last_candidate) if last_candidate else None
                    )
                    state["error_message"] = (
                        f"第 {position} 道题连续重复当前或历史试卷中的已有事实，"
                        "当前资料中可区分的独立事实不足；可以重试、替换或人工调整。"
                    )
                    state["updated_at"] = utc_now().isoformat()
                    task.status = "awaiting_intervention"
                    task.current_phase = f"第 {position} 道题需要人工处理"
                    task.error_message = state["error_message"]
                    task.question_states = copy.deepcopy(question_states)
                    db.commit()
                    return
                if state_was_updated_while_generating:
                    continue
                generated.append(item)
                if _task_was_cancelled(db, task_id):
                    return
                state["status"] = "ready"
                state["question"] = _state_question_payload(item)
                state["error_message"] = None
                state["updated_at"] = utc_now().isoformat()
                recent_chunk_ids.update(item.source_chunk_ids)
                recent_chunk_ids.update(item.quote_entry_ids)
                recent_chunk_ids.update(item.plot_event_ids)
                task.completed_questions = sum(
                    _finalized_state_status(current.get("status"))
                    for current in question_states
                )
                task.current_phase = f"已完成第 {position} / {task.total_questions} 道题"
                task.question_states = copy.deepcopy(question_states)
                db.commit()

            if _task_was_cancelled(db, task_id):
                return
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
            if _task_was_cancelled(db, task_id):
                return
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
                        plot_event_ids=item.plot_event_ids,
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
