import time


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

    organize = client.post(f"/api/journal/days/{local_date}/organize")
    assert organize.status_code == 202
    body = wait_for_day(client, local_date)
    assert body["organization_status"] == "completed"
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
