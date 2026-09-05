from __future__ import annotations

import json
from pathlib import Path
import time

import fitz
import pytest
from openpyxl import Workbook

from app.database import SessionLocal
from app.models import ContentChunk, ExamShare, PdfDocument, PlotEvent, ResourceMaterial
from app.schemas import QuizGenerateRequest
from app.services.material_parser import parse_material_document, parse_material_file
from app.services.quiz_generation import resolve_source_mode


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


def wait_for_generation(client, task_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/quiz-generation-tasks/{task_id}")
        assert response.status_code == 200
        task = response.json()
        if task["status"] == "completed":
            return task
        if task["status"] == "failed":
            raise AssertionError(task["error_message"])
        time.sleep(0.01)
    raise AssertionError("专题出题任务在测试等待时间内没有完成")


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


def test_qianfu_style_episode_page_csv_is_parsed(tmp_path):
    csv_path = tmp_path / "dialogues.csv"
    csv_path.write_text(
        "\n".join(
            [
                "集数,页码,类型,角色,内容",
                "1,17,环境描写,,1. 空镜山城重庆 日外",
                "1,17,台词,林怀复,……据我所知，参加旧金山会议的代表。",
                "1,17,旁白,,甲（OS）：是呀，前不久我外甥在津浦战役中率部起义。",
                "1,18,台词,余则成,张名义，出什么事了？",
                "1,18,台词,,爸爸……爸爸……",
            ]
        ),
        encoding="utf-8",
    )

    records = parse_material_file(
        material_for(csv_path, file_format="csv", material_type="quote_sheet")
    )

    assert len(records) == 5
    dialogue_records = [record for record in records if record.speaker]
    assert len(dialogue_records) == 2
    assert dialogue_records[0].speaker == "林怀复"
    assert dialogue_records[0].episode_number == 1
    assert dialogue_records[0].page_number == 17
    no_speaker_records = [record for record in records if not record.speaker]
    assert len(no_speaker_records) == 3
    no_speaker_dialogue = next(
        record for record in no_speaker_records if record.content == "爸爸……爸爸……"
    )
    assert no_speaker_dialogue.speaker_origin == "unknown"
    assert no_speaker_dialogue.is_dialogue is True
    assert next(
        record for record in records if record.content == "1. 空镜山城重庆 日外"
    ).is_dialogue is False
    assert next(
        record for record in records if record.content.startswith("甲（OS）")
    ).is_dialogue is False


def test_typed_quote_sheet_only_sends_dialogue_rows_to_review(client, monkeypatch):
    book = create_resource(client, "潜伏分类校对测试")
    payload = (
        "集数,页码,类型,角色,内容\n"
        "1,17,环境描写,,空镜山城重庆 日外\n"
        "1,17,旁白,,抗战胜利在即，许多人面临新的抉择。\n"
        "1,17,台词,林怀复,他们才造谣。\n"
        "1,18,台词,余则成,张名义，出什么事了？\n"
        "1,18,台词,,爸爸……爸爸……\n"
    ).encode("utf-8")
    material = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="typed-dialogues.csv",
        content=payload,
        material_type="quote_sheet",
    )

    parse_material_document(material["id"])

    stored_material = client.get(f"/api/books/{book['id']}/materials").json()[0]
    assert stored_material["parse_status"] == "needs_review"
    assert stored_material["segment_count"] == 5
    assert stored_material["quote_count"] == 3
    quotes = client.get(f"/api/books/{book['id']}/quotes").json()
    assert quotes["total"] == 3
    assert quotes["pending_count"] == 1
    assert quotes["confirmed_count"] == 2
    assert {item["quote_text"] for item in quotes["items"]} == {
        "他们才造谣。",
        "张名义，出什么事了？",
        "爸爸……爸爸……",
    }


