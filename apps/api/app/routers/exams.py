from __future__ import annotations

import copy
import hmac
import secrets
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.config import get_settings
from app.dependencies import (
    get_optional_identity,
    get_optional_wechat_identity,
    require_admin,
    require_ready_identity,
)
from app.models import Book, ExamAnswer, ExamAttempt, ExamShare, Quiz
from app.models import ExamShareVersion
from app.schemas import (
    AnswerSubmission,
    ExamAnswerResponse,
    ExamShareEditResponse,
    ExamAttemptCreate,
    ExamAttemptResponse,
    ExamAttemptSummary,
    ExamQuestionResponse,
    ExamShareCreate,
    ExamShareDetail,
    ExamShareSummary,
    ExamShareUpdate,
    ExamShareVersionSummary,
    QuestionResponse,
    QuestionUpdateRequest,
    PublicExamResponse,
    QuizSubmitRequest,
)
from app.services.auth import AuthIdentity, add_audit_log, hash_session_token
from app.services.exam_sharing import (
    analyze_attempt_learning,
    as_utc,
    detect_device_type,
    effective_share_status,
    grade_objective,
    launch_exam_grading,
    retry_exam_grading,
    serialize_quiz,
    snapshot_payload,
    snapshot_questions,
    unanswered_grade,
)
from app.services.quiz_generation import regenerate_snapshot_question
from app.services.question_dedup import refresh_question_signature
from app.services.wechat_auth import (
    WechatIdentity,
    effective_configuration as effective_wechat_configuration,
)

router = APIRouter(tags=["exam-shares"])
admin_router = APIRouter(prefix="/admin/exam-shares", tags=["admin-exam-shares"])
public_router = APIRouter(prefix="/public", tags=["public-exams"])
settings = get_settings()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:80]
    return request.client.host[:80] if request.client else None


def attempt_ip_changed(attempt: ExamAttempt) -> bool:
    return bool(
        attempt.started_ip_address
        and attempt.submitted_ip_address
        and attempt.started_ip_address != attempt.submitted_ip_address
    )


def apply_created_date_range(statement, created_from: date | None, created_to: date | None):
    if created_from and created_to and created_from > created_to:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    beijing_timezone = timezone(timedelta(hours=8))
    if created_from:
        start = datetime.combine(created_from, time.min, tzinfo=beijing_timezone).astimezone(timezone.utc)
        statement = statement.where(ExamShare.created_at >= start)
    if created_to:
        end = datetime.combine(
            created_to + timedelta(days=1),
            time.min,
            tzinfo=beijing_timezone,
        ).astimezone(timezone.utc)
        statement = statement.where(ExamShare.created_at < end)
    return statement


def share_statement():
    return select(ExamShare).options(
        selectinload(ExamShare.owner_user),
        selectinload(ExamShare.attempts).selectinload(ExamAttempt.answers),
    )


def edit_share_statement():
    return select(ExamShare).options(
        selectinload(ExamShare.owner_user),
        selectinload(ExamShare.book),
        selectinload(ExamShare.versions),
    )


def get_owned_share_or_404(db: Session, share_id: str, identity: AuthIdentity) -> ExamShare:
    share = db.scalar(
        share_statement().where(
            ExamShare.id == share_id,
            ExamShare.workspace_id == identity.workspace.id,
            ExamShare.owner_user_id == identity.user.id,
        )
    )
    if share is None:
        raise HTTPException(status_code=404, detail="未找到这个考试活动")
    return share


def get_admin_share_or_404(db: Session, share_id: str) -> ExamShare:
    share = db.scalar(share_statement().where(ExamShare.id == share_id))
    if share is None:
        raise HTTPException(status_code=404, detail="未找到这个考试活动")
    return share


def get_editable_share_or_404(
    db: Session, share_id: str, identity: AuthIdentity
) -> ExamShare:
    statement = edit_share_statement().where(ExamShare.id == share_id)
    if identity.user.role != "admin":
        statement = statement.where(
            ExamShare.workspace_id == identity.workspace.id,
            ExamShare.owner_user_id == identity.user.id,
        )
    share = db.scalar(statement)
    if share is None:
        raise HTTPException(status_code=404, detail="未找到这个考试活动")
    return share


def get_admin_editable_share_or_404(db: Session, share_id: str) -> ExamShare:
    share = db.scalar(edit_share_statement().where(ExamShare.id == share_id))
    if share is None:
        raise HTTPException(status_code=404, detail="未找到这个考试活动")
    return share


def get_attempt_or_404(db: Session, attempt_id: str) -> ExamAttempt:
    attempt = db.scalar(
        select(ExamAttempt)
        .options(
            selectinload(ExamAttempt.answers),
            selectinload(ExamAttempt.exam_share).selectinload(ExamShare.owner_user),
        )
        .where(ExamAttempt.id == attempt_id)
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="未找到这份答卷")
    return attempt


def question_counts(share: ExamShare) -> tuple[int, int, int, int]:
    questions = snapshot_questions(share)
    return (
        len(questions),
        sum(item.get("question_type") == "single" for item in questions),
        sum(item.get("question_type") == "multiple" for item in questions),
        sum(item.get("question_type") == "short" for item in questions),
    )


