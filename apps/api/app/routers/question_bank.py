from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import require_ready_identity
from app.models import Book, QuestionBankEntry, QuestionBankUsage, Quiz
from app.schemas import (
    QuestionBankBulkPromoteRequest,
    QuestionBankEntryListResponse,
    QuestionBankEntryResponse,
    QuestionBankEntryUpdateRequest,
    QuestionBankUsageResponse,
)
from app.services.auth import AuthIdentity
from app.services.question_bank import (
    promote_question_to_bank,
    update_question_bank_entry,
)


router = APIRouter(tags=["question-bank"])


def _book_or_404(db: Session, book_id: str, identity: AuthIdentity, *, write: bool = False) -> Book:
    book = db.scalar(select(Book).where(Book.id == book_id, Book.workspace_id == identity.workspace.id))
    if book is None:
        raise HTTPException(status_code=404, detail="未找到这个资源")
    if write and book.shelf_status != "active":
        raise HTTPException(status_code=409, detail="这个资源已下架，不能修改题库")
    return book


def _quiz_or_404(db: Session, quiz_id: str, identity: AuthIdentity) -> Quiz:
    quiz = db.scalar(
        select(Quiz)
        .options(selectinload(Quiz.questions), selectinload(Quiz.book))
        .join(Quiz.book)
        .where(Quiz.id == quiz_id, Book.workspace_id == identity.workspace.id)
    )
    if quiz is None:
        raise HTTPException(status_code=404, detail="未找到这套复习试卷")
    return quiz


def _usage_response(usage: QuestionBankUsage) -> QuestionBankUsageResponse:
    return QuestionBankUsageResponse(
        id=usage.id,
        entry_id=usage.entry_id,
        quiz_id=usage.quiz_id,
        question_id=usage.question_id,
        quiz_title=usage.quiz_title_snapshot,
        question_position=usage.question_position,
        used_at=usage.used_at,
    )


def _entry_response(entry: QuestionBankEntry) -> QuestionBankEntryResponse:
    return QuestionBankEntryResponse(
        id=entry.id,
        book_id=entry.book_id,
        origin_quiz_id=entry.origin_quiz_id,
        origin_question_id=entry.origin_question_id,
        question_type=entry.question_type,
        question_subtype=entry.question_subtype,
        prompt=entry.prompt,
        options=list(entry.options or []),
        correct_answers=list(entry.correct_answers or []),
        explanation=entry.explanation or "",
        knowledge_point=entry.knowledge_point or "",
        difficulty=entry.difficulty,
        estimated_seconds=entry.estimated_seconds,
        reference_answer=entry.reference_answer,
        grading_rubric=list(entry.grading_rubric or []),
        source_chunk_ids=list(entry.source_chunk_ids or []),
        quote_entry_ids=list(entry.quote_entry_ids or []),
        plot_event_ids=list(entry.plot_event_ids or []),
        source_segment_ids=list(entry.source_segment_ids or []),
        fact_key=entry.fact_key,
        fact_claim=entry.fact_claim,
        semantic_signature=dict(entry.semantic_signature or {}),
        source_evidence=list(entry.source_evidence or []),
        source_mode=entry.source_mode,
        max_score=entry.max_score,
        status=entry.status,
        use_count=entry.use_count or 0,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        usages=[_usage_response(usage) for usage in sorted(entry.usages, key=lambda item: item.used_at)],
    )