def test_classic_quote_quiz_uses_material_and_preserves_snapshot(client, monkeypatch):
    book = create_resource(client, "潜伏经典台词专题")
    payload = (
        "台词,角色,集,上下文\n"
        "会议现在开始,吴站长,1,站内会议\n"
        "这件事要谨慎,余则成,2,秘密交谈\n"
        "先把情况弄清楚,李涯,3,调查讨论\n"
    ).encode("utf-8")
    material = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="topic-quotes.csv",
        content=payload,
        material_type="quote_sheet",
    )
    parse_material_document(material["id"])

    generated = client.post(
        f"/api/books/{book['id']}/quizzes",
        json={
            "duration_minutes": 15,
            "difficulty": "medium",
            "single_count": 1,
            "multiple_count": 1,
            "short_count": 1,
            "generation_theme": "classic_quotes",
            "theme_config": {
                "material_ids": [material["id"]],
                "character_names": [],
                "question_subtypes": [
                    "quote_speaker",
                    "quote_context",
                    "quote_meaning",
                ],
            },
        },
    )
    assert generated.status_code == 202
    task = wait_for_generation(client, generated.json()["id"])
    assert task["source_mode"] == "material"
    assert task["generation_theme"] == "classic_quotes"
    assert task["theme_config"]["material_ids"] == [material["id"]]

    quiz = client.get(f"/api/quizzes/{task['quiz_id']}")
    assert quiz.status_code == 200
    body = quiz.json()
    assert body["source_mode"] == "material"
    assert body["generation_theme"] == "classic_quotes"
    assert len(body["questions"]) == 3
    assert len({item["quote_entry_ids"][0] for item in body["questions"]}) == 3
    assert all(item["source_segment_ids"] for item in body["questions"])
    assert all(item["source_evidence"][0]["material_id"] == material["id"] for item in body["questions"])

    shared = client.post(f"/api/quizzes/{task['quiz_id']}/exam-shares", json={})
    assert shared.status_code == 201
    public_exam = client.get(f"/api/public/exams/{shared.json()['share_code']}")
    assert public_exam.status_code == 200
    assert public_exam.json()["generation_theme"] == "classic_quotes"
    attempt = client.post(
        f"/api/public/exams/{shared.json()['share_code']}/attempts",
        json={"participant_name": "本地测试用户"},
    )
    assert attempt.status_code == 201
    assert attempt.json()["generation_theme"] == "classic_quotes"
    assert all(not question["quote_entry_ids"] for question in attempt.json()["questions"])
    assert all(not question["source_segment_ids"] for question in attempt.json()["questions"])
    assert all(not question["source_evidence"] for question in attempt.json()["questions"])
    with SessionLocal() as db:
        share = db.get(ExamShare, shared.json()["id"])
        assert share.quiz_snapshot["generation_theme"] == "classic_quotes"
        assert share.quiz_snapshot["theme_config"]["material_ids"] == [material["id"]]
        assert all(question["quote_entry_ids"] for question in share.quiz_snapshot["questions"])


def test_general_quiz_without_pdf_uses_confirmed_quotes_as_sources(client, monkeypatch):
    book = create_resource(client, "潜伏综合台词来源")
    payload = (
        "台词,角色,集,上下文\n"
        "会议现在开始,吴站长,1,站内会议\n"
        "这件事要谨慎,余则成,2,秘密交谈\n"
    ).encode("utf-8")
    material = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="general-quotes.csv",
        content=payload,
        material_type="quote_sheet",
    )
    parse_material_document(material["id"])

    generated = client.post(
        f"/api/books/{book['id']}/quizzes",
        json={"single_count": 1, "multiple_count": 0, "short_count": 0},
    )
    assert generated.status_code == 202
    task = wait_for_generation(client, generated.json()["id"])
    assert task["source_mode"] == "material"

    quiz = client.get(f"/api/quizzes/{task['quiz_id']}")
    assert quiz.status_code == 200
    body = quiz.json()
    assert body["source_mode"] == "material"
    assert body["questions"][0]["quote_entry_ids"]
    assert body["questions"][0]["source_evidence"][0]["material_id"] == material["id"]


