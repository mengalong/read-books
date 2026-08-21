import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import (
    Book,
    ContentChunk,
    ExamAnswer,
    ExamAttempt,
    ExamShare,
    PdfDocument,
    Question,
    Quiz,
)
from app.services.auth import create_user_with_workspace
from app.services.quiz_provider import GeneratedQuestion, MockQuizAiProvider


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


def create_shareable_multiple_quiz(client, title: str = "考试多选评分测试书") -> tuple[str, str]:
    book_response = client.post(
        "/api/books",
        json={
            "title": title,
            "author": "测试作者",
            "description": "用于验证多选评分流程。",
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
        db.add(
            Question(
                quiz_id=quiz.id,
                position=1,
                question_type="multiple",
                prompt="以下哪些做法更能帮助记忆？",
                options=[
                    {"id": "A", "text": "主动回忆"},
                    {"id": "B", "text": "间隔重复"},
                    {"id": "C", "text": "只看目录"},
                    {"id": "D", "text": "泛读不回想"},
                ],
                correct_answers=["A", "B"],
                explanation="主动回忆和间隔重复都能帮助记忆。",
                knowledge_point="记忆策略",
                difficulty="medium",
                estimated_seconds=90,
                reference_answer=None,
                grading_rubric=[],
                source_chunk_ids=["chunk-1"],
                source_evidence=[
                    {
                        "chunk_id": "chunk-1",
                        "file_name": "测试书.pdf",
                        "page_number": 8,
                        "excerpt": "主动回忆和间隔重复都能帮助记忆。",
                        "highlight": "主动回忆和间隔重复都能帮助记忆。",
                        "support": "用于验证多选评分。",
                    }
                ],
                max_score=40,
            )
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


def test_exam_share_edit_keeps_started_attempts_on_old_snapshot_and_deletes_history(client):
    _, quiz_id = create_shareable_quiz(client, "考试版本隔离测试书")
    share = create_exam_share(client, quiz_id, "版本隔离考试")

    with TestClient(app) as public_client:
        started = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "旧版读者"},
        )
        assert started.status_code == 201
        started_body = started.json()
        attempt_id = started_body["id"]
        access_token = started_body["access_token"]
        question_id = started_body["questions"][0]["id"]
        assert started_body["questions"][0]["prompt"] == "书中提出的核心做法是什么？"

        updated = client.patch(
            f"/api/exam-shares/{share['id']}/questions/{question_id}",
            json={
                "prompt": "新的核心做法是什么？",
                "correct_answers": ["B"],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["prompt"] == "新的核心做法是什么？"

        editable = client.get(f"/api/exam-shares/{share['id']}/editable")
        assert editable.status_code == 200
        editable_body = editable.json()
        assert editable_body["snapshot_version"] == 2
        assert [item["version"] for item in editable_body["versions"]] == [2, 1]
        assert editable_body["versions"][0]["is_current"] is True

        existing_attempt = public_client.get(
            f"/api/public/exam-attempts/{attempt_id}",
            headers={"X-Exam-Attempt-Token": access_token},
        )
        assert existing_attempt.status_code == 200
        assert existing_attempt.json()["questions"][0]["prompt"] == "书中提出的核心做法是什么？"

        old_submission = public_client.post(
            f"/api/public/exam-attempts/{attempt_id}/submit",
            json={
                "answers": [
                    {
                        "question_id": question_id,
                        "selected_answers": ["A"],
                    }
                ],
                "elapsed_seconds": 12,
            },
            headers={"X-Exam-Attempt-Token": access_token},
        )
        assert old_submission.status_code == 202
        assert old_submission.json()["total_score"] == 40

        fresh = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "新版本读者"},
        )
        assert fresh.status_code == 201
        fresh_body = fresh.json()
        assert fresh_body["questions"][0]["prompt"] == "新的核心做法是什么？"
        fresh_submission = public_client.post(
            f"/api/public/exam-attempts/{fresh_body['id']}/submit",
            json={
                "answers": [
                    {
                        "question_id": question_id,
                        "selected_answers": ["B"],
                    }
                ],
                "elapsed_seconds": 12,
            },
            headers={"X-Exam-Attempt-Token": fresh_body["access_token"]},
        )
        assert fresh_submission.status_code == 202
        assert fresh_submission.json()["total_score"] == 40

    deleted_history = client.delete(f"/api/exam-shares/{share['id']}/versions/1")
    assert deleted_history.status_code == 204
    after_delete = client.get(f"/api/exam-shares/{share['id']}/editable")
    assert after_delete.status_code == 200
    assert [item["version"] for item in after_delete.json()["versions"]] == [2]
    blocked_delete = client.delete(f"/api/exam-shares/{share['id']}/versions/2")
    assert blocked_delete.status_code == 409


def test_exam_share_question_regeneration_creates_new_version(client, monkeypatch):
    book_id, quiz_id = create_shareable_quiz(client, "考试重出测试书")
    with SessionLocal() as db:
        pdf = PdfDocument(
            book_id=book_id,
            file_name="考试原文.pdf",
            file_path="demo://exam-regeneration",
            file_size=2048,
            page_count=3,
            chunk_count=3,
            parse_status="completed",
        )
        db.add(pdf)
        db.flush()
        db.add_all(
            [
                ContentChunk(
                    id="exam-chunk-1",
                    book_id=book_id,
                    pdf_id=pdf.id,
                    page_number=1,
                    sequence=1,
                    content="第 1 页原文，主动回忆可以帮助检验掌握程度。",
                    char_count=26,
                ),
                ContentChunk(
                    id="exam-chunk-2",
                    book_id=book_id,
                    pdf_id=pdf.id,
                    page_number=2,
                    sequence=1,
                    content="第 2 页原文，间隔重复有助于巩固记忆。",
                    char_count=24,
                ),
                ContentChunk(
                    id="exam-chunk-3",
                    book_id=book_id,
                    pdf_id=pdf.id,
                    page_number=3,
                    sequence=1,
                    content="第 3 页原文，理解核心概念比死记硬背更重要。",
                    char_count=24,
                ),
            ]
        )
        db.commit()

    share = create_exam_share(client, quiz_id, "考试重出考试")
    editable_before = client.get(f"/api/exam-shares/{share['id']}/editable")
    assert editable_before.status_code == 200
    question_id = editable_before.json()["questions"][0]["id"]

    def fake_generate(self, **kwargs):
        assert kwargs["resource_type"] == "book"
        assert kwargs["source_mode"] == "pdf"
        assert kwargs["question_exclusions"][0]["role"] == "current_question"
        return [
            GeneratedQuestion(
                question_type="single",
                prompt="重出的考试题",
                options=[
                    {"id": "A", "text": "新选项 A"},
                    {"id": "B", "text": "新选项 B"},
                    {"id": "C", "text": "新选项 C"},
                    {"id": "D", "text": "新选项 D"},
                ],
                correct_answers=["C"],
                explanation="重出后的解析",
                knowledge_point="重出后的知识点",
                estimated_seconds=45,
                reference_answer=None,
                grading_rubric=[],
                source_chunk_ids=["exam-chunk-2"],
                source_evidence=[],
                max_score=40,
            )
        ]

    monkeypatch.setattr(MockQuizAiProvider, "generate_questions", fake_generate)

    regenerated = client.post(
        f"/api/exam-shares/{share['id']}/questions/{question_id}/regenerate",
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["prompt"] == "重出的考试题"
    assert regenerated.json()["correct_answers"] == ["C"]

    editable_after = client.get(f"/api/exam-shares/{share['id']}/editable")
    assert editable_after.status_code == 200
    body = editable_after.json()
    assert body["snapshot_version"] == 2
    assert [item["version"] for item in body["versions"]] == [2, 1]
    assert body["versions"][0]["is_current"] is True

    with TestClient(app) as public_client:
        started = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "重出后读者"},
        )
        assert started.status_code == 201
        assert started.json()["questions"][0]["prompt"] == "重出的考试题"

