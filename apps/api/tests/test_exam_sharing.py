import time

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Book, Question, Quiz
from app.services.auth import create_user_with_workspace


def create_shareable_quiz(client, title: str = "考试分享测试书") -> tuple[str, str]:
    book_response = client.post(
        "/api/books",
        json={
            "title": title,
            "author": "测试作者",
            "description": "用于验证考试分享流程。",
            "cover_color": "#2F6B5F",
            "language": "中文",
            "reading_status": "finished",
            "tags": [],
        },
    )
    assert book_response.status_code == 201
    book_id = book_response.json()["id"]
    with SessionLocal() as db:
        quiz = Quiz(
            book_id=book_id,
            title="第 1 套复习试卷",
            difficulty="medium",
            duration_minutes=15,
            status="ready",
            source_mode="pdf",
            max_score=100,
        )
        db.add(quiz)
        db.flush()
        db.add_all(
            [
                Question(
                    quiz_id=quiz.id,
                    position=1,
                    question_type="single",
                    prompt="书中提出的核心做法是什么？",
                    options=[
                        {"id": "A", "text": "主动回忆"},
                        {"id": "B", "text": "只看摘要"},
                    ],
                    correct_answers=["A"],
                    explanation="原文强调主动回忆。",
                    knowledge_point="主动回忆",
                    difficulty="medium",
                    estimated_seconds=45,
                    reference_answer=None,
                    grading_rubric=[],
                    source_chunk_ids=["chunk-1"],
                    source_evidence=[
                        {
                            "chunk_id": "chunk-1",
                            "file_name": "测试书.pdf",
                            "page_number": 8,
                            "excerpt": "主动回忆比重复阅读更能检验掌握程度。",
                            "highlight": "主动回忆比重复阅读更能检验掌握程度。",
                            "support": "直接支持正确答案。",
                        }
                    ],
                    max_score=40,
                ),
                Question(
                    quiz_id=quiz.id,
                    position=2,
                    question_type="short",
                    prompt="为什么需要主动回忆？",
                    options=[],
                    correct_answers=[],
                    explanation="主动回忆能够暴露遗忘点。",
                    knowledge_point="遗忘检测",
                    difficulty="medium",
                    estimated_seconds=180,
                    reference_answer="主动回忆能够暴露遗忘点并加强记忆。",
                    grading_rubric=[
                        {"point": "能够暴露遗忘点", "keywords": ["遗忘"], "score": 30},
                        {"point": "能够加强记忆", "keywords": ["记忆"], "score": 30},
                    ],
                    source_chunk_ids=["chunk-1"],
                    source_evidence=[
                        {
                            "chunk_id": "chunk-1",
                            "file_name": "测试书.pdf",
                            "page_number": 8,
                            "excerpt": "主动回忆可以暴露遗忘点并加强记忆。",
                            "highlight": "主动回忆可以暴露遗忘点并加强记忆。",
                            "support": "用于问答评分。",
                        }
                    ],
                    max_score=60,
                ),
            ]
        )
        db.commit()
        quiz_id = quiz.id
    return book_id, quiz_id


def create_exam_share(client, quiz_id: str, name: str = "读书复习公开考试") -> dict:
    response = client.post(
        f"/api/quizzes/{quiz_id}/exam-shares",
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()


def test_anonymous_exam_flow_hides_sources_and_answers(client):
    _, quiz_id = create_shareable_quiz(client)
    share = create_exam_share(client, quiz_id)

    with TestClient(app) as public_client:
        intro = public_client.get(f"/api/public/exams/{share['share_code']}")
        assert intro.status_code == 200
        assert intro.json()["authenticated"] is False
        assert "questions" not in intro.json()

        invalid = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "A"},
        )
        assert invalid.status_code == 422

        started = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "匿名读者"},
        )
        assert started.status_code == 201
        attempt = started.json()
        token = attempt["access_token"]
        assert token
        assert all(question["correct_answers"] is None for question in attempt["questions"])
        assert all(question["source_evidence"] == [] for question in attempt["questions"])

        denied = public_client.get(f"/api/public/exam-attempts/{attempt['id']}")
        assert denied.status_code == 404

        headers = {"X-Exam-Attempt-Token": token}
        submitted = public_client.post(
            f"/api/public/exam-attempts/{attempt['id']}/submit",
            json={"answers": [], "elapsed_seconds": 12},
            headers=headers,
        )
        assert submitted.status_code == 202
        assert submitted.json()["status"] == "completed"
        assert submitted.json()["total_score"] == 0

        result = public_client.get(
            f"/api/public/exam-attempts/{attempt['id']}/result",
            headers=headers,
        )
        assert result.status_code == 200
        result_body = result.json()
        assert result_body["questions"][0]["correct_answers"] == ["A"]
        assert result_body["questions"][0]["source_evidence"] == []
        assert result_body["questions"][1]["grading_rubric"] == []
        assert len(result_body["answers"]) == 2
        assert all(answer["score"] == 0 for answer in result_body["answers"])

    detail = client.get(f"/api/exam-shares/{share['id']}")
    assert detail.status_code == 200
    assert detail.json()["started_count"] == 1
    assert detail.json()["submitted_count"] == 1
    manager_attempt = client.get(
        f"/api/exam-shares/{share['id']}/attempts/{attempt['id']}"
    )
    assert manager_attempt.status_code == 200
    assert manager_attempt.json()["questions"][0]["source_evidence"][0]["page_number"] == 8


