from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_ready_identity
from app.services.auth import AuthIdentity
from app.models import (
    Book,
    ExamShare,
    ModelUsageRecord,
    Question,
    Quiz,
    QuizGenerationTask,
    ReviewAnswer,
    ReviewTask,
)
from app.schemas import (
    AnswerResult,
    QuestionResponse,
    QuizGenerateRequest,
    QuizGenerationTaskResponse,
    QuizGenerationCallResponse,
    QuizGenerationDebugResponse,
    QuizGenerationInterventionRequest,
    QuizGenerationTaskDebugResponse,
    QuizQuestionGenerationTrace,
    QuizResponse,
    QuizSummary,
    ReviewTaskResponse,
    ReviewTaskSummary,
    QuestionUpdateRequest,
    QuizSubmitRequest,
)
from app.services.model_config import get_effective_model_configuration
from app.services.model_usage import new_usage_context
from app.services.book_stats import to_quiz_summary
from app.services.prompt_config import get_effective_prompt_templates
from app.services.question_dedup import refresh_question_signature
from app.services.quiz_generation import (
    apply_generation_intervention,
    regenerate_quiz_question,
    start_generation_task,
)
from app.services.quiz_provider import GradeResult, get_quiz_provider, key_sentence

router = APIRouter(tags=["quizzes"])
settings = get_settings()


def current_provider(db: Session, usage_context=None):
    configuration = get_effective_model_configuration(db, settings)
    prompts = get_effective_prompt_templates(db)
    return get_quiz_provider(settings, configuration, prompts, usage_context)


def get_quiz_or_404(
    db: Session, quiz_id: str, identity: AuthIdentity, *, for_write: bool = False
) -> Quiz:
    conditions = [Quiz.id == quiz_id]
    conditions.append(Book.workspace_id == identity.workspace.id)
    quiz = db.scalar(
        select(Quiz)
        .options(selectinload(Quiz.questions), selectinload(Quiz.book))
        .join(Quiz.book)
        .where(*conditions)
    )
    if not quiz:
        raise HTTPException(status_code=404, detail="未找到这套复习试卷")
    return quiz


def get_review_or_404(
    db: Session, review_id: str, identity: AuthIdentity, *, for_write: bool = False
) -> ReviewTask:
    conditions = [ReviewTask.id == review_id]
    conditions.append(Book.workspace_id == identity.workspace.id)
    review = db.scalar(
        select(ReviewTask)
        .join(ReviewTask.book)
        .options(
            selectinload(ReviewTask.book),
            selectinload(ReviewTask.quiz).selectinload(Quiz.questions),
            selectinload(ReviewTask.answers).selectinload(ReviewAnswer.question),
        )
        .where(*conditions)
    )
    if not review:
        raise HTTPException(status_code=404, detail="未找到这次复习任务")
    return review


def question_focus_text(question: Question) -> str:
    options = question.options if isinstance(question.options, list) else []
    correct_answers = (
        set(question.correct_answers) if isinstance(question.correct_answers, list) else set()
    )
    option_text = " ".join(
        option.get("text", "")
        for option in options
        if (
            isinstance(option, dict)
            and isinstance(option.get("text"), str)
            and option.get("id") in correct_answers
        )
    )
    return " ".join(
        value
        for value in (
            question.prompt,
            question.explanation,
            question.knowledge_point,
            question.reference_answer or "",
            option_text,
        )
        if value
    )


def clean_optional_text(value: str | None) -> str:
    return value.strip() if isinstance(value, str) else ""


def to_question_response(question: Question, reveal_answers: bool) -> QuestionResponse:
    focus_text = question_focus_text(question)
    source_evidence = []
    for item in question.source_evidence:
        evidence = dict(item)
        if not evidence.get("highlight") and isinstance(evidence.get("excerpt"), str):
            evidence["highlight"] = key_sentence(evidence["excerpt"], focus_text)
        source_evidence.append(evidence)
    return QuestionResponse(
        id=question.id,
        position=question.position,
        question_type=question.question_type,
        question_subtype=question.question_subtype,
        prompt=question.prompt,
        options=question.options,
        explanation=question.explanation if reveal_answers else None,
        knowledge_point=question.knowledge_point,
        difficulty=question.difficulty,
        estimated_seconds=question.estimated_seconds,
        reference_answer=question.reference_answer if reveal_answers else None,
        grading_rubric=question.grading_rubric if reveal_answers else [],
        source_evidence=source_evidence,
        quote_entry_ids=list(question.quote_entry_ids or []),
        source_segment_ids=list(question.source_segment_ids or []),
        max_score=question.max_score,
        correct_answers=question.correct_answers if reveal_answers else None,
        source_mode=question.source_mode,
    )


