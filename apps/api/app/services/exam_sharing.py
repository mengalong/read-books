from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import SessionLocal
from app.models import ExamAnswer, ExamAttempt, ExamShare, Question, Quiz
from app.services.model_config import get_effective_model_configuration
from app.services.model_usage import new_usage_context
from app.services.prompt_config import get_effective_prompt_templates
from app.services.quiz_provider import GradeResult, get_quiz_provider


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def detect_device_type(user_agent: str | None) -> str:
    value = (user_agent or "").lower()
    if not value:
        return "unknown"
    if "ipad" in value or "tablet" in value or ("android" in value and "mobile" not in value):
        return "tablet"
    if any(marker in value for marker in ("mobile", "iphone", "ipod", "windows phone")):
        return "mobile"
    if any(marker in value for marker in ("windows", "macintosh", "x11", "linux", "cros")):
        return "desktop"
    return "unknown"


def effective_share_status(share: ExamShare) -> str:
    if share.status == "active" and share.expires_at and as_utc(share.expires_at) <= utc_now():
        return "expired"
    return share.status


def snapshot_payload(source: ExamShare | ExamAttempt | dict[str, Any]) -> dict[str, Any]:
    if isinstance(source, dict):
        return source if isinstance(source, dict) else {}
    if isinstance(source, ExamAttempt):
        if isinstance(source.quiz_snapshot, dict) and source.quiz_snapshot:
            return source.quiz_snapshot
        if isinstance(source.exam_share.quiz_snapshot, dict):
            return source.exam_share.quiz_snapshot
        return {}
    if isinstance(source.quiz_snapshot, dict):
        return source.quiz_snapshot
    return {}


def serialize_question(question: Question) -> dict[str, Any]:
    return {
        "id": question.id,
        "position": question.position,
        "question_type": question.question_type,
        "question_subtype": question.question_subtype,
        "prompt": question.prompt,
        "options": list(question.options or []),
        "correct_answers": list(question.correct_answers or []),
        "explanation": question.explanation,
        "knowledge_point": question.knowledge_point,
        "difficulty": question.difficulty,
        "estimated_seconds": question.estimated_seconds,
        "reference_answer": question.reference_answer,
        "grading_rubric": list(question.grading_rubric or []),
        "source_chunk_ids": list(question.source_chunk_ids or []),
        "quote_entry_ids": list(question.quote_entry_ids or []),
        "plot_event_ids": list(question.plot_event_ids or []),
        "source_segment_ids": list(question.source_segment_ids or []),
        "fact_key": question.fact_key,
        "fact_claim": question.fact_claim,
        "semantic_signature": dict(question.semantic_signature or {}),
        "source_evidence": list(question.source_evidence or []),
        "max_score": question.max_score,
        "source_mode": question.source_mode,
    }


def serialize_quiz(quiz: Quiz) -> dict[str, Any]:
    return {
        "version": 1,
        "quiz_id": quiz.id,
        "title": quiz.title,
        "difficulty": quiz.difficulty,
        "duration_minutes": quiz.duration_minutes,
        "source_mode": quiz.source_mode,
        "generation_theme": quiz.generation_theme,
        "theme_config": dict(quiz.theme_config or {}),
        "max_score": quiz.max_score,
        "questions": [serialize_question(question) for question in quiz.questions],
    }


def snapshot_questions(source: ExamShare | ExamAttempt | dict[str, Any]) -> list[dict[str, Any]]:
    questions = snapshot_payload(source).get("questions", [])
    return sorted(
        [item for item in questions if isinstance(item, dict)],
        key=lambda item: int(item.get("position", 0)),
    )


def _missing_focus_points(question: dict[str, Any], answer: ExamAnswer) -> list[str]:
    option_labels = {
        str(option.get("id")): f'{option.get("id")}. {option.get("text")}'
        for option in question.get("options") or []
        if isinstance(option, dict) and option.get("id") and option.get("text")
    }
    points = [
        option_labels.get(str(point), str(point).strip())
        for point in answer.missing_points or []
        if str(point).strip()
    ]
    return list(dict.fromkeys(points))


