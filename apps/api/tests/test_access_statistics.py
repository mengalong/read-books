from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import User, UserAccessVisit, UserSession
from app.services.auth import create_user_with_workspace


def test_access_statistics_supports_day_month_and_year_tables(client):
    with SessionLocal() as db:
        user, workspace = create_user_with_workspace(
            db,
            username="access-report-user",
            display_name="访问统计用户",
            password="AccessReport1!",
            must_change_password=False,
        )
        db.add(
            UserAccessVisit(
                user_id=user.id,
                workspace_id=workspace.id,
                session_id=None,
                entry_type="login",
                started_at=datetime(2026, 8, 5, 15, 50, tzinfo=timezone.utc),
                last_activity_at=datetime(2026, 8, 5, 16, 20, tzinfo=timezone.utc),
                ended_at=datetime(2026, 8, 5, 16, 20, tzinfo=timezone.utc),
                end_reason="logout",
            )
        )
        db.commit()
        user_id = user.id

    daily = client.get(
        "/api/settings/access-statistics",
        params={
            "granularity": "day",
            "start_date": "2026-08-05",
            "end_date": "2026-08-06",
            "user_id": user_id,
        },
    )
    assert daily.status_code == 200
    daily_body = daily.json()
    assert daily_body["timezone"] == "Asia/Shanghai"
    assert daily_body["summary"] == {
        "visit_count": 1,
        "login_count": 1,
        "active_user_count": 1,
        "total_duration_seconds": 1800,
        "average_duration_seconds": 1800,
    }
    assert [period["period_key"] for period in daily_body["periods"]] == [
        "2026-08-05",
        "2026-08-06",
    ]
    assert daily_body["periods"][0]["visit_count"] == 1
    assert daily_body["periods"][0]["total_duration_seconds"] == 600
    assert daily_body["periods"][1]["visit_count"] == 0
    assert daily_body["periods"][1]["active_user_count"] == 1
    assert daily_body["periods"][1]["total_duration_seconds"] == 1200
    target_user = next(item for item in daily_body["users"] if item["user_id"] == user_id)
    assert target_user["active_period_count"] == 2
    assert target_user["visit_count"] == 1

    monthly = client.get(
        "/api/settings/access-statistics",
        params={
            "granularity": "month",
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "user_id": user_id,
        },
    )
    assert monthly.status_code == 200
    assert monthly.json()["periods"][0]["period_key"] == "2026-08"
    assert monthly.json()["periods"][0]["total_duration_seconds"] == 1800

    yearly = client.get(
        "/api/settings/access-statistics",
        params={
            "granularity": "year",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "user_id": user_id,
        },
    )
    assert yearly.status_code == 200
    assert yearly.json()["periods"][0]["period_key"] == "2026"
    assert yearly.json()["periods"][0]["visit_count"] == 1


def test_activity_heartbeat_reuses_visit_and_logout_closes_it(client):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "test-admin"))
        session = db.scalar(
            select(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.created_at.desc())
        )
        session_id = session.id
        before = db.scalar(
            select(func.count(UserAccessVisit.id)).where(
                UserAccessVisit.session_id == session_id
            )
        )

    assert client.post("/api/auth/activity").status_code == 204
    assert client.post("/api/auth/activity").status_code == 204
    with SessionLocal() as db:
        after = db.scalar(
            select(func.count(UserAccessVisit.id)).where(
                UserAccessVisit.session_id == session_id
            )
        )
        assert after == before

    assert client.post("/api/auth/logout").status_code == 204
    with SessionLocal() as db:
        visit = db.scalar(
            select(UserAccessVisit)
            .where(UserAccessVisit.session_id == session_id)
            .order_by(UserAccessVisit.started_at.desc())
        )
        assert visit.ended_at is not None
        assert visit.end_reason == "logout"


def test_regular_user_cannot_read_access_statistics(client):
    with SessionLocal() as db:
        create_user_with_workspace(
            db,
            username="access-regular-user",
            display_name="普通访问用户",
            password="AccessUser1!",
            must_change_password=False,
        )
        db.commit()

    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"username": "access-regular-user", "password": "AccessUser1!"},
    ).status_code == 200
    assert client.get("/api/settings/access-statistics").status_code == 403