def to_attempt_summary(attempt: ExamAttempt) -> ExamAttemptSummary:
    percentage = (
        round((attempt.total_score or 0) / attempt.max_score * 100, 1)
        if attempt.total_score is not None and attempt.max_score
        else None
    )
    return ExamAttemptSummary(
        id=attempt.id,
        participant_type=attempt.participant_type,
        participant_user_id=attempt.participant_user_id,
        participant_name=attempt.participant_name,
        participant_avatar_url=attempt.participant_avatar_url,
        status=attempt.status,
        total_score=attempt.total_score,
        max_score=attempt.max_score,
        score_percentage=percentage,
        elapsed_seconds=attempt.elapsed_seconds,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        completed_at=attempt.completed_at,
        grading_error=attempt.grading_error,
        device_type=attempt.device_type,
        started_ip_address=attempt.started_ip_address,
        submitted_ip_address=attempt.submitted_ip_address,
        ip_changed=attempt_ip_changed(attempt),
    )


def to_share_summary(share: ExamShare) -> ExamShareSummary:
    attempts = list(share.attempts)
    completed = [attempt for attempt in attempts if attempt.status == "completed"]
    submitted_count = sum(attempt.status != "in_progress" for attempt in attempts)
    question_count, single_count, multiple_count, short_count = question_counts(share)
    percentages = [
        (attempt.total_score or 0) / attempt.max_score * 100
        for attempt in completed
        if attempt.max_score
    ]
    snapshot = snapshot_payload(share)
    return ExamShareSummary(
        id=share.id,
        share_code=share.share_code,
        name=share.name,
        status=effective_share_status(share),
        quiz_id=share.quiz_id,
        book_id=share.book_id,
        owner_user_id=share.owner_user_id,
        owner_username=share.owner_user.username,
        owner_display_name=share.owner_user.display_name,
        workspace_id=share.workspace_id,
        book_title=share.book_title,
        book_author=share.book_author,
        quiz_title=share.quiz_title,
        source_mode=share.source_mode,
        generation_theme=str(snapshot.get("generation_theme", "general")),
        theme_config=dict(snapshot.get("theme_config") or {}),
        difficulty=share.difficulty,
        duration_minutes=share.duration_minutes,
        max_score=share.max_score,
        question_count=question_count,
        single_count=single_count,
        multiple_count=multiple_count,
        short_count=short_count,
        started_count=len(attempts),
        submitted_count=submitted_count,
        grading_count=sum(attempt.status == "grading" for attempt in attempts),
        grading_failed_count=sum(attempt.status == "grading_failed" for attempt in attempts),
        completion_rate=round(submitted_count / len(attempts) * 100, 1) if attempts else 0,
        average_score=round(sum(percentages) / len(percentages), 1) if percentages else None,
        highest_score=round(max(percentages), 1) if percentages else None,
        created_at=share.created_at,
        updated_at=share.updated_at,
        stopped_at=share.stopped_at,
        expires_at=share.expires_at,
        last_attempt_at=share.last_attempt_at,
    )


def to_share_detail(share: ExamShare) -> ExamShareDetail:
    summary = to_share_summary(share)
    return ExamShareDetail(
        **summary.model_dump(),
        attempts=[
            to_attempt_summary(attempt)
            for attempt in sorted(share.attempts, key=lambda item: item.started_at, reverse=True)
        ],
    )


def to_share_version_summary(
    version: ExamShareVersion, *, current_version: int
) -> ExamShareVersionSummary:
    questions = snapshot_questions(version.quiz_snapshot)
    return ExamShareVersionSummary(
        version=version.version,
        is_current=version.version == current_version,
        question_count=len(questions),
        single_count=sum(item.get("question_type") == "single" for item in questions),
        multiple_count=sum(item.get("question_type") == "multiple" for item in questions),
        short_count=sum(item.get("question_type") == "short" for item in questions),
        max_score=round(sum(float(item.get("max_score") or 0) for item in questions), 1),
        created_at=version.created_at,
    )


def to_edit_response(share: ExamShare) -> ExamShareEditResponse:
    current_version = int(share.snapshot_version or 1)
    snapshot = snapshot_payload(share)
    return ExamShareEditResponse(
        id=share.id,
        share_code=share.share_code,
        name=share.name,
        status=effective_share_status(share),
        quiz_id=share.quiz_id,
        book_id=share.book_id,
        owner_user_id=share.owner_user_id,
        owner_username=share.owner_user.username,
        owner_display_name=share.owner_user.display_name,
        book_title=share.book_title,
        book_author=share.book_author,
        quiz_title=share.quiz_title,
        source_mode=share.source_mode,
        generation_theme=str(snapshot.get("generation_theme", "general")),
        theme_config=dict(snapshot.get("theme_config") or {}),
        difficulty=share.difficulty,
        duration_minutes=share.duration_minutes,
        max_score=share.max_score,
        snapshot_version=current_version,
        created_at=share.created_at,
        updated_at=share.updated_at,
        questions=[
            to_question_response(question, reveal_answers=True, include_sources=True)
            for question in snapshot_questions(share)
        ],
        versions=[
            to_share_version_summary(version, current_version=current_version)
            for version in sorted(
                share.versions,
                key=lambda item: item.version,
                reverse=True,
            )
        ],
    )


