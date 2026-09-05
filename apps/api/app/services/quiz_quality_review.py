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


def build_quiz_review_payload(quiz: Quiz, question_id: str | None = None) -> dict[str, Any]:
    questions = []
    selected_questions = sorted(quiz.questions, key=lambda item: item.position)
    if question_id is not None:
        selected_questions = [item for item in selected_questions if item.id == question_id]
        if not selected_questions:
            raise ValueError("未找到需要审查的题目")
    for question in selected_questions:
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
        "total_question_count": len(quiz.questions),
        "review_scope": "question" if question_id is not None else "quiz",
        "questions": questions,
    }


def _text_list(value: Any, limit: int = 8, item_limit: int = 500) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_compact(item, item_limit) for item in value if str(item).strip()][:limit]


def _suggested_options(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    options = []
    for item in value[:4]:
        if not isinstance(item, dict):
            continue
        option_id = _compact(item.get("id"), 8)
        text = _compact(item.get("text"), 500)
        if option_id and text:
            options.append({"id": option_id, "text": text})
    return options


def _normalize_issue(raw: Any, default_position: int | None = None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    position = raw.get("question_position", default_position)
    if not isinstance(position, int):
        position = default_position
    severity = raw.get("severity") if raw.get("severity") in VALID_SEVERITIES else "medium"
    category = raw.get("category") if raw.get("category") in VALID_CATEGORIES else "other"
    problem = _compact(raw.get("problem"), 1_500)
    suggestion = _compact(raw.get("suggestion"), 1_500)
    if not problem or not suggestion:
        return None
    proposed_prompt = raw.get("suggested_prompt") or raw.get("proposed_prompt") or raw.get("recommended_prompt")
    proposed_options = raw.get("suggested_options") or raw.get("proposed_options") or raw.get("recommended_options")
    proposed_answers = raw.get("suggested_correct_answers") or raw.get("proposed_correct_answers") or raw.get("recommended_correct_answers")
    proposed_explanation = raw.get("suggested_explanation") or raw.get("proposed_explanation")
    proposed_knowledge = raw.get("suggested_knowledge_point") or raw.get("proposed_knowledge_point")
    proposed_reference = raw.get("suggested_reference_answer") or raw.get("proposed_reference_answer")
    proposed_rubric = raw.get("suggested_grading_rubric") or raw.get("proposed_grading_rubric")
    return {
        "question_position": position,
        "severity": severity,
        "category": category,
        "problem": problem,
        "suggestion": suggestion,
        "evidence": _compact(raw.get("evidence"), 900) or None,
        "suggested_prompt": _compact(proposed_prompt, 1_500) or None,
        "suggested_options": _suggested_options(proposed_options),
        "suggested_correct_answers": [
            _compact(item, 8) for item in proposed_answers[:4]
        ] if isinstance(proposed_answers, list) else [],
        "suggested_explanation": _compact(proposed_explanation, 1_500) or None,
        "suggested_knowledge_point": _compact(proposed_knowledge, 300) or None,
        "suggested_reference_answer": _compact(proposed_reference, 1_500) or None,
        "suggested_grading_rubric": [item for item in (proposed_rubric or [])[:12] if isinstance(item, dict)]
        if isinstance(proposed_rubric, list)
        else [],
    }


def _score_for_issues(issues: list[dict[str, Any]]) -> int:
    if any(issue["severity"] == "high" for issue in issues):
        return 40
    if any(issue["severity"] == "medium" for issue in issues):
        return 70
    if issues:
        return 90
    return 100


def _verdict_for_score(score: int, issues: list[dict[str, Any]]) -> str:
    if score < 50 or any(issue["severity"] == "high" for issue in issues):
        return "high_risk"
    if score < 85 or issues:
        return "needs_revision"
    return "pass"


def normalize_quality_review(
    payload: Any,
    question_count: int,
    reviewed_positions: list[int] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("模型审查结果不是 JSON 对象")
    positions = sorted(
        set(reviewed_positions or range(1, question_count + 1))
        & set(range(1, question_count + 1))
    )
    if not positions:
        raise RuntimeError("没有可审查的题目")
    raw_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    issues_by_position: dict[int | None, list[dict[str, Any]]] = {}
    for raw in raw_issues[:100]:
        issue = _normalize_issue(raw)
        if issue is not None:
            issues_by_position.setdefault(issue["question_position"], []).append(issue)

    question_reviews: dict[int, dict[str, Any]] = {}
    raw_question_reviews = payload.get("question_reviews")
    if isinstance(raw_question_reviews, list):
        for raw in raw_question_reviews[:question_count]:
            if not isinstance(raw, dict) or not isinstance(raw.get("question_position"), int):
                continue
            position = raw["question_position"]
            if position not in positions:
                continue
            current_issues = []
            raw_review_issues = raw.get("issues") if isinstance(raw.get("issues"), list) else []
            for item in raw_review_issues[:30]:
                issue = _normalize_issue(item, position)
                if issue is not None:
                    current_issues.append(issue)
            current_issues.extend(issues_by_position.pop(position, []))
            deduped_issues = []
            seen = set()
            for issue in current_issues:
                key = (issue["category"], issue["problem"])
                if key not in seen:
                    seen.add(key)
                    deduped_issues.append(issue)
            raw_score = raw.get("score")
            score = int(round(float(raw_score))) if isinstance(raw_score, (int, float)) else _score_for_issues(deduped_issues)
            score = max(0, min(100, score))
            verdict = raw.get("verdict") if raw.get("verdict") in VALID_VERDICTS else _verdict_for_score(score, deduped_issues)
            if deduped_issues and verdict == "pass":
                verdict = "needs_revision"
            question_reviews[position] = {
                "question_position": position,
                "score": score,
                "verdict": verdict,
                "summary": _compact(raw.get("summary"), 1_200),
                "strengths": _text_list(raw.get("strengths")),
                "issues": deduped_issues,
            }

    for position in positions:
        if position in question_reviews:
            continue
        current_issues = issues_by_position.pop(position, [])
        score = _score_for_issues(current_issues)
        question_reviews[position] = {
            "question_position": position,
            "score": score,
            "verdict": _verdict_for_score(score, current_issues),
            "summary": "未发现需要修改的问题。" if not current_issues else "发现需要人工确认的问题。",
            "strengths": [],
            "issues": current_issues,
        }
    ordered_reviews = [question_reviews[position] for position in positions]
    all_issues = [issue for review in ordered_reviews for issue in review["issues"]]
    all_issues.extend(issues_by_position.get(None, []))
    raw_verdict = payload.get("overall_verdict")
    severity_verdict = (
        "high_risk" if any(review["verdict"] == "high_risk" for review in ordered_reviews)
        else "needs_revision" if any(review["verdict"] == "needs_revision" for review in ordered_reviews)
        else "pass"
    )
    verdict = raw_verdict if raw_verdict in VALID_VERDICTS else severity_verdict
    if severity_verdict == "high_risk" or (verdict == "pass" and all_issues):
        verdict = "high_risk" if severity_verdict == "high_risk" else "needs_revision"
    raw_score = payload.get("score")
    score = int(round(float(raw_score))) if isinstance(raw_score, (int, float)) else round(sum(review["score"] for review in ordered_reviews) / len(ordered_reviews))
    score = max(0, min(100, score))
    strengths = _text_list(payload.get("strengths"))
    for review in ordered_reviews:
        for strength in review["strengths"]:
            if strength not in strengths:
                strengths.append(strength)
    return {
        "schema_version": "quiz_quality_review.v2",
        "overall_verdict": verdict,
        "score": score,
        "summary": _compact(payload.get("summary"), 2_000),
        "strengths": strengths[:10],
        "issues": all_issues[:100],
        "reviewed_question_count": len(positions),
        "total_question_count": question_count,
        "reviewed_question_positions": positions,
        "question_reviews": ordered_reviews,
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
    quiz.quality_review_question_id = None
    quiz.quality_review_result = None
    quiz.quality_review_error = None
    quiz.quality_review_requested_at = _utc_now()
    quiz.quality_review_completed_at = None
    db.commit()
    return task_id


def start_quiz_question_quality_review(db: Session, quiz: Quiz, question_id: str) -> str:
    if quiz.quality_review_status in {"pending", "processing"}:
        raise ValueError("这套试卷正在审查，请等待当前任务完成")
    if not any(question.id == question_id for question in quiz.questions):
        raise ValueError("未找到需要审查的题目")
    task_id = str(uuid4())
    quiz.quality_review_status = "pending"
    quiz.quality_review_task_id = task_id
    quiz.quality_review_question_id = question_id
    quiz.quality_review_error = None
    quiz.quality_review_requested_at = _utc_now()
    quiz.quality_review_completed_at = None
    db.commit()
    return task_id


def merge_question_quality_review(
    existing: dict[str, Any] | None,
    latest: dict[str, Any],
    question_count: int,
) -> dict[str, Any]:
    latest_positions = set(latest.get("reviewed_question_positions") or [])
    if existing and not existing.get("question_reviews"):
        existing = normalize_quality_review(existing, question_count)
    previous_reviews = {
        item.get("question_position"): item
        for item in (existing or {}).get("question_reviews", [])
        if isinstance(item, dict) and isinstance(item.get("question_position"), int)
    }
    for item in latest.get("question_reviews", []):
        if isinstance(item, dict) and item.get("question_position") in latest_positions:
            previous_reviews[item["question_position"]] = item
    ordered_reviews = [previous_reviews[position] for position in sorted(previous_reviews)]
    all_issues = [issue for review in ordered_reviews for issue in review.get("issues", [])]
    verdict = (
        "high_risk" if any(review.get("verdict") == "high_risk" for review in ordered_reviews)
        else "needs_revision" if any(review.get("verdict") == "needs_revision" for review in ordered_reviews)
        else "pass"
    )
    scores = [int(review.get("score", 0)) for review in ordered_reviews]
    strengths: list[str] = []
    for review in ordered_reviews:
        for item in review.get("strengths", []):
            if item not in strengths:
                strengths.append(item)
    summary = f"已审查 {len(ordered_reviews)}/{question_count} 道题。"
    if latest.get("summary"):
        summary = f"{summary}{latest['summary']}"
    return {
        "schema_version": "quiz_quality_review.v2",
        "overall_verdict": verdict,
        "score": round(sum(scores) / len(scores)) if scores else 0,
        "summary": summary[:2_000],
        "strengths": strengths[:10],
        "issues": all_issues[:100],
        "reviewed_question_count": len(ordered_reviews),
        "total_question_count": question_count,
        "reviewed_question_positions": sorted(previous_reviews),
        "question_reviews": ordered_reviews,
        "generated_at": _utc_now().isoformat(),
    }


def run_quiz_quality_review(
    quiz_id: str,
    task_id: str,
    question_id: str | None = None,
) -> None:
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
        payload = build_quiz_review_payload(quiz, question_id)
        question_count = len(quiz.questions)
        reviewed_positions = [
            question.position for question in quiz.questions if question.id == question_id
        ] if question_id else [question.position for question in quiz.questions]
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
        result = normalize_quality_review(raw_result, question_count, reviewed_positions)
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
        quiz.quality_review_result = (
            merge_question_quality_review(
                quiz.quality_review_result, result, result["total_question_count"]
            )
            if question_id
            else result
        )
        quiz.quality_review_question_id = None
        quiz.quality_review_error = None
        quiz.quality_review_completed_at = _utc_now()
        db.commit()


def recover_quality_review_tasks(db: Session) -> list[tuple[str, str, str | None]]:
    quizzes = list(
        db.scalars(
            select(Quiz).where(Quiz.quality_review_status.in_(["pending", "processing"]))
        ).all()
    )
    tasks: list[tuple[str, str, str | None]] = []
    changed = False
    for quiz in quizzes:
        task_id = quiz.quality_review_task_id or str(uuid4())
        quiz.quality_review_task_id = task_id
        quiz.quality_review_status = "pending"
        tasks.append((quiz.id, task_id, quiz.quality_review_question_id))
        changed = True
    if changed:
        db.commit()
    return tasks
