from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Answer, Book, ContentChunk, PdfDocument, Question, Quiz
from app.schemas import (
    AnswerResult,
    HistoryItem,
    QuestionResponse,
    QuizGenerateRequest,
    QuizResponse,
    QuizResult,
    QuizSubmitRequest,
)
from app.services.quiz_provider import GradeResult, get_quiz_provider

router = APIRouter(tags=["quizzes"])
settings = get_settings()
provider = get_quiz_provider(settings)


def get_quiz_or_404(db: Session, quiz_id: str) -> Quiz:
    quiz = db.scalar(
        select(Quiz)
        .options(selectinload(Quiz.questions), selectinload(Quiz.answers))
        .where(Quiz.id == quiz_id)
    )
    if not quiz:
        raise HTTPException(status_code=404, detail="未找到这套测试")
    return quiz


def to_question_response(question: Question, reveal_answers: bool) -> QuestionResponse:
    return QuestionResponse(
        id=question.id,
        position=question.position,
        question_type=question.question_type,
        prompt=question.prompt,
        options=question.options,
        explanation=question.explanation if reveal_answers else None,
        knowledge_point=question.knowledge_point,
        difficulty=question.difficulty,
        estimated_seconds=question.estimated_seconds,
        reference_answer=question.reference_answer if reveal_answers else None,
        grading_rubric=question.grading_rubric if reveal_answers else [],
        source_evidence=question.source_evidence,
        max_score=question.max_score,
        correct_answers=question.correct_answers if reveal_answers else None,
    )


def to_quiz_response(quiz: Quiz, reveal_answers: bool = False) -> QuizResponse:
    return QuizResponse(
        id=quiz.id,
        book_id=quiz.book_id,
        book_title=quiz.book.title,
        title=quiz.title,
        difficulty=quiz.difficulty,
        duration_minutes=quiz.duration_minutes,
        status=quiz.status,
        total_score=quiz.total_score,
        max_score=quiz.max_score,
        elapsed_seconds=quiz.elapsed_seconds,
        submitted_at=quiz.submitted_at,
        next_review_date=quiz.next_review_date,
        created_at=quiz.created_at,
        questions=[to_question_response(question, reveal_answers) for question in quiz.questions],
    )