def test_exam_share_name_rejects_blank_values(client):
    _, quiz_id = create_shareable_quiz(client, "活动名称校验测试书")

    blank_create = client.post(
        f"/api/quizzes/{quiz_id}/exam-shares",
        json={"name": "   "},
    )
    assert blank_create.status_code == 422

    share = create_exam_share(client, quiz_id)
    blank_update = client.patch(
        f"/api/exam-shares/{share['id']}",
        json={"name": "\t\n"},
    )
    assert blank_update.status_code == 422
    null_update = client.patch(
        f"/api/exam-shares/{share['id']}",
        json={"name": None},
    )
    assert null_update.status_code == 422

    invalid_range = client.get(
        "/api/exam-shares?created_from=2026-08-07&created_to=2026-08-06"
    )
    assert invalid_range.status_code == 422


def test_exam_expiration_blocks_answering_but_keeps_completed_history(client):
    _, quiz_id = create_shareable_quiz(client, "考试有效期测试书")
    future = datetime.now(timezone.utc) + timedelta(days=2)
    created = client.post(
        f"/api/quizzes/{quiz_id}/exam-shares",
        json={"name": "限时考试", "expires_at": future.isoformat()},
    )
    assert created.status_code == 201
    share = created.json()
    assert share["expires_at"] is not None

    past_update = client.patch(
        f"/api/exam-shares/{share['id']}",
        json={"expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()},
    )
    assert past_update.status_code == 422

    with TestClient(app) as public_client:
        in_progress = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "未交卷读者"},
        ).json()
        completed = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "已交卷读者"},
        ).json()
        completed_headers = {"X-Exam-Attempt-Token": completed["access_token"]}
        submitted = public_client.post(
            f"/api/public/exam-attempts/{completed['id']}/submit",
            json={"answers": [], "elapsed_seconds": 18},
            headers=completed_headers,
        )
        assert submitted.status_code == 202

        with SessionLocal() as db:
            db_share = db.get(ExamShare, share["id"])
            db_share.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()

        intro = public_client.get(
            f"/api/public/exams/{share['share_code']}",
            headers=completed_headers,
        )
        assert intro.status_code == 200
        assert intro.json()["status"] == "expired"
        assert intro.json()["existing_attempt_id"] == completed["id"]
        assert intro.json()["existing_attempt_status"] == "completed"

        late_start = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "迟到读者"},
        )
        assert late_start.status_code == 409
        assert late_start.json()["detail"] == "你来晚了，考试已经结束"

        in_progress_headers = {"X-Exam-Attempt-Token": in_progress["access_token"]}
        blocked_attempt = public_client.get(
            f"/api/public/exam-attempts/{in_progress['id']}",
            headers=in_progress_headers,
        )
        assert blocked_attempt.status_code == 409
        assert blocked_attempt.json()["detail"] == "你来晚了，考试已经结束"

        history = public_client.get(
            f"/api/public/exam-attempts/{completed['id']}/result",
            headers=completed_headers,
        )
        assert history.status_code == 200
        assert history.json()["participant_name"] == "已交卷读者"

    cleared = client.patch(
        f"/api/exam-shares/{share['id']}",
        json={"expires_at": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["expires_at"] is None


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
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148",
                "X-Forwarded-For": "203.0.113.10, 127.0.0.1",
            },
        )
        assert started.status_code == 201
        attempt = started.json()
        token = attempt["access_token"]
        assert token
        assert all(question["correct_answers"] is None for question in attempt["questions"])
        assert all(question["source_evidence"] == [] for question in attempt["questions"])
        assert attempt["device_type"] is None
        assert attempt["started_ip_address"] is None

        denied = public_client.get(f"/api/public/exam-attempts/{attempt['id']}")
        assert denied.status_code == 404

        headers = {
            "X-Exam-Attempt-Token": token,
            "X-Forwarded-For": "203.0.113.11, 127.0.0.1",
        }
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
        assert [
            item["knowledge_point"] for item in result_body["weak_knowledge_points"]
        ] == ["遗忘检测", "主动回忆"]
        assert result_body["weak_knowledge_points"][0]["focus_points"] == [
            "能够暴露遗忘点",
            "能够加强记忆",
        ]
        assert "遗忘检测" in result_body["recommended_direction"]
        assert result_body["submitted_ip_address"] is None

    detail = client.get(f"/api/exam-shares/{share['id']}")
    assert detail.status_code == 200
    assert detail.json()["started_count"] == 1
    assert detail.json()["submitted_count"] == 1
    summary = detail.json()["attempts"][0]
    assert summary["device_type"] == "mobile"
    assert summary["started_ip_address"] == "203.0.113.10"
    assert summary["submitted_ip_address"] == "203.0.113.11"
    assert summary["ip_changed"] is True
    manager_attempt = client.get(
        f"/api/exam-shares/{share['id']}/attempts/{attempt['id']}"
    )
    assert manager_attempt.status_code == 200
    assert manager_attempt.json()["questions"][0]["source_evidence"][0]["page_number"] == 8
    assert manager_attempt.json()["device_type"] == "mobile"
    assert manager_attempt.json()["started_ip_address"] == "203.0.113.10"
    assert manager_attempt.json()["submitted_ip_address"] == "203.0.113.11"
    assert manager_attempt.json()["ip_changed"] is True
    assert "iPhone" in manager_attempt.json()["user_agent"]


