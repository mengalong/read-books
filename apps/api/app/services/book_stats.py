from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Book, ContentChunk, PdfDocument, Quiz
from app.schemas import BookDetail, BookStats, BookSummary, PdfResponse


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
            func.count(Quiz.id),
            func.avg(Quiz.total_score),
            func.max(Quiz.submitted_at),
            func.max(Quiz.next_review_date),
        ).where(Quiz.book_id == book_id, Quiz.status == "submitted")
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
    return BookSummary(
        **BookSummary.model_validate(book).model_dump(exclude={"stats"}),
        stats=get_book_stats(db, book.id),
    )


def to_book_detail(db: Session, book: Book) -> BookDetail:
    summary = to_book_summary(db, book)
    pdfs = db.scalars(
        select(PdfDocument)
        .where(PdfDocument.book_id == book.id)
        .order_by(PdfDocument.created_at.desc())
    ).all()
    return BookDetail(
        **summary.model_dump(),
        pdfs=[PdfResponse.model_validate(pdf) for pdf in pdfs],
    )