def analyze_attempt_learning(
    attempt: ExamAttempt,
) -> tuple[list[dict[str, Any]], str | None]:
    if attempt.status != "completed":
        return [], None

    questions = {
        str(question.get("id")): question
        for question in snapshot_questions(attempt)
    }
    grouped: dict[str, dict[str, Any]] = {}
    for answer in attempt.answers:
        question = questions.get(answer.snapshot_question_id)
        if question is None or answer.max_score <= 0:
            continue
        knowledge_point = (
            str(question.get("knowledge_point") or "").strip() or "未标注知识点"
        )
        item = grouped.setdefault(
            knowledge_point,
            {
                "knowledge_point": knowledge_point,
                "score": 0.0,
                "max_score": 0.0,
                "question_count": 0,
                "focus_points": [],
                "question_types": set(),
            },
        )
        item["score"] += float(answer.score or 0)
        item["max_score"] += float(answer.max_score)
        item["question_count"] += 1
        item["question_types"].add(str(question.get("question_type") or ""))
        item["focus_points"].extend(_missing_focus_points(question, answer))

    weak_points: list[dict[str, Any]] = []
    mastery_points: list[tuple[float, float, str]] = []
    for item in grouped.values():
        score_percentage = round(item["score"] / item["max_score"] * 100, 1)
        mastery_points.append(
            (score_percentage, -item["max_score"], item["knowledge_point"])
        )
        if score_percentage >= 60:
            continue
        focus_points = list(dict.fromkeys(item["focus_points"]))[:4]
        knowledge_point = item["knowledge_point"]
        if focus_points:
            recommendation = "建议回到相关章节核对原文，再围绕待补充内容用自己的语言复述关键关系。"
        elif "short" in item["question_types"]:
            recommendation = "重点补全核心论述、因果关系和关键细节，并对照参考答案重新组织一次完整表达。"
        elif "multiple" in item["question_types"]:
            recommendation = "重点厘清相关要素之间的关系与选项边界，避免漏选或混淆相近表述。"
        else:
            recommendation = "重点核对相关章节中的关键事实、人物关系或核心概念，并进行一次主动回忆。"
        weak_points.append(
            {
                "knowledge_point": knowledge_point,
                "score": round(item["score"], 2),
                "max_score": round(item["max_score"], 2),
                "score_percentage": score_percentage,
                "question_count": item["question_count"],
                "focus_points": focus_points,
                "recommendation": recommendation,
            }
        )

    weak_points.sort(
        key=lambda item: (
            item["score_percentage"],
            -item["max_score"],
            item["knowledge_point"],
        )
    )
    if not weak_points:
        if not mastery_points:
            return [], None
        _, _, knowledge_point = min(mastery_points)
        return (
            [],
            f"本次未发现得分率低于 60% 的薄弱知识点。建议继续巩固“{knowledge_point}”，并通过间隔复习保持掌握。",
        )
    primary = weak_points[0]
    direction = f'优先深入掌握“{primary["knowledge_point"]}”。'
    if primary["focus_points"]:
        direction += f'重点补足：{"、".join(primary["focus_points"])}。'
    direction += primary["recommendation"]
    return weak_points, direction


def grade_objective(question: dict[str, Any], selected: list[str]) -> GradeResult:
    selected_set = set(selected)
    correct_set = set(question.get("correct_answers") or [])
    max_score = float(question.get("max_score") or 0)
    if question.get("question_type") == "single":
        is_correct = selected_set == correct_set
        return GradeResult(
            score=max_score if is_correct else 0,
            is_correct=is_correct,
            feedback="回答正确。" if is_correct else "答案不正确。",
            matched_points=list(correct_set & selected_set),
            missing_points=list(correct_set - selected_set),
        )

    correct_hits = len(correct_set & selected_set)
    wrong_hits = len(selected_set - correct_set)
    if wrong_hits > 0:
        score = 0.0
    else:
        score = round(max_score * correct_hits / max(len(correct_set), 1), 1)
    is_correct = selected_set == correct_set
    return GradeResult(
        score=score,
        is_correct=is_correct,
        feedback="全部选对。" if is_correct else "本题错选记 0 分，少选按命中比例计分。",
        matched_points=list(correct_set & selected_set),
        missing_points=list(correct_set - selected_set),
    )


