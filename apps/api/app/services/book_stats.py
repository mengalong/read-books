from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Book, ContentChunk, PdfDocument, Quiz, QuizGenerationTask, ReviewTask
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
    quiz_count, average_score, last_reviewed_at, next_review_date = db.execute(
        select(
            func.count(ReviewTask.id),
            func.avg(ReviewTask.total_score),
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
    return BookSummary(
        **BookSummary.model_validate(book).model_dump(
            exclude={
                "stats",
                "active_generation_task_id",
                "active_generation_status",
                "active_generation_completed_questions",
                "active_generation_total_questions",
                "active_generation_phase",
            }
        ),
        stats=get_book_stats(db, book.id),
        active_generation_task_id=active_task.id if active_task else None,
        active_generation_status=active_task.status if active_task else None,
        active_generation_completed_questions=active_task.completed_questions if active_task else 0,
        active_generation_total_questions=active_task.total_questions if active_task else 0,
        active_generation_phase=active_task.current_phase if active_task else None,
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
    quiz_summaries = []
    for quiz in quizzes:
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
        quiz_summaries.append(
            QuizSummary(
                id=quiz.id,
                book_id=quiz.book_id,
                title=quiz.title,
                difficulty=quiz.difficulty,
                duration_minutes=quiz.duration_minutes,
                status=quiz.status,
                question_count=len(quiz.questions),
                max_score=quiz.max_score,
                created_at=quiz.created_at,
                review_count=review_count,
                latest_score=latest_review.total_score if latest_review else None,
                last_reviewed_at=latest_review.submitted_at if latest_review else None,
            )
        )
    return BookDetail(
        **summary.model_dump(),
        pdfs=[PdfResponse.model_validate(pdf) for pdf in pdfs],
        quizzes=quiz_summaries,
    )
