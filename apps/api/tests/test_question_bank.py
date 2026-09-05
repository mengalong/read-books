from __future__ import annotations

import time

from app.database import SessionLocal
from app.models import ContentChunk, PdfDocument, Question, Quiz, QuestionBankEntry


def create_book(client) -> dict:
    response = client.post(
        "/api/books",
        json={
            "title": "题库测试书",
            "author": "作者",
            "description": "题库测试",
            "resource_type": "book",
            "cover_color": "#2F6B5F",
            "language": "中文",
            "reading_status": "finished",
            "tags": [],
        },
    )
    assert response.status_code == 201
    return response.json()


def create_source_and_quiz(book_id: str) -> tuple[str, str]:
    with SessionLocal() as db:
        pdf = PdfDocument(
            book_id=book_id,
            file_name="source.pdf",
            file_path="demo://source",
            file_size=1,
            page_count=1,
            chunk_count=1,
            parse_status="completed",
        )
        db.add(pdf)
        db.flush()
        chunk = ContentChunk(
            book_id=book_id,
            pdf_id=pdf.id,
            page_number=1,
            sequence=1,
            content="人物接受任务并进入新的行动阶段。",
            char_count=16,
        )
        db.add(chunk)
        db.flush()
        quiz = Quiz(book_id=book_id, title="原始试卷", source_mode="pdf", max_score=6)
        db.add(quiz)
        db.flush()
        question = Question(
            quiz_id=quiz.id,
            position=1,
            question_type="single",
            question_subtype="general",
            prompt="人物接受任务后进入了什么阶段？",
            options=[
                {"id": "A", "text": "新的行动阶段"},
                {"id": "B", "text": "休息阶段"},
                {"id": "C", "text": "回忆阶段"},
                {"id": "D", "text": "没有变化"},
            ],
            correct_answers=["A"],
            explanation="原文明确描述了新的行动阶段。",
            knowledge_point="人物行动",
            difficulty="medium",
            estimated_seconds=45,
            source_chunk_ids=[chunk.id],
            source_evidence=[{"chunk_id": chunk.id, "file_name": "source.pdf", "page_number": 1, "excerpt": chunk.content, "support": "原文"}],
            fact_key="人物|进入|新的行动阶段",
            fact_claim="人物接受任务后进入新的行动阶段",
            semantic_signature={"fact_claim": "人物接受任务后进入新的行动阶段"},
            source_mode="pdf",
            max_score=6,
        )
        db.add(question)
        db.commit()
        return quiz.id, question.id


def wait_generation(client, task_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/quiz-generation-tasks/{task_id}")
        assert response.status_code == 200
        task = response.json()
        if task["status"] == "completed":
            return task
        if task["status"] == "failed":
            raise AssertionError(task["error_message"])
        time.sleep(0.01)
    raise AssertionError("题库复用出题任务未完成")


def test_promote_edit_list_and_track_usage(client):
    book = create_book(client)
    quiz_id, question_id = create_source_and_quiz(book["id"])
    promoted = client.post(f"/api/quizzes/{quiz_id}/questions/{question_id}/question-bank")
    assert promoted.status_code == 201
    entry = promoted.json()
    assert entry["use_count"] == 1
    assert entry["usages"][0]["quiz_title"] == "原始试卷"

    listing = client.get(f"/api/books/{book['id']}/question-bank?unused_only=true")
    assert listing.status_code == 200
    assert listing.json()["total"] == 0

    updated = client.patch(
        f"/api/books/{book['id']}/question-bank/{entry['id']}",
        json={"prompt": "修改后的题干", "knowledge_point": "修改后的知识点"},
    )
    assert updated.status_code == 200
    assert updated.json()["prompt"] == "修改后的题干"
    assert updated.json()["knowledge_point"] == "修改后的知识点"

    deleted = client.delete(f"/api/quizzes/{quiz_id}")
    assert deleted.status_code == 204
    remaining = client.get(f"/api/books/{book['id']}/question-bank").json()["items"][0]
    assert remaining["usages"][0]["quiz_id"] is None
    assert remaining["usages"][0]["quiz_title"] == "原始试卷"


def test_generation_prefers_a_bank_question_and_records_new_usage(client):
    book = create_book(client)
    quiz_id, question_id = create_source_and_quiz(book["id"])
    promoted = client.post(f"/api/quizzes/{quiz_id}/questions/{question_id}/question-bank").json()

    generated = client.post(
        f"/api/books/{book['id']}/quizzes",
        json={"single_count": 1, "multiple_count": 0, "short_count": 0, "use_question_bank": True},
    )
    assert generated.status_code == 202
    task = wait_generation(client, generated.json()["id"])
    with SessionLocal() as db:
        entry = db.get(QuestionBankEntry, promoted["id"])
        assert entry is not None
        assert entry.use_count == 2
        assert len(entry.usages) == 2
        question = db.query(Question).filter(Question.quiz_id == task["quiz_id"]).one()
        assert question.question_bank_entry_id == entry.id
