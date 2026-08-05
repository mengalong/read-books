from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import User, UserAccessVisit, Workspace, WorkspaceMember
from app.schemas import (
    AccessStatisticsPeriodResponse,
    AccessStatisticsReportResponse,
    AccessStatisticsSummaryResponse,
    AccessStatisticsUserResponse,
)
from app.services.auth import ACCESS_VISIT_END_GRACE, as_utc

AccessGranularity = Literal["day", "month", "year"]
BEIJING_TIMEZONE_NAME = "Asia/Shanghai"
BEIJING_TIMEZONE = ZoneInfo(BEIJING_TIMEZONE_NAME)
MAX_PERIODS = {"day": 366, "month": 120, "year": 20}


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _shift_month(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _period_start(value: date, granularity: AccessGranularity) -> datetime:
    if granularity == "month":
        value = _month_start(value)
    elif granularity == "year":
        value = date(value.year, 1, 1)
    return datetime.combine(value, datetime.min.time(), tzinfo=BEIJING_TIMEZONE)


def _next_period(value: datetime, granularity: AccessGranularity) -> datetime:
    if granularity == "day":
        return value + timedelta(days=1)
    if granularity == "month":
        next_month = _shift_month(value.date(), 1)
        return datetime.combine(next_month, datetime.min.time(), tzinfo=BEIJING_TIMEZONE)
    return value.replace(year=value.year + 1)


def _default_start(anchor: date, granularity: AccessGranularity) -> date:
    if granularity == "day":
        return anchor - timedelta(days=29)
    if granularity == "month":
        return _shift_month(anchor, -11)
    return date(anchor.year - 4, 1, 1)


def resolve_access_range(
    granularity: AccessGranularity,
    start_date: date | None,
    end_date: date | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime, list[tuple[datetime, datetime]]]:
    local_today = (now or datetime.now(timezone.utc)).astimezone(BEIJING_TIMEZONE).date()
    anchor = end_date or local_today
    requested_start = start_date or _default_start(anchor, granularity)
    if requested_start > anchor:
        raise ValueError("开始日期不能晚于结束日期")
    range_start = _period_start(requested_start, granularity)
    range_end = _next_period(_period_start(anchor, granularity), granularity)
    periods: list[tuple[datetime, datetime]] = []
    cursor = range_start
    while cursor < range_end:
        next_cursor = _next_period(cursor, granularity)
        periods.append((cursor, next_cursor))
        if len(periods) > MAX_PERIODS[granularity]:
            raise ValueError(
                f"按{'天' if granularity == 'day' else '月' if granularity == 'month' else '年'}"
                f"汇总最多查询 {MAX_PERIODS[granularity]} 个时间段"
            )
        cursor = next_cursor
    return range_start, range_end, periods


def _effective_end(visit: UserAccessVisit, now: datetime) -> datetime:
    if visit.ended_at is not None:
        return max(as_utc(visit.started_at), as_utc(visit.ended_at))
    estimated = as_utc(visit.last_activity_at) + ACCESS_VISIT_END_GRACE
    return max(as_utc(visit.started_at), min(now, estimated))


def _overlap_seconds(
    visit: UserAccessVisit, start: datetime, end: datetime, now: datetime
) -> int:
    overlap_start = max(as_utc(visit.started_at), start)
    overlap_end = min(_effective_end(visit, now), end)
    return max(0, int((overlap_end - overlap_start).total_seconds()))


def _period_key(start: datetime, granularity: AccessGranularity) -> str:
    if granularity == "day":
        return start.strftime("%Y-%m-%d")
    if granularity == "month":
        return start.strftime("%Y-%m")
    return start.strftime("%Y")


def _summary_for_visits(
    visits: list[UserAccessVisit], start: datetime, end: datetime, now: datetime
) -> AccessStatisticsSummaryResponse:
    started = [visit for visit in visits if start <= as_utc(visit.started_at) < end]
    overlaps = {
        visit.id: _overlap_seconds(visit, start, end, now)
        for visit in visits
    }
    active_visits = {visit_id: seconds for visit_id, seconds in overlaps.items() if seconds > 0}
    total_duration = sum(active_visits.values())
    active_users = {
        visit.user_id for visit in visits if overlaps.get(visit.id, 0) > 0
    }
    return AccessStatisticsSummaryResponse(
        visit_count=len(started),
        login_count=sum(visit.entry_type == "login" for visit in started),
        active_user_count=len(active_users),
        total_duration_seconds=total_duration,
        average_duration_seconds=(
            round(total_duration / len(active_visits)) if active_visits else 0
        ),
    )


def get_access_statistics_report(
    db: Session,
    *,
    granularity: AccessGranularity,
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: str | None = None,
    now: datetime | None = None,
) -> AccessStatisticsReportResponse:
    current = as_utc(now or datetime.now(timezone.utc))
    local_start, local_end, local_periods = resolve_access_range(
        granularity, start_date, end_date, now=current
    )
    range_start = local_start.astimezone(timezone.utc)
    range_end = local_end.astimezone(timezone.utc)

    user_rows = db.execute(
        select(User, Workspace)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(Workspace.workspace_type == "personal")
        .order_by(User.created_at.desc())
    ).all()
    users = {user.id: (user, workspace) for user, workspace in user_rows}
    if user_id and user_id not in users:
        raise ValueError("未找到该用户")

    visits = list(
        db.scalars(
            select(UserAccessVisit)
            .where(
                UserAccessVisit.started_at < range_end,
                or_(
                    UserAccessVisit.ended_at >= range_start,
                    and_(
                        UserAccessVisit.ended_at.is_(None),
                        UserAccessVisit.last_activity_at
                        >= range_start - ACCESS_VISIT_END_GRACE,
                    ),
                ),
            )
            .order_by(UserAccessVisit.started_at)
        ).all()
    )
    selected_visits = [visit for visit in visits if not user_id or visit.user_id == user_id]

    periods = []
    for local_period_start, local_period_end in local_periods:
        period_start = local_period_start.astimezone(timezone.utc)
        period_end = local_period_end.astimezone(timezone.utc)
        period_summary = _summary_for_visits(
            selected_visits, period_start, period_end, current
        )
        key = _period_key(local_period_start, granularity)
        periods.append(
            AccessStatisticsPeriodResponse(
                period_key=key,
                period_label=key,
                period_start=period_start,
                period_end=period_end,
                **period_summary.model_dump(),
            )
        )

    user_summaries = []
    for current_user, workspace in users.values():
        current_visits = [visit for visit in visits if visit.user_id == current_user.id]
        summary = _summary_for_visits(current_visits, range_start, range_end, current)
        overlapping_visits = [
            visit
            for visit in current_visits
            if _overlap_seconds(visit, range_start, range_end, current) > 0
        ]
        active_period_count = sum(
            any(
                _overlap_seconds(
                    visit,
                    period_start.astimezone(timezone.utc),
                    period_end.astimezone(timezone.utc),
                    current,
                )
                > 0
                for visit in current_visits
            )
            for period_start, period_end in local_periods
        )
        user_summaries.append(
            AccessStatisticsUserResponse(
                user_id=current_user.id,
                workspace_id=workspace.id,
                username=current_user.username,
                display_name=current_user.display_name,
                visit_count=summary.visit_count,
                login_count=summary.login_count,
                active_period_count=active_period_count,
                total_duration_seconds=summary.total_duration_seconds,
                average_duration_seconds=summary.average_duration_seconds,
                first_visit_at=(
                    min(as_utc(visit.started_at) for visit in overlapping_visits)
                    if overlapping_visits
                    else None
                ),
                last_visit_at=(
                    max(_effective_end(visit, current) for visit in overlapping_visits)
                    if overlapping_visits
                    else None
                ),
            )
        )
    user_summaries.sort(
        key=lambda item: (item.visit_count, item.total_duration_seconds), reverse=True
    )

    return AccessStatisticsReportResponse(
        granularity=granularity,
        timezone=BEIJING_TIMEZONE_NAME,
        range_start=range_start,
        range_end=range_end,
        selected_user_id=user_id,
        summary=_summary_for_visits(selected_visits, range_start, range_end, current),
        periods=periods,
        users=user_summaries,
    )
