from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.database import SessionLocal
from app.models import ModelUsageRecord, User


@dataclass(frozen=True)
class ModelUsageContext:
    task_id: str
    task_type: str
    task_label: str
    book_id: str | None = None
    quiz_id: str | None = None
    user_id: str | None = None
    workspace_id: str | None = None


@dataclass(frozen=True)
class ModelUsageEvent:
    context: ModelUsageContext
    phase: str
    call_number: int
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    status: str
    error_message: str | None
    latency_ms: int


@dataclass(frozen=True)
class ModelUsageSummary:
    task_count: int
    total_calls: int
    successful_calls: int
    failed_calls: int
    unreported_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ModelUsageTask:
    task_id: str
    task_type: str
    task_label: str
    status: str
    book_id: str | None
    quiz_id: str | None
    user_id: str | None
    username: str | None
    display_name: str | None
    workspace_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    unreported_calls: int
    started_at: datetime
    finished_at: datetime
    stages: list[ModelUsageRecord]


@dataclass(frozen=True)
class ModelUsageUserSummary:
    user_id: str
    username: str
    display_name: str
    task_count: int
    total_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


def new_usage_context(
    task_type: str,
    task_label: str,
    *,
    book_id: str | None = None,
    quiz_id: str | None = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> ModelUsageContext:
    return ModelUsageContext(
        task_id=str(uuid4()),
        task_type=task_type,
        task_label=task_label,
        book_id=book_id,
        quiz_id=quiz_id,
        user_id=user_id,
        workspace_id=workspace_id,
    )


def token_counts(body: Any) -> tuple[int | None, int | None, int | None]:
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return None, None, None

    def non_negative_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and value >= 0:
            return value
        return None

    input_tokens = non_negative_int(usage.get("prompt_tokens"))
    if input_tokens is None:
        input_tokens = non_negative_int(usage.get("input_tokens"))
    output_tokens = non_negative_int(usage.get("completion_tokens"))
    if output_tokens is None:
        output_tokens = non_negative_int(usage.get("output_tokens"))
    total_tokens = non_negative_int(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


def record_model_usage(event: ModelUsageEvent) -> None:
    with SessionLocal() as db:
        db.add(
            ModelUsageRecord(
                task_id=event.context.task_id,
                task_type=event.context.task_type,
                task_label=event.context.task_label,
                phase=event.phase,
                call_number=event.call_number,
                model_name=event.model_name,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                total_tokens=event.total_tokens,
                status=event.status,
                error_message=event.error_message,
                latency_ms=event.latency_ms,
                book_id=event.context.book_id,
                quiz_id=event.context.quiz_id,
                user_id=event.context.user_id,
                workspace_id=event.context.workspace_id,
            )
        )
        db.commit()


def attach_quiz_to_usage(task_id: str, quiz_id: str) -> None:
    with SessionLocal() as db:
        db.execute(
            update(ModelUsageRecord)
            .where(ModelUsageRecord.task_id == task_id)
            .values(quiz_id=quiz_id)
        )
        db.commit()


def get_model_usage_report(
    db: Session,
    *,
    task_type: str | None = None,
    user_id: str | None = None,
    limit: int = 50,
) -> tuple[ModelUsageSummary, list[ModelUsageTask]]:
    filters = [ModelUsageRecord.task_type == task_type] if task_type else []
    if user_id:
        filters.append(ModelUsageRecord.user_id == user_id)
    summary_row = db.execute(
        select(
            func.count(func.distinct(ModelUsageRecord.task_id)),
            func.count(ModelUsageRecord.id),
            func.sum(case((ModelUsageRecord.status == "success", 1), else_=0)),
            func.sum(case((ModelUsageRecord.status == "failed", 1), else_=0)),
            func.sum(case((ModelUsageRecord.total_tokens.is_(None), 1), else_=0)),
            func.coalesce(func.sum(ModelUsageRecord.input_tokens), 0),
            func.coalesce(func.sum(ModelUsageRecord.output_tokens), 0),
            func.coalesce(func.sum(ModelUsageRecord.total_tokens), 0),
        ).where(*filters)
    ).one()
    summary = ModelUsageSummary(*(int(value or 0) for value in summary_row))

    task_rows = db.execute(
        select(
            ModelUsageRecord.task_id,
            func.max(ModelUsageRecord.created_at).label("last_called_at"),
        )
        .where(*filters)
        .group_by(ModelUsageRecord.task_id)
        .order_by(func.max(ModelUsageRecord.created_at).desc())
        .limit(limit)
    ).all()
    task_ids = [row.task_id for row in task_rows]
    if not task_ids:
        return summary, []

    records = list(
        db.scalars(
            select(ModelUsageRecord)
            .options(selectinload(ModelUsageRecord.user))
            .where(ModelUsageRecord.task_id.in_(task_ids))
            .order_by(ModelUsageRecord.created_at, ModelUsageRecord.call_number)
        ).all()
    )
    records_by_task: dict[str, list[ModelUsageRecord]] = {task_id: [] for task_id in task_ids}
    for record in records:
        records_by_task[record.task_id].append(record)

    tasks: list[ModelUsageTask] = []
    for task_id in task_ids:
        stages = records_by_task[task_id]
        first = stages[0]
        tasks.append(
            ModelUsageTask(
                task_id=task_id,
                task_type=first.task_type,
                task_label=first.task_label,
                status="failed" if any(stage.status == "failed" for stage in stages) else "success",
                book_id=first.book_id,
                quiz_id=next((stage.quiz_id for stage in stages if stage.quiz_id), None),
                user_id=first.user_id,
                username=first.user.username if first.user else None,
                display_name=first.user.display_name if first.user else None,
                workspace_id=first.workspace_id,
                input_tokens=sum(stage.input_tokens or 0 for stage in stages),
                output_tokens=sum(stage.output_tokens or 0 for stage in stages),
                total_tokens=sum(stage.total_tokens or 0 for stage in stages),
                unreported_calls=sum(stage.total_tokens is None for stage in stages),
                started_at=stages[0].created_at,
                finished_at=stages[-1].created_at,
                stages=stages,
            )
        )
    return summary, tasks


def get_model_usage_user_summaries(
    db: Session, *, task_type: str | None = None
) -> list[ModelUsageUserSummary]:
    filters = [ModelUsageRecord.user_id.is_not(None)]
    if task_type:
        filters.append(ModelUsageRecord.task_type == task_type)
    rows = db.execute(
        select(
            User.id,
            User.username,
            User.display_name,
            func.count(func.distinct(ModelUsageRecord.task_id)),
            func.count(ModelUsageRecord.id),
            func.coalesce(func.sum(ModelUsageRecord.input_tokens), 0),
            func.coalesce(func.sum(ModelUsageRecord.output_tokens), 0),
            func.coalesce(func.sum(ModelUsageRecord.total_tokens), 0),
        )
        .join(ModelUsageRecord, ModelUsageRecord.user_id == User.id)
        .where(*filters)
        .group_by(User.id, User.username, User.display_name)
        .order_by(func.coalesce(func.sum(ModelUsageRecord.total_tokens), 0).desc())
    ).all()
    return [
        ModelUsageUserSummary(
            user_id=row[0],
            username=row[1],
            display_name=row[2],
            task_count=int(row[3] or 0),
            total_calls=int(row[4] or 0),
            input_tokens=int(row[5] or 0),
            output_tokens=int(row[6] or 0),
            total_tokens=int(row[7] or 0),
        )
        for row in rows
    ]
