from __future__ import annotations

import time

from app.database import SessionLocal
from app.models import Question, Quiz
from app.services.quiz_quality_review import normalize_quality_review


def create_quiz(client) -> dict:
    response = client.post(
        "/api/books",
        json={
            "title": "审查测试书",
            "author": "作者",
            "description": "用于测试试卷审查",
            "resource_type": "book",
            "cover_color": "#2F6B5F",
            "language": "中文",
            "reading_status": "finished",
            "tags": [],
        },
    )
    assert response.status_code == 201
    book = response.json()
    with SessionLocal() as db:
        quiz = Quiz(
            book_id=book["id"],
            title="审查测试试卷",
            difficulty="medium",
            duration_minutes=15,
            source_mode="pdf",
            max_score=6,
        )
        db.add(quiz)
        db.flush()
        db.add(
            Question(
                quiz_id=quiz.id,
                position=1,
                question_type="single",
                question_subtype="general",
                prompt="人物采取了什么行动？",
                options=[
                    {"id": "A", "text": "采取行动"},
                    {"id": "B", "text": "没有行动"},
                ],
                correct_answers=["A"],
                explanation="来源明确描述了该行动。",
                knowledge_point="人物行动",
                difficulty="medium",
                estimated_seconds=45,
                source_chunk_ids=["chunk-1"],
                source_evidence=[{"chunk_id": "chunk-1", "excerpt": "人物采取行动。"}],
                max_score=6,
                source_mode="pdf",
            )
        )
        db.commit()
        quiz_id = quiz.id
    return {"book_id": book["id"], "quiz_id": quiz_id}


def test_normalize_quality_review_turns_pass_with_issues_into_revision():
    result = normalize_quality_review(
        {
            "overall_verdict": "pass",
            "summary": "发现一处问题",
            "issues": [
                {
                    "question_position": 1,
                    "severity": "medium",
                    "category": "wording",
                    "problem": "题干略有歧义",
                    "suggestion": "补充限定条件",
                }
            ],
        },
        1,
    )

    assert result["overall_verdict"] == "needs_revision"
    assert result["issues"][0]["category"] == "wording"
    assert result["reviewed_question_count"] == 1


def test_quality_review_task_completes_in_mock_mode(client):
    ids = create_quiz(client)
    response = client.post(f"/api/quizzes/{ids['quiz_id']}/quality-review")
    assert response.status_code == 202
    assert response.json()["status"] in {"pending", "processing", "completed"}

    for _ in range(100):
        result = client.get(f"/api/quizzes/{ids['quiz_id']}/quality-review")
        assert result.status_code == 200
        payload = result.json()
        if payload["status"] == "completed":
            assert payload["result"]["schema_version"] == "quiz_quality_review.v1"
            assert payload["result"]["reviewed_question_count"] == 1
            break
        assert payload["status"] in {"pending", "processing"}
        time.sleep(0.01)
    else:
        raise AssertionError("模型审查任务在测试等待时间内没有完成")


def test_quality_review_is_not_started_twice_while_running(client, monkeypatch):
    ids = create_quiz(client)
    monkeypatch.setattr(
        "app.routers.quizzes.run_quiz_quality_review",
        lambda *_: time.sleep(0.2),
    )
    first = client.post(f"/api/quizzes/{ids['quiz_id']}/quality-review")
    assert first.status_code == 202
    second = client.post(f"/api/quizzes/{ids['quiz_id']}/quality-review")
    assert second.status_code == 409