def test_public_exam_multiple_choice_scores_zero_on_wrong_selection_and_partial_on_missing_selection(client):
    _, quiz_id = create_shareable_multiple_quiz(client, "公开多选评分测试书")
    share = create_exam_share(client, quiz_id)

    with TestClient(app) as public_client:
        started = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "多选读者"},
        )
        assert started.status_code == 201
        attempt = started.json()

        with SessionLocal() as db:
            question = db.scalars(
                select(Question).where(Question.quiz_id == quiz_id).order_by(Question.position)
            ).one()
            correct_answers = list(question.correct_answers)
            assert len(correct_answers) >= 2
            wrong_answer = next(
                option["id"]
                for option in question.options
                if option["id"] not in correct_answers
            )
            max_score = question.max_score

        partial = public_client.post(
            f"/api/public/exam-attempts/{attempt['id']}/submit",
            json={
                "answers": [
                    {
                        "question_id": question.id,
                        "selected_answers": correct_answers[:-1],
                    }
                ],
                "elapsed_seconds": 12,
            },
            headers={"X-Exam-Attempt-Token": attempt["access_token"]},
        )
        assert partial.status_code == 202
        partial_body = partial.json()
        expected_partial_score = round(max_score * (len(correct_answers) - 1) / len(correct_answers), 1)
        assert partial_body["status"] == "completed"
        assert partial_body["total_score"] == pytest.approx(expected_partial_score)

        second = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "错选读者"},
        )
        assert second.status_code == 201
        second_attempt = second.json()
        wrong = public_client.post(
            f"/api/public/exam-attempts/{second_attempt['id']}/submit",
            json={
                "answers": [
                    {
                        "question_id": question.id,
                        "selected_answers": [correct_answers[0], wrong_answer],
                    }
                ],
                "elapsed_seconds": 12,
            },
            headers={"X-Exam-Attempt-Token": second_attempt["access_token"]},
        )
        assert wrong.status_code == 202
        assert wrong.json()["status"] == "completed"
        assert wrong.json()["total_score"] == 0


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
    assert result["weak_knowledge_points"] == []
    assert "未发现得分率低于 60%" in result["recommended_direction"]


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


