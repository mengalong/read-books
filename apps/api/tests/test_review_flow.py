from pathlib import Path

import fitz
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Book, ContentChunk, PdfDocument, Question
from app.services.pdf_parser import parse_pdf_document


def create_source_book(client, title: str = "测试书籍") -> tuple[str, str]:
    response = client.post(
        "/api/books",
        json={
            "title": title,
            "author": "测试作者",
            "description": "一段用于接口测试的书籍内容。",
            "reading_status": "finished",
            "tags": ["测试"],
        },
    )
    assert response.status_code == 201
    book_id = response.json()["id"]

    with SessionLocal() as db:
        pdf = PdfDocument(
            book_id=book_id,
            file_name="测试材料.pdf",
            file_path="demo://test",
            file_size=1024,
            page_count=10,
            chunk_count=10,
            parse_status="completed",
        )
        db.add(pdf)
        db.flush()
        for index in range(10):
            content = (
                f"第{index + 1}部分说明主动回忆需要从记忆中提取内容。"
                f"间隔练习会根据掌握程度调整第{index + 1}次复习的时间。"
            )
            db.add(
                ContentChunk(
                    book_id=book_id,
                    pdf_id=pdf.id,
                    page_number=index + 1,
                    sequence=index + 1,
                    content=content,
                    char_count=len(content),
                )
            )
        db.commit()
        return book_id, pdf.id


def test_health_and_book_crud(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["mock_mode"] is True

    book_id, _ = create_source_book(client, "接口测试书")
    detail = client.get(f"/api/books/{book_id}")
    assert detail.status_code == 200
    assert detail.json()["stats"]["chunk_count"] == 10

    updated = client.patch(f"/api/books/{book_id}", json={"reading_status": "reviewing"})
    assert updated.status_code == 200
    assert updated.json()["reading_status"] == "reviewing"


def test_generate_submit_and_avoid_recent_sources(client):
    book_id, _ = create_source_book(client, "复习流程测试书")
    payload = {
        "duration_minutes": 15,
        "difficulty": "medium",
        "single_count": 2,
        "multiple_count": 1,
        "short_count": 1,
    }
    generated = client.post(f"/api/books/{book_id}/quizzes", json=payload)
    assert generated.status_code == 201
    quiz = generated.json()
    assert len(quiz["questions"]) == 4
    assert all(question["source_evidence"] for question in quiz["questions"])
    assert all(question["correct_answers"] is None for question in quiz["questions"])

    first_sources = {
        evidence["chunk_id"]
        for question in quiz["questions"]
        for evidence in question["source_evidence"]
    }
    with SessionLocal() as db:
        questions = db.scalars(
            select(Question).where(Question.quiz_id == quiz["id"]).order_by(Question.position)
        ).all()
        answers = [
            {
                "question_id": question.id,
                "selected_answers": question.correct_answers,
                "text_answer": question.reference_answer if question.question_type == "short" else None,
            }
            for question in questions
        ]

    submitted = client.post(
        f"/api/quizzes/{quiz['id']}/submit",
        json={"elapsed_seconds": 420, "answers": answers},
    )
    assert submitted.status_code == 200
    result = submitted.json()
    assert result["status"] == "submitted"
    assert result["next_review_date"] is not None
    assert result["questions"][-1]["reference_answer"]
    assert result["questions"][-1]["grading_rubric"]

    second = client.post(f"/api/books/{book_id}/quizzes", json=payload)
    assert second.status_code == 201
    second_sources = {
        evidence["chunk_id"]
        for question in second.json()["questions"]
        for evidence in question["source_evidence"]
    }
    assert first_sources.isdisjoint(second_sources)

    history = client.get(f"/api/books/{book_id}/history")
    assert history.status_code == 200
    assert len(history.json()) == 2


def test_pdf_parser_keeps_page_numbers(client, tmp_path: Path):
    response = client.post(
        "/api/books",
        json={"title": "PDF 解析测试", "author": "测试作者"},
    )
    book_id = response.json()["id"]
    file_path = tmp_path / "sample.pdf"
    document = fitz.open()
    for page_number in range(1, 3):
        page = document.new_page()
        page.insert_text((72, 72), (f"Page {page_number} source material. " * 20))
    document.save(file_path)
    document.close()

    with SessionLocal() as db:
        pdf = PdfDocument(
            book_id=book_id,
            file_name=file_path.name,
            file_path=str(file_path),
            file_size=file_path.stat().st_size,
            parse_status="pending",
        )
        db.add(pdf)
        db.commit()
        pdf_id = pdf.id

    parse_pdf_document(pdf_id)
    with SessionLocal() as db:
        parsed_pdf = db.get(PdfDocument, pdf_id)
        chunks = db.scalars(
            select(ContentChunk)
            .where(ContentChunk.pdf_id == pdf_id)
            .order_by(ContentChunk.page_number)
        ).all()
        assert parsed_pdf is not None
        assert parsed_pdf.parse_status == "completed"
        assert parsed_pdf.page_count == 2
        assert {chunk.page_number for chunk in chunks} == {1, 2}


def test_pdf_parser_uses_ocr_for_unreadable_text(client, tmp_path: Path, monkeypatch):
    response = client.post(
        "/api/books",
        json={"title": "PDF OCR 测试", "author": "测试作者"},
    )
    book_id = response.json()["id"]
    file_path = tmp_path / "unreadable.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "cid text")
    document.save(file_path)
    document.close()

    with SessionLocal() as db:
        pdf = PdfDocument(
            book_id=book_id,
            file_name=file_path.name,
            file_path=str(file_path),
            file_size=file_path.stat().st_size,
            parse_status="pending",
        )
        db.add(pdf)
        db.commit()
        pdf_id = pdf.id

    ocr_text = "红楼梦中的人物关系和情节发展构成了这段可用于复习测试的中文原文。"
    ocr_calls: list[str] = []

    def fake_extract_with_ocr(source_path: str) -> list[tuple[int, str]]:
        ocr_calls.append(source_path)
        return [(1, ocr_text)]

    monkeypatch.setattr(
        "app.services.pdf_parser.extract_with_ocr",
        fake_extract_with_ocr,
    )
    parse_pdf_document(pdf_id)

    with SessionLocal() as db:
        parsed_pdf = db.get(PdfDocument, pdf_id)
        chunks = db.scalars(
            select(ContentChunk).where(ContentChunk.pdf_id == pdf_id)
        ).all()
        assert parsed_pdf is not None
        assert parsed_pdf.parse_status == "completed"
        assert ocr_calls == [str(file_path)]
        assert [chunk.content for chunk in chunks] == [ocr_text]
