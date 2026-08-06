import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_admin, require_ready_identity
from app.models import (
    Book,
    ContentChunk,
    ExamShare,
    PdfDocument,
    Quiz,
    QuizGenerationTask,
    User,
)
from app.services.auth import AuthIdentity, add_audit_log, get_personal_workspace
from app.schemas import (
    AdminBookCopyRequest,
    AdminBookCopyResponse,
    BookCreate,
    BookDetail,
    BookSummary,
    BookUpdate,
    ChunkResponse,
    PdfResponse,
    PreGenerationResponse,
)
from app.services.book_stats import to_book_detail, to_book_summary
from app.services.pdf_parser import parse_pdf_document
from app.services.pre_generation import start_pre_generation

router = APIRouter(prefix="/books", tags=["books"])
admin_router = APIRouter(prefix="/admin/books", tags=["admin-books"])
settings = get_settings()


def get_book_or_404(
    db: Session, book_id: str, identity: AuthIdentity, *, for_write: bool = False
) -> Book:
    statement = select(Book).where(Book.id == book_id, Book.workspace_id == identity.workspace.id)
    book = db.scalar(statement)
    if not book:
        raise HTTPException(status_code=404, detail="未找到这本书")
    return book


def get_admin_book_or_404(db: Session, book_id: str) -> Book:
    book = db.scalar(select(Book).where(Book.id == book_id))
    if not book:
        raise HTTPException(status_code=404, detail="未找到这本书")
    return book


def ensure_book_is_active(book: Book) -> None:
    if book.shelf_status != "active":
        raise HTTPException(status_code=409, detail="这本书已下架，请恢复后再进行此操作")


def ensure_book_has_no_active_generation(db: Session, book: Book) -> None:
    active_task = db.scalar(
        select(QuizGenerationTask.id).where(
            QuizGenerationTask.book_id == book.id,
            QuizGenerationTask.status.in_(["pending", "processing"]),
        )
    )
    if active_task:
        raise HTTPException(status_code=409, detail="这本书正在生成试卷，完成后才能下架或删除")


def delete_book_and_files(db: Session, book: Book) -> None:
    file_paths = [pdf.file_path for pdf in book.pdfs if not pdf.file_path.startswith("demo://")]
    db.execute(
        update(ExamShare)
        .where(ExamShare.book_id == book.id)
        .values(
            status="source_deleted",
            book_id=None,
            quiz_id=None,
            stopped_at=datetime.now(timezone.utc),
        )
    )
    db.delete(book)
    db.commit()
    for file_path in file_paths:
        Path(file_path).unlink(missing_ok=True)