@router.post(
    "/books/{book_id}/quizzes",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_quiz(
    book_id: str, payload: QuizGenerateRequest, db: Session = Depends(get_db)
) -> QuizResponse:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="未找到这本书")
    if payload.single_count + payload.multiple_count + payload.short_count == 0:
        raise HTTPException(status_code=422, detail="至少需要选择一种题型")
    if payload.page_start and payload.page_end and payload.page_start > payload.page_end:
        raise HTTPException(status_code=422, detail="起始页不能晚于结束页")

    statement = (
        select(ContentChunk)
        .join(PdfDocument, PdfDocument.id == ContentChunk.pdf_id)
        .where(ContentChunk.book_id == book_id, PdfDocument.parse_status == "completed")
        .order_by(ContentChunk.page_number, ContentChunk.sequence)
    )
    if payload.page_start:
        statement = statement.where(ContentChunk.page_number >= payload.page_start)
    if payload.page_end:
        statement = statement.where(ContentChunk.page_number <= payload.page_end)
    chunks = list(db.scalars(statement).all())
    if not chunks:
        raise HTTPException(status_code=409, detail="还没有可用于出题的 PDF 原文，请先完成解析")

    pdf_ids = {chunk.pdf_id for chunk in chunks}
    file_names = dict(
        db.execute(
            select(PdfDocument.id, PdfDocument.file_name).where(PdfDocument.id.in_(pdf_ids))
        ).all()
    )
    generation_number = db.scalar(select(func.count(Quiz.id)).where(Quiz.book_id == book_id)) or 0
    recent_chunk_rows = db.scalars(
        select(Question.source_chunk_ids)
        .join(Quiz, Quiz.id == Question.quiz_id)
        .where(Quiz.book_id == book_id)
        .order_by(Quiz.created_at.desc())
        .limit(40)
    ).all()
    recent_chunk_ids = {chunk_id for row in recent_chunk_rows for chunk_id in row}

    try:
        generated = provider.generate_questions(
            chunks=chunks,
            file_names=file_names,
            single_count=payload.single_count,
            multiple_count=payload.multiple_count,
            short_count=payload.short_count,
            difficulty=payload.difficulty,
            generation_number=generation_number,
            recent_chunk_ids=recent_chunk_ids,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not generated:
        raise HTTPException(status_code=409, detail="现有原文不足以生成可靠题目")

    quiz = Quiz(
        book_id=book_id,
        title=f"第 {generation_number + 1} 次复习测试",
        difficulty=payload.difficulty,
        duration_minutes=payload.duration_minutes,
        status="ready",
        max_score=sum(item.max_score for item in generated),
    )
    db.add(quiz)
    db.flush()
    for position, item in enumerate(generated, start=1):
        db.add(
            Question(
                quiz_id=quiz.id,
                position=position,
                question_type=item.question_type,
                prompt=item.prompt,
                options=item.options,
                correct_answers=item.correct_answers,
                explanation=item.explanation,
                knowledge_point=item.knowledge_point,
                difficulty=payload.difficulty,
                estimated_seconds=item.estimated_seconds,
                reference_answer=item.reference_answer,
                grading_rubric=item.grading_rubric,
                source_chunk_ids=item.source_chunk_ids,
                source_evidence=item.source_evidence,
                max_score=item.max_score,
            )
        )
    db.commit()
    quiz = get_quiz_or_404(db, quiz.id)
    return to_quiz_response(quiz)


@router.get("/quizzes/{quiz_id}", response_model=QuizResponse)
def get_quiz(quiz_id: str, db: Session = Depends(get_db)) -> QuizResponse:
    quiz = get_quiz_or_404(db, quiz_id)
    return to_quiz_response(quiz, reveal_answers=quiz.status == "submitted")


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
    accuracy = max(0.0, correct_hits / max(len(correct_set), 1) - wrong_hits / 4)
    score = round(question.max_score * accuracy, 1)
    is_correct = selected_set == correct_set
    return GradeResult(
        score=score,
        is_correct=is_correct,
        feedback="全部选对。" if is_correct else "本题按选对项计分，错选会扣除部分得分。",
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


@router.post("/quizzes/{quiz_id}/submit", response_model=QuizResult)
def submit_quiz(
    quiz_id: str, payload: QuizSubmitRequest, db: Session = Depends(get_db)
) -> QuizResult:
    quiz = get_quiz_or_404(db, quiz_id)
    if quiz.status == "submitted":
        raise HTTPException(status_code=409, detail="这套测试已经提交")

    submitted = {answer.question_id: answer for answer in payload.answers}
    question_ids = {question.id for question in quiz.questions}
    unknown_ids = set(submitted) - question_ids
    if unknown_ids:
        raise HTTPException(status_code=422, detail="提交内容包含不属于这套测试的题目")

    total_score = 0.0
    for question in quiz.questions:
        item = submitted.get(question.id)
        selected_answers = item.selected_answers if item else []
        text_answer = item.text_answer if item else None
        if question.question_type == "short":
            grade = provider.grade_short_answer(question, text_answer or "")
        else:
            grade = grade_objective(question, selected_answers)
        total_score += grade.score
        db.add(
            Answer(
                quiz_id=quiz.id,
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

    quiz.total_score = round(total_score, 1)
    quiz.elapsed_seconds = payload.elapsed_seconds
    quiz.status = "submitted"
    quiz.submitted_at = datetime.now(timezone.utc)
    score_percent = quiz.total_score / quiz.max_score * 100 if quiz.max_score else 0
    quiz.next_review_date = calculate_next_review(score_percent)
    db.commit()
    return build_result(get_quiz_or_404(db, quiz.id))


def build_result(quiz: Quiz) -> QuizResult:
    base = to_quiz_response(quiz, reveal_answers=True)
    answers = sorted(quiz.answers, key=lambda answer: answer.question.position)
    weak_points = [
        answer.question.knowledge_point
        for answer in answers
        if answer.max_score and answer.score / answer.max_score < 0.6
    ]
    return QuizResult(
        **base.model_dump(),
        answers=[
            AnswerResult(
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
            for answer in answers
        ],
        weak_points=list(dict.fromkeys(weak_points)),
    )


@router.get("/quizzes/{quiz_id}/result", response_model=QuizResult)
def get_quiz_result(quiz_id: str, db: Session = Depends(get_db)) -> QuizResult:
    quiz = get_quiz_or_404(db, quiz_id)
    if quiz.status != "submitted":
        raise HTTPException(status_code=409, detail="提交测试后才能查看结果")
    return build_result(quiz)


@router.get("/books/{book_id}/history", response_model=list[HistoryItem])
def get_book_history(book_id: str, db: Session = Depends(get_db)) -> list[HistoryItem]:
    if not db.get(Book, book_id):
        raise HTTPException(status_code=404, detail="未找到这本书")
    quizzes = db.scalars(
        select(Quiz)
        .options(selectinload(Quiz.questions))
        .where(Quiz.book_id == book_id)
        .order_by(Quiz.created_at.desc())
    ).all()
    return [
        HistoryItem(
            id=quiz.id,
            title=quiz.title,
            difficulty=quiz.difficulty,
            status=quiz.status,
            total_score=quiz.total_score,
            max_score=quiz.max_score,
            duration_minutes=quiz.duration_minutes,
            elapsed_seconds=quiz.elapsed_seconds,
            question_count=len(quiz.questions),
            created_at=quiz.created_at,
            submitted_at=quiz.submitted_at,
            next_review_date=quiz.next_review_date,
        )
        for quiz in quizzes
    ]

