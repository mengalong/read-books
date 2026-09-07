import time
import json
from datetime import date, datetime

from app.database import SessionLocal
from app.models import User
from app.services.auth import create_user_with_workspace
from app.services.journal_service import capture_to_model_dict
from app.models import JournalCapture


def wait_for_day(client, local_date: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/journal/days/{local_date}")
        assert response.status_code == 200
        body = response.json()
        if body["organization_status"] in {"completed", "failed"}:
            return body
        time.sleep(0.02)
    raise AssertionError("日常整理任务没有完成")


def test_quick_captures_are_classified_and_organized(client):
    local_date = "2026-09-07"
    todo = client.post(
        "/api/journal/captures",
        json={
            "content": "明天给设计师确认首页文案",
            "capture_type": "todo",
            "local_date": local_date,
        },
    )
    assert todo.status_code == 201
    assert todo.json()["capture_type"] == "todo"

    idea = client.post(
        "/api/journal/captures",
        json={
            "content": "突然想到可以把读书笔记做成一张关系图",
            "capture_type": "note",
            "local_date": local_date,
        },
    )
    assert idea.status_code == 201

    organize = client.post(
        f"/api/journal/days/{local_date}/organize",
        json={"writing_style": "lu_xun"},
    )
    assert organize.status_code == 202
    body = wait_for_day(client, local_date)
    assert body["organization_status"] == "completed"
    assert body["writing_style"] == "lu_xun"
    assert "## 今日概览" in body["journal_text"]
    assert "## 待办" in body["journal_text"]
    assert "明天给设计师确认首页文案" in body["journal_text"]
    assert body["summary"]["capture_count"] == 2
    items = {item["item_type"]: item for item in body["items"]}
    assert items["todo"]["status"] == "open"
    assert items["idea"]["status"] == "needs_review"
    assert items["idea"]["source_capture_ids"]

    confirmed = client.patch(
        f"/api/journal/items/{items['idea']['id']}",
        json={"status": "inbox"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "inbox"


def test_journal_item_filters_and_day_edit(client):
    local_date = "2026-09-08"
    capture = client.post(
        "/api/journal/captures",
        json={
            "content": "想读《夜晚的潜水艇》",
            "capture_type": "want_read",
            "local_date": local_date,
        },
    )
    assert capture.status_code == 201
    assert client.post(f"/api/journal/days/{local_date}/organize").status_code == 202
    body = wait_for_day(client, local_date)
    assert body["items"][0]["item_type"] == "want_read"

    filtered = client.get("/api/journal/items?item_type=want_read")
    assert filtered.status_code == 200
    assert any(item["title"] == "想读《夜晚的潜水艇》" for item in filtered.json())

    edited = client.patch(
        f"/api/journal/days/{local_date}",
        json={"journal_text": "今天想读一本新的书。", "confirm": True},
    )
    assert edited.status_code == 200
    assert edited.json()["journal_text"] == "今天想读一本新的书。"
    assert edited.json()["confirmed_at"] is not None


def test_journal_data_is_isolated_by_workspace(client):
    with SessionLocal() as db:
        if db.query(User).filter(User.username == "journal-reader").one_or_none() is None:
            create_user_with_workspace(
                db,
                username="journal-reader",
                display_name="日常记录隔离用户",
                password="JournalReader1!",
                must_change_password=False,
            )
            db.commit()

    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"username": "journal-reader", "password": "JournalReader1!"},
    ).status_code == 200
    created = client.post(
        "/api/journal/captures",
        json={
            "content": "这个记录只属于普通用户",
            "capture_type": "note",
            "local_date": "2035-01-01",
        },
    )
    assert created.status_code == 201
    capture_id = created.json()["id"]

    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "TestAdmin1!"},
    ).status_code == 200
    admin_day = client.get("/api/journal/days/2035-01-01")
    assert admin_day.status_code == 200
    assert admin_day.json()["captures"] == []
    assert client.delete(f"/api/journal/captures/{capture_id}").status_code == 404


def test_captures_and_items_can_be_edited_and_deleted(client):
    local_date = "2035-01-02"
    created = client.post(
        "/api/journal/captures",
        json={
            "content": "先记一条待办",
            "capture_type": "todo",
            "local_date": local_date,
        },
    )
    assert created.status_code == 201
    capture_id = created.json()["id"]

    edited_capture = client.patch(
        f"/api/journal/captures/{capture_id}",
        json={
            "content": "更新后的灵感",
            "capture_type": "idea",
            "local_date": local_date,
        },
    )
    assert edited_capture.status_code == 200
    assert edited_capture.json()["content"] == "更新后的灵感"
    assert edited_capture.json()["capture_type"] == "idea"

    day = client.get(f"/api/journal/days/{local_date}")
    assert day.status_code == 200
    assert day.json()["captures"][0]["content"] == "更新后的灵感"
    item = day.json()["items"][0]
    edited_item = client.patch(
        f"/api/journal/items/{item['id']}",
        json={"item_type": "want_read", "title": "想读的一本书", "status": "inbox"},
    )
    assert edited_item.status_code == 200
    assert edited_item.json()["item_type"] == "want_read"
    assert edited_item.json()["title"] == "想读的一本书"
    deleted_item = client.delete(f"/api/journal/items/{item['id']}")
    assert deleted_item.status_code == 204
    deleted_capture = client.delete(f"/api/journal/captures/{capture_id}")
    assert deleted_capture.status_code == 204


def test_model_capture_payload_serializes_calendar_values():
    capture = JournalCapture(
        id="capture-json",
        workspace_id="workspace-json",
        content="一条记录",
        capture_type="note",
        local_date=date(2035, 1, 3),
        captured_at=datetime(2035, 1, 3, 9, 0),
        tags=[],
    )
    payload = capture_to_model_dict(capture)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "2035-01-03" in serialized