def test_logged_user_reuses_attempt_and_short_answer_is_graded(client):
    _, quiz_id = create_shareable_quiz(client, "登录用户考试测试书")
    share = create_exam_share(client, quiz_id, "登录用户考试")

    first = client.post(
        f"/api/public/exams/{share['share_code']}/attempts",
        json={},
    )
    second = client.post(
        f"/api/public/exams/{share['share_code']}/attempts",
        json={"participant_name": "不会采用这个名称"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["participant_type"] == "user"

    question_ids = [question["id"] for question in first.json()["questions"]]
    submitted = client.post(
        f"/api/public/exam-attempts/{first.json()['id']}/submit",
        json={
            "elapsed_seconds": 65,
            "answers": [
                {"question_id": question_ids[0], "selected_answers": ["A"]},
                {
                    "question_id": question_ids[1],
                    "selected_answers": [],
                    "text_answer": "主动回忆能够暴露遗忘点，也可以加强记忆。",
                },
            ],
        },
    )
    assert submitted.status_code == 202

    result = submitted.json()
    for _ in range(100):
        if result["status"] in {"completed", "grading_failed"}:
            break
        time.sleep(0.02)
        result = client.get(
            f"/api/public/exam-attempts/{first.json()['id']}/result"
        ).json()
    assert result["status"] == "completed"
    assert result["total_score"] > 40
    assert len(result["answers"]) == 2


def test_share_stop_source_deletion_and_workspace_permissions(client):
    _, quiz_id = create_shareable_quiz(client, "权限隔离考试测试书")
    share = create_exam_share(client, quiz_id, "权限隔离考试")
    with SessionLocal() as db:
        user, _ = create_user_with_workspace(
            db,
            username="exam-reader",
            display_name="考试读者",
            password="ExamReader1!",
            must_change_password=False,
        )
        db.commit()
        user_id = user.id

    with TestClient(app) as user_client:
        login = user_client.post(
            "/api/auth/login",
            json={"username": "exam-reader", "password": "ExamReader1!"},
        )
        assert login.status_code == 200
        assert user_client.get(f"/api/exam-shares/{share['id']}").status_code == 404
        public_start = user_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={},
        )
        assert public_start.status_code == 201
        assert public_start.json()["participant_name"] == "考试读者"

    admin_list = client.get(f"/api/admin/exam-shares?owner_id={share['owner_user_id']}")
    assert admin_list.status_code == 200
    assert any(item["id"] == share["id"] for item in admin_list.json())
    assert not any(item["owner_user_id"] == user_id for item in admin_list.json())

    stopped = client.patch(
        f"/api/exam-shares/{share['id']}",
        json={"status": "stopped"},
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    with TestClient(app) as anonymous:
        blocked = anonymous.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "新的读者"},
        )
        assert blocked.status_code == 409

    resumed = client.patch(
        f"/api/exam-shares/{share['id']}",
        json={"status": "active"},
    )
    assert resumed.status_code == 200
    deleted = client.delete(f"/api/quizzes/{quiz_id}")
    assert deleted.status_code == 204
    source_deleted = client.get(f"/api/exam-shares/{share['id']}")
    assert source_deleted.status_code == 200
    assert source_deleted.json()["status"] == "source_deleted"
    assert source_deleted.json()["quiz_id"] is None
    assert len(source_deleted.json()["attempts"]) == 1