def test_general_source_mode_uses_combined_sources_when_pdf_and_quotes_exist(client, monkeypatch):
    book = create_resource(client, "潜伏综合来源判定")
    payload = "台词,角色,集,上下文\n会议现在开始,吴站长,1,站内会议\n".encode("utf-8")
    material = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="combined-quotes.csv",
        content=payload,
        material_type="quote_sheet",
    )
    parse_material_document(material["id"])

    with SessionLocal() as db:
        pdf = PdfDocument(
            book_id=book["id"],
            file_name="source.pdf",
            file_path="demo://source",
            file_size=1,
            page_count=1,
            chunk_count=1,
            parse_status="completed",
        )
        db.add(pdf)
        db.flush()
        db.add(
            ContentChunk(
                book_id=book["id"],
                pdf_id=pdf.id,
                page_number=1,
                sequence=1,
                content="余则成在站内接到新的任务。",
                char_count=14,
            )
        )
        db.commit()
        assert resolve_source_mode(
            db,
            book["id"],
            QuizGenerateRequest(single_count=1, multiple_count=0, short_count=0),
        ) == "combined"

    generated = client.post(
        f"/api/books/{book['id']}/quizzes",
        json={"single_count": 1, "multiple_count": 0, "short_count": 0},
    )
    assert generated.status_code == 202
    task = wait_for_generation(client, generated.json()["id"])
    assert task["source_mode"] == "combined"
    quiz = client.get(f"/api/quizzes/{task['quiz_id']}")
    assert quiz.status_code == 200
    question = quiz.json()["questions"][0]
    assert question["quote_entry_ids"] or question["source_evidence"]
    assert question["source_evidence"]


def test_general_source_mode_uses_combined_sources_when_plot_and_quotes_exist_without_pdf(client, monkeypatch):
    book = create_resource(client, "潜伏剧情台词综合判定")
    quote = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="combined-plot-quotes.csv",
        content="台词,角色,集,上下文\n会议现在开始,吴站长,1,站内会议\n".encode("utf-8"),
        material_type="quote_sheet",
    )
    parse_material_document(quote["id"])
    plot_payload = {
        "schema_version": "plot_summary.v1",
        "source_registry": [{"source_id": "src-plot", "title": "剧情资料"}],
        "events": [{
            "event_id": "s01e01-event-001",
            "level": "event",
            "season_number": 1,
            "episode_number": 1,
            "sequence": 1,
            "title": "任务安排",
            "summary": "组织为任务安排新的身份掩护。",
            "cause": "任务需要新的身份安排。",
            "action": "相关人物接受并执行安排。",
            "result": "人物进入新的行动阶段。",
            "future_impact": "为后续合作和冲突埋下基础。",
            "characters": ["余则成", "翠平"],
            "source_refs": ["src-plot"],
            "confidence": "confirmed",
            "question_usable": True,
        }],
    }
    plot = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="combined-plot.json",
        content=json.dumps(plot_payload, ensure_ascii=False).encode("utf-8"),
        material_type="plot_summary",
    )
    parse_material_document(plot["id"])

    with SessionLocal() as db:
        assert resolve_source_mode(
            db,
            book["id"],
            QuizGenerateRequest(single_count=1, multiple_count=0, short_count=0),
        ) == "combined"

    generated = client.post(
        f"/api/books/{book['id']}/quizzes",
        json={"single_count": 1, "multiple_count": 0, "short_count": 0},
    )
    assert generated.status_code == 202
    assert generated.json()["source_mode"] == "combined"


