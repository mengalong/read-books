from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import JournalCapture, JournalDay, JournalItem
from app.services.journal_provider import ITEM_TYPES, JournalOrganization, get_journal_provider
from app.services.model_config import get_effective_model_configuration
from app.services.model_usage import new_usage_context
from app.services.prompt_config import get_prompt_template

JOURNAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
CAPTURE_TYPES = {"note", *ITEM_TYPES}
ITEM_STATUSES = {
    "todo": {"open", "done", "cancelled", "needs_review"},
    "idea": {"inbox", "archived", "dismissed", "needs_review"},
    "want_read": {"inbox", "added", "completed", "dismissed", "needs_review"},
    "want_watch": {"inbox", "added", "completed", "dismissed", "needs_review"},
}


def local_date_for_now(value: datetime | None = None) -> date:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(JOURNAL_TIMEZONE).date()


def normalize_capture_type(value: str | None) -> str:
    return value if value in CAPTURE_TYPES else "note"


def _clean_title(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:240]


def _title_key(value: str) -> str:
    return re.sub(r"[\s，。！？、：；,.!?;:'\"“”‘’（）()\[\]{}]+", "", value).lower()


def _safe_source_ids(value: Any, capture_ids: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item) for item in value if str(item) in capture_ids))


def _item_status(item_type: str, *, explicit: bool) -> str:
    if not explicit:
        return "needs_review"
    return "open" if item_type == "todo" else "inbox"


def upsert_journal_item(
    db: Session,
    *,
    workspace_id: str,
    user_id: str | None,
    item_type: str,
    title: str,
    description: str = "",
    source_capture_ids: list[str] | None = None,
    confidence: float | None = None,
    due_date: date | None = None,
    explicit: bool = False,
) -> JournalItem | None:
    if item_type not in ITEM_TYPES:
        return None
    clean_title = _clean_title(title)
    if not clean_title:
        return None
    source_ids = list(dict.fromkeys(source_capture_ids or []))
    candidates = db.scalars(
        select(JournalItem)
        .where(
            JournalItem.workspace_id == workspace_id,
            JournalItem.item_type == item_type,
            JournalItem.status.not_in({"dismissed", "cancelled", "archived"}),
        )
        .order_by(JournalItem.updated_at.desc())
        .limit(100)
    ).all()
    item = next(
        (
            candidate
            for candidate in candidates
            if _title_key(candidate.title) == _title_key(clean_title)
        ),
        None,
    )
    if item is None:
        item = JournalItem(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            item_type=item_type,
            title=clean_title,
            description=str(description or "").strip()[:2_000],
            status=_item_status(item_type, explicit=explicit),
            source_capture_ids=source_ids,
            confidence=confidence,
            due_date=due_date,
            metadata_json={"source": "explicit" if explicit else "ai", "needs_confirmation": not explicit},
        )
        db.add(item)
        return item

    existing_ids = list(item.source_capture_ids or [])
    item.source_capture_ids = list(dict.fromkeys(existing_ids + source_ids))
    if description and not item.description:
        item.description = str(description).strip()[:2_000]
    if confidence is not None:
        item.confidence = max(item.confidence or 0, min(1.0, float(confidence)))
    if due_date is not None:
        item.due_date = due_date
    if explicit and item.status == "needs_review":
        item.status = _item_status(item_type, explicit=True)
        item.metadata_json = {**(item.metadata_json or {}), "needs_confirmation": False}
    return item


def capture_to_dict(capture: JournalCapture) -> dict[str, Any]:
    return {
        "id": capture.id,
        "content": capture.content,
        "capture_type": capture.capture_type,
        "local_date": capture.local_date,
        "captured_at": capture.captured_at,
        "tags": list(capture.tags or []),
        "created_at": capture.created_at,
    }


def capture_to_model_dict(capture: JournalCapture) -> dict[str, Any]:
    """Use JSON-safe scalar values when sending captures to a model provider."""
    payload = capture_to_dict(capture)
    for key in ("local_date", "captured_at", "created_at"):
        value = payload.get(key)
        if hasattr(value, "isoformat"):
            payload[key] = value.isoformat()
    return payload