def unanswered_grade(question: dict[str, Any]) -> GradeResult:
    if question.get("question_type") == "short":
        missing = [
            str(item.get("point", ""))
            for item in question.get("grading_rubric", [])
            if isinstance(item, dict) and item.get("point")
        ]
    else:
        missing = list(question.get("correct_answers") or [])
    return GradeResult(
        score=0,
        is_correct=False,
        feedback="本题未作答，按 0 分处理。",
        matched_points=[],
        missing_points=missing,
    )


def _finish_attempt(db: Session, attempt: ExamAttempt) -> None:
    attempt.total_score = round(sum(answer.score for answer in attempt.answers), 1)
    attempt.status = "completed"
    attempt.grading_error = None
    attempt.completed_at = utc_now()
    db.commit()


def run_exam_grading(attempt_id: str) -> None:
    with SessionLocal() as db:
        attempt = db.scalar(
            select(ExamAttempt)
            .options(
                selectinload(ExamAttempt.answers),
                selectinload(ExamAttempt.exam_share),
            )
            .where(ExamAttempt.id == attempt_id)
        )
        if attempt is None or attempt.status != "grading":
            return

        questions = {str(item.get("id")): item for item in snapshot_questions(attempt)}
        pending_answers = [answer for answer in attempt.answers if answer.grading_status == "pending"]
        if not pending_answers:
            _finish_attempt(db, attempt)
            return

        settings = get_settings()
        configuration = get_effective_model_configuration(db, settings)
        prompts = get_effective_prompt_templates(db)
        usage_context = new_usage_context(
            "exam_grading",
            f"评分考试《{attempt.exam_share.name}》中的答卷",
            book_id=attempt.exam_share.book_id,
            quiz_id=attempt.exam_share.quiz_id,
            user_id=attempt.exam_share.owner_user_id,
            workspace_id=attempt.exam_share.workspace_id,
            exam_share_id=attempt.exam_share_id,
            exam_attempt_id=attempt.id,
        )
        provider = get_quiz_provider(settings, configuration, prompts, usage_context)

        try:
            for answer in pending_answers:
                question = questions.get(answer.snapshot_question_id)
                if question is None:
                    raise RuntimeError("考试快照中缺少待评分题目")
                grade = provider.grade_short_answer(SimpleNamespace(**question), answer.text_answer or "")
                answer.score = grade.score
                answer.is_correct = grade.is_correct
                answer.feedback = grade.feedback
                answer.matched_points = grade.matched_points
                answer.missing_points = grade.missing_points
                answer.grading_status = "completed"
                db.commit()
            _finish_attempt(db, attempt)
        except Exception as exc:
            db.rollback()
            attempt = db.scalar(
                select(ExamAttempt)
                .options(selectinload(ExamAttempt.answers))
                .where(ExamAttempt.id == attempt_id)
            )
            if attempt is None:
                return
            attempt.status = "grading_failed"
            attempt.grading_error = str(exc)[:2000]
            for answer in attempt.answers:
                if answer.grading_status == "pending":
                    answer.grading_status = "failed"
                    answer.feedback = "问答题评分失败，等待重新评分。"
            db.commit()


def launch_exam_grading(attempt_id: str) -> None:
    threading.Thread(target=run_exam_grading, args=(attempt_id,), daemon=True).start()


def retry_exam_grading(db: Session, attempt: ExamAttempt) -> None:
    if attempt.status != "grading_failed":
        raise ValueError("只有评分失败的答卷可以重新评分")
    retried = False
    for answer in attempt.answers:
        if answer.grading_status == "failed":
            answer.grading_status = "pending"
            answer.feedback = "等待 AI 评分。"
            retried = True
    if not retried:
        raise ValueError("这份答卷没有需要重新评分的题目")
    attempt.status = "grading"
    attempt.grading_error = None
    db.commit()
    launch_exam_grading(attempt.id)


def recover_exam_grading_tasks(db: Session) -> list[str]:
    return list(db.scalars(select(ExamAttempt.id).where(ExamAttempt.status == "grading")).all())
