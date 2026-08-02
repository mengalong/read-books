from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Book, ContentChunk, PdfDocument, Quiz
from app.schemas import (
    BookCreate,
    BookDetail,
    BookSummary,
    BookUpdate,
    ChunkResponse,
    PdfResponse,
)
from app.services.book_stats import to_book_detail, to_book_summary
from app.services.pdf_parser import parse_pdf_document

router = APIRouter(prefix="/books", tags=["books"])
settings = get_settings()


def get_book_or_404(db: Session, book_id: str) -> Book:
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="未找到这本书")
    return book


@router.get("", response_model=list[BookSummary])
def list_books(
    search: str | None = None,
    reading_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[BookSummary]:
    statement = select(Book).order_by(Book.updated_at.desc())
    if search:
        keyword = f"%{search.strip()}%"
        statement = statement.where(or_(Book.title.ilike(keyword), Book.author.ilike(keyword)))
    if reading_status:
        statement = statement.where(Book.reading_status == reading_status)
    return [to_book_summary(db, book) for book in db.scalars(statement).all()]


@router.post("", response_model=BookDetail, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate, db: Session = Depends(get_db)) -> BookDetail:
    book = Book(**payload.model_dump())
    db.add(book)
    db.commit()
    db.refresh(book)
    return to_book_detail(db, book)


@router.get("/{book_id}", response_model=BookDetail)
def get_book(book_id: str, db: Session = Depends(get_db)) -> BookDetail:
    return to_book_detail(db, get_book_or_404(db, book_id))


@router.patch("/{book_id}", response_model=BookDetail)
def update_book(
    book_id: str, payload: BookUpdate, db: Session = Depends(get_db)
) -> BookDetail:
    book = get_book_or_404(db, book_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(book, key, value)
    db.commit()
    db.refresh(book)
    return to_book_detail(db, book)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: str, db: Session = Depends(get_db)) -> None:
    book = get_book_or_404(db, book_id)
    file_paths = [pdf.file_path for pdf in book.pdfs if not pdf.file_path.startswith("demo://")]
    db.delete(book)
    db.commit()
    for file_path in file_paths:
        Path(file_path).unlink(missing_ok=True)


@router.post(
    "/{book_id}/pdfs", response_model=PdfResponse, status_code=status.HTTP_202_ACCEPTED
)
async def upload_pdf(
    book_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PdfResponse:
    get_book_or_404(db, book_id)
    original_name = Path(file.filename or "book.pdf").name
    if not original_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请选择 PDF 文件")

    settings.ensure_directories()
    stored_path = settings.upload_dir / f"{uuid4()}.pdf"
    file_size = 0
    first_chunk = True
    try:
        with stored_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                if first_chunk and not chunk.startswith(b"%PDF"):
                    raise HTTPException(status_code=400, detail="文件内容不是有效的 PDF")
                first_chunk = False
                destination.write(chunk)
                file_size += len(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if file_size == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="PDF 文件为空")

    pdf = PdfDocument(
        book_id=book_id,
        file_name=original_name,
        file_path=str(stored_path.resolve()),
        file_size=file_size,
        parse_status="pending",
    )
    db.add(pdf)
    db.commit()
    db.refresh(pdf)
    background_tasks.add_task(parse_pdf_document, pdf.id)
    return PdfResponse.model_validate(pdf)


@router.get("/{book_id}/pdfs", response_model=list[PdfResponse])
def list_pdfs(book_id: str, db: Session = Depends(get_db)) -> list[PdfDocument]:
    get_book_or_404(db, book_id)
    return list(
        db.scalars(
            select(PdfDocument)
            .where(PdfDocument.book_id == book_id)
            .order_by(PdfDocument.created_at.desc())
        ).all()
    )


@router.get("/{book_id}/pdfs/{pdf_id}", response_model=PdfResponse)
def get_pdf(book_id: str, pdf_id: str, db: Session = Depends(get_db)) -> PdfDocument:
    pdf = db.get(PdfDocument, pdf_id)
    if not pdf or pdf.book_id != book_id:
        raise HTTPException(status_code=404, detail="未找到这个 PDF")
    return pdf


@router.delete("/{book_id}/pdfs/{pdf_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pdf(book_id: str, pdf_id: str, db: Session = Depends(get_db)) -> None:
    pdf = db.get(PdfDocument, pdf_id)
    if not pdf or pdf.book_id != book_id:
        raise HTTPException(status_code=404, detail="未找到这个 PDF")

    draft_quiz_ids = db.scalars(
        select(Quiz.id).where(Quiz.book_id == book_id, Quiz.status != "submitted")
    ).all()
    if draft_quiz_ids:
        db.execute(delete(Quiz).where(Quiz.id.in_(draft_quiz_ids)))
    file_path = pdf.file_path
    db.delete(pdf)
    db.commit()
    if not file_path.startswith("demo://"):
        Path(file_path).unlink(missing_ok=True)


@router.get("/{book_id}/chunks", response_model=list[ChunkResponse])
def list_chunks(
    book_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ChunkResponse]:
    get_book_or_404(db, book_id)
    rows = db.execute(
        select(ContentChunk, PdfDocument.file_name)
        .join(PdfDocument, PdfDocument.id == ContentChunk.pdf_id)
        .where(ContentChunk.book_id == book_id)
        .order_by(ContentChunk.page_number, ContentChunk.sequence)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [
        ChunkResponse(
            id=chunk.id,
            pdf_id=chunk.pdf_id,
            page_number=chunk.page_number,
            sequence=chunk.sequence,
            content=chunk.content,
            char_count=chunk.char_count,
            file_name=file_name,
        )
        for chunk, file_name in rows
    ]