def to_quiz_response(quiz: Quiz, reveal_answers: bool = False) -> QuizResponse:
    return QuizResponse(
        id=quiz.id,
        book_id=quiz.book_id,
        book_title=quiz.book.title,
        title=quiz.title,
        difficulty=quiz.difficulty,
        duration_minutes=quiz.duration_minutes,
        status="ready",
        source_mode=quiz.source_mode,
        generation_theme=quiz.generation_theme,
        theme_config=quiz.theme_config or {},
        total_score=None,
        max_score=quiz.max_score,
        elapsed_seconds=None,
        submitted_at=None,
        next_review_date=None,
        created_at=quiz.created_at,
        questions=[to_question_response(question, reveal_answers) for question in quiz.questions],
    )


def _legacy_question_states(task: QuizGenerationTask, db: Session) -> list[dict[str, object]]:
    if task.status != "completed" or not task.quiz_id:
        return list(task.question_states or [])
    states = list(task.question_states or [])
    if states and any(
        isinstance(state, dict) and state.get("status") in {"ready", "confirmed"}
        for state in states
    ):
        return states
    questions = db.scalars(
        select(Question).where(Question.quiz_id == task.quiz_id).order_by(Question.position)
    ).all()
    if not questions:
        return states
    return [
        {
            "position": question.position,
            "question_type": question.question_type,
            "status": "ready",
            "attempts": 0,
            "error_message": None,
            "question": {
                "question_type": question.question_type,
                "prompt": question.prompt,
                "options": list(question.options or []),
                "correct_answers": list(question.correct_answers or []),
                "explanation": question.explanation,
                "knowledge_point": question.knowledge_point,
                "estimated_seconds": question.estimated_seconds,
                "reference_answer": question.reference_answer,
                "grading_rubric": list(question.grading_rubric or []),
                "source_chunk_ids": list(question.source_chunk_ids or []),
                "source_evidence": list(question.source_evidence or []),
                "max_score": question.max_score,
            },
            "updated_at": question.updated_at,
        }
        for question in questions
    ]


