from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_ready_identity
from app.models import QuoteEntry, QuizGenerationTask, ResourceMaterial
from app.routers.books import ensure_book_is_active, get_book_or_404
from app.schemas import (
    MaterialResponse,
    QuoteEntryBulkRequest,
    QuoteEntryListResponse,
    QuoteEntryResponse,
    QuoteEntryUpdateRequest,
)
from app.services.auth import AuthIdentity
from app.services.material_parser import parse_material_document


router = APIRouter(tags=["materials"])
settings = get_settings()
ALLOWED_FORMATS = {"pdf", "txt", "srt", "vtt", "ass", "csv", "xlsx"}
FORMAT_TYPES = {
    "book_text": {"pdf", "txt"},
    "script": {"pdf", "txt"},
    "subtitle": {"srt", "vtt", "ass"},
    "quote_sheet": {"csv", "xlsx"},
}


def _quote_response(quote: QuoteEntry) -> QuoteEntryResponse:
    values = {
        field: getattr(quote, field)
        for field in QuoteEntryResponse.model_fields
        if field != "material_file_name"
    }
    return QuoteEntryResponse(
        **values,
        material_file_name=quote.material.file_name,
    )


def _material_or_404(
    db: Session,
    book_id: str,
    material_id: str,
    identity: AuthIdentity,
) -> ResourceMaterial:
    get_book_or_404(db, book_id, identity)
    material = db.scalar(
        select(ResourceMaterial).where(
            ResourceMaterial.id == material_id,
            ResourceMaterial.book_id == book_id,
        )
    )
    if material is None:
        raise HTTPException(status_code=404, detail="未找到这份可信资料")
    return material


def _refresh_material_status(db: Session, material_id: str) -> None:
    material = db.get(ResourceMaterial, material_id)
    if material is None or material.parse_status == "failed":
        return
    pending_count = db.scalar(
        select(func.count(QuoteEntry.id)).where(
            QuoteEntry.material_id == material_id,
            QuoteEntry.review_status == "pending",
        )
    ) or 0
    material.parse_status = "needs_review" if pending_count else "completed"


