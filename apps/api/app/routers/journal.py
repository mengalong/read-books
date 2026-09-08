from __future__ import annotations

import calendar
import threading
from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_ready_identity
from app.models import JournalCapture, JournalDay, JournalDayVersion, JournalItem
from app.schemas import (
    JournalCaptureCreate,
    JournalCaptureUpdate,
    JournalCaptureResponse,
    JournalDayResponse,
    JournalDaySummaryResponse,
    JournalDayUpdate,
    JournalDayVersionResponse,
    JournalOrganizeRequest,
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
    sync_legacy_status,
    save_day_version,
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
        and item.review_status != "deleted"
    ]
    return JournalDayResponse(
        id=day.id,
        local_date=day.local_date,
        writing_style=day.writing_style,
        model_consent=day.model_consent,
        mood_score=day.mood_score,
        energy_score=day.energy_score,
        meaning_score=day.meaning_score,
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


def mark_day_stale(db: Session, workspace_id: str, local_date: date) -> None:
    day = db.scalar(
        select(JournalDay).where(
            JournalDay.workspace_id == workspace_id,
            JournalDay.local_date == local_date,
        )
    )
    if day is not None and day.organization_status == "completed":
        day.organization_status = "not_started"
        day.organized_at = None
        day.confirmed_at = None


def mark_item_days_stale(db: Session, workspace_id: str, item: JournalItem) -> None:
    source_ids = set(item.source_capture_ids or [])
    if not source_ids:
        return
    captures = db.scalars(
        select(JournalCapture).where(JournalCapture.workspace_id == workspace_id)
    ).all()
    for capture in captures:
        if capture.id in source_ids:
            mark_day_stale(db, workspace_id, capture.local_date)


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
        item_metadata = (
            {"mentioned_at": captured_at.isoformat()}
            if capture_type in {"want_read", "want_watch"}
            else None
        )
        upsert_journal_item(
            db,
            workspace_id=identity.workspace.id,
            user_id=identity.user.id,
            item_type=capture_type,
            title=content,
            source_capture_ids=[capture.id],
            confidence=1.0,
            explicit=True,
            metadata=item_metadata,
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


@router.patch("/captures/{capture_id}", response_model=JournalCaptureResponse)
def update_capture(
    capture_id: str,
    payload: JournalCaptureUpdate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> JournalCaptureResponse:
    capture = db.scalar(
        select(JournalCapture).where(
            JournalCapture.id == capture_id,
            JournalCapture.workspace_id == identity.workspace.id,
        )
    )
    if capture is None:
        raise HTTPException(status_code=404, detail="未找到这条快速记录")
    previous_date = capture.local_date
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="快速记录不能为空")
    capture.content = content
    capture.capture_type = normalize_capture_type(payload.capture_type)
    if payload.local_date is not None:
        capture.local_date = payload.local_date
    if payload.captured_at is not None:
        captured_at = payload.captured_at
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        capture.captured_at = captured_at
        if payload.local_date is None:
            capture.local_date = local_date_for_now(captured_at)
    capture.tags = [str(tag).strip()[:40] for tag in payload.tags if str(tag).strip()][:20]

    related_items = db.scalars(
        select(JournalItem).where(JournalItem.workspace_id == identity.workspace.id)
    ).all()
    related = [
        item
        for item in related_items
        if capture.id in (item.source_capture_ids or [])
    ]
    explicit_related = [
        item
        for item in related
        if (item.metadata_json or {}).get("source") == "explicit"
    ]
    if capture.capture_type in ITEM_STATUSES:
        explicit_item = next(
            (item for item in explicit_related if item.item_type == capture.capture_type),
            None,
        )
        if explicit_item is None:
            explicit_item = next(
                (
                    item
                    for item in explicit_related
                    if item.status not in {"done", "completed", "dismissed", "cancelled"}
                ),
                None,
            )
        if explicit_item is None:
            explicit_item = upsert_journal_item(
                db,
                workspace_id=identity.workspace.id,
                user_id=identity.user.id,
                item_type=capture.capture_type,
                title=content,
                source_capture_ids=[capture.id],
                confidence=1.0,
                explicit=True,
            )
        if explicit_item is not None:
            explicit_item.item_type = capture.capture_type
            explicit_item.title = content
            explicit_item.source_capture_ids = list(
                dict.fromkeys((explicit_item.source_capture_ids or []) + [capture.id])
            )
            explicit_item.metadata_json = {
                **(explicit_item.metadata_json or {}),
                "source": "explicit",
                "needs_confirmation": False,
            }
            if explicit_item.status == "needs_review":
                explicit_item.status = "open" if capture.capture_type == "todo" else "inbox"
    else:
        for item in explicit_related:
            if item.status not in {"done", "completed", "dismissed", "cancelled"}:
                item.status = "dismissed"
                item.metadata_json = {
                    **(item.metadata_json or {}),
                    "needs_confirmation": False,
                    "dismiss_reason": "source_capture_reclassified",
                }
    mark_day_stale(db, identity.workspace.id, previous_date)
    mark_day_stale(db, identity.workspace.id, capture.local_date)
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
    previous_date = capture.local_date
    db.delete(capture)
    mark_day_stale(db, identity.workspace.id, previous_date)
    db.commit()


@router.post("/days/{local_date}/organize", response_model=JournalDayResponse, status_code=status.HTTP_202_ACCEPTED)
def organize_journal_day(
    local_date: date,
    payload: JournalOrganizeRequest | None = None,
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
        if payload and payload.writing_style:
            day.writing_style = payload.writing_style
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
    if payload.writing_style is not None:
        day.writing_style = payload.writing_style
    if payload.model_consent is not None:
        day.model_consent = payload.model_consent
    for field in ("mood_score", "energy_score", "meaning_score"):
        value = getattr(payload, field)
        if value is not None:
            setattr(day, field, value)
    if payload.journal_text is not None:
        save_day_version(db, day, source="manual")
    if payload.confirm is True:
        day.confirmed_at = datetime.now(timezone.utc)
    elif payload.confirm is False:
        day.confirmed_at = None
    db.commit()
    db.refresh(day)
    return day_response(db, identity, day)


@router.get("/days/{local_date}/versions", response_model=list[JournalDayVersionResponse])
def list_journal_day_versions(
    local_date: date,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[JournalDayVersionResponse]:
    day = get_day_or_404(db, identity, local_date)
    versions = db.scalars(
        select(JournalDayVersion)
        .where(JournalDayVersion.journal_day_id == day.id)
        .order_by(JournalDayVersion.version_number.desc())
    ).all()
    return [JournalDayVersionResponse.model_validate(version) for version in versions]


@router.post("/days/{local_date}/versions/{version_number}/restore", response_model=JournalDayResponse)
def restore_journal_day_version(
    local_date: date,
    version_number: int,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> JournalDayResponse:
    day = get_day_or_404(db, identity, local_date)
    version = db.scalar(
        select(JournalDayVersion).where(
            JournalDayVersion.journal_day_id == day.id,
            JournalDayVersion.version_number == version_number,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="未找到这个日记版本")
    save_day_version(db, day, source="restore")
    day.journal_text = version.journal_text
    day.writing_style = version.writing_style
    day.confirmed_at = None
    db.commit()
    db.refresh(day)
    return day_response(db, identity, day)


@router.get("/summaries", response_model=list[JournalDaySummaryResponse])
def list_journal_summaries(
    period: str = Query(default="month"),
    anchor_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> list[JournalDaySummaryResponse]:
    if period not in {"week", "month"}:
        raise HTTPException(status_code=422, detail="周期只能是 week 或 month")
    anchor = anchor_date or local_date_for_now()
    if period == "week":
        start = anchor.fromordinal(anchor.toordinal() - anchor.weekday())
        end = start.fromordinal(start.toordinal() + 6)
    else:
        start = anchor.replace(day=1)
        end = anchor.replace(day=calendar.monthrange(anchor.year, anchor.month)[1])
    item_rows = db.scalars(
        select(JournalItem).where(JournalItem.workspace_id == identity.workspace.id)
    ).all()
    days = db.scalars(
        select(JournalDay)
        .where(
            JournalDay.workspace_id == identity.workspace.id,
            JournalDay.local_date >= start,
            JournalDay.local_date <= end,
        )
        .order_by(JournalDay.local_date.desc())
    ).all()
    summaries: list[JournalDaySummaryResponse] = []
    for day in days:
        captures = db.scalars(
            select(JournalCapture.id).where(
                JournalCapture.workspace_id == identity.workspace.id,
                JournalCapture.local_date == day.local_date,
            )
        ).all()
        capture_ids = set(captures)
        relevant = [
            item for item in item_rows
            if capture_ids.intersection(set(item.source_capture_ids or []))
            and item.review_status != "deleted"
        ]
        summaries.append(
            JournalDaySummaryResponse(
                local_date=day.local_date,
                capture_count=len(captures),
                item_count=len(relevant),
                completed_todo_count=sum(
                    1 for item in relevant if item.item_type == "todo" and item.review_status == "completed"
                ),
                mood_score=day.mood_score,
                energy_score=day.energy_score,
                meaning_score=day.meaning_score,
                journal_preview=(day.journal_text or "").replace("\n", " ")[:180],
            )
        )
    return summaries


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
        statement = statement.where(JournalItem.review_status == item_status)
    else:
        statement = statement.where(
            (JournalItem.review_status != "deleted") | JournalItem.review_status.is_(None)
        )
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
    next_type = payload.item_type or item.item_type
    if next_type not in ITEM_STATUSES:
        raise HTTPException(status_code=422, detail="不支持这个项目类型")
    if payload.status is not None and payload.status not in ITEM_STATUSES[next_type]:
        raise HTTPException(status_code=422, detail="不支持这个项目状态")
    previous_type = item.item_type
    type_changed = payload.item_type is not None and payload.item_type != previous_type
    if type_changed:
        item.item_type = payload.item_type
    if payload.review_status is not None:
        sync_legacy_status(item, payload.review_status)
    elif payload.status is not None:
        legacy_to_review = {
            "needs_review": "pending",
            "open": "confirmed",
            "inbox": "confirmed",
            "added": "confirmed",
            "done": "completed",
            "completed": "completed",
            "dismissed": "cancelled",
            "cancelled": "cancelled",
        }
        mapped = legacy_to_review.get(payload.status)
        if mapped:
            sync_legacy_status(item, mapped)
            # Preserve the legacy value for older clients while review_status
            # remains the canonical state used by the current UI.
            item.status = payload.status
    elif type_changed:
        sync_legacy_status(item, "confirmed")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key in {"item_type", "review_status", "metadata", "status"}:
            continue
        if key == "title" and isinstance(value, str):
            value = value.strip()
        if key == "description" and isinstance(value, str):
            value = value.strip()
        setattr(item, key, value)
    if type_changed:
        item.metadata_json = {
            **(item.metadata_json or {}),
            "needs_confirmation": False,
            "manual_type_override": True,
        }
    if payload.metadata is not None:
        item.metadata_json = {**(item.metadata_json or {}), **payload.metadata}
    if payload.title is not None or payload.description is not None or payload.metadata is not None:
        item.metadata_json = {**(item.metadata_json or {}), "manual_content_override": True}
    if item.item_type in {"want_read", "want_watch"} and (
        type_changed or payload.title is not None or payload.description is not None
    ):
        item.metadata_json = {
            **(item.metadata_json or {}),
            "media_title": item.title,
            "reason": item.description or item.title,
            "media_kind": "book" if item.item_type == "want_read" else "movie_or_tv",
        }
    if payload.status in {"open", "inbox", "added"}:
        item.metadata_json = {**(item.metadata_json or {}), "needs_confirmation": False}
    mark_item_days_stale(db, identity.workspace.id, item)
    db.commit()
    db.refresh(item)
    return item_response(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_journal_item(
    item_id: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_ready_identity),
) -> None:
    item = db.scalar(
        select(JournalItem).where(
            JournalItem.id == item_id,
            JournalItem.workspace_id == identity.workspace.id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="未找到这个日常项目")
    mark_item_days_stale(db, identity.workspace.id, item)
    sync_legacy_status(item, "deleted")
    item.metadata_json = {**(item.metadata_json or {}), "deleted_at": datetime.now(timezone.utc).isoformat()}
    db.commit()
