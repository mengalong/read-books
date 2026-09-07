from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_ready_identity
from app.models import JournalCapture, JournalDay, JournalItem
from app.schemas import (
    JournalCaptureCreate,
    JournalCaptureResponse,
    JournalDayResponse,
    JournalDayUpdate,
    JournalItemResponse,
    JournalItemUpdate,
)
from app.services.auth import AuthIdentity
from app.services.journal_service import (
    CAPTURE_TYPES,
    ITEM_STATUSES,
    capture_to_dict,
    get_or_create_day,
    item_to_dict,
    local_date_for_now,
    normalize_capture_type,
    organize_day,
    upsert_journal_item,
)

router = APIRouter(prefix="/journal", tags=["journal"])
settings = get_settings()


def get_day_or_404(db: Session, identity: AuthIdentity, local_date: date) -> JournalDay:
    day = db.scalar(
        select(JournalDay).where(
            JournalDay.workspace_id == identity.workspace.id,
            JournalDay.local_date == local_date,
        )
    )
    if day is None:
        raise HTTPException(status_code=404, detail="这一天还没有记录")
    return day


def capture_response(capture: JournalCapture) -> JournalCaptureResponse:
    return JournalCaptureResponse(**capture_to_dict(capture))


def item_response(item: JournalItem) -> JournalItemResponse:
    return JournalItemResponse(**item_to_dict(item))


def day_response(db: Session, identity: AuthIdentity, day: JournalDay) -> JournalDayResponse:
    captures = db.scalars(
        select(JournalCapture)
        .where(
            JournalCapture.workspace_id == identity.workspace.id,
            JournalCapture.local_date == day.local_date,
        )
        .order_by(JournalCapture.captured_at.asc())
    ).all()
    items = db.scalars(
        select(JournalItem)
        .where(JournalItem.workspace_id == identity.workspace.id)
        .order_by(JournalItem.updated_at.desc())
    ).all()
    capture_ids = {capture.id for capture in captures}
    day_items = [
        item
        for item in items
        if capture_ids.intersection(set(item.source_capture_ids or []))
    ]
    return JournalDayResponse(
        id=day.id,
        local_date=day.local_date,
        organization_status=day.organization_status,
        journal_text=day.journal_text,
        summary=dict(day.summary or {}),
        organization_task_id=day.organization_task_id,
        organization_error=day.organization_error,
        organized_at=day.organized_at,
        confirmed_at=day.confirmed_at,
        created_at=day.created_at,
        updated_at=day.updated_at,
        captures=[capture_response(capture) for capture in captures],
        items=[item_response(item) for item in day_items],
    )


@router.get("/days/{local_date}", response_model=JournalDayResponse)
def get_journal_day(
    local_date: date,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> JournalDayResponse:
    day = get_or_create_day(
        db,
        workspace_id=identity.workspace.id,
        user_id=identity.user.id,
        local_date=local_date,
    )
    db.commit()
    db.refresh(day)
    return day_response(db, identity, day)


@router.post("/captures", response_model=JournalCaptureResponse, status_code=status.HTTP_201_CREATED)
def create_capture(
    payload: JournalCaptureCreate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> JournalCaptureResponse:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="快速记录不能为空")
    captured_at = payload.captured_at or datetime.now(timezone.utc)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    local_date = payload.local_date or local_date_for_now(captured_at)
    capture_type = normalize_capture_type(payload.capture_type)
    capture = JournalCapture(
        workspace_id=identity.workspace.id,
        created_by_user_id=identity.user.id,
        content=content,
        capture_type=capture_type,
        local_date=local_date,
        captured_at=captured_at,
        tags=[str(tag).strip()[:40] for tag in payload.tags if str(tag).strip()][:20],
    )
    db.add(capture)
    db.flush()
    if capture_type in ITEM_STATUSES:
        upsert_journal_item(
            db,
            workspace_id=identity.workspace.id,
            user_id=identity.user.id,
            item_type=capture_type,
            title=content,
            source_capture_ids=[capture.id],
            confidence=1.0,
            explicit=True,
        )
    get_or_create_day(
        db,
        workspace_id=identity.workspace.id,
        user_id=identity.user.id,
        local_date=local_date,
    )
    db.commit()
    db.refresh(capture)
    return capture_response(capture)


@router.delete("/captures/{capture_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_capture(
    capture_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> None:
    capture = db.scalar(
        select(JournalCapture).where(
            JournalCapture.id == capture_id,
            JournalCapture.workspace_id == identity.workspace.id,
        )
    )
    if capture is None:
        raise HTTPException(status_code=404, detail="未找到这条快速记录")
    db.delete(capture)
    db.commit()


@router.post("/days/{local_date}/organize", response_model=JournalDayResponse, status_code=status.HTTP_202_ACCEPTED)
def organize_journal_day(
    local_date: date,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> JournalDayResponse:
    day = get_or_create_day(
        db,
        workspace_id=identity.workspace.id,
        user_id=identity.user.id,
        local_date=local_date,
    )
    if day.organization_status not in {"pending", "processing"}:
        day.organization_status = "pending"
        day.organization_error = None
        day.organization_task_id = str(uuid4())
        db.commit()
        threading.Thread(target=organize_day, args=(day.id,), daemon=True).start()
    return day_response(db, identity, day)


@router.patch("/days/{local_date}", response_model=JournalDayResponse)
def update_journal_day(
    local_date: date,
    payload: JournalDayUpdate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> JournalDayResponse:
    day = get_day_or_404(db, identity, local_date)
    if payload.journal_text is not None:
        day.journal_text = payload.journal_text.strip()
    if payload.confirm is True:
        day.confirmed_at = datetime.now(timezone.utc)
    elif payload.confirm is False:
        day.confirmed_at = None
    db.commit()
    db.refresh(day)
    return day_response(db, identity, day)


@router.get("/items", response_model=list[JournalItemResponse])
def list_journal_items(
    item_type: str | None = Query(default=None),
    item_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[JournalItemResponse]:
    statement = select(JournalItem).where(JournalItem.workspace_id == identity.workspace.id)
    if item_type:
        if item_type not in ITEM_STATUSES:
            raise HTTPException(status_code=422, detail="不支持的日常项目类型")
        statement = statement.where(JournalItem.item_type == item_type)
    if item_status:
        statement = statement.where(JournalItem.status == item_status)
    rows = db.scalars(statement.order_by(JournalItem.updated_at.desc()).limit(200)).all()
    return [item_response(row) for row in rows]


@router.patch("/items/{item_id}", response_model=JournalItemResponse)
def update_journal_item(
    item_id: str,
    payload: JournalItemUpdate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> JournalItemResponse:
    item = db.scalar(
        select(JournalItem).where(
            JournalItem.id == item_id,
            JournalItem.workspace_id == identity.workspace.id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="未找到这个日常项目")
    if payload.status is not None and payload.status not in ITEM_STATUSES[item.item_type]:
        raise HTTPException(status_code=422, detail="不支持这个项目状态")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "title" and isinstance(value, str):
            value = value.strip()
        if key == "description" and isinstance(value, str):
            value = value.strip()
        setattr(item, key, value)
    if payload.status in {"open", "inbox", "added"}:
        item.metadata_json = {**(item.metadata_json or {}), "needs_confirmation": False}
    db.commit()
    db.refresh(item)
    return item_response(item)
