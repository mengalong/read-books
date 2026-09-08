from __future__ import annotations

import re
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import JournalCapture, JournalDay, JournalDayVersion, JournalItem
from app.services.journal_provider import ITEM_TYPES, JournalOrganization, get_journal_provider
from app.services.model_config import get_effective_model_configuration
from app.services.model_usage import new_usage_context
from app.services.prompt_config import get_prompt_template

JOURNAL_TIMEZONE = ZoneInfo("Asia/Shanghai")
CAPTURE_TYPES = {"note", *ITEM_TYPES}
ITEM_STATUSES = {
    "todo": {"open", "done", "cancelled", "needs_review", "dismissed", "deleted"},
    "idea": {"inbox", "archived", "dismissed", "needs_review", "deleted"},
    "want_read": {"inbox", "added", "completed", "dismissed", "needs_review", "deleted"},
    "want_watch": {"inbox", "added", "completed", "dismissed", "needs_review", "deleted"},
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


def _canonical_key(item_type: str, title: str, metadata: dict[str, Any]) -> str:
    supplied = _title_key(str(metadata.get("canonical_key") or ""))
    if supplied:
        return f"{item_type}:{supplied}"[:240]
    if item_type in {"want_read", "want_watch"}:
        media_title = _title_key(str(metadata.get("media_title") or title))
        return f"{item_type}:{media_title}"[:240]
    normalized = _title_key(title)
    for phrase in (
        "我想要",
        "我想",
        "想要",
        "需要",
        "记得",
        "计划",
        "给日记",
        "为日记",
        "添加",
        "增加",
        "实现",
        "做一个",
        "做个",
        "把",
    ):
        normalized = normalized.replace(phrase, "")
    return f"{item_type}:{normalized or _title_key(title)}"[:240]


def _similar_canonical_key(first: str | None, second: str) -> bool:
    if not first:
        return False
    if first == second:
        return True
    first_value = first.split(":", 1)[-1]
    second_value = second.split(":", 1)[-1]
    if min(len(first_value), len(second_value)) < 5:
        return False
    return SequenceMatcher(None, first_value, second_value).ratio() >= 0.78


def _safe_source_ids(value: Any, capture_ids: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item) for item in value if str(item) in capture_ids))


def _item_status(item_type: str, *, explicit: bool) -> str:
    if not explicit:
        return "needs_review"
    return "open" if item_type == "todo" else "inbox"


def _review_status_from_legacy(status: str | None, *, explicit: bool) -> str:
    if status in {"deleted"}:
        return "deleted"
    if status in {"dismissed", "cancelled", "archived"}:
        return "cancelled"
    if status in {"done", "completed"}:
        return "completed"
    if status in {"open", "inbox", "added"}:
        return "confirmed"
    return "confirmed" if explicit else "pending"


def review_status_for_item(item: JournalItem) -> str:
    return item.review_status or _review_status_from_legacy(item.status, explicit=False)


def sync_legacy_status(item: JournalItem, review_status: str) -> None:
    """Keep legacy status readable for old clients while the UI uses review_status."""
    item.review_status = review_status
    if review_status == "pending":
        item.status = "needs_review"
    elif review_status == "confirmed":
        item.status = "open" if item.item_type == "todo" else "inbox"
    elif review_status == "completed":
        item.status = "done" if item.item_type == "todo" else "completed"
    elif review_status in {"cancelled", "deleted"}:
        item.status = "dismissed"


