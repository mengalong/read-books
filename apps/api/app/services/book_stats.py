from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Book,
    ContentChunk,
    PdfDocument,
    QuoteEntry,
    Quiz,
    QuizGenerationTask,
    ResourceMaterial,
    ReviewTask,
)
from app.schemas import BookDetail, BookStats, BookSummary, PdfResponse, QuizSummary


def get_book_stats(db: Session, book_id: str) -> BookStats:
    pdf_count, completed_pdf_count = db.execute(
        select(
            func.count(PdfDocument.id),
            func.count(PdfDocument.id).filter(PdfDocument.parse_status == "completed"),
        ).where(PdfDocument.book_id == book_id)
    ).one()
    chunk_count = db.scalar(
        select(func.count(ContentChunk.id)).where(ContentChunk.book_id == book_id)
    )
    material_count, ready_material_count = db.execute(
        select(
            func.count(ResourceMaterial.id),
            func.count(ResourceMaterial.id).filter(
                ResourceMaterial.parse_status == "completed"
            ),
        ).where(ResourceMaterial.book_id == book_id)
    ).one()
    quote_count, confirmed_quote_count = db.execute(
        select(
            func.count(QuoteEntry.id),
            func.count(QuoteEntry.id).filter(
                QuoteEntry.review_status == "confirmed",
                QuoteEntry.enabled_for_generation.is_(True),
            ),
        ).where(QuoteEntry.book_id == book_id)
    ).one()
    quiz_count, average_score, last_reviewed_at, next_review_date = db.execute(
        select(
            func.count(ReviewTask.id),
            func.avg(ReviewTask.total_score * 100.0 / func.nullif(ReviewTask.max_score, 0)),
            func.max(ReviewTask.submitted_at),
            func.max(ReviewTask.next_review_date),
        ).where(ReviewTask.book_id == book_id, ReviewTask.status == "submitted")
    ).one()
    return BookStats(
        pdf_count=pdf_count or 0,
        completed_pdf_count=completed_pdf_count or 0,
        chunk_count=chunk_count or 0,
        quiz_count=quiz_count or 0,
        average_score=round(float(average_score), 1) if average_score is not None else None,
        last_reviewed_at=last_reviewed_at,
        next_review_date=next_review_date,
        material_count=material_count or 0,
        ready_material_count=ready_material_count or 0,
        quote_count=quote_count or 0,
        confirmed_quote_count=confirmed_quote_count or 0,
    )


def to_book_summary(db: Session, book: Book) -> BookSummary:
    active_task = db.scalar(
        select(QuizGenerationTask)
        .where(
            QuizGenerationTask.book_id == book.id,
            QuizGenerationTask.status.in_(["pending", "processing"]),
        )
        .order_by(QuizGenerationTask.created_at.desc())
    )
    owner = book.workspace.created_by_user if book.workspace else book.created_by_user
    return BookSummary(
        **BookSummary.model_validate(book).model_dump(
            exclude={
                "stats",
                "active_generation_task_id",
                "active_generation_status",
                "active_generation_completed_questions",
                "active_generation_total_questions",
                "active_generation_phase",
                "owner_user_id",
                "owner_display_name",
            }
        ),
        owner_user_id=owner.id if owner else None,
        owner_display_name=owner.display_name if owner else None,
        stats=get_book_stats(db, book.id),
        active_generation_task_id=active_task.id if active_task else None,
        active_generation_status=active_task.status if active_task else None,
        active_generation_completed_questions=active_task.completed_questions if active_task else 0,
        active_generation_total_questions=active_task.total_questions if active_task else 0,
        active_generation_phase=active_task.current_phase if active_task else None,
    )


def to_quiz_summary(db: Session, quiz: Quiz) -> QuizSummary:
    question_counts = {"single": 0, "multiple": 0, "short": 0}
    for question in quiz.questions:
        if question.question_type in question_counts:
            question_counts[question.question_type] += 1
    review_count = db.scalar(
        select(func.count(ReviewTask.id)).where(
            ReviewTask.quiz_id == quiz.id, ReviewTask.status == "submitted"
        )
    ) or 0
    latest_review = db.scalar(
        select(ReviewTask)
        .where(ReviewTask.quiz_id == quiz.id, ReviewTask.status == "submitted")
        .order_by(ReviewTask.submitted_at.desc())
        .limit(1)
    )
    return QuizSummary(
        id=quiz.id,
        book_id=quiz.book_id,
        title=quiz.title,
        difficulty=quiz.difficulty,
        duration_minutes=quiz.duration_minutes,
        status=quiz.status,
        source_mode=quiz.source_mode,
        generation_theme=quiz.generation_theme,
        theme_config=quiz.theme_config or {},
        question_count=len(quiz.questions),
        single_count=question_counts["single"],
        multiple_count=question_counts["multiple"],
        short_count=question_counts["short"],
        max_score=quiz.max_score,
        created_at=quiz.created_at,
        review_count=review_count,
        latest_score=latest_review.total_score if latest_review else None,
        last_reviewed_at=latest_review.submitted_at if latest_review else None,
    )


def to_book_detail(db: Session, book: Book) -> BookDetail:
    summary = to_book_summary(db, book)
    pdfs = db.scalars(
        select(PdfDocument)
        .where(PdfDocument.book_id == book.id)
        .order_by(PdfDocument.created_at.desc())
    ).all()
    quizzes = db.scalars(
        select(Quiz)
        .options(selectinload(Quiz.questions))
        .where(Quiz.book_id == book.id)
        .order_by(Quiz.created_at.desc())
    ).all()
    quiz_summaries = [to_quiz_summary(db, quiz) for quiz in quizzes]
    return BookDetail(
        **summary.model_dump(),
        pdfs=[PdfResponse.model_validate(pdf) for pdf in pdfs],
        quizzes=quiz_summaries,
    )