def to_question_response(
    question: dict,
    *,
    reveal_answers: bool,
    include_sources: bool,
) -> ExamQuestionResponse:
    return ExamQuestionResponse(
        id=str(question["id"]),
        position=int(question.get("position", 0)),
        question_type=question["question_type"],
        question_subtype=str(question.get("question_subtype", "general")),
        prompt=str(question.get("prompt", "")),
        options=question.get("options") or [],
        knowledge_point=str(question.get("knowledge_point", "")),
        difficulty=str(question.get("difficulty", "medium")),
        estimated_seconds=int(question.get("estimated_seconds", 0)),
        max_score=float(question.get("max_score", 0)),
        correct_answers=list(question.get("correct_answers") or []) if reveal_answers else None,
        explanation=str(question.get("explanation", "")) if reveal_answers else None,
        reference_answer=(question.get("reference_answer") if reveal_answers else None),
        grading_rubric=list(question.get("grading_rubric") or []) if include_sources else [],
        source_evidence=list(question.get("source_evidence") or []) if include_sources else [],
        quote_entry_ids=list(question.get("quote_entry_ids") or []) if include_sources else [],
        source_segment_ids=list(question.get("source_segment_ids") or []) if include_sources else [],
    )


def to_attempt_response(
    attempt: ExamAttempt,
    *,
    manager_view: bool = False,
    access_token: str | None = None,
) -> ExamAttemptResponse:
    reveal_answers = manager_view or attempt.status == "completed"
    weak_knowledge_points, recommended_direction = analyze_attempt_learning(attempt)
    questions = snapshot_questions(attempt)
    answers = sorted(
        attempt.answers,
        key=lambda answer: next(
            (
                int(question.get("position", 0))
                for question in questions
                if question.get("id") == answer.snapshot_question_id
            ),
            0,
        ),
    )
    snapshot = snapshot_payload(attempt)
    return ExamAttemptResponse(
        id=attempt.id,
        exam_share_id=attempt.exam_share_id,
        share_code=attempt.exam_share.share_code,
        exam_name=attempt.exam_share.name,
        book_title=attempt.exam_share.book_title,
        quiz_title=attempt.exam_share.quiz_title,
        participant_type=attempt.participant_type,
        participant_name=attempt.participant_name,
        participant_avatar_url=attempt.participant_avatar_url,
        status=attempt.status,
        total_score=attempt.total_score,
        max_score=attempt.max_score,
        elapsed_seconds=attempt.elapsed_seconds,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        completed_at=attempt.completed_at,
        grading_error=attempt.grading_error if manager_view else None,
        device_type=attempt.device_type if manager_view else None,
        user_agent=attempt.user_agent if manager_view else None,
        started_ip_address=attempt.started_ip_address if manager_view else None,
        submitted_ip_address=attempt.submitted_ip_address if manager_view else None,
        ip_changed=attempt_ip_changed(attempt) if manager_view else False,
        duration_minutes=attempt.exam_share.duration_minutes,
        source_mode=attempt.exam_share.source_mode,
        generation_theme=str(snapshot.get("generation_theme", "general")),
        theme_config=dict(snapshot.get("theme_config") or {}),
        questions=[
            to_question_response(
                question,
                reveal_answers=reveal_answers,
                include_sources=manager_view,
            )
            for question in questions
        ],
        answers=[
            ExamAnswerResponse(
                question_id=answer.snapshot_question_id,
                selected_answers=answer.selected_answers,
                text_answer=answer.text_answer,
                score=answer.score,
                max_score=answer.max_score,
                is_correct=answer.is_correct,
                feedback=answer.feedback,
                matched_points=answer.matched_points,
                missing_points=answer.missing_points,
                grading_status=answer.grading_status,
            )
            for answer in answers
        ] if reveal_answers else [],
        weak_knowledge_points=weak_knowledge_points if reveal_answers else [],
        recommended_direction=recommended_direction if reveal_answers else None,
        access_token=access_token,
    )


def verify_public_attempt_access(
    attempt: ExamAttempt,
    identity: AuthIdentity | None,
    wechat_identity: WechatIdentity | None,
    attempt_token: str | None,
) -> None:
    if attempt.participant_type == "user":
        if identity is not None and identity.user.id == attempt.participant_user_id:
            return
    elif attempt.participant_type == "wechat":
        if (
            wechat_identity is not None
            and wechat_identity.user.id == attempt.participant_wechat_user_id
        ):
            return
    elif attempt.access_token_hash and attempt_token:
        if hmac.compare_digest(attempt.access_token_hash, hash_session_token(attempt_token)):
            return
    raise HTTPException(status_code=404, detail="未找到这份答卷")