def _structured_metadata(
    item_type: str,
    raw_metadata: Any,
    *,
    title: str,
    description: str,
    source_captures: list[JournalCapture],
) -> dict[str, Any]:
    metadata = {
        key: value
        for key, value in (raw_metadata.items() if isinstance(raw_metadata, dict) else [])
        if key in {"media_title", "reason", "mentioned_at", "creator", "media_kind", "canonical_key", "priority"}
        and isinstance(value, (str, int, float, bool))
    }
    if item_type in {"want_read", "want_watch"}:
        metadata.setdefault("media_title", title)
        metadata.setdefault("reason", description or title)
        if source_captures:
            mentioned_at = source_captures[0].captured_at
            metadata.setdefault(
                "mentioned_at",
                mentioned_at.isoformat() if hasattr(mentioned_at, "isoformat") else str(mentioned_at),
            )
        metadata.setdefault("media_kind", "book" if item_type == "want_read" else "movie_or_tv")
    return metadata


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
    metadata: dict[str, Any] | None = None,
) -> JournalItem | None:
    if item_type not in ITEM_TYPES:
        return None
    clean_title = _clean_title(title)
    if not clean_title:
        return None
    source_ids = list(dict.fromkeys(source_capture_ids or []))
    structured_metadata = dict(metadata or {})
    if item_type in {"want_read", "want_watch"}:
        media_match = re.search(r"《([^》]{1,160})》", clean_title)
        structured_metadata.setdefault(
            "media_title", media_match.group(1).strip() if media_match else clean_title
        )
        structured_metadata.setdefault("reason", clean_title)
        structured_metadata.setdefault("media_kind", "book" if item_type == "want_read" else "movie_or_tv")
    dedupe_key = str(structured_metadata.get("media_title") or clean_title)
    canonical_key = _canonical_key(item_type, clean_title, structured_metadata)
    candidates = db.scalars(
        select(JournalItem)
        .where(
            JournalItem.workspace_id == workspace_id,
            JournalItem.item_type == item_type,
        )
        .order_by(JournalItem.updated_at.desc())
        .limit(100)
    ).all()
    item = next(
        (
            candidate
            for candidate in candidates
            if (
                set(candidate.source_capture_ids or []).intersection(source_ids)
                or _similar_canonical_key(candidate.canonical_key, canonical_key)
                or _title_key(candidate.title) == _title_key(clean_title)
                or _title_key(str((candidate.metadata_json or {}).get("media_title") or ""))
                == _title_key(dedupe_key)
            )
        ),
        None,
    )
    if item is None:
        item = JournalItem(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            item_type=item_type,
            canonical_key=canonical_key,
            title=str(structured_metadata.get("media_title") or clean_title)[:240],
            description=str(description or "").strip()[:2_000],
            status=_item_status(item_type, explicit=explicit),
            review_status=_review_status_from_legacy(None, explicit=explicit),
            source_capture_ids=source_ids,
            confidence=confidence,
            due_date=due_date,
            metadata_json={
                **structured_metadata,
                "dedupe_key": _title_key(dedupe_key),
                "source": "explicit" if explicit else "ai",
                "needs_confirmation": not explicit,
            },
        )
        db.add(item)
        return item

    existing_ids = list(item.source_capture_ids or [])
    item.source_capture_ids = list(dict.fromkeys(existing_ids + source_ids))
    item.canonical_key = item.canonical_key or canonical_key
    manual_content = (item.metadata_json or {}).get("manual_content_override") is True
    if description and not item.description and not manual_content:
        item.description = str(description).strip()[:2_000]
    if confidence is not None:
        item.confidence = max(item.confidence or 0, min(1.0, float(confidence)))
    if due_date is not None:
        item.due_date = due_date
    if structured_metadata and not manual_content:
        item.metadata_json = {**(item.metadata_json or {}), **structured_metadata}
    if explicit and item.status == "needs_review":
        sync_legacy_status(item, "confirmed")
        item.metadata_json = {**(item.metadata_json or {}), "needs_confirmation": False}
    if explicit and item.review_status == "pending":
        sync_legacy_status(item, "confirmed")
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
        "canonical_key": item.canonical_key,
        "review_status": review_status_for_item(item),
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


def save_day_version(
    db: Session,
    day: JournalDay,
    *,
    source: str,
    journal_text: str | None = None,
    writing_style: str | None = None,
) -> JournalDayVersion | None:
    text = (journal_text if journal_text is not None else day.journal_text).strip()
    if not text:
        return None
    latest = db.scalar(
        select(JournalDayVersion)
        .where(JournalDayVersion.journal_day_id == day.id)
        .order_by(JournalDayVersion.version_number.desc())
        .limit(1)
    )
    if latest is not None and latest.journal_text == text:
        return latest
    version = JournalDayVersion(
        journal_day_id=day.id,
        version_number=(latest.version_number if latest else 0) + 1,
        source=source,
        journal_text=text,
        writing_style=writing_style or day.writing_style or "natural",
    )
    db.add(version)
    db.flush()
    return version


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
            if configuration.provider_mode != "mock" and not day.model_consent:
                raise RuntimeError("今天未允许将原始记录发送给模型，请先开启模型整理授权")
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
            existing_items = db.scalars(
                select(JournalItem).where(JournalItem.workspace_id == day.workspace_id)
            ).all()
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
                structured_metadata = _structured_metadata(
                    item_type,
                    raw_item.get("metadata"),
                    title=title,
                    description=str(raw_item.get("description") or ""),
                    source_captures=source_captures,
                )
                raw_canonical_key = raw_item.get("canonical_key")
                if isinstance(raw_canonical_key, str) and raw_canonical_key.strip():
                    structured_metadata["canonical_key"] = raw_canonical_key.strip()[:240]
                manual_override = next(
                    (
                        existing
                        for existing in existing_items
                        if set(existing.source_capture_ids or []).intersection(source_ids)
                        and (existing.metadata_json or {}).get("manual_type_override") is True
                    ),
                    None,
                )
                if manual_override is not None:
                    manual_override.source_capture_ids = list(
                        dict.fromkeys((manual_override.source_capture_ids or []) + source_ids)
                    )
                    if structured_metadata and (manual_override.metadata_json or {}).get(
                        "manual_content_override"
                    ) is not True:
                        manual_override.metadata_json = {
                            **(manual_override.metadata_json or {}),
                            **structured_metadata,
                        }
                    db.flush()
                    item_ids.append(manual_override.id)
                    continue
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
                    metadata=structured_metadata,
                )
                if item is not None:
                    db.flush()
                    item_ids.append(item.id)
            save_day_version(db, day, source="before_organization")
            day.journal_text = organization.journal_text
            day.summary = {
                "highlights": organization.highlights,
                "item_ids": list(dict.fromkeys(item_ids)),
                "capture_count": len(captures),
            }
            day.organization_status = "completed"
            day.organization_error = None
            day.organized_at = datetime.now(timezone.utc)
            save_day_version(db, day, source="organization")
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