def test_admin_can_retry_failed_exam_grading(client, monkeypatch):
    _, quiz_id = create_shareable_quiz(client, "管理员重试评分测试书")
    share = create_exam_share(client, quiz_id, "管理员重试评分考试")
    started = client.post(
        f"/api/public/exams/{share['share_code']}/attempts",
        json={},
    )
    assert started.status_code == 201
    attempt_id = started.json()["id"]
    short_question_id = next(
        question["id"]
        for question in started.json()["questions"]
        if question["question_type"] == "short"
    )
    submitted = client.post(
        f"/api/public/exam-attempts/{attempt_id}/submit",
        json={"answers": [], "elapsed_seconds": 30},
    )
    assert submitted.status_code == 202

    with SessionLocal() as db:
        attempt = db.get(ExamAttempt, attempt_id)
        answer = db.query(ExamAnswer).filter_by(
            exam_attempt_id=attempt_id,
            snapshot_question_id=short_question_id,
        ).one()
        attempt.status = "grading_failed"
        attempt.grading_error = "测试评分失败"
        answer.grading_status = "failed"
        answer.feedback = "等待重新评分。"
        db.commit()

    monkeypatch.setattr(
        "app.services.exam_sharing.launch_exam_grading",
        lambda _: None,
    )
    retried = client.post(
        f"/api/admin/exam-shares/{share['id']}/attempts/{attempt_id}/retry-grading"
    )
    assert retried.status_code == 202
    assert retried.json()["status"] == "grading"
    assert retried.json()["grading_error"] is None
    assert next(
        answer
        for answer in retried.json()["answers"]
        if answer["question_id"] == short_question_id
    )["grading_status"] == "pending"