@router.get("", response_model=list[BookSummary])
def list_books(
    search: str | None = None,
    reading_status: str | None = Query(default=None, alias="status"),
    shelf_status: Literal["active", "unlisted"] = Query(default="active"),
    owner_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[BookSummary]:
    statement = (
        select(Book)
        .where(
            Book.workspace_id == identity.workspace.id,
            Book.shelf_status == shelf_status,
        )
        .order_by(Book.updated_at.desc())
    )
    if owner_id and owner_id != identity.user.id:
        raise HTTPException(status_code=403, detail="不能查看其他用户的书籍")
    if search:
        keyword = f"%{search.strip()}%"
        statement = statement.where(or_(Book.title.ilike(keyword), Book.author.ilike(keyword)))
    if reading_status:
        statement = statement.where(Book.reading_status == reading_status)
    return [to_book_summary(db, book) for book in db.scalars(statement).all()]


@router.post("", response_model=BookDetail, status_code=status.HTTP_201_CREATED)
def create_book(
    payload: BookCreate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> BookDetail:
    book = Book(
        **payload.model_dump(),
        workspace_id=identity.workspace.id,
        created_by_user_id=identity.user.id,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return to_book_detail(db, book)


@router.get("/{book_id}", response_model=BookDetail)
def get_book(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> BookDetail:
    return to_book_detail(db, get_book_or_404(db, book_id, identity))


@router.patch("/{book_id}", response_model=BookDetail)
def update_book(
    book_id: str,
    payload: BookUpdate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> BookDetail:
    book = get_book_or_404(db, book_id, identity, for_write=True)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(book, key, value)
    db.commit()
    db.refresh(book)
    return to_book_detail(db, book)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> None:
    book = get_book_or_404(db, book_id, identity, for_write=True)
    ensure_book_has_no_active_generation(db, book)
    delete_book_and_files(db, book)


@router.post("/{book_id}/unlist", response_model=BookDetail)
def unlist_book(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> BookDetail:
    book = get_book_or_404(db, book_id, identity, for_write=True)
    ensure_book_has_no_active_generation(db, book)
    book.shelf_status = "unlisted"
    db.commit()
    db.refresh(book)
    return to_book_detail(db, book)


@router.post("/{book_id}/restore", response_model=BookDetail)
def restore_book(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> BookDetail:
    book = get_book_or_404(db, book_id, identity, for_write=True)
    book.shelf_status = "active"
    db.commit()
    db.refresh(book)
    return to_book_detail(db, book)


@router.post(
    "/{book_id}/pdfs", response_model=PdfResponse, status_code=status.HTTP_202_ACCEPTED
)
async def upload_pdf(
    book_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> PdfResponse:
    book = get_book_or_404(db, book_id, identity, for_write=True)
    ensure_book_is_active(book)
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
    import threading

    threading.Thread(target=parse_pdf_document, args=(pdf.id,), daemon=True).start()
    return PdfResponse.model_validate(pdf)


@router.post(
    "/{book_id}/pre-generation",
    response_model=PreGenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_book_pre_generation(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> PreGenerationResponse:
    book = get_book_or_404(db, book_id, identity, for_write=True)
    ensure_book_is_active(book)
    try:
        return start_pre_generation(db, book_id, created_by_user_id=identity.user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{book_id}/pdfs", response_model=list[PdfResponse])
def list_pdfs(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[PdfDocument]:
    get_book_or_404(db, book_id, identity)
    return list(
        db.scalars(
            select(PdfDocument)
            .where(PdfDocument.book_id == book_id)
            .order_by(PdfDocument.created_at.desc())
        ).all()
    )


@router.get("/{book_id}/pdfs/{pdf_id}", response_model=PdfResponse)
def get_pdf(
    book_id: str,
    pdf_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> PdfDocument:
    get_book_or_404(db, book_id, identity)
    pdf = db.get(PdfDocument, pdf_id)
    if not pdf or pdf.book_id != book_id:
        raise HTTPException(status_code=404, detail="未找到这个 PDF")
    return pdf


@router.delete("/{book_id}/pdfs/{pdf_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pdf(
    book_id: str,
    pdf_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> None:
    get_book_or_404(db, book_id, identity, for_write=True)
    pdf = db.get(PdfDocument, pdf_id)
    if not pdf or pdf.book_id != book_id:
        raise HTTPException(status_code=404, detail="未找到这个 PDF")

    draft_quiz_ids = db.scalars(
        select(Quiz.id).where(Quiz.book_id == book_id, Quiz.status != "submitted")
    ).all()
    if draft_quiz_ids:
        db.execute(
            update(ExamShare)
            .where(ExamShare.quiz_id.in_(draft_quiz_ids))
            .values(
                status="source_deleted",
                quiz_id=None,
                stopped_at=datetime.now(timezone.utc),
            )
        )
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
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[ChunkResponse]:
    get_book_or_404(db, book_id, identity)
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


@admin_router.get("", response_model=list[BookSummary])
def list_admin_books(
    search: str | None = None,
    reading_status: str | None = Query(default=None, alias="status"),
    shelf_status: Literal["active", "unlisted"] | None = Query(default=None),
    owner_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: AuthIdentity = Depends(require_admin),
) -> list[BookSummary]:
    statement = select(Book).order_by(Book.updated_at.desc())
    if owner_id:
        statement = statement.where(Book.created_by_user_id == owner_id)
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        statement = statement.where(or_(Book.title.ilike(keyword), Book.author.ilike(keyword)))
    if reading_status:
        statement = statement.where(Book.reading_status == reading_status)
    if shelf_status:
        statement = statement.where(Book.shelf_status == shelf_status)
    return [to_book_summary(db, book) for book in db.scalars(statement).all()]


@admin_router.get("/{book_id}", response_model=BookDetail)
def get_admin_book(
    book_id: str,
    db: Session = Depends(get_db),
    _: AuthIdentity = Depends(require_admin),
) -> BookDetail:
    return to_book_detail(db, get_admin_book_or_404(db, book_id))


@admin_router.post("/{book_id}/unlist", response_model=BookDetail)
def unlist_admin_book(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> BookDetail:
    book = get_admin_book_or_404(db, book_id)
    ensure_book_has_no_active_generation(db, book)
    changed = book.shelf_status != "unlisted"
    book.shelf_status = "unlisted"
    if changed:
        add_audit_log(
            db,
            actor_user_id=identity.user.id,
            action="admin.book_unlisted",
            target_type="book",
            target_id=book.id,
            details={"owner_user_id": book.created_by_user_id},
        )
    db.commit()
    db.refresh(book)
    return to_book_detail(db, book)


@admin_router.post("/{book_id}/restore", response_model=BookDetail)
def restore_admin_book(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> BookDetail:
    book = get_admin_book_or_404(db, book_id)
    changed = book.shelf_status != "active"
    book.shelf_status = "active"
    if changed:
        add_audit_log(
            db,
            actor_user_id=identity.user.id,
            action="admin.book_restored",
            target_type="book",
            target_id=book.id,
            details={"owner_user_id": book.created_by_user_id},
        )
    db.commit()
    db.refresh(book)
    return to_book_detail(db, book)


@admin_router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_book(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> None:
    book = get_admin_book_or_404(db, book_id)
    ensure_book_has_no_active_generation(db, book)
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="admin.book_deleted",
        target_type="book",
        target_id=book.id,
        details={
            "title": book.title,
            "owner_user_id": book.created_by_user_id,
            "workspace_id": book.workspace_id,
        },
    )
    delete_book_and_files(db, book)


@admin_router.get("/{book_id}/chunks", response_model=list[ChunkResponse])
def list_admin_book_chunks(
    book_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: AuthIdentity = Depends(require_admin),
) -> list[ChunkResponse]:
    get_admin_book_or_404(db, book_id)
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


@admin_router.post(
    "/{book_id}/copy",
    response_model=AdminBookCopyResponse,
    status_code=status.HTTP_201_CREATED,
)
def copy_admin_book(
    book_id: str,
    payload: AdminBookCopyRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> AdminBookCopyResponse:
    source = get_admin_book_or_404(db, book_id)
    target_user = db.get(User, payload.target_user_id)
    if target_user is None or target_user.status != "active":
        raise HTTPException(status_code=404, detail="未找到可用的目标用户")
    target_workspace = get_personal_workspace(db, target_user.id)
    if target_workspace is None:
        raise HTTPException(status_code=409, detail="目标用户缺少个人工作空间")
    if source.workspace_id == target_workspace.id:
        raise HTTPException(status_code=409, detail="这本书已经在目标用户的书架中")
    if payload.copy_content and not payload.copy_pdf:
        raise HTTPException(status_code=422, detail="复制原文片段时必须同时复制 PDF")

    settings.ensure_directories()
    copied_paths: list[Path] = []
    copied_pdf_count = 0
    copied_chunk_count = 0
    try:
        copied_book = Book(
            title=source.title,
            author=source.author,
            description=source.description,
            cover_color=source.cover_color,
            language=source.language,
            reading_status=source.reading_status,
            shelf_status="active",
            tags=list(source.tags or []),
            workspace_id=target_workspace.id,
            created_by_user_id=target_user.id,
            pre_generation_enabled=False,
            pre_generation_status="disabled",
            pre_generation_error=None,
            pre_generation_quiz_id=None,
        )
        db.add(copied_book)
        db.flush()

        if payload.copy_pdf:
            for source_pdf in source.pdfs:
                source_path = Path(source_pdf.file_path)
                if source_pdf.file_path.startswith("demo://"):
                    target_path = source_pdf.file_path
                else:
                    if not source_path.is_file():
                        raise HTTPException(
                            status_code=409,
                            detail=f"源 PDF 文件不存在：{source_pdf.file_name}",
                        )
                    target_path = settings.upload_dir / f"{uuid4()}.pdf"
                    shutil.copy2(source_path, target_path)
                    copied_paths.append(target_path)

                target_pdf = PdfDocument(
                    book_id=copied_book.id,
                    file_name=source_pdf.file_name,
                    file_path=str(target_path),
                    file_size=source_pdf.file_size,
                    page_count=source_pdf.page_count,
                    chunk_count=source_pdf.chunk_count if payload.copy_content else 0,
                    parse_status=source_pdf.parse_status if payload.copy_content else "not_copied",
                    error_message=(
                        source_pdf.error_message
                        if payload.copy_content
                        else "未复制原文片段"
                    ),
                )
                db.add(target_pdf)
                db.flush()
                copied_pdf_count += 1
                if payload.copy_content:
                    for source_chunk in source_pdf.chunks:
                        db.add(
                            ContentChunk(
                                book_id=copied_book.id,
                                pdf_id=target_pdf.id,
                                page_number=source_chunk.page_number,
                                sequence=source_chunk.sequence,
                                content=source_chunk.content,
                                char_count=source_chunk.char_count,
                            )
                        )
                        copied_chunk_count += 1

        add_audit_log(
            db,
            actor_user_id=identity.user.id,
            action="admin.book_copied",
            target_type="book",
            target_id=copied_book.id,
            details={
                "source_book_id": source.id,
                "target_user_id": target_user.id,
                "copied_pdf": payload.copy_pdf,
                "copied_content": payload.copy_content,
                "copied_pdf_count": copied_pdf_count,
                "copied_chunk_count": copied_chunk_count,
            },
        )
        db.commit()
        db.refresh(copied_book)
        return AdminBookCopyResponse(
            book=to_book_detail(db, copied_book),
            source_book_id=source.id,
            target_user_id=target_user.id,
            copied_pdf_count=copied_pdf_count,
            copied_chunk_count=copied_chunk_count,
        )
    except HTTPException:
        db.rollback()
        for path in copied_paths:
            path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        db.rollback()
        for path in copied_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"复制书籍失败：{exc}") from exc