def item_to_dict(item: JournalItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "title": item.title,
        "description": item.description,
        "status": item.status,
        "source_capture_ids": list(item.source_capture_ids or []),
        "confidence": item.confidence,
        "due_date": item.due_date,
        "metadata": dict(item.metadata_json or {}),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def get_or_create_day(
    db: Session, *, workspace_id: str, user_id: str | None, local_date: date
) -> JournalDay:
    day = db.scalar(
        select(JournalDay).where(
            JournalDay.workspace_id == workspace_id,
            JournalDay.local_date == local_date,
        )
    )
    if day is None:
        day = JournalDay(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            local_date=local_date,
        )
        db.add(day)
        db.flush()
    return day


def organize_day(day_id: str, *, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    with SessionLocal() as db:
        day = db.get(JournalDay, day_id)
        if day is None:
            return
        if day.organization_status == "processing":
            return
        day.organization_status = "processing"
        db.commit()

    try:
        with SessionLocal() as db:
            day = db.get(JournalDay, day_id)
            if day is None:
                return
            captures = list(
                db.scalars(
                    select(JournalCapture)
                    .where(
                        JournalCapture.workspace_id == day.workspace_id,
                        JournalCapture.local_date == day.local_date,
                    )
                    .order_by(JournalCapture.captured_at.asc())
                ).all()
            )
            capture_payload = [capture_to_model_dict(capture) for capture in captures]
            configuration = get_effective_model_configuration(db, settings)
            prompt_template = get_prompt_template(db, "journal_organization")
            context = new_usage_context(
                "journal_daily_organization",
                f"{day.local_date.isoformat()} 日常整理",
                user_id=day.created_by_user_id,
                workspace_id=day.workspace_id,
                task_id=day.organization_task_id,
            )
            provider = get_journal_provider(
                settings, configuration, context, prompt_template=prompt_template
            )
            organization = provider.organize_day(
                capture_payload, day.local_date, day.writing_style or "natural"
            )
            capture_ids = {capture.id for capture in captures}
            item_ids: list[str] = []
            for raw_item in organization.items:
                item_type = str(raw_item.get("item_type") or "")
                source_ids = _safe_source_ids(raw_item.get("source_capture_ids"), capture_ids)
                source_captures = [
                    capture for capture in captures if capture.id in source_ids
                ]
                explicit_captures = [
                    capture
                    for capture in source_captures
                    if capture.capture_type == item_type
                ]
                explicit = bool(explicit_captures)
                if not source_ids:
                    continue
                title = (
                    explicit_captures[0].content
                    if explicit_captures
                    else str(raw_item.get("title") or "")
                )
                confidence = raw_item.get("confidence")
                if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
                    confidence = 1.0 if explicit else 0.65
                due_date = None
                raw_due_date = raw_item.get("due_date")
                if isinstance(raw_due_date, str):
                    try:
                        due_date = date.fromisoformat(raw_due_date)
                    except ValueError:
                        due_date = None
                item = upsert_journal_item(
                    db,
                    workspace_id=day.workspace_id,
                    user_id=day.created_by_user_id,
                    item_type=item_type,
                    title=title,
                    description=str(raw_item.get("description") or ""),
                    source_capture_ids=source_ids,
                    confidence=float(confidence),
                    due_date=due_date,
                    explicit=explicit,
                )
                if item is not None:
                    db.flush()
                    item_ids.append(item.id)
            day.journal_text = organization.journal_text
            day.summary = {
                "highlights": organization.highlights,
                "item_ids": list(dict.fromkeys(item_ids)),
                "capture_count": len(captures),
            }
            day.organization_status = "completed"
            day.organization_error = None
            day.organized_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        with SessionLocal() as db:
            day = db.get(JournalDay, day_id)
            if day is not None:
                day.organization_status = "failed"
                day.organization_error = str(exc)[:1_000]
                db.commit()


def recover_journal_organization_tasks() -> list[str]:
    with SessionLocal() as db:
        days = db.scalars(
            select(JournalDay.id).where(JournalDay.organization_status == "processing")
        ).all()
        if days:
            db.query(JournalDay).filter(JournalDay.organization_status == "processing").update(
                {JournalDay.organization_status: "pending"}, synchronize_session=False
            )
            db.commit()
        return list(days)


def source_capture_ids_for_item(item: JournalItem) -> list[str]:
    return list(item.source_capture_ids or [])
