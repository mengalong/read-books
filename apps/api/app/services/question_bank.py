from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Question, QuestionBankEntry, QuestionBankUsage, Quiz
from app.services.quiz_provider import GeneratedQuestion


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fallback_fact_key(question: Question) -> str:
    payload = "|".join(
        [
            question.question_type or "",
            question.prompt or "",
            json.dumps(question.correct_answers or [], ensure_ascii=False, sort_keys=True),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _entry_key(question: Question) -> str:
    return question.fact_key or _fallback_fact_key(question)


def _copy_question_fields(question: Question) -> dict[str, Any]:
    return {
        "question_type": question.question_type,
        "question_subtype": question.question_subtype,
        "prompt": question.prompt,
        "options": list(question.options or []),
        "correct_answers": list(question.correct_answers or []),
        "explanation": question.explanation or "",
        "knowledge_point": question.knowledge_point or "",
        "difficulty": question.difficulty or "medium",
        "estimated_seconds": question.estimated_seconds or 45,
        "reference_answer": question.reference_answer,
        "grading_rubric": list(question.grading_rubric or []),
        "source_chunk_ids": list(question.source_chunk_ids or []),
        "quote_entry_ids": list(question.quote_entry_ids or []),
        "plot_event_ids": list(question.plot_event_ids or []),
        "source_segment_ids": list(question.source_segment_ids or []),
        "fact_key": _entry_key(question),
        "fact_claim": question.fact_claim,
        "semantic_signature": dict(question.semantic_signature or {}),
        "source_evidence": list(question.source_evidence or []),
        "source_mode": question.source_mode,
        "max_score": question.max_score or 0,
    }


def _usage_exists(db: Session, entry_id: str, quiz_id: str) -> QuestionBankUsage | None:
    return db.scalar(
        select(QuestionBankUsage).where(
            QuestionBankUsage.entry_id == entry_id,
            QuestionBankUsage.quiz_id == quiz_id,
        )
    )


def record_question_bank_usage(
    db: Session,
    entry: QuestionBankEntry,
    quiz: Quiz,
    question: Question | None = None,
) -> QuestionBankUsage:
    usage = _usage_exists(db, entry.id, quiz.id)
    if usage is not None:
        if question is not None:
            usage.question_id = question.id
            usage.question_position = question.position
        return usage
    usage = QuestionBankUsage(
        book_id=quiz.book_id,
        entry_id=entry.id,
        quiz_id=quiz.id,
        question_id=question.id if question is not None else None,
        quiz_title_snapshot=quiz.title,
        question_position=question.position if question is not None else None,
        used_at=_utc_now(),
    )
    db.add(usage)
    entry.use_count = int(entry.use_count or 0) + 1
    entry.last_used_at = usage.used_at
    return usage


def promote_question_to_bank(
    db: Session,
    quiz: Quiz,
    question: Question,
    user_id: str | None,
) -> tuple[QuestionBankEntry, bool]:
    fact_key = _entry_key(question)
    existing = db.scalar(
        select(QuestionBankEntry).where(
            QuestionBankEntry.book_id == quiz.book_id,
            QuestionBankEntry.fact_key == fact_key,
            QuestionBankEntry.status == "active",
        )
    )
    created = existing is None
    if existing is None:
        entry = QuestionBankEntry(
            book_id=quiz.book_id,
            created_by_user_id=user_id,
            origin_quiz_id=quiz.id,
            origin_question_id=question.id,
            **_copy_question_fields(question),
        )
        db.add(entry)
        db.flush()
    else:
        entry = existing
    question.question_bank_entry_id = entry.id
    record_question_bank_usage(db, entry, quiz, question)
    db.commit()
    db.refresh(entry)
    return entry, created


def update_question_bank_entry(
    db: Session,
    entry: QuestionBankEntry,
    changes: dict[str, Any],
) -> QuestionBankEntry:
    for field in (
        "prompt",
        "options",
        "correct_answers",
        "explanation",
        "knowledge_point",
        "reference_answer",
        "grading_rubric",
        "difficulty",
    ):
        if field in changes:
            setattr(entry, field, changes[field])
    if "status" in changes:
        entry.status = changes["status"]
    if "options" in changes or "correct_answers" in changes or "prompt" in changes:
        key_payload = "|".join(
            [
                entry.question_type,
                entry.prompt,
                json.dumps(entry.correct_answers or [], ensure_ascii=False, sort_keys=True),
            ]
        )
        entry.fact_key = hashlib.sha256(key_payload.encode("utf-8")).hexdigest()
        signature = dict(entry.semantic_signature or {})
        if "prompt" in changes:
            entry.fact_claim = entry.prompt
        signature["fact_claim"] = entry.fact_claim or entry.prompt
        entry.semantic_signature = signature
    db.commit()
    db.refresh(entry)
    return entry


def entry_matches_source(
    entry: QuestionBankEntry,
    source_mode: str,
    source_focus: str,
) -> bool:
    has_pdf = bool(entry.source_chunk_ids)
    has_plot = bool(entry.plot_event_ids)
    has_dialogue = bool(entry.quote_entry_ids)
    if source_mode == "pdf":
        return has_pdf and source_focus == "content"
    if source_mode == "material":
        return has_dialogue
    if source_mode == "plot":
        return has_plot
    if source_mode == "model_knowledge":
        return not (has_pdf or has_plot or has_dialogue)
    if source_focus == "content":
        return has_pdf or has_plot
    if source_focus == "dialogue":
        return has_dialogue
    if source_focus == "integrated":
        return (has_pdf or has_plot) and has_dialogue
    return has_pdf or has_plot or has_dialogue


def find_bank_candidates(
    db: Session,
    book_id: str,
    source_mode: str,
    source_focus: str,
    question_type: str,
    *,
    generation_theme: str = "general",
) -> list[QuestionBankEntry]:
    if generation_theme != "general":
        return []
    rows = list(
        db.scalars(
            select(QuestionBankEntry).where(
                QuestionBankEntry.book_id == book_id,
                QuestionBankEntry.question_type == question_type,
                QuestionBankEntry.status == "active",
            )
        ).all()
    )
    rows = [
        entry for entry in rows if entry_matches_source(entry, source_mode, source_focus)
    ]
    rows.sort(
        key=lambda entry: (
            int(entry.use_count or 0),
            entry.last_used_at.timestamp() if entry.last_used_at else 0,
            entry.created_at.timestamp() if entry.created_at else 0,
        )
    )
    return rows


def entry_to_generated_question(entry: QuestionBankEntry) -> GeneratedQuestion:
    return GeneratedQuestion(
        question_type=entry.question_type,
        prompt=entry.prompt,
        options=list(entry.options or []),
        correct_answers=list(entry.correct_answers or []),
        explanation=entry.explanation or "",
        knowledge_point=entry.knowledge_point or "",
        estimated_seconds=entry.estimated_seconds or 45,
        reference_answer=entry.reference_answer,
        grading_rubric=list(entry.grading_rubric or []),
        source_chunk_ids=list(entry.source_chunk_ids or []),
        source_evidence=list(entry.source_evidence or []),
        max_score=entry.max_score or 0,
        question_subtype=entry.question_subtype or "general",
        quote_entry_ids=list(entry.quote_entry_ids or []),
        plot_event_ids=list(entry.plot_event_ids or []),
        source_segment_ids=list(entry.source_segment_ids or []),
        fact_key=entry.fact_key or "",
        fact_claim=entry.fact_claim or "",
        semantic_signature=dict(entry.semantic_signature or {}),
        question_bank_entry_id=entry.id,
    )
