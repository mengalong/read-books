from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from openpyxl import Workbook

from app.database import SessionLocal
from app.models import ResourceMaterial
from app.services.material_parser import parse_material_document, parse_material_file


def create_resource(client, title: str = "潜伏") -> dict:
    response = client.post(
        "/api/books",
        json={
            "title": title,
            "author": "姜伟",
            "description": "电视剧台词资料测试",
            "resource_type": "tv_series",
            "cover_color": "#2F6B5F",
            "language": "中文",
            "reading_status": "finished",
            "tags": ["电视剧"],
        },
    )
    assert response.status_code == 201
    return response.json()


def upload_without_background_parse(
    client,
    monkeypatch,
    book_id: str,
    *,
    name: str,
    content: bytes,
    material_type: str,
):
    monkeypatch.setattr("app.routers.materials.parse_material_document", lambda _: None)
    response = client.post(
        f"/api/books/{book_id}/materials",
        data={"material_type": material_type, "season_number": "1", "episode_label": "第1集"},
        files={"file": (name, content, "application/octet-stream")},
    )
    assert response.status_code == 202
    return response.json()


def material_for(path: Path, *, file_format: str, material_type: str) -> ResourceMaterial:
    return ResourceMaterial(
        book_id="book-id",
        material_type=material_type,
        file_format=file_format,
        file_name=path.name,
        file_path=str(path),
        file_size=path.stat().st_size,
        file_hash="hash",
        parse_status="pending",
    )


def test_structured_quote_sheet_is_ready_for_generation(client, monkeypatch):
    book = create_resource(client, "潜伏台词表测试")
    payload = (
        "台词,角色,季,集,开始时间,结束时间,场景,上下文\n"
        "既然来了，就要把事情办好,吴站长,1,1,00:10:01.000,00:10:04.000,办公室,站内会议\n"
        "有些事情急不得,余则成,1,1,00:11:01.000,00:11:03.000,走廊,两人交谈\n"
    ).encode("utf-8")
    material = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="quotes.csv",
        content=payload,
        material_type="quote_sheet",
    )

    parse_material_document(material["id"])

    materials = client.get(f"/api/books/{book['id']}/materials")
    assert materials.status_code == 200
    assert materials.json()[0]["parse_status"] == "completed"
    assert materials.json()[0]["segment_count"] == 2
    assert materials.json()[0]["quote_count"] == 2

    quotes = client.get(f"/api/books/{book['id']}/quotes")
    assert quotes.status_code == 200
    body = quotes.json()
    assert body["total"] == 2
    assert body["pending_count"] == 0
    assert body["confirmed_count"] == 2
    assert body["speakers"] == ["余则成", "吴站长"]
    assert all(item["enabled_for_generation"] for item in body["items"])
    assert {item["speaker_origin"] for item in body["items"]} == {"provided"}
    assert body["items"][0]["material_file_name"] == "quotes.csv"

    detail = client.get(f"/api/books/{book['id']}")
    assert detail.status_code == 200
    assert detail.json()["stats"]["material_count"] == 1
    assert detail.json()["stats"]["ready_material_count"] == 1
    assert detail.json()["stats"]["confirmed_quote_count"] == 2


def test_subtitle_without_speaker_requires_review(client, monkeypatch):
    book = create_resource(client, "潜伏字幕测试")
    payload = (
        "1\n00:00:01,000 --> 00:00:03,000\n吴站长：会议现在开始。\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\n这件事需要再想想。\n"
    ).encode("utf-8")
    material = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="episode-01.srt",
        content=payload,
        material_type="subtitle",
    )

    parse_material_document(material["id"])

    materials = client.get(f"/api/books/{book['id']}/materials").json()
    assert materials[0]["parse_status"] == "needs_review"
    quotes = client.get(f"/api/books/{book['id']}/quotes").json()
    assert quotes["total"] == 2
    assert quotes["pending_count"] == 1
    pending = next(item for item in quotes["items"] if item["review_status"] == "pending")

    response = client.patch(
        f"/api/books/{book['id']}/quotes/{pending['id']}",
        json={"speaker": "余则成", "review_status": "confirmed"},
    )
    assert response.status_code == 200
    assert response.json()["speaker_origin"] == "confirmed"
    assert response.json()["enabled_for_generation"] is True
    assert client.get(f"/api/books/{book['id']}/materials").json()[0]["parse_status"] == "completed"