def to_generation_response(
    task: QuizGenerationTask, db: Session | None = None
) -> QuizGenerationTaskResponse:
    return QuizGenerationTaskResponse(
        id=task.id,
        book_id=task.book_id,
        task_type=task.task_type,
        status=task.status,
        source_mode=task.source_mode,
        generation_theme=task.generation_theme,
        theme_config=task.theme_config or {},
        total_questions=task.total_questions,
        completed_questions=task.completed_questions,
        current_question_position=task.current_question_position,
        current_phase=task.current_phase,
        difficulty=task.difficulty,
        duration_minutes=task.duration_minutes,
        single_count=task.single_count,
        multiple_count=task.multiple_count,
        short_count=task.short_count,
        quiz_id=task.quiz_id,
        error_message=task.error_message,
        question_states=(
            _legacy_question_states(task, db)
            if db is not None
            else list(task.question_states or [])
        ),
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def to_answer_result(answer: ReviewAnswer) -> AnswerResult:
    return AnswerResult(
        question_id=answer.question_id,
        selected_answers=answer.selected_answers,
        text_answer=answer.text_answer,
        score=answer.score,
        max_score=answer.max_score,
        is_correct=answer.is_correct,
        feedback=answer.feedback,
        matched_points=answer.matched_points,
        missing_points=answer.missing_points,
    )


def to_review_response(review: ReviewTask) -> ReviewTaskResponse:
    reveal = review.status == "submitted"
    ordered_answers = sorted(review.answers, key=lambda answer: answer.question.position)
    weak_points = [
        answer.question.knowledge_point
        for answer in ordered_answers
        if answer.max_score and answer.score / answer.max_score < 0.6
    ]
    return ReviewTaskResponse(
        id=review.id,
        quiz_id=review.quiz_id,
        book_id=review.book_id,
        book_title=review.book.title,
        title=review.quiz.title,
        attempt_number=review.attempt_number,
        status=review.status,
        source_mode=review.quiz.source_mode,
        generation_theme=review.quiz.generation_theme,
        theme_config=review.quiz.theme_config or {},
        difficulty=review.quiz.difficulty,
        duration_minutes=review.quiz.duration_minutes,
        total_score=review.total_score,
        max_score=review.max_score,
        elapsed_seconds=review.elapsed_seconds,
        submitted_at=review.submitted_at,
        next_review_date=review.next_review_date,
        created_at=review.created_at,
        questions=[
            to_question_response(question, reveal) for question in review.quiz.questions
        ],
        answers=[to_answer_result(answer) for answer in ordered_answers],
        weak_points=list(dict.fromkeys(weak_points)),
    )


def to_review_summary(review: ReviewTask) -> ReviewTaskSummary:
    return ReviewTaskSummary(
        id=review.id,
        quiz_id=review.quiz_id,
        book_id=review.book_id,
        book_title=review.book.title,
        title=review.quiz.title,
        attempt_number=review.attempt_number,
        status=review.status,
        total_score=review.total_score,
        max_score=review.max_score,
        duration_minutes=review.quiz.duration_minutes,
        elapsed_seconds=review.elapsed_seconds,
        question_count=len(review.quiz.questions),
        created_at=review.created_at,
        submitted_at=review.submitted_at,
        next_review_date=review.next_review_date,
    )


@router.post(
    "/books/{book_id}/quizzes",
    response_model=QuizGenerationTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_quiz(
    book_id: str,
    payload: QuizGenerateRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuizGenerationTaskResponse:
    try:
        book = db.scalar(
            select(Book).where(Book.id == book_id, Book.workspace_id == identity.workspace.id)
        )
        if book is None:
            raise ValueError("未找到这本书")
        if book.shelf_status != "active":
            raise ValueError("这本书已下架，请恢复后再生成试卷")
        task = start_generation_task(
            db,
            book_id,
            payload,
            "manual_quiz_generation",
            created_by_user_id=identity.user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return to_generation_response(task, db)


@router.get(
    "/quiz-generation-tasks/{task_id}", response_model=QuizGenerationTaskResponse
)
def get_generation_task(
    task_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuizGenerationTaskResponse:
    statement = select(QuizGenerationTask).where(QuizGenerationTask.id == task_id)
    statement = statement.join(QuizGenerationTask.book).where(
        Book.workspace_id == identity.workspace.id
    )
    task = db.scalar(statement)
    if not task:
        raise HTTPException(status_code=404, detail="未找到这次出题任务")
    return to_generation_response(task)


@router.post(
    "/quiz-generation-tasks/{task_id}/questions/{position}/intervene",
    response_model=QuizGenerationTaskResponse,
)
def intervene_generation_task(
    task_id: str,
    position: int,
    payload: QuizGenerationInterventionRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuizGenerationTaskResponse:
    task = db.scalar(
        select(QuizGenerationTask)
        .join(QuizGenerationTask.book)
        .where(
            QuizGenerationTask.id == task_id,
            Book.workspace_id == identity.workspace.id,
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="未找到这次出题任务")
    try:
        updated = apply_generation_intervention(
            db,
            task.id,
            position,
            action=payload.action,
            question_payload=payload.question,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return to_generation_response(updated, db)


@router.get(
    "/quiz-generation-tasks/{task_id}/debug",
    response_model=QuizGenerationTaskDebugResponse,
)
def get_generation_task_debug(
    task_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuizGenerationTaskDebugResponse:
    task = db.scalar(
        select(QuizGenerationTask)
        .join(QuizGenerationTask.book)
        .where(
            QuizGenerationTask.id == task_id,
            Book.workspace_id == identity.workspace.id,
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="未找到这次出题任务")
    records = list(
        db.scalars(
            select(ModelUsageRecord)
            .where(ModelUsageRecord.task_id == task.id)
            .order_by(ModelUsageRecord.created_at, ModelUsageRecord.call_number)
        ).all()
    )
    return QuizGenerationTaskDebugResponse(
        task_id=task.id,
        calls=[
            QuizGenerationCallResponse(
                id=record.id,
                question_position=record.question_position,
                phase=record.phase,
                call_number=record.call_number,
                model_name=record.model_name,
                request_messages=list(record.request_messages or []),
                model_response=record.model_response,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                total_tokens=record.total_tokens,
                status=record.status,
                error_message=record.error_message,
                latency_ms=record.latency_ms,
                created_at=record.created_at,
            )
            for record in records
        ],
    )


@router.get("/quizzes/{quiz_id}", response_model=QuizResponse)
def get_quiz(
    quiz_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuizResponse:
    return to_quiz_response(get_quiz_or_404(db, quiz_id, identity))


@router.get(
    "/quizzes/{quiz_id}/generation-debug", response_model=QuizGenerationDebugResponse
)
def get_quiz_generation_debug(
    quiz_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuizGenerationDebugResponse:
    quiz = get_quiz_or_404(db, quiz_id, identity)
    record_filter = [ModelUsageRecord.quiz_id == quiz.id]
    if quiz.generation_task_id:
        record_filter = [
            or_(
                ModelUsageRecord.quiz_id == quiz.id,
                ModelUsageRecord.task_id == quiz.generation_task_id,
            )
        ]
    records = list(
        db.scalars(
            select(ModelUsageRecord)
            .where(*record_filter)
            .order_by(ModelUsageRecord.question_position, ModelUsageRecord.created_at)
        ).all()
    )
    calls_by_position: dict[int, list[ModelUsageRecord]] = {}
    unassigned: list[ModelUsageRecord] = []
    for record in records:
        if record.question_position is None:
            unassigned.append(record)
        else:
            calls_by_position.setdefault(record.question_position, []).append(record)

    def call_response(record: ModelUsageRecord) -> QuizGenerationCallResponse:
        return QuizGenerationCallResponse(
            id=record.id,
            question_position=record.question_position,
            phase=record.phase,
            call_number=record.call_number,
            model_name=record.model_name,
            request_messages=list(record.request_messages or []),
            model_response=record.model_response,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            total_tokens=record.total_tokens,
            status=record.status,
            error_message=record.error_message,
            latency_ms=record.latency_ms,
            created_at=record.created_at,
        )

    traces: list[QuizQuestionGenerationTrace] = []
    for question in quiz.questions:
        question_calls = [call_response(record) for record in calls_by_position.get(question.position, [])]
        traces.append(
            QuizQuestionGenerationTrace(
                question_id=question.id,
                position=question.position,
                prompt=question.prompt,
                source_chunk_ids=list(question.source_chunk_ids or []),
                quote_entry_ids=list(question.quote_entry_ids or []),
                calls=question_calls,
                input_tokens=sum(call.input_tokens or 0 for call in question_calls),
                output_tokens=sum(call.output_tokens or 0 for call in question_calls),
                total_tokens=sum(call.total_tokens or 0 for call in question_calls),
                unreported_calls=sum(call.total_tokens is None for call in question_calls),
            )
        )
    task = db.get(QuizGenerationTask, quiz.generation_task_id) if quiz.generation_task_id else None
    return QuizGenerationDebugResponse(
        quiz_id=quiz.id,
        book_id=quiz.book_id,
        quiz_title=quiz.title,
        generation_task_id=quiz.generation_task_id,
        task_type=task.task_type if task else None,
        task_status=task.status if task else None,
        model_name=next((record.model_name for record in records if record.model_name), None),
        questions=traces,
        unassigned_calls=[call_response(record) for record in unassigned],
        input_tokens=sum(record.input_tokens or 0 for record in records),
        output_tokens=sum(record.output_tokens or 0 for record in records),
        total_tokens=sum(record.total_tokens or 0 for record in records),
    )


@router.get("/quizzes/{quiz_id}/editable", response_model=QuizResponse)
def get_editable_quiz(
    quiz_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuizResponse:
    return to_quiz_response(get_quiz_or_404(db, quiz_id, identity), reveal_answers=True)


@router.patch("/quizzes/{quiz_id}/questions/{question_id}", response_model=QuestionResponse)
def update_question(
    quiz_id: str,
    question_id: str,
    payload: QuestionUpdateRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuestionResponse:
    quiz = get_quiz_or_404(db, quiz_id, identity, for_write=True)
    question = next((item for item in quiz.questions if item.id == question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="未找到这道题目")

    changes = payload.model_dump(exclude_unset=True)
    if changes.keys() & {"prompt", "options", "correct_answers", "knowledge_point", "reference_answer"}:
        question.fact_key = None
        question.fact_claim = None
        question.semantic_signature = None
    if "prompt" in changes:
        prompt = clean_optional_text(changes["prompt"])
        if not prompt:
            raise HTTPException(status_code=422, detail="题干不能为空")
        question.prompt = prompt
    if "explanation" in changes:
        explanation = clean_optional_text(changes["explanation"])
        question.explanation = explanation or ""
    if "knowledge_point" in changes:
        knowledge_point = clean_optional_text(changes["knowledge_point"])
        if not knowledge_point:
            raise HTTPException(status_code=422, detail="知识点不能为空")
        question.knowledge_point = knowledge_point
    if "reference_answer" in changes:
        reference_answer = clean_optional_text(changes["reference_answer"])
        question.reference_answer = reference_answer or None
    if "grading_rubric" in changes:
        question.grading_rubric = changes["grading_rubric"] or []

    if question.question_type == "short":
        if "options" in changes and changes["options"]:
            raise HTTPException(status_code=422, detail="问答题不支持选项")
        if "correct_answers" in changes and changes["correct_answers"]:
            raise HTTPException(status_code=422, detail="问答题不需要标准选项答案")
        question.options = []
        question.correct_answers = []
    else:
        option_ids = [option["id"] for option in question.options]
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
            question.options = normalized_options

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
            if question.question_type == "single" and len(deduped) != 1:
                raise HTTPException(status_code=422, detail="单选题只能有一个标准答案")
            if question.question_type == "multiple" and len(deduped) < 1:
                raise HTTPException(status_code=422, detail="多选题至少要有一个标准答案")
            question.correct_answers = deduped

    refresh_question_signature(question)
    db.commit()
    db.refresh(question)
    return to_question_response(question, True)


@router.post("/quizzes/{quiz_id}/questions/{question_id}/regenerate", response_model=QuestionResponse)
def regenerate_question(
    quiz_id: str,
    question_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuestionResponse:
    quiz = get_quiz_or_404(db, quiz_id, identity, for_write=True)
    question = next((item for item in quiz.questions if item.id == question_id), None)
    if question is None:
        raise HTTPException(status_code=404, detail="未找到这道题目")

    try:
        regenerated = regenerate_quiz_question(db, quiz, question, user_id=identity.user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return to_question_response(regenerated, True)


@router.delete("/quizzes/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(
    quiz_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> None:
    quiz = get_quiz_or_404(db, quiz_id, identity, for_write=True)
    if not quiz:
        raise HTTPException(status_code=404, detail="未找到这套复习试卷")

    book = db.get(Book, quiz.book_id)
    db.execute(
        update(QuizGenerationTask)
        .where(QuizGenerationTask.quiz_id == quiz.id)
        .values(quiz_id=None)
    )
    if book and book.pre_generation_quiz_id == quiz.id:
        book.pre_generation_quiz_id = None
        book.pre_generation_enabled = False
        book.pre_generation_status = "disabled"
        book.pre_generation_error = None
    db.execute(
        update(ExamShare)
        .where(ExamShare.quiz_id == quiz.id)
        .values(status="source_deleted", quiz_id=None, stopped_at=datetime.now(timezone.utc))
    )
    db.delete(quiz)
    db.commit()


@router.get("/books/{book_id}/quizzes", response_model=list[QuizSummary])
def list_book_quizzes(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[QuizSummary]:
    book_statement = select(Book).where(Book.id == book_id)
    book_statement = book_statement.where(Book.workspace_id == identity.workspace.id)
    if not db.scalar(book_statement):
        raise HTTPException(status_code=404, detail="未找到这本书")
    statement = select(Quiz).options(selectinload(Quiz.questions)).where(Quiz.book_id == book_id)
    quizzes = db.scalars(
        statement.order_by(Quiz.created_at.desc())
    ).all()
    return [to_quiz_summary(db, quiz) for quiz in quizzes]


def grade_objective(question: Question, selected: list[str]) -> GradeResult:
    selected_set = set(selected)
    correct_set = set(question.correct_answers)
    if question.question_type == "single":
        is_correct = selected_set == correct_set
        return GradeResult(
            score=question.max_score if is_correct else 0,
            is_correct=is_correct,
            feedback="回答正确。" if is_correct else "答案与原文依据不符。",
            matched_points=list(correct_set & selected_set),
            missing_points=list(correct_set - selected_set),
        )

    correct_hits = len(correct_set & selected_set)
    wrong_hits = len(selected_set - correct_set)
    if wrong_hits > 0:
        score = 0.0
    else:
        score = round(question.max_score * correct_hits / max(len(correct_set), 1), 1)
    is_correct = selected_set == correct_set
    return GradeResult(
        score=score,
        is_correct=is_correct,
        feedback="全部选对。" if is_correct else "本题错选记 0 分，少选按命中比例计分。",
        matched_points=list(correct_set & selected_set),
        missing_points=list(correct_set - selected_set),
    )


def calculate_next_review(score_percent: float) -> date:
    if score_percent < 60:
        days = 1
    elif score_percent < 80:
        days = 3
    elif score_percent < 90:
        days = 7
    else:
        days = 14
    return date.today() + timedelta(days=days)


@router.post("/quizzes/{quiz_id}/reviews", response_model=ReviewTaskResponse)
def start_review(
    quiz_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ReviewTaskResponse:
    quiz = get_quiz_or_404(db, quiz_id, identity, for_write=True)
    if quiz.book.shelf_status != "active":
        raise HTTPException(status_code=409, detail="这本书已下架，请恢复后再开始复习")
    attempt_number = (
        db.scalar(select(func.max(ReviewTask.attempt_number)).where(ReviewTask.quiz_id == quiz_id)) or 0
    ) + 1
    review = ReviewTask(
        book_id=quiz.book_id,
        quiz_id=quiz.id,
        attempt_number=attempt_number,
        status="in_progress",
        max_score=quiz.max_score,
    )
    db.add(review)
    db.commit()
    review = get_review_or_404(db, review.id, identity)
    return to_review_response(review)


@router.get("/reviews", response_model=list[ReviewTaskSummary])
def list_reviews(
    book_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    owner_id: str | None = Query(default=None),
    review_status: Literal["in_progress", "submitted"] | None = Query(
        default=None, alias="status"
    ),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[ReviewTaskSummary]:
    statement = (
        select(ReviewTask)
        .join(ReviewTask.book)
        .options(
            selectinload(ReviewTask.book),
            selectinload(ReviewTask.quiz).selectinload(Quiz.questions),
        )
        .order_by(ReviewTask.created_at.desc())
    )
    statement = statement.where(Book.workspace_id == identity.workspace.id)
    if owner_id and owner_id != identity.user.id:
        raise HTTPException(status_code=403, detail="不能查看其他用户的复习记录")
    if owner_id:
        statement = statement.where(Book.created_by_user_id == owner_id)
    if book_id:
        statement = statement.where(ReviewTask.book_id == book_id)
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        statement = statement.where(or_(Book.title.ilike(keyword), Book.author.ilike(keyword)))
    if review_status:
        statement = statement.where(ReviewTask.status == review_status)
    return [to_review_summary(review) for review in db.scalars(statement).all()]


@router.get("/reviews/{review_id}", response_model=ReviewTaskResponse)
def get_review(
    review_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ReviewTaskResponse:
    return to_review_response(get_review_or_404(db, review_id, identity))


@router.post("/reviews/{review_id}/reopen", response_model=ReviewTaskResponse)
def reopen_review(
    review_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ReviewTaskResponse:
    review = get_review_or_404(db, review_id, identity, for_write=True)
    if review.book.shelf_status != "active":
        raise HTTPException(status_code=409, detail="这本书已下架，请恢复后再重新答题")
    for answer in list(review.answers):
        db.delete(answer)
    review.status = "in_progress"
    review.total_score = None
    review.elapsed_seconds = None
    review.submitted_at = None
    review.next_review_date = None
    db.commit()
    return to_review_response(get_review_or_404(db, review_id, identity))


@router.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> None:
    review = get_review_or_404(db, review_id, identity, for_write=True)
    db.delete(review)
    db.commit()


@router.post("/reviews/{review_id}/submit", response_model=ReviewTaskResponse)
def submit_review(
    review_id: str,
    payload: QuizSubmitRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ReviewTaskResponse:
    review = get_review_or_404(db, review_id, identity, for_write=True)
    if review.status == "submitted":
        raise HTTPException(status_code=409, detail="这次复习已经提交，请先选择重新答题")
    submitted = {answer.question_id: answer for answer in payload.answers}
    question_ids = {question.id for question in review.quiz.questions}
    if set(submitted) - question_ids:
        raise HTTPException(status_code=422, detail="提交内容包含不属于这套试卷的题目")

    total_score = 0.0
    usage_context = new_usage_context(
        "quiz_submission",
        f"提交《{review.book.title}》第 {review.attempt_number} 次复习",
        book_id=review.book_id,
        quiz_id=review.quiz_id,
        user_id=identity.user.id,
        workspace_id=review.book.workspace_id,
    )
    provider = current_provider(db, usage_context)
    try:
        for question in review.quiz.questions:
            item = submitted.get(question.id)
            selected_answers = item.selected_answers if item else []
            text_answer = item.text_answer if item else None
            has_answer = bool(selected_answers) if question.question_type != "short" else bool((text_answer or "").strip())
            if not has_answer:
                missing_points = (
                    [str(rubric_item["point"]) for rubric_item in question.grading_rubric]
                    if question.question_type == "short"
                    else list(question.correct_answers)
                )
                grade = GradeResult(
                    score=0,
                    is_correct=False,
                    feedback="本题未作答，按 0 分处理。",
                    matched_points=[],
                    missing_points=missing_points,
                )
            elif question.question_type == "short":
                grade = provider.grade_short_answer(question, text_answer or "")
            else:
                grade = grade_objective(question, selected_answers)
            total_score += grade.score
            db.add(
                ReviewAnswer(
                    review_task_id=review.id,
                    question_id=question.id,
                    selected_answers=selected_answers,
                    text_answer=text_answer,
                    score=grade.score,
                    max_score=question.max_score,
                    is_correct=grade.is_correct,
                    feedback=grade.feedback,
                    matched_points=grade.matched_points,
                    missing_points=grade.missing_points,
                )
            )
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    review.total_score = round(total_score, 1)
    review.elapsed_seconds = payload.elapsed_seconds
    review.status = "submitted"
    review.submitted_at = datetime.now(timezone.utc)
    score_percent = review.total_score / review.max_score * 100 if review.max_score else 0
    review.next_review_date = calculate_next_review(score_percent)
    db.commit()
    db.expire(review, ["answers"])
    return to_review_response(get_review_or_404(db, review.id, identity))


@router.get("/reviews/{review_id}/result", response_model=ReviewTaskResponse)
def get_review_result(
    review_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ReviewTaskResponse:
    review = get_review_or_404(db, review_id, identity)
    if review.status != "submitted":
        raise HTTPException(status_code=409, detail="提交复习后才能查看结果")
    return to_review_response(review)


@router.get("/books/{book_id}/history", response_model=list[ReviewTaskSummary])
def get_book_history(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[ReviewTaskSummary]:
    book_statement = select(Book).where(Book.id == book_id)
    book_statement = book_statement.where(Book.workspace_id == identity.workspace.id)
    if not db.scalar(book_statement):
        raise HTTPException(status_code=404, detail="未找到这本书")
    reviews = db.scalars(
        select(ReviewTask)
        .join(ReviewTask.book)
        .options(
            selectinload(ReviewTask.book),
            selectinload(ReviewTask.quiz).selectinload(Quiz.questions),
        )
        .where(ReviewTask.book_id == book_id)
        .order_by(ReviewTask.created_at.desc())
    ).all()
    return [to_review_summary(review) for review in reviews]


@router.post("/quizzes/{quiz_id}/submit", response_model=ReviewTaskResponse)
def legacy_submit_quiz(
    quiz_id: str,
    payload: QuizSubmitRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ReviewTaskResponse:
    get_quiz_or_404(db, quiz_id, identity, for_write=True)
    statement = select(ReviewTask).where(
        ReviewTask.quiz_id == quiz_id, ReviewTask.status == "in_progress"
    )
    statement = statement.join(ReviewTask.book).where(
        Book.workspace_id == identity.workspace.id
    )
    review = db.scalar(
        statement
        .order_by(ReviewTask.created_at.desc())
    )
    if not review:
        review_response = start_review(quiz_id, db, identity)
        review_id = review_response.id
    else:
        review_id = review.id
    return submit_review(review_id, payload, db, identity)


@router.get("/quizzes/{quiz_id}/result", response_model=ReviewTaskResponse)
def legacy_quiz_result(
    quiz_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ReviewTaskResponse:
    get_quiz_or_404(db, quiz_id, identity)
    statement = select(ReviewTask).where(
        ReviewTask.quiz_id == quiz_id, ReviewTask.status == "submitted"
    )
    statement = statement.join(ReviewTask.book).where(
        Book.workspace_id == identity.workspace.id
    )
    review = db.scalar(
        statement
        .order_by(ReviewTask.submitted_at.desc())
    )
    if not review:
        raise HTTPException(status_code=409, detail="提交复习后才能查看结果")
    return get_review_result(review.id, db, identity)