def test_topic_generation_validates_material_count_and_character(client, monkeypatch):
    book = create_resource(client, "潜伏专题范围校验")
    material = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="single-quote.csv",
        content="台词,角色\n会议现在开始,吴站长\n".encode("utf-8"),
        material_type="quote_sheet",
    )
    parse_material_document(material["id"])
    base = {
        "duration_minutes": 15,
        "difficulty": "medium",
        "single_count": 2,
        "multiple_count": 0,
        "short_count": 0,
        "generation_theme": "classic_quotes",
        "theme_config": {
            "material_ids": [material["id"]],
            "question_subtypes": ["quote_speaker"],
        },
    }
    insufficient = client.post(f"/api/books/{book['id']}/quizzes", json=base)
    assert insufficient.status_code == 409
    assert "只有 1 条" in insufficient.json()["detail"]

    character_payload = {
        **base,
        "single_count": 1,
        "generation_theme": "character",
        "theme_config": {
            "material_ids": [material["id"]],
            "character_names": ["不存在的角色"],
            "question_subtypes": ["quote_speaker"],
        },
    }
    missing_character = client.post(
        f"/api/books/{book['id']}/quizzes", json=character_payload
    )
    assert missing_character.status_code == 409
    assert "只有 0 条" in missing_character.json()["detail"]


def test_plot_summary_json_is_parsed_managed_and_used_as_source(client, monkeypatch):
    book = create_resource(client, "潜伏剧情梗概导入")
    payload = {
        "schema_version": "plot_summary.v1",
        "source_registry": [{"source_id": "src-001", "title": "百科资料", "url": "https://example.com"}],
        "character_profiles": [{"character_id": "char-001", "name": "余则成", "fate": "继续潜伏", "source_refs": ["src-001"]}],
        "relationship_arcs": [{"relationship_id": "rel-001", "characters": ["余则成", "翠平"], "ending_state": "共同执行任务", "source_refs": ["src-001"]}],
        "quote_candidates": [{"quote_id": "quote-001", "speaker": "吴站长", "quote_text": "会议开始", "exact_quote_verified": False}],
        "events": [
            {
                "event_id": "s01e01-event-001",
                "level": "event",
                "season_number": 1,
                "episode_number": 1,
                "sequence": 1,
                "title": "任务安排",
                "summary": "组织为任务安排身份掩护。",
                "cause": "任务需要新的身份安排。",
                "action": "相关人物接受并执行身份掩护安排。",
                "result": "人物进入新的行动阶段。",
                "future_impact": "为后续合作和冲突埋下基础。",
                "characters": ["余则成", "翠平"],
                "source_refs": ["src-001"],
                "confidence": "confirmed",
                "question_usable": True,
            }
        ],
    }
    material = upload_without_background_parse(
        client,
        monkeypatch,
        book["id"],
        name="潜伏剧情梗概.json",
        content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        material_type="plot_summary",
    )
    parse_material_document(material["id"])

    events = client.get(f"/api/books/{book['id']}/plot-events?material_id={material['id']}")
    assert events.status_code == 200
    assert events.json()["total"] == 1
    assert events.json()["items"][0]["title"] == "任务安排"
    assert events.json()["items"][0]["enabled_for_generation"] is True
    with SessionLocal() as db:
        stored = db.query(PlotEvent).filter(PlotEvent.material_id == material["id"]).one()
        assert stored.source_refs == ["src-001"]
        stored_material = db.get(ResourceMaterial, material["id"])
        assert stored_material.structured_content["character_profiles"][0]["name"] == "余则成"
        assert stored_material.structured_content["relationship_arcs"]
        assert stored_material.structured_content["quote_candidates"]
        assert resolve_source_mode(
            db,
            book["id"],
            QuizGenerateRequest(single_count=1, multiple_count=0, short_count=0),
        ) == "plot"

    generated = client.post(
        f"/api/books/{book['id']}/quizzes",
        json={"single_count": 1, "multiple_count": 0, "short_count": 0},
    )
    assert generated.status_code == 202
    task_id = generated.json()["id"]
    for _ in range(500):
        task_response = client.get(f"/api/quiz-generation-tasks/{task_id}")
        assert task_response.status_code == 200
        task = task_response.json()
        if task["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert task["status"] == "completed", task.get("error_message")
    assert task["source_mode"] == "plot"
    quiz = client.get(f"/api/quizzes/{task['quiz_id']}")
    assert quiz.status_code == 200
    assert quiz.json()["questions"][0]["plot_event_ids"]