def test_bulk_review_and_material_deletion(client, monkeypatch):
    book = create_resource(client, "潜伏台词校对测试")
    material = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="episode-02.txt",
        content="第一句没有角色\n第二句也没有角色\n".encode("utf-8"),
        material_type="script",
    )
    parse_material_document(material["id"])
    quotes = client.get(f"/api/books/{book['id']}/quotes").json()["items"]

    confirm = client.post(
        f"/api/books/{book['id']}/quotes/bulk-confirm",
        json={"quote_ids": [item["id"] for item in quotes]},
    )
    assert confirm.status_code == 200
    assert all(item["review_status"] == "confirmed" for item in confirm.json())

    reject = client.post(
        f"/api/books/{book['id']}/quotes/bulk-reject",
        json={"quote_ids": [quotes[0]["id"]]},
    )
    assert reject.status_code == 200
    assert reject.json()[0]["review_status"] == "rejected"
    assert reject.json()[0]["enabled_for_generation"] is False

    with SessionLocal() as db:
        stored_path = Path(db.get(ResourceMaterial, material["id"]).file_path)
    assert stored_path.exists()
    response = client.delete(f"/api/books/{book['id']}/materials/{material['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/books/{book['id']}/materials").json() == []
    assert client.get(f"/api/books/{book['id']}/quotes").json()["total"] == 0
    assert not stored_path.exists()


def test_duplicate_and_invalid_materials_are_rejected(client, monkeypatch):
    book = create_resource(client, "潜伏重复资料测试")
    payload = "台词,角色\n开会了,吴站长\n".encode("utf-8")
    upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="quotes.csv",
        content=payload,
        material_type="quote_sheet",
    )
    duplicate = client.post(
        f"/api/books/{book['id']}/materials",
        data={"material_type": "quote_sheet"},
        files={"file": ("quotes-copy.csv", payload, "text/csv")},
    )
    assert duplicate.status_code == 409

    invalid = client.post(
        f"/api/books/{book['id']}/materials",
        data={"material_type": "subtitle"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert invalid.status_code == 400

    template = client.get("/api/material-templates/quote-sheet.csv")
    assert template.status_code == 200
    assert "台词,角色" in template.content.decode("utf-8-sig")


def test_vtt_and_ass_preserve_timing_and_provided_speakers(tmp_path):
    vtt_path = tmp_path / "episode.vtt"
    vtt_path.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:03.500\n[吴站长] 会议开始。\n",
        encoding="utf-8",
    )
    vtt_records = parse_material_file(
        material_for(vtt_path, file_format="vtt", material_type="subtitle")
    )
    assert len(vtt_records) == 1
    assert vtt_records[0].speaker == "吴站长"
    assert vtt_records[0].content == "会议开始。"
    assert vtt_records[0].start_ms == 1_000
    assert vtt_records[0].end_ms == 3_500

    ass_path = tmp_path / "episode.ass"
    ass_path.write_text(
        "[Script Info]\nTitle: test\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:04.00,0:00:06.25,Default,余则成,0,0,0,,这件事要谨慎。\n",
        encoding="utf-8",
    )
    ass_records = parse_material_file(
        material_for(ass_path, file_format="ass", material_type="subtitle")
    )
    assert len(ass_records) == 1
    assert ass_records[0].speaker == "余则成"
    assert ass_records[0].start_ms == 4_000
    assert ass_records[0].end_ms == 6_250


def test_xlsx_quote_sheet_and_pdf_script_parsing(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["台词", "角色", "集", "场景"])
    sheet.append(["这是一条结构化台词。", "吴站长", 3, "办公室"])
    xlsx_path = tmp_path / "quotes.xlsx"
    workbook.save(xlsx_path)
    workbook.close()

    xlsx_records = parse_material_file(
        material_for(xlsx_path, file_format="xlsx", material_type="quote_sheet")
    )
    assert len(xlsx_records) == 1
    assert xlsx_records[0].speaker == "吴站长"
    assert xlsx_records[0].episode_number == 3
    assert xlsx_records[0].scene_label == "办公室"

    pdf_path = tmp_path / "script.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Station chief: The meeting starts now.")
    document.save(pdf_path)
    document.close()

    pdf_records = parse_material_file(
        material_for(pdf_path, file_format="pdf", material_type="script")
    )
    assert pdf_records
    assert pdf_records[0].speaker == "Station chief"
    assert pdf_records[0].page_number == 1


def test_quote_sheet_requires_quote_and_speaker(tmp_path):
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text("台词,角色\n只有台词,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="缺少台词或角色"):
        parse_material_file(
            material_for(csv_path, file_format="csv", material_type="quote_sheet")
        )