@router.post(
    "/books/{book_id}/materials",
    response_model=MaterialResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_material(
    book_id: str,
    file: UploadFile = File(...),
    material_type: str = Form(...),
    season_number: int | None = Form(default=None),
    episode_label: str | None = Form(default=None),
    version_label: str | None = Form(default=None),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> MaterialResponse:
    book = get_book_or_404(db, book_id, identity, for_write=True)
    ensure_book_is_active(book)
    if material_type not in FORMAT_TYPES:
        raise HTTPException(status_code=400, detail="不支持的可信资料类型")
    if season_number is not None and not 1 <= season_number <= 999:
        raise HTTPException(status_code=400, detail="季数必须在 1 到 999 之间")
    original_name = Path(file.filename or "material").name
    file_format = Path(original_name).suffix.lower().lstrip(".")
    if file_format not in ALLOWED_FORMATS or file_format not in FORMAT_TYPES[material_type]:
        expected = "、".join(sorted(FORMAT_TYPES[material_type]))
        raise HTTPException(status_code=400, detail=f"这类资料只支持 {expected} 格式")

    settings.ensure_directories()
    stored_path = settings.upload_dir / f"{uuid4()}.{file_format}"
    digest = hashlib.sha256()
    file_size = 0
    first_chunk = True
    try:
        with stored_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                if first_chunk and file_format == "pdf" and not chunk.startswith(b"%PDF"):
                    raise HTTPException(status_code=400, detail="文件内容不是有效的 PDF")
                if first_chunk and file_format == "xlsx" and not chunk.startswith(b"PK"):
                    raise HTTPException(status_code=400, detail="文件内容不是有效的 XLSX")
                first_chunk = False
                destination.write(chunk)
                digest.update(chunk)
                file_size += len(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    if file_size == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="可信资料文件为空")

    material = ResourceMaterial(
        book_id=book_id,
        created_by_user_id=identity.user.id,
        material_type=material_type,
        file_format=file_format,
        file_name=original_name,
        file_path=str(stored_path.resolve()),
        file_size=file_size,
        file_hash=digest.hexdigest(),
        season_number=season_number,
        episode_label=episode_label.strip()[:80] if episode_label and episode_label.strip() else None,
        version_label=version_label.strip()[:120] if version_label and version_label.strip() else None,
        parse_status="pending",
    )
    db.add(material)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="这份资料已经上传过了") from exc
    db.refresh(material)
    threading.Thread(target=parse_material_document, args=(material.id,), daemon=True).start()
    return MaterialResponse.model_validate(material)


@router.get("/books/{book_id}/materials", response_model=list[MaterialResponse])
def list_materials(
    book_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[ResourceMaterial]:
    get_book_or_404(db, book_id, identity)
    return list(
        db.scalars(
            select(ResourceMaterial)
            .where(ResourceMaterial.book_id == book_id)
            .order_by(ResourceMaterial.created_at.desc())
        ).all()
    )


@router.get("/books/{book_id}/materials/{material_id}", response_model=MaterialResponse)
def get_material(
    book_id: str,
    material_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ResourceMaterial:
    return _material_or_404(db, book_id, material_id, identity)


@router.post(
    "/books/{book_id}/materials/{material_id}/reparse",
    response_model=MaterialResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reparse_material(
    book_id: str,
    material_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> ResourceMaterial:
    book = get_book_or_404(db, book_id, identity, for_write=True)
    ensure_book_is_active(book)
    material = _material_or_404(db, book_id, material_id, identity)
    if material.parse_status in {"pending", "processing"}:
        raise HTTPException(status_code=409, detail="这份资料正在解析")
    material.parse_status = "pending"
    material.error_message = None
    db.commit()
    db.refresh(material)
    threading.Thread(target=parse_material_document, args=(material.id,), daemon=True).start()
    return material


@router.delete(
    "/books/{book_id}/materials/{material_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_material(
    book_id: str,
    material_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> None:
    get_book_or_404(db, book_id, identity, for_write=True)
    material = _material_or_404(db, book_id, material_id, identity)
    if material.parse_status == "processing":
        raise HTTPException(status_code=409, detail="资料正在解析，完成后才能删除")
    active_tasks = db.scalars(
        select(QuizGenerationTask).where(
            QuizGenerationTask.book_id == book_id,
            QuizGenerationTask.status.in_(["pending", "processing"]),
        )
    ).all()
    if any(
        material_id in (task.theme_config or {}).get("material_ids", [])
        for task in active_tasks
    ):
        raise HTTPException(status_code=409, detail="资料正在用于生成专题试卷，完成后才能删除")
    file_path = material.file_path
    db.delete(material)
    db.commit()
    Path(file_path).unlink(missing_ok=True)


@router.get("/books/{book_id}/quotes", response_model=QuoteEntryListResponse)
def list_quotes(
    book_id: str,
    material_id: str | None = None,
    speaker: str | None = None,
    review_status: str | None = Query(default=None),
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuoteEntryListResponse:
    get_book_or_404(db, book_id, identity)
    filters = [QuoteEntry.book_id == book_id]
    if material_id:
        filters.append(QuoteEntry.material_id == material_id)
    if speaker:
        filters.append(QuoteEntry.speaker == speaker)
    if review_status:
        if review_status not in {"pending", "confirmed", "rejected"}:
            raise HTTPException(status_code=400, detail="不支持的台词校对状态")
        filters.append(QuoteEntry.review_status == review_status)
    if search and search.strip():
        filters.append(QuoteEntry.quote_text.contains(search.strip()))

    total = db.scalar(select(func.count(QuoteEntry.id)).where(*filters)) or 0
    quotes = list(
        db.scalars(
            select(QuoteEntry)
            .where(*filters)
            .order_by(QuoteEntry.material_id, QuoteEntry.episode_number, QuoteEntry.start_ms, QuoteEntry.created_at)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    speakers = list(
        db.scalars(
            select(QuoteEntry.speaker)
            .where(
                QuoteEntry.book_id == book_id,
                QuoteEntry.speaker.is_not(None),
                QuoteEntry.review_status == "confirmed",
            )
            .distinct()
            .order_by(QuoteEntry.speaker)
        ).all()
    )
    pending_count, confirmed_count = db.execute(
        select(
            func.count(QuoteEntry.id).filter(QuoteEntry.review_status == "pending"),
            func.count(QuoteEntry.id).filter(QuoteEntry.review_status == "confirmed"),
        ).where(QuoteEntry.book_id == book_id)
    ).one()
    return QuoteEntryListResponse(
        items=[_quote_response(quote) for quote in quotes],
        total=total,
        speakers=speakers,
        pending_count=pending_count or 0,
        confirmed_count=confirmed_count or 0,
    )


@router.patch("/books/{book_id}/quotes/{quote_id}", response_model=QuoteEntryResponse)
def update_quote(
    book_id: str,
    quote_id: str,
    payload: QuoteEntryUpdateRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> QuoteEntryResponse:
    get_book_or_404(db, book_id, identity, for_write=True)
    quote = db.scalar(
        select(QuoteEntry).where(QuoteEntry.id == quote_id, QuoteEntry.book_id == book_id)
    )
    if quote is None:
        raise HTTPException(status_code=404, detail="未找到这条台词")
    if "speaker" in payload.model_fields_set:
        quote.speaker = payload.speaker.strip() if payload.speaker and payload.speaker.strip() else None
        quote.speaker_origin = "confirmed" if quote.speaker else "unknown"
    if "context" in payload.model_fields_set:
        quote.context = payload.context.strip() if payload.context and payload.context.strip() else None
    if payload.review_status is not None:
        quote.review_status = payload.review_status
        if payload.review_status == "rejected":
            quote.enabled_for_generation = False
        elif payload.review_status == "confirmed" and payload.enabled_for_generation is None:
            quote.enabled_for_generation = True
    if payload.enabled_for_generation is not None:
        if payload.enabled_for_generation and quote.review_status != "confirmed":
            raise HTTPException(status_code=409, detail="只有已确认台词才能用于出题")
        quote.enabled_for_generation = payload.enabled_for_generation
    db.flush()
    _refresh_material_status(db, quote.material_id)
    db.commit()
    db.refresh(quote)
    return _quote_response(quote)


def _bulk_review(
    book_id: str,
    payload: QuoteEntryBulkRequest,
    review_status: str,
    db: Session,
    identity: AuthIdentity,
) -> list[QuoteEntryResponse]:
    get_book_or_404(db, book_id, identity, for_write=True)
    quotes = list(
        db.scalars(
            select(QuoteEntry).where(
                QuoteEntry.book_id == book_id,
                QuoteEntry.id.in_(set(payload.quote_ids)),
            )
        ).all()
    )
    if len(quotes) != len(set(payload.quote_ids)):
        raise HTTPException(status_code=404, detail="部分台词不存在或不属于当前资源")
    material_ids = {quote.material_id for quote in quotes}
    for quote in quotes:
        quote.review_status = review_status
        quote.enabled_for_generation = review_status == "confirmed"
    db.flush()
    for material_id in material_ids:
        _refresh_material_status(db, material_id)
    db.commit()
    for quote in quotes:
        db.refresh(quote)
    return [_quote_response(quote) for quote in quotes]


@router.post(
    "/books/{book_id}/quotes/bulk-confirm",
    response_model=list[QuoteEntryResponse],
)
def bulk_confirm_quotes(
    book_id: str,
    payload: QuoteEntryBulkRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[QuoteEntryResponse]:
    return _bulk_review(book_id, payload, "confirmed", db, identity)


@router.post(
    "/books/{book_id}/quotes/bulk-reject",
    response_model=list[QuoteEntryResponse],
)
def bulk_reject_quotes(
    book_id: str,
    payload: QuoteEntryBulkRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[QuoteEntryResponse]:
    return _bulk_review(book_id, payload, "rejected", db, identity)


@router.get("/material-templates/quote-sheet.csv")
def download_quote_sheet_template(
    _: AuthIdentity = Depends(require_ready_identity),
) -> Response:
    content = "台词,角色,季,集,开始时间,结束时间,场景,上下文,版本说明\n"
    return Response(
        content="\ufeff" + content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="quote-sheet-template.csv"'},
    )
