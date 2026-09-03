"""Incremental summary generation for uploaded material (books/subtitles/dialogue sheets).

This module builds a lightweight understanding layer on top of `MaterialSegment` rows:
per-scope (chapter/episode/page-range) summaries plus one book-level summary. Summaries
are used only as background context for question generation prompts; they are never a
citable source of fact. The `_validate_questions` ID-existence checks in quiz_provider.py
remain the sole gate for what can be cited.

Incremental strategy: each scope's `content_signature` is a hash of the sorted segment ids
that belong to it. When new material is uploaded, only scopes whose segment set changed are
regenerated; unaffected scopes are left untouched. The book-level summary is regenerated only
when any child scope changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import Book, MaterialSegment, MaterialUnderstanding, ResourceMaterial
from app.services.model_config import EffectiveModelConfiguration, get_effective_model_configuration
from app.services.model_usage import ModelUsageContext, new_usage_context, record_model_usage, token_counts
from app.services.quiz_provider import compact_text, get_quiz_provider, parse_json_object

logger = logging.getLogger(__name__)

MAX_SCOPE_SEGMENT_CHARS = 6_000
MAX_SUMMARY_CHARS = 800
MAX_BOOK_SUMMARY_INPUT_CHARS = 6_000
PDF_PAGE_WINDOW = 20


@dataclass(frozen=True)
class ScopeGroup:
    scope_type: str
    scope_ref: str
    segment_ids: list[str]
    text: str


def _signature_for_ids(segment_ids: list[str]) -> str:
    normalized = "|".join(sorted(segment_ids))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _group_material_segments(segments: list[MaterialSegment]) -> list[ScopeGroup]:
    buckets: dict[str, list[MaterialSegment]] = {}
    order: list[str] = []
    for segment in segments:
        if segment.episode_number is not None:
            key = f"episode:{segment.episode_number}"
        elif segment.page_number is not None:
            key = f"page:{segment.page_number}"
        else:
            key = "material"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(segment)

    groups: list[ScopeGroup] = []
    for key in order:
        rows = sorted(buckets[key], key=lambda item: item.sequence)
        scope_type, scope_ref = key.split(":", 1) if ":" in key else ("material", "")
        lines = []
        for row in rows:
            prefix = f"{row.speaker}：" if row.speaker else ""
            lines.append(f"{prefix}{row.content}")
        text = "\n".join(lines)[:MAX_SCOPE_SEGMENT_CHARS]
        groups.append(
            ScopeGroup(
                scope_type=scope_type if scope_type in {"episode", "page"} else "material",
                scope_ref=scope_ref,
                segment_ids=[row.id for row in rows],
                text=text,
            )
        )
    return groups


def _chunk_pdf_pages(pages: list[tuple[int, str, str]]) -> list[ScopeGroup]:
    """Group PDF ContentChunk rows into fixed-size page windows for summarization."""
    groups: dict[tuple[int, int], list[tuple[int, str, str]]] = {}
    order: list[tuple[int, int]] = []
    for chunk_id, page_number, content in pages:
        window_start = ((page_number - 1) // PDF_PAGE_WINDOW) * PDF_PAGE_WINDOW + 1
        window_end = window_start + PDF_PAGE_WINDOW - 1
        key = (window_start, window_end)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((chunk_id, page_number, content))

    result: list[ScopeGroup] = []
    for window_start, window_end in order:
        rows = groups[(window_start, window_end)]
        text = "\n".join(content for _, _, content in rows)[:MAX_SCOPE_SEGMENT_CHARS]
        result.append(
            ScopeGroup(
                scope_type="page_range",
                scope_ref=f"{window_start}-{window_end}",
                segment_ids=[chunk_id for chunk_id, _, _ in rows],
                text=text,
            )
        )
    return result


def _summarize_text(
    provider: Any,
    configuration: EffectiveModelConfiguration,
    usage_context: ModelUsageContext,
    label: str,
    text: str,
) -> tuple[str, dict[str, Any]]:
    if configuration.provider_mode == "mock":
        return compact_text(text, MAX_SUMMARY_CHARS), {}
    messages = [
        {
            "role": "system",
            "content": (
                "你是资料理解摘要器，只输出 JSON，不要输出 Markdown。摘要仅用于帮助后续出题时"
                "理解上下文背景，不会被当作可直接引用的原文，因此不需要逐字保留台词，但不得添加"
                "原文中不存在的事实、人物或情节。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请为下面这段《{label}》内容生成结构化摘要，帮助模型理解剧情/内容脉络与关键人物关系，"
                "严格忠实于原文，不要编造、不要推测未写明的内容。\n\n"
                f"原文内容：\n{text}\n\n"
                "只返回 JSON：{\"summary\": \"200字以内的摘要\", "
                "\"key_entities\": {\"characters\": [\"人物\"], \"events\": [\"关键事件\"]}}"
            ),
        },
    ]
    content = provider._chat_completion(messages, phase="material_understanding")
    payload = parse_json_object(content)
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise RuntimeError("资料理解摘要缺少 summary 字段")
    key_entities = payload.get("key_entities")
    if not isinstance(key_entities, dict):
        key_entities = {}
    return compact_text(summary.strip(), MAX_SUMMARY_CHARS), key_entities


def _upsert_understanding(
    db: Session,
    *,
    book_id: str,
    scope_type: str,
    scope_ref: str,
    summary_text: str,
    key_entities: dict[str, Any],
    source_segment_ids: list[str],
    source_chunk_ids: list[str],
    content_signature: str,
    status: str,
    error_message: str | None = None,
) -> MaterialUnderstanding:
    existing = db.scalar(
        select(MaterialUnderstanding).where(
            MaterialUnderstanding.book_id == book_id,
            MaterialUnderstanding.scope_type == scope_type,
            MaterialUnderstanding.scope_ref == scope_ref,
        )
    )
    if existing is None:
        existing = MaterialUnderstanding(
            book_id=book_id,
            scope_type=scope_type,
            scope_ref=scope_ref,
        )
        db.add(existing)
    existing.summary_text = summary_text
    existing.key_entities = key_entities
    existing.source_segment_ids = source_segment_ids
    existing.source_chunk_ids = source_chunk_ids
    existing.content_signature = content_signature
    existing.status = status
    existing.error_message = error_message
    db.flush()
    return existing


def refresh_material_understanding(
    book_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    """Incrementally regenerate per-scope and book-level summaries for a book's trusted material.

    Only scopes whose underlying segment set changed since the last run are regenerated,
    identified by comparing `content_signature` (a hash of the scope's sorted segment ids).
    """
    settings = settings or get_settings()
    if not settings.material_understanding_enabled:
        return
    with SessionLocal() as db:
        book = db.get(Book, book_id)
        if book is None:
            return
        segments = list(
            db.scalars(
                select(MaterialSegment)
                .join(ResourceMaterial, ResourceMaterial.id == MaterialSegment.material_id)
                .where(
                    MaterialSegment.book_id == book_id,
                    ResourceMaterial.parse_status.in_(["completed", "needs_review"]),
                )
                .order_by(MaterialSegment.material_id, MaterialSegment.sequence)
            ).all()
        )
        if not segments:
            return

        configuration = get_effective_model_configuration(db, settings)
        usage_context = new_usage_context(
            "material_understanding",
            f"《{book.title}》可信资料理解层摘要",
            book_id=book.id,
        )
        provider = get_quiz_provider(settings, configuration, usage_context=usage_context)

        groups = _group_material_segments(segments)
        changed_any = False
        all_segment_ids: list[str] = []
        combined_summaries: list[str] = []

        for group in groups:
            all_segment_ids.extend(group.segment_ids)
            signature = _signature_for_ids(group.segment_ids)
            existing = db.scalar(
                select(MaterialUnderstanding).where(
                    MaterialUnderstanding.book_id == book_id,
                    MaterialUnderstanding.scope_type == group.scope_type,
                    MaterialUnderstanding.scope_ref == group.scope_ref,
                )
            )
            if existing is not None and existing.content_signature == signature and existing.status == "completed":
                combined_summaries.append(existing.summary_text)
                continue
            changed_any = True
            label = (
                f"{book.title} 第 {group.scope_ref} 集"
                if group.scope_type == "episode"
                else f"{book.title} {group.scope_ref}"
                if group.scope_ref
                else book.title
            )
            try:
                summary, key_entities = _summarize_text(
                    provider, configuration, usage_context, label, group.text
                )
                _upsert_understanding(
                    db,
                    book_id=book_id,
                    scope_type=group.scope_type,
                    scope_ref=group.scope_ref,
                    summary_text=summary,
                    key_entities=key_entities,
                    source_segment_ids=group.segment_ids,
                    source_chunk_ids=[],
                    content_signature=signature,
                    status="completed",
                )
                combined_summaries.append(summary)
                db.commit()
            except Exception as exc:
                logger.exception("资料理解层摘要生成失败: book=%s scope=%s", book_id, group.scope_ref)
                db.rollback()
                _upsert_understanding(
                    db,
                    book_id=book_id,
                    scope_type=group.scope_type,
                    scope_ref=group.scope_ref,
                    summary_text="",
                    key_entities={},
                    source_segment_ids=group.segment_ids,
                    source_chunk_ids=[],
                    content_signature=signature,
                    status="failed",
                    error_message=str(exc) or "资料理解层摘要生成失败",
                )
                db.commit()

        if changed_any and combined_summaries:
            book_signature = _signature_for_ids(all_segment_ids)
            book_level = db.scalar(
                select(MaterialUnderstanding).where(
                    MaterialUnderstanding.book_id == book_id,
                    MaterialUnderstanding.scope_type == "book",
                    MaterialUnderstanding.scope_ref == "",
                )
            )
            if book_level is None or book_level.content_signature != book_signature:
                joined = "\n".join(combined_summaries)[:MAX_BOOK_SUMMARY_INPUT_CHARS]
                try:
                    book_summary, book_entities = _summarize_text(
                        provider, configuration, usage_context, book.title, joined
                    )
                    _upsert_understanding(
                        db,
                        book_id=book_id,
                        scope_type="book",
                        scope_ref="",
                        summary_text=book_summary,
                        key_entities=book_entities,
                        source_segment_ids=all_segment_ids,
                        source_chunk_ids=[],
                        content_signature=book_signature,
                        status="completed",
                    )
                    db.commit()
                except Exception as exc:
                    logger.exception("资料理解层全局摘要生成失败: book=%s", book_id)
                    db.rollback()
                    _upsert_understanding(
                        db,
                        book_id=book_id,
                        scope_type="book",
                        scope_ref="",
                        summary_text="",
                        key_entities={},
                        source_segment_ids=all_segment_ids,
                        source_chunk_ids=[],
                        content_signature=book_signature,
                        status="failed",
                        error_message=str(exc) or "资料理解层全局摘要生成失败",
                    )
                    db.commit()


def get_understanding_context(
    db: Session, book_id: str, *, episode_numbers: set[int] | None = None
) -> str:
    """Return a compact background-context string for prompt injection.

    Includes the book-level summary plus any completed episode/scope summaries whose
    `scope_ref` matches the given episode numbers (when provided). Callers must present
    this text to the model strictly as background understanding, never as a citable source.
    """
    rows = list(
        db.scalars(
            select(MaterialUnderstanding).where(
                MaterialUnderstanding.book_id == book_id,
                MaterialUnderstanding.status == "completed",
            )
        ).all()
    )
    if not rows:
        return ""
    book_level = [row for row in rows if row.scope_type == "book"]
    scoped = [
        row
        for row in rows
        if row.scope_type != "book"
        and (
            episode_numbers is None
            or row.scope_ref in {str(number) for number in episode_numbers}
        )
    ]
    parts: list[str] = []
    if book_level:
        parts.append(f"整体背景摘要：{book_level[0].summary_text}")
    for row in scoped[:5]:
        scope_label = f"第{row.scope_ref}集" if row.scope_type == "episode" else row.scope_ref
        parts.append(f"{scope_label}背景摘要：{row.summary_text}")
    return "\n".join(parts)