@router.post(
    "/quizzes/{quiz_id}/exam-shares",
    response_model=ExamShareDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_exam_share(
    quiz_id: str,
    payload: ExamShareCreate,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ExamShareDetail:
    quiz = db.scalar(
        select(Quiz)
        .options(selectinload(Quiz.questions), selectinload(Quiz.book))
        .join(Quiz.book)
        .where(Quiz.id == quiz_id, Book.workspace_id == identity.workspace.id)
    )
    if quiz is None:
        raise HTTPException(status_code=404, detail="未找到这套复习试卷")
    if quiz.book.shelf_status != "active":
        raise HTTPException(status_code=409, detail="这本书已下架，不能创建考试分享")
    if quiz.status != "ready" or not quiz.questions:
        raise HTTPException(status_code=409, detail="只有已经生成完成的试卷可以分享")
    if any(not question.prompt or question.max_score <= 0 for question in quiz.questions):
        raise HTTPException(status_code=409, detail="试卷题目数据不完整，不能创建考试分享")

    name = (payload.name or f"{quiz.book.title} · {quiz.title}").strip()
    expires_at = as_utc(payload.expires_at) if payload.expires_at else None
    if expires_at and expires_at <= utc_now():
        raise HTTPException(status_code=422, detail="考试结束时间必须晚于当前时间")
    while True:
        share_code = secrets.token_urlsafe(24)
        if not db.scalar(select(ExamShare.id).where(ExamShare.share_code == share_code)):
            break
    share = ExamShare(
        share_code=share_code,
        name=name,
        quiz_id=quiz.id,
        book_id=quiz.book_id,
        owner_user_id=identity.user.id,
        workspace_id=identity.workspace.id,
        status="active",
        quiz_snapshot=serialize_quiz(quiz),
        snapshot_version=1,
        book_title=quiz.book.title,
        book_author=quiz.book.author,
        quiz_title=quiz.title,
        source_mode=quiz.source_mode,
        difficulty=quiz.difficulty,
        duration_minutes=quiz.duration_minutes,
        max_score=quiz.max_score,
        expires_at=expires_at,
    )
    db.add(share)
    db.flush()
    db.add(
        ExamShareVersion(
            exam_share_id=share.id,
            version=1,
            quiz_snapshot=copy.deepcopy(share.quiz_snapshot),
        )
    )
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="exam_share.created",
        target_type="exam_share",
        target_id=share.id,
        details={
            "quiz_id": quiz.id,
            "book_id": quiz.book_id,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return to_share_detail(get_owned_share_or_404(db, share.id, identity))


@router.get("/exam-shares", response_model=list[ExamShareSummary])
def list_exam_shares(
    search: str | None = Query(default=None),
    share_status: Literal["active", "stopped", "source_deleted", "expired"] | None = Query(
        default=None, alias="status"
    ),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[ExamShareSummary]:
    statement = share_statement().where(
        ExamShare.workspace_id == identity.workspace.id,
        ExamShare.owner_user_id == identity.user.id,
    )
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                ExamShare.name.ilike(keyword),
                ExamShare.book_title.ilike(keyword),
                ExamShare.quiz_title.ilike(keyword),
            )
        )
    statement = apply_created_date_range(statement, created_from, created_to)
    shares = list(db.scalars(statement.order_by(ExamShare.created_at.desc())).unique().all())
    summaries = [to_share_summary(share) for share in shares]
    return [item for item in summaries if not share_status or item.status == share_status]


@router.get("/exam-shares/{share_id}", response_model=ExamShareDetail)
def get_exam_share(
    share_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ExamShareDetail:
    return to_share_detail(get_owned_share_or_404(db, share_id, identity))


@router.patch("/exam-shares/{share_id}", response_model=ExamShareDetail)
def update_exam_share(
    share_id: str,
    payload: ExamShareUpdate,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ExamShareDetail:
    share = get_owned_share_or_404(db, share_id, identity)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        if changes["name"] is None:
            raise HTTPException(status_code=422, detail="考试活动名称不能为空")
        share.name = changes["name"]
    if "expires_at" in changes:
        expires_at = as_utc(changes["expires_at"]) if changes["expires_at"] else None
        if expires_at and expires_at <= utc_now():
            raise HTTPException(status_code=422, detail="考试结束时间必须晚于当前时间")
        share.expires_at = expires_at
        add_audit_log(
            db,
            actor_user_id=identity.user.id,
            action="exam_share.expiration_updated",
            target_type="exam_share",
            target_id=share.id,
            details={"expires_at": expires_at.isoformat() if expires_at else None},
            ip_address=client_ip(request),
        )
    new_status = changes.get("status")
    if new_status and new_status != share.status:
        if share.quiz_id is None or share.book_id is None:
            raise HTTPException(status_code=409, detail="原试卷已经删除，不能修改分享状态")
        share.status = new_status
        share.stopped_at = utc_now() if new_status == "stopped" else None
        add_audit_log(
            db,
            actor_user_id=identity.user.id,
            action=f"exam_share.{new_status}",
            target_type="exam_share",
            target_id=share.id,
            ip_address=client_ip(request),
        )
    db.commit()
    return to_share_detail(get_owned_share_or_404(db, share_id, identity))


def _get_snapshot_question_or_404(share: ExamShare, question_id: str) -> dict[str, object]:
    question = next(
        (
            item
            for item in snapshot_questions(share)
            if str(item.get("id")) == question_id
        ),
        None,
    )
    if question is None:
        raise HTTPException(status_code=404, detail="未找到这道题目")
    return question


def _persist_share_snapshot(
    db: Session,
    share: ExamShare,
    snapshot: dict[str, object],
    *,
    request: Request,
    identity: AuthIdentity,
    action: str,
    details: dict[str, object] | None = None,
) -> None:
    share.snapshot_version = int(share.snapshot_version or 0) + 1
    share.quiz_snapshot = snapshot
    db.add(
        ExamShareVersion(
            exam_share_id=share.id,
            version=share.snapshot_version,
            quiz_snapshot=copy.deepcopy(snapshot),
        )
    )
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action=action,
        target_type="exam_share",
        target_id=share.id,
        details=details or {},
        ip_address=client_ip(request),
    )


def _apply_snapshot_question_updates(
    question: dict[str, object], payload: QuestionUpdateRequest
) -> None:
    changes = payload.model_dump(exclude_unset=True)
    if changes.keys() & {"prompt", "options", "correct_answers", "knowledge_point", "reference_answer"}:
        question["fact_key"] = None
        question["fact_claim"] = None
        question["semantic_signature"] = {}
    if "prompt" in changes:
        prompt = str(changes["prompt"] or "").strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="题干不能为空")
        question["prompt"] = prompt
    if "explanation" in changes:
        explanation = str(changes["explanation"] or "").strip()
        question["explanation"] = explanation or ""
    if "knowledge_point" in changes:
        knowledge_point = str(changes["knowledge_point"] or "").strip()
        if not knowledge_point:
            raise HTTPException(status_code=422, detail="知识点不能为空")
        question["knowledge_point"] = knowledge_point
    if "reference_answer" in changes:
        reference_answer = str(changes["reference_answer"] or "").strip()
        question["reference_answer"] = reference_answer or None
    if "grading_rubric" in changes:
        question["grading_rubric"] = changes["grading_rubric"] or []

    question_type = str(question.get("question_type") or "")
    if question_type == "short":
        if "options" in changes and changes["options"]:
            raise HTTPException(status_code=422, detail="问答题不支持选项")
        if "correct_answers" in changes and changes["correct_answers"]:
            raise HTTPException(status_code=422, detail="问答题不需要标准选项答案")
        question["options"] = []
        question["correct_answers"] = []
        refresh_question_signature(question)
        return

    option_ids = [
        str(option["id"])
        for option in (question.get("options") or [])
        if isinstance(option, dict) and option.get("id") is not None
    ]
    if "options" in changes:
        options = changes["options"] or []
        normalized_options: list[dict[str, str]] = []
        for option in options:
            if not isinstance(option, dict):
                raise HTTPException(status_code=422, detail="选项格式不正确")
            option_id = str(option.get("id", "")).strip().upper()
            option_text = str(option.get("text", "")).strip()
            if not option_id or not option_text:
                raise HTTPException(status_code=422, detail="选项内容不能为空")
            normalized_options.append({"id": option_id, "text": option_text})
        if len(normalized_options) != 4:
            raise HTTPException(status_code=422, detail="选择题需要保留四个选项")
        option_ids = [option["id"] for option in normalized_options]
        if set(option_ids) != {"A", "B", "C", "D"}:
            raise HTTPException(status_code=422, detail="选择题选项编号必须是 A、B、C、D")
        question["options"] = normalized_options

    if "correct_answers" in changes:
        correct_answers = [
            str(answer).strip().upper()
            for answer in changes["correct_answers"]
            if str(answer).strip()
        ]
        deduped = list(dict.fromkeys(correct_answers))
        if not deduped:
            raise HTTPException(status_code=422, detail="请选择标准答案")
        if not set(deduped).issubset(set(option_ids)):
            raise HTTPException(status_code=422, detail="标准答案必须来自选项")
        if question_type == "single" and len(deduped) != 1:
            raise HTTPException(status_code=422, detail="单选题只能有一个标准答案")
        if question_type == "multiple" and len(deduped) < 1:
            raise HTTPException(status_code=422, detail="多选题至少要有一个标准答案")
        question["correct_answers"] = deduped

    refresh_question_signature(question)


@router.get("/exam-shares/{share_id}/editable", response_model=ExamShareEditResponse)
def get_exam_share_editable(
    share_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ExamShareEditResponse:
    return to_edit_response(get_editable_share_or_404(db, share_id, identity))


@router.patch("/exam-shares/{share_id}/questions/{question_id}", response_model=QuestionResponse)
def update_exam_share_question(
    share_id: str,
    question_id: str,
    payload: QuestionUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuestionResponse:
    share = get_editable_share_or_404(db, share_id, identity)
    snapshot = copy.deepcopy(share.quiz_snapshot or {})
    question = _get_snapshot_question_or_404(share, question_id)
    snapshot_question = next(
        (item for item in snapshot.get("questions", []) if str(item.get("id")) == question_id),
        None,
    )
    if snapshot_question is None:
        raise HTTPException(status_code=404, detail="未找到这道题目")

    _apply_snapshot_question_updates(snapshot_question, payload)
    _persist_share_snapshot(
        db,
        share,
        snapshot,
        request=request,
        identity=identity,
        action="exam_share.question_updated",
        details={"question_id": question_id, "snapshot_version": int(share.snapshot_version or 0) + 1},
    )
    db.commit()
    return next(
        (
            to_question_response(item, reveal_answers=True, include_sources=True)
            for item in snapshot_questions(share)
            if str(item.get("id")) == question_id
        ),
        to_question_response(question, reveal_answers=True, include_sources=True),
    )


@router.post("/exam-shares/{share_id}/questions/{question_id}/regenerate", response_model=QuestionResponse)
def regenerate_exam_share_question(
    share_id: str,
    question_id: str,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuestionResponse:
    share = get_editable_share_or_404(db, share_id, identity)
    if share.book is None:
        raise HTTPException(status_code=409, detail="原资源已删除，不能重新出题")
    snapshot = copy.deepcopy(share.quiz_snapshot or {})
    questions = [
        item
        for item in snapshot.get("questions", [])
        if isinstance(item, dict)
    ]
    current_question = _get_snapshot_question_or_404(share, question_id)
    try:
        regenerated = regenerate_snapshot_question(
            db,
            book_id=share.book_id or "",
            book_title=share.book.title,
            author=share.book.author,
            resource_type=share.book.resource_type,
            source_mode=share.source_mode,
            generation_theme=str(snapshot.get("generation_theme", "general")),
            theme_config=dict(snapshot.get("theme_config") or {}),
            difficulty=share.difficulty,
            duration_minutes=share.duration_minutes,
            workspace_id=share.workspace_id,
            quiz_id=share.quiz_id,
            exam_share_id=share.id,
            current_question=current_question,
            sibling_questions=questions,
            user_id=identity.user.id,
            generation_number=int(share.snapshot_version or 0),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    snapshot_questions_list = snapshot.get("questions", [])
    for index, item in enumerate(snapshot_questions_list):
        if isinstance(item, dict) and str(item.get("id")) == question_id:
            snapshot_questions_list[index] = regenerated
            break
    _persist_share_snapshot(
        db,
        share,
        snapshot,
        request=request,
        identity=identity,
        action="exam_share.question_regenerated",
        details={"question_id": question_id, "snapshot_version": int(share.snapshot_version or 0) + 1},
    )
    db.commit()
    return to_question_response(regenerated, reveal_answers=True, include_sources=True)


@router.delete("/exam-shares/{share_id}/versions/{version}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exam_share_version(
    share_id: str,
    version: int,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> None:
    share = get_editable_share_or_404(db, share_id, identity)
    current_version = int(share.snapshot_version or 1)
    if version >= current_version:
        raise HTTPException(status_code=409, detail="当前版本不能删除")
    version_row = db.scalar(
        select(ExamShareVersion).where(
            ExamShareVersion.exam_share_id == share.id,
            ExamShareVersion.version == version,
        )
    )
    if version_row is None:
        raise HTTPException(status_code=404, detail="未找到这个历史版本")
    db.delete(version_row)
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="exam_share.version_deleted",
        target_type="exam_share",
        target_id=share.id,
        details={"version": version},
        ip_address=client_ip(request),
    )
    db.commit()


@router.get("/exam-shares/{share_id}/attempts", response_model=list[ExamAttemptSummary])
def list_exam_attempts(
    share_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[ExamAttemptSummary]:
    share = get_owned_share_or_404(db, share_id, identity)
    return [
        to_attempt_summary(attempt)
        for attempt in sorted(share.attempts, key=lambda item: item.started_at, reverse=True)
    ]


@router.get(
    "/exam-shares/{share_id}/attempts/{attempt_id}", response_model=ExamAttemptResponse
)
def get_exam_attempt_for_owner(
    share_id: str,
    attempt_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ExamAttemptResponse:
    get_owned_share_or_404(db, share_id, identity)
    attempt = get_attempt_or_404(db, attempt_id)
    if attempt.exam_share_id != share_id:
        raise HTTPException(status_code=404, detail="未找到这份答卷")
    return to_attempt_response(attempt, manager_view=True)


@router.post(
    "/exam-shares/{share_id}/attempts/{attempt_id}/retry-grading",
    response_model=ExamAttemptResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_exam_attempt_grading(
    share_id: str,
    attempt_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ExamAttemptResponse:
    get_owned_share_or_404(db, share_id, identity)
    attempt = get_attempt_or_404(db, attempt_id)
    if attempt.exam_share_id != share_id:
        raise HTTPException(status_code=404, detail="未找到这份答卷")
    try:
        retry_exam_grading(db, attempt)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return to_attempt_response(get_attempt_or_404(db, attempt_id), manager_view=True)


@public_router.get("/exams/{share_code}", response_model=PublicExamResponse)
def get_public_exam(
    share_code: str,
    x_exam_attempt_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    identity: AuthIdentity | None = Depends(get_optional_identity),
    wechat_identity: WechatIdentity | None = Depends(get_optional_wechat_identity),
) -> PublicExamResponse:
    share = db.scalar(
        share_statement().where(ExamShare.share_code == share_code)
    )
    if share is None:
        raise HTTPException(status_code=404, detail="考试链接不存在或已经失效")
    existing = None
    if identity:
        existing = next(
            (
                attempt
                for attempt in share.attempts
                if attempt.participant_user_id == identity.user.id
            ),
            None,
        )
    elif wechat_identity:
        existing = next(
            (
                attempt
                for attempt in share.attempts
                if attempt.participant_wechat_user_id == wechat_identity.user.id
            ),
            None,
        )
    elif x_exam_attempt_token:
        token_hash = hash_session_token(x_exam_attempt_token)
        existing = next(
            (
                attempt
                for attempt in share.attempts
                if attempt.access_token_hash
                and hmac.compare_digest(attempt.access_token_hash, token_hash)
            ),
            None,
        )
    question_count, single_count, multiple_count, short_count = question_counts(share)
    wechat_configuration = effective_wechat_configuration(db, settings)
    wechat_login_enabled = wechat_configuration.login_available
    wechat_login_required = (
        wechat_login_enabled and wechat_configuration.required_for_public_exams
    )
    if identity:
        identity_type = "user"
        participant_name = identity.user.display_name
        participant_avatar_url = None
    elif wechat_identity:
        identity_type = "wechat"
        participant_name = wechat_identity.user.nickname
        participant_avatar_url = wechat_identity.user.avatar_url
    else:
        identity_type = "anonymous"
        participant_name = None
        participant_avatar_url = None
    return PublicExamResponse(
        share_code=share.share_code,
        name=share.name,
        status=effective_share_status(share),
        book_title=share.book_title,
        book_author=share.book_author,
        quiz_title=share.quiz_title,
        owner_display_name=share.owner_user.display_name,
        difficulty=share.difficulty,
        duration_minutes=share.duration_minutes,
        source_mode=share.source_mode,
        generation_theme=str(snapshot_payload(share).get("generation_theme", "general")),
        theme_config=dict(snapshot_payload(share).get("theme_config") or {}),
        max_score=share.max_score,
        question_count=question_count,
        single_count=single_count,
        multiple_count=multiple_count,
        short_count=short_count,
        expires_at=share.expires_at,
        authenticated=identity is not None or wechat_identity is not None,
        identity_type=identity_type,
        participant_name=participant_name,
        participant_avatar_url=participant_avatar_url,
        wechat_login_enabled=wechat_login_enabled,
        wechat_login_required=wechat_login_required,
        existing_attempt_id=existing.id if existing else None,
        existing_attempt_status=existing.status if existing else None,
    )


@public_router.post(
    "/exams/{share_code}/attempts",
    response_model=ExamAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_public_exam_attempt(
    share_code: str,
    payload: ExamAttemptCreate,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity | None = Depends(get_optional_identity),
    wechat_identity: WechatIdentity | None = Depends(get_optional_wechat_identity),
) -> ExamAttemptResponse:
    share = db.scalar(share_statement().where(ExamShare.share_code == share_code))
    if share is None:
        raise HTTPException(status_code=404, detail="考试链接不存在或已经失效")
    if effective_share_status(share) != "active":
        detail = (
            "你来晚了，考试已经结束"
            if effective_share_status(share) == "expired"
            else "这场考试当前不能开始新的答题"
        )
        raise HTTPException(status_code=409, detail=detail)

    access_token = None
    wechat_configuration = effective_wechat_configuration(db, settings)
    if identity:
        existing = next(
            (
                attempt
                for attempt in share.attempts
                if attempt.participant_user_id == identity.user.id
            ),
            None,
        )
        if existing:
            return to_attempt_response(existing)
        participant_type = "user"
        participant_user_id = identity.user.id
        participant_wechat_user_id = None
        participant_name = identity.user.display_name
        participant_avatar_url = None
        access_token_hash = None
    elif wechat_identity:
        existing = next(
            (
                attempt
                for attempt in share.attempts
                if attempt.participant_wechat_user_id == wechat_identity.user.id
            ),
            None,
        )
        if existing:
            return to_attempt_response(existing)
        participant_type = "wechat"
        participant_user_id = None
        participant_wechat_user_id = wechat_identity.user.id
        participant_name = wechat_identity.user.nickname
        participant_avatar_url = wechat_identity.user.avatar_url
        access_token_hash = None
    else:
        if (
            wechat_configuration.login_available
            and wechat_configuration.required_for_public_exams
        ):
            raise HTTPException(status_code=401, detail="请先完成微信登录认证")
        participant_name = (payload.participant_name or "").strip()
        if len(participant_name) < 2:
            raise HTTPException(status_code=422, detail="答题名称需要填写 2-50 个字符")
        participant_type = "anonymous"
        participant_user_id = None
        participant_wechat_user_id = None
        participant_avatar_url = None
        access_token = secrets.token_urlsafe(48)
        access_token_hash = hash_session_token(access_token)

    attempt = ExamAttempt(
        exam_share_id=share.id,
        participant_type=participant_type,
        participant_user_id=participant_user_id,
        participant_wechat_user_id=participant_wechat_user_id,
        participant_name=participant_name,
        participant_avatar_url=participant_avatar_url,
        access_token_hash=access_token_hash,
        snapshot_version=share.snapshot_version,
        quiz_snapshot=copy.deepcopy(share.quiz_snapshot),
        status="in_progress",
        max_score=share.max_score,
        started_at=utc_now(),
        device_type=detect_device_type(request.headers.get("user-agent")),
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        started_ip_address=client_ip(request),
    )
    share.last_attempt_at = attempt.started_at
    db.add(attempt)
    db.commit()
    attempt = get_attempt_or_404(db, attempt.id)
    return to_attempt_response(attempt, access_token=access_token)


def public_attempt_dependency(
    attempt_id: str,
    db: Session,
    identity: AuthIdentity | None,
    wechat_identity: WechatIdentity | None,
    attempt_token: str | None,
) -> ExamAttempt:
    attempt = get_attempt_or_404(db, attempt_id)
    verify_public_attempt_access(attempt, identity, wechat_identity, attempt_token)
    if attempt.status == "in_progress" and effective_share_status(attempt.exam_share) == "expired":
        raise HTTPException(status_code=409, detail="你来晚了，考试已经结束")
    return attempt


@public_router.get("/exam-attempts/{attempt_id}", response_model=ExamAttemptResponse)
def get_public_exam_attempt(
    attempt_id: str,
    x_exam_attempt_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    identity: AuthIdentity | None = Depends(get_optional_identity),
    wechat_identity: WechatIdentity | None = Depends(get_optional_wechat_identity),
) -> ExamAttemptResponse:
    attempt = public_attempt_dependency(
        attempt_id, db, identity, wechat_identity, x_exam_attempt_token
    )
    return to_attempt_response(attempt)


@public_router.post(
    "/exam-attempts/{attempt_id}/submit",
    response_model=ExamAttemptResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_public_exam_attempt(
    attempt_id: str,
    payload: QuizSubmitRequest,
    request: Request,
    x_exam_attempt_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    identity: AuthIdentity | None = Depends(get_optional_identity),
    wechat_identity: WechatIdentity | None = Depends(get_optional_wechat_identity),
) -> ExamAttemptResponse:
    attempt = public_attempt_dependency(
        attempt_id, db, identity, wechat_identity, x_exam_attempt_token
    )
    if attempt.status != "in_progress":
        raise HTTPException(status_code=409, detail="这份答卷已经提交")
    if len({item.question_id for item in payload.answers}) != len(payload.answers):
        raise HTTPException(status_code=422, detail="同一道题不能重复提交")

    submitted: dict[str, AnswerSubmission] = {
        item.question_id: item for item in payload.answers
    }
    questions = snapshot_questions(attempt)
    question_ids = {str(question.get("id")) for question in questions}
    if set(submitted) - question_ids:
        raise HTTPException(status_code=422, detail="提交内容包含不属于这场考试的题目")

    has_pending_grading = False
    completed_score = 0.0
    for question in questions:
        question_id = str(question["id"])
        item = submitted.get(question_id)
        selected_answers = item.selected_answers if item else []
        text_answer = item.text_answer if item else None
        has_answer = (
            bool((text_answer or "").strip())
            if question.get("question_type") == "short"
            else bool(selected_answers)
        )
        if not has_answer:
            grade = unanswered_grade(question)
            grading_status = "completed"
        elif question.get("question_type") == "short":
            grade = None
            grading_status = "pending"
            has_pending_grading = True
        else:
            grade = grade_objective(question, selected_answers)
            grading_status = "completed"
        if grade:
            completed_score += grade.score
        db.add(
            ExamAnswer(
                exam_attempt_id=attempt.id,
                snapshot_question_id=question_id,
                selected_answers=selected_answers,
                text_answer=text_answer,
                score=grade.score if grade else 0,
                max_score=float(question.get("max_score") or 0),
                is_correct=grade.is_correct if grade else False,
                feedback=grade.feedback if grade else "等待 AI 评分。",
                matched_points=grade.matched_points if grade else [],
                missing_points=grade.missing_points if grade else [],
                grading_status=grading_status,
            )
        )

    now = utc_now()
    attempt.elapsed_seconds = payload.elapsed_seconds
    attempt.submitted_at = now
    attempt.submitted_ip_address = client_ip(request)
    if has_pending_grading:
        attempt.status = "grading"
    else:
        attempt.total_score = round(completed_score, 1)
        attempt.status = "completed"
        attempt.completed_at = now
    db.commit()
    if has_pending_grading:
        launch_exam_grading(attempt.id)
    return to_attempt_response(get_attempt_or_404(db, attempt.id))


@public_router.get("/exam-attempts/{attempt_id}/result", response_model=ExamAttemptResponse)
def get_public_exam_result(
    attempt_id: str,
    x_exam_attempt_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    identity: AuthIdentity | None = Depends(get_optional_identity),
    wechat_identity: WechatIdentity | None = Depends(get_optional_wechat_identity),
) -> ExamAttemptResponse:
    attempt = public_attempt_dependency(
        attempt_id, db, identity, wechat_identity, x_exam_attempt_token
    )
    if attempt.status == "in_progress":
        raise HTTPException(status_code=409, detail="交卷后才能查看结果")
    return to_attempt_response(attempt)


@admin_router.get("", response_model=list[ExamShareSummary])
def list_admin_exam_shares(
    search: str | None = Query(default=None),
    owner_id: str | None = Query(default=None),
    share_status: Literal["active", "stopped", "source_deleted", "expired"] | None = Query(
        default=None, alias="status"
    ),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: AuthIdentity = Depends(require_admin),
) -> list[ExamShareSummary]:
    statement = share_statement()
    if owner_id:
        statement = statement.where(ExamShare.owner_user_id == owner_id)
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                ExamShare.name.ilike(keyword),
                ExamShare.book_title.ilike(keyword),
                ExamShare.quiz_title.ilike(keyword),
            )
        )
    statement = apply_created_date_range(statement, created_from, created_to)
    shares = list(db.scalars(statement.order_by(ExamShare.created_at.desc())).unique().all())
    summaries = [to_share_summary(share) for share in shares]
    return [item for item in summaries if not share_status or item.status == share_status]


@admin_router.get("/{share_id}", response_model=ExamShareDetail)
def get_admin_exam_share(
    share_id: str,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> ExamShareDetail:
    share = get_admin_share_or_404(db, share_id)
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="admin.exam_share_viewed",
        target_type="exam_share",
        target_id=share.id,
        details={"owner_user_id": share.owner_user_id},
        ip_address=client_ip(request),
    )
    db.commit()
    return to_share_detail(share)


@admin_router.get(
    "/{share_id}/attempts/{attempt_id}", response_model=ExamAttemptResponse
)
def get_admin_exam_attempt(
    share_id: str,
    attempt_id: str,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> ExamAttemptResponse:
    share = get_admin_share_or_404(db, share_id)
    attempt = get_attempt_or_404(db, attempt_id)
    if attempt.exam_share_id != share.id:
        raise HTTPException(status_code=404, detail="未找到这份答卷")
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="admin.exam_attempt_viewed",
        target_type="exam_attempt",
        target_id=attempt.id,
        details={"exam_share_id": share.id, "owner_user_id": share.owner_user_id},
        ip_address=client_ip(request),
    )
    db.commit()
    return to_attempt_response(attempt, manager_view=True)


@admin_router.post(
    "/{share_id}/attempts/{attempt_id}/retry-grading",
    response_model=ExamAttemptResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_admin_exam_attempt_grading(
    share_id: str,
    attempt_id: str,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> ExamAttemptResponse:
    share = get_admin_share_or_404(db, share_id)
    attempt = get_attempt_or_404(db, attempt_id)
    if attempt.exam_share_id != share.id:
        raise HTTPException(status_code=404, detail="未找到这份答卷")
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="admin.exam_attempt_grading_retried",
        target_type="exam_attempt",
        target_id=attempt.id,
        details={"exam_share_id": share.id, "owner_user_id": share.owner_user_id},
        ip_address=client_ip(request),
    )
    try:
        retry_exam_grading(db, attempt)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return to_attempt_response(get_attempt_or_404(db, attempt.id), manager_view=True)