@router.get("/books/{book_id}/question-bank", response_model=QuestionBankEntryListResponse)
def list_question_bank(
    book_id: str,
    search: str | None = None,
    question_type: str | None = Query(default=None),
    entry_status: str | None = Query(default=None, alias="status"),
    unused_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuestionBankEntryListResponse:
    _book_or_404(db, book_id, identity)
    filters = [QuestionBankEntry.book_id == book_id]
    if search and search.strip():
        term = search.strip()
        filters.append(
            (QuestionBankEntry.prompt.contains(term))
            | (QuestionBankEntry.knowledge_point.contains(term))
            | (QuestionBankEntry.fact_claim.contains(term))
        )
    if question_type:
        if question_type not in {"single", "multiple", "short"}:
            raise HTTPException(status_code=400, detail="不支持的题型")
        filters.append(QuestionBankEntry.question_type == question_type)
    if entry_status:
        if entry_status not in {"active", "disabled"}:
            raise HTTPException(status_code=400, detail="不支持的题库状态")
        filters.append(QuestionBankEntry.status == entry_status)
    if unused_only:
        filters.append(QuestionBankEntry.use_count == 0)
    total = db.scalar(select(func.count(QuestionBankEntry.id)).where(*filters)) or 0
    entries = list(
        db.scalars(
            select(QuestionBankEntry)
            .options(selectinload(QuestionBankEntry.usages))
            .where(*filters)
            .order_by(QuestionBankEntry.use_count, QuestionBankEntry.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    unused_count = db.scalar(
        select(func.count(QuestionBankEntry.id)).where(
            QuestionBankEntry.book_id == book_id,
            QuestionBankEntry.status == "active",
            QuestionBankEntry.use_count == 0,
        )
    ) or 0
    return QuestionBankEntryListResponse(
        items=[_entry_response(entry) for entry in entries],
        total=total,
        unused_count=unused_count,
    )


@router.patch(
    "/books/{book_id}/question-bank/{entry_id}",
    response_model=QuestionBankEntryResponse,
)
def patch_question_bank_entry(
    book_id: str,
    entry_id: str,
    payload: QuestionBankEntryUpdateRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuestionBankEntryResponse:
    _book_or_404(db, book_id, identity, write=True)
    entry = db.scalar(
        select(QuestionBankEntry)
        .options(selectinload(QuestionBankEntry.usages))
        .where(QuestionBankEntry.id == entry_id, QuestionBankEntry.book_id == book_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="未找到这道题库题目")
    changes = payload.model_dump(exclude_unset=True)
    if entry.question_type in {"single", "multiple"}:
        options = changes.get("options", entry.options or [])
        option_ids = [item.get("id") if isinstance(item, dict) else item.id for item in options]
        if option_ids != ["A", "B", "C", "D"]:
            raise HTTPException(status_code=422, detail="选择题需要保留 A、B、C、D 四个选项")
        answers = changes.get("correct_answers", entry.correct_answers or [])
        if not answers or not set(answers).issubset(set(option_ids)):
            raise HTTPException(status_code=422, detail="标准答案必须来自选项")
        if entry.question_type == "single" and len(answers) != 1:
            raise HTTPException(status_code=422, detail="单选题只能有一个标准答案")
    if entry.question_type == "short" and "reference_answer" in changes and not (changes["reference_answer"] or "").strip():
        raise HTTPException(status_code=422, detail="问答题需要保留参考答案")
    entry = update_question_bank_entry(db, entry, changes)
    return _entry_response(entry)


@router.post(
    "/quizzes/{quiz_id}/questions/{question_id}/question-bank",
    response_model=QuestionBankEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def promote_question(
    quiz_id: str,
    question_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuestionBankEntryResponse:
    quiz = _quiz_or_404(db, quiz_id, identity)
    question = next((item for item in quiz.questions if item.id == question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="未找到这道题目")
    entry, _ = promote_question_to_bank(db, quiz, question, identity.user.id)
    return _entry_response(entry)


@router.post(
    "/quizzes/{quiz_id}/question-bank",
    response_model=list[QuestionBankEntryResponse],
    status_code=status.HTTP_201_CREATED,
)
def bulk_promote_questions(
    quiz_id: str,
    payload: QuestionBankBulkPromoteRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[QuestionBankEntryResponse]:
    quiz = _quiz_or_404(db, quiz_id, identity)
    questions = {question.id: question for question in quiz.questions}
    missing = [question_id for question_id in payload.question_ids if question_id not in questions]
    if missing:
        raise HTTPException(status_code=404, detail="部分题目不存在")
    entries = []
    for question_id in dict.fromkeys(payload.question_ids):
        entry, _ = promote_question_to_bank(db, quiz, questions[question_id], identity.user.id)
        entries.append(entry)
    return [_entry_response(entry) for entry in entries]
