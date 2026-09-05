from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import SessionLocal
from app.models import Quiz
from app.services.model_config import get_effective_model_configuration
from app.services.model_usage import new_usage_context
from app.services.prompt_config import get_effective_prompt_templates
from app.services.quiz_provider import get_quiz_provider


QUALITY_REVIEW_STATUSES = {"not_started", "pending", "processing", "completed", "failed"}
VALID_VERDICTS = {"pass", "needs_revision", "high_risk"}
VALID_SEVERITIES = {"high", "medium", "low"}
VALID_CATEGORIES = {
    "fact",
    "answer",
    "source",
    "ambiguity",
    "duplicate",
    "wording",
    "difficulty",
    "other",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _compact(value: Any, limit: int = 800) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[:limit].rstrip()}……"


def build_quiz_review_payload(quiz: Quiz) -> dict[str, Any]:
    questions = []
    for question in sorted(quiz.questions, key=lambda item: item.position):
        evidence = []
        for item in list(question.source_evidence or [])[:4]:
            if not isinstance(item, dict):
                continue
            evidence.append(
                {
                    "source_chunk_id": item.get("chunk_id"),
                    "plot_event_id": item.get("plot_event_id"),
                    "quote_entry_id": item.get("quote_entry_id"),
                    "file_name": item.get("file_name"),
                    "excerpt": _compact(item.get("excerpt") or item.get("highlight"), 900),
                }
            )
        questions.append(
            {
                "position": question.position,
                "question_type": question.question_type,
                "question_subtype": question.question_subtype,
                "prompt": _compact(question.prompt, 1_200),
                "options": [
                    {"id": item.get("id"), "text": _compact(item.get("text"), 500)}
                    for item in (question.options or [])
                    if isinstance(item, dict)
                ],
                "correct_answers": list(question.correct_answers or []),
                "explanation": _compact(question.explanation, 1_000),
                "knowledge_point": _compact(question.knowledge_point, 300),
                "reference_answer": _compact(question.reference_answer, 1_000),
                "grading_rubric": list(question.grading_rubric or [])[:12],
                "fact_claim": _compact(question.fact_claim, 600),
                "fact_key": _compact(question.fact_key, 600),
                "source_mode": question.source_mode or quiz.source_mode,
                "source_chunk_ids": list(question.source_chunk_ids or []),
                "plot_event_ids": list(question.plot_event_ids or []),
                "quote_entry_ids": list(question.quote_entry_ids or []),
                "source_evidence": evidence,
            }
        )
    return {
        "book_id": quiz.book_id,
        "title": quiz.title,
        "book_title": quiz.book.title if quiz.book else "",
        "difficulty": quiz.difficulty,
        "source_mode": quiz.source_mode,
        "generation_theme": quiz.generation_theme,
        "questions": questions,
    }


def normalize_quality_review(payload: Any, question_count: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("模型审查结果不是 JSON 对象")
    verdict = payload.get("overall_verdict")
    if verdict not in VALID_VERDICTS:
        verdict = "needs_revision"
    summary = _compact(payload.get("summary"), 2_000)
    strengths = payload.get("strengths")
    if not isinstance(strengths, list):
        strengths = []
    normalized_strengths = [_compact(item, 500) for item in strengths if str(item).strip()][:10]
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        raw_issues = []
    issues = []
    for raw in raw_issues[:100]:
        if not isinstance(raw, dict):
            continue
        position = raw.get("question_position")
        if not isinstance(position, int) or not 1 <= position <= question_count:
            position = None
        severity = raw.get("severity") if raw.get("severity") in VALID_SEVERITIES else "medium"
        category = raw.get("category") if raw.get("category") in VALID_CATEGORIES else "other"
        problem = _compact(raw.get("problem"), 1_500)
        suggestion = _compact(raw.get("suggestion"), 1_500)
        if not problem or not suggestion:
            continue
        issues.append(
            {
                "question_position": position,
                "severity": severity,
                "category": category,
                "problem": problem,
                "suggestion": suggestion,
                "evidence": _compact(raw.get("evidence"), 900) or None,
            }
        )
    if issues and verdict == "pass":
        verdict = "needs_revision"
    return {
        "schema_version": "quiz_quality_review.v1",
        "overall_verdict": verdict,
        "summary": summary,
        "strengths": normalized_strengths,
        "issues": issues,
        "reviewed_question_count": question_count,
        "generated_at": _utc_now().isoformat(),
    }


def start_quiz_quality_review(db: Session, quiz: Quiz) -> str:
    if quiz.quality_review_status in {"pending", "processing"}:
        raise ValueError("这套试卷正在审查，请等待当前任务完成")
    if not quiz.questions:
        raise ValueError("试卷没有题目，无法进行模型审查")
    task_id = str(uuid4())
    quiz.quality_review_status = "pending"
    quiz.quality_review_task_id = task_id
    quiz.quality_review_result = None
    quiz.quality_review_error = None
    quiz.quality_review_requested_at = _utc_now()
    quiz.quality_review_completed_at = None
    db.commit()
    return task_id


def run_quiz_quality_review(quiz_id: str, task_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        quiz = db.scalar(
            select(Quiz)
            .options(selectinload(Quiz.questions), selectinload(Quiz.book))
            .where(Quiz.id == quiz_id)
        )
        if quiz is None or quiz.quality_review_task_id != task_id:
            return
        quiz.quality_review_status = "processing"
        db.commit()
        payload = build_quiz_review_payload(quiz)
        configuration = get_effective_model_configuration(db, settings)
        prompt_templates = get_effective_prompt_templates(db)
        user_id = quiz.book.created_by_user_id if quiz.book else None
        workspace_id = quiz.book.workspace_id if quiz.book else None

    usage_context = new_usage_context(
        "quiz_quality_review",
        f"试卷审查：{payload.get('title') or quiz_id}",
        book_id=payload.get("book_id"),
        quiz_id=quiz_id,
        user_id=user_id,
        workspace_id=workspace_id,
        task_id=task_id,
    )
    provider = get_quiz_provider(settings, configuration, prompt_templates, usage_context)
    try:
        raw_result = provider.review_quiz(payload)
        result = normalize_quality_review(raw_result, len(payload.get("questions") or []))
    except Exception as exc:
        with SessionLocal() as db:
            quiz = db.get(Quiz, quiz_id)
            if quiz is not None and quiz.quality_review_task_id == task_id:
                quiz.quality_review_status = "failed"
                quiz.quality_review_error = _compact(str(exc), 1_000)
                quiz.quality_review_completed_at = _utc_now()
                db.commit()
        return

    with SessionLocal() as db:
        quiz = db.get(Quiz, quiz_id)
        if quiz is None or quiz.quality_review_task_id != task_id:
            return
        quiz.quality_review_status = "completed"
        quiz.quality_review_result = result
        quiz.quality_review_error = None
        quiz.quality_review_completed_at = _utc_now()
        db.commit()


def recover_quality_review_tasks(db: Session) -> list[tuple[str, str]]:
    quizzes = list(
        db.scalars(
            select(Quiz).where(Quiz.quality_review_status.in_(["pending", "processing"]))
        ).all()
    )
    tasks: list[tuple[str, str]] = []
    changed = False
    for quiz in quizzes:
        task_id = quiz.quality_review_task_id or str(uuid4())
        quiz.quality_review_task_id = task_id
        quiz.quality_review_status = "pending"
        tasks.append((quiz.id, task_id))
        changed = True
    if changed:
        db.commit()
    return tasks
