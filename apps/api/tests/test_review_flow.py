from pathlib import Path
import time

import fitz
import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Book,
    ContentChunk,
    ModelConfiguration,
    PdfDocument,
    Question,
    Quiz,
    QuoteEntry,
    ResourceMaterial,
    User,
    WorkspaceMember,
)
from app.services.model_usage import ModelUsageEvent, new_usage_context, record_model_usage
from app.services.pdf_parser import parse_pdf_document
from app.services.pre_generation import recover_pre_generation_tasks
from app.services.quiz_provider import GeneratedQuestion, HttpQuizAiProvider, MockQuizAiProvider


def create_source_book(
    client, title: str = "测试书籍", author: str = "测试作者"
) -> tuple[str, str]:
    response = client.post(
        "/api/books",
        json={
            "title": title,
            "author": author,
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
    raise AssertionError("出题任务在测试等待时间内没有完成")


def test_token_usage_report_groups_calls_by_task(client):
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "test-admin").one()
        workspace_id = db.query(WorkspaceMember.workspace_id).filter(
            WorkspaceMember.user_id == user.id
        ).scalar()
        user_id = user.id
    context = new_usage_context(
        "token_report_test",
        "Token 统计测试",
        user_id=user_id,
        workspace_id=workspace_id,
    )
    record_model_usage(
        ModelUsageEvent(
            context=context,
            phase="quiz_generation",
            call_number=1,
            model_name="usage-model",
            input_tokens=120,
            output_tokens=30,
            total_tokens=150,
            status="success",
            error_message=None,
            latency_ms=240,
        )
    )
    record_model_usage(
        ModelUsageEvent(
            context=context,
            phase="quiz_generation_repair",
            call_number=2,
            model_name="usage-model",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            status="failed",
            error_message="返回格式错误",
            latency_ms=180,
        )
    )

    response = client.get("/api/settings/token-usage?task_type=token_report_test")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "task_count": 1,
        "total_calls": 2,
        "successful_calls": 1,
        "failed_calls": 1,
        "unreported_calls": 1,
        "input_tokens": 120,
        "output_tokens": 30,
        "total_tokens": 150,
    }
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["status"] == "failed"
    assert body["tasks"][0]["username"] == "test-admin"
    assert body["users"][0]["user_id"] == user_id
    filtered = client.get(
        f"/api/settings/token-usage?task_type=token_report_test&user_id={user_id}"
    )
    assert filtered.status_code == 200
    assert filtered.json()["summary"]["total_tokens"] == 150
    assert [stage["phase"] for stage in body["tasks"][0]["stages"]] == [
        "quiz_generation",
        "quiz_generation_repair",
    ]


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


def test_unanswered_review_questions_score_zero(client):
    book_id, _ = create_source_book(client, "提前交卷测试书", "提前交卷专属作者")
    generated = client.post(
        f"/api/books/{book_id}/quizzes",
        json={
            "duration_minutes": 15,
            "difficulty": "medium",
            "single_count": 1,
            "multiple_count": 1,
            "short_count": 1,
        },
    )
    assert generated.status_code == 202
    task = wait_for_generation(client, generated.json()["id"])
    review = client.post(f"/api/quizzes/{task['quiz_id']}/reviews")
    assert review.status_code == 200

    submitted = client.post(
        f"/api/reviews/{review.json()['id']}/submit",
        json={"elapsed_seconds": 45, "answers": []},
    )

    assert submitted.status_code == 200
    result = submitted.json()
    assert result["status"] == "submitted"
    assert result["total_score"] == 0
    assert len(result["answers"]) == 3
    assert all(answer["score"] == 0 for answer in result["answers"])
    assert all(answer["feedback"] == "本题未作答，按 0 分处理。" for answer in result["answers"])
    with SessionLocal() as db:
        db.delete(db.get(Book, book_id))
        db.commit()


def test_book_unlist_blocks_new_activity_and_can_be_restored(client):
    book_id, _ = create_source_book(client, "上下架测试书")
    generated = client.post(
        f"/api/books/{book_id}/quizzes",
        json={
            "duration_minutes": 15,
            "difficulty": "medium",
            "single_count": 1,
            "multiple_count": 0,
            "short_count": 0,
        },
    )
    task = wait_for_generation(client, generated.json()["id"])
    quiz_id = task["quiz_id"]

    unlisted = client.post(f"/api/books/{book_id}/unlist")
    assert unlisted.status_code == 200
    assert unlisted.json()["shelf_status"] == "unlisted"
    assert book_id not in {item["id"] for item in client.get("/api/books").json()}
    assert book_id in {
        item["id"]
        for item in client.get("/api/books?shelf_status=unlisted").json()
    }

    assert client.post(
        f"/api/books/{book_id}/quizzes",
        json={
            "duration_minutes": 15,
            "difficulty": "medium",
            "single_count": 1,
            "multiple_count": 0,
            "short_count": 0,
        },
    ).status_code == 409
    assert client.post(f"/api/books/{book_id}/pre-generation").status_code == 409
    assert client.post(f"/api/quizzes/{quiz_id}/reviews").status_code == 409
    assert client.post(
        f"/api/books/{book_id}/pdfs",
        files={"file": ("blocked.pdf", b"%PDF-1.4\n", "application/pdf")},
    ).status_code == 409

    restored = client.post(f"/api/books/{book_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["shelf_status"] == "active"
    assert client.post(f"/api/quizzes/{quiz_id}/reviews").status_code == 200

    assert client.delete(f"/api/books/{book_id}").status_code == 204
    assert client.get(f"/api/books/{book_id}").status_code == 404


def test_quiz_summary_counts_question_types_and_delete_cascades_reviews(client):
    book_id, _ = create_source_book(client, "试卷管理测试书")
    generated = client.post(
        f"/api/books/{book_id}/quizzes",
        json={
            "duration_minutes": 15,
            "difficulty": "hard",
            "single_count": 1,
            "multiple_count": 1,
            "short_count": 1,
        },
    )
    assert generated.status_code == 202
    generation_task = wait_for_generation(client, generated.json()["id"])
    quiz_id = generation_task["quiz_id"]

    expected_summary = {
        "difficulty": "hard",
        "question_count": 3,
        "single_count": 1,
        "multiple_count": 1,
        "short_count": 1,
    }
    book_detail = client.get(f"/api/books/{book_id}")
    assert book_detail.status_code == 200
    assert {
        key: book_detail.json()["quizzes"][0][key] for key in expected_summary
    } == expected_summary
    quiz_list = client.get(f"/api/books/{book_id}/quizzes")
    assert quiz_list.status_code == 200
    assert {key: quiz_list.json()[0][key] for key in expected_summary} == expected_summary
    quiz_detail = client.get(f"/api/quizzes/{quiz_id}")
    assert quiz_detail.status_code == 200
    assert quiz_detail.json()["max_score"] == 100
    assert [
        question["max_score"] for question in quiz_detail.json()["questions"]
    ] == [16.7, 27.8, 55.5]

    review = client.post(f"/api/quizzes/{quiz_id}/reviews")
    assert review.status_code == 200
    review_id = review.json()["id"]
    with SessionLocal() as db:
        questions = db.scalars(
            select(Question).where(Question.quiz_id == quiz_id).order_by(Question.position)
        ).all()
        short_question = next(
            question for question in questions if question.question_type == "short"
        )
        assert sum(
            item["score"] for item in short_question.grading_rubric
        ) == pytest.approx(short_question.max_score)
        answers = [
            {
                "question_id": question.id,
                "selected_answers": question.correct_answers,
                "text_answer": question.reference_answer
                if question.question_type == "short"
                else None,
            }
            for question in questions
        ]
        book = db.get(Book, book_id)
        book.pre_generation_enabled = True
        book.pre_generation_status = "completed"
        book.pre_generation_quiz_id = quiz_id
        db.commit()

    submitted = client.post(
        f"/api/reviews/{review_id}/submit",
        json={"elapsed_seconds": 300, "answers": answers},
    )
    assert submitted.status_code == 200

    deleted = client.delete(f"/api/quizzes/{quiz_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/quizzes/{quiz_id}").status_code == 404
    assert client.get(f"/api/reviews/{review_id}").status_code == 404
    after_delete = client.get(f"/api/books/{book_id}")
    assert after_delete.status_code == 200
    assert after_delete.json()["quizzes"] == []
    assert after_delete.json()["pre_generation_enabled"] is False
    assert after_delete.json()["pre_generation_status"] == "disabled"
    assert after_delete.json()["pre_generation_quiz_id"] is None
    task_after_delete = client.get(f"/api/quiz-generation-tasks/{generation_task['id']}")
    assert task_after_delete.status_code == 200
    assert task_after_delete.json()["quiz_id"] is None


def test_update_quiz_question_and_reveal_latest_content(client):
    book_id, _ = create_source_book(client, "题目修正测试书", "修正测试作者")
    generated = client.post(
        f"/api/books/{book_id}/quizzes",
        json={
            "duration_minutes": 15,
            "difficulty": "medium",
            "single_count": 1,
            "multiple_count": 0,
            "short_count": 0,
        },
    )
    assert generated.status_code == 202
    quiz_id = wait_for_generation(client, generated.json()["id"])["quiz_id"]
    review = client.post(f"/api/quizzes/{quiz_id}/reviews")
    assert review.status_code == 200

    with SessionLocal() as db:
        question = db.scalars(
            select(Question).where(Question.quiz_id == quiz_id).order_by(Question.position)
        ).first()
        assert question is not None

    updated = client.patch(
        f"/api/quizzes/{quiz_id}/questions/{question.id}",
        json={
            "prompt": "修正后的题干",
            "knowledge_point": "修正后的知识点",
            "explanation": "修正后的解析",
            "options": [
                {"id": "A", "text": "错误选项"},
                {"id": "B", "text": "正确选项"},
                {"id": "C", "text": "干扰项一"},
                {"id": "D", "text": "干扰项二"},
            ],
            "correct_answers": ["B"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["prompt"] == "修正后的题干"
    assert updated.json()["correct_answers"] == ["B"]
    with SessionLocal() as db:
        refreshed_question = db.get(Question, question.id)
        assert refreshed_question is not None
        assert refreshed_question.fact_key
        assert refreshed_question.fact_claim == "修正后的题干"
        assert refreshed_question.semantic_signature["answer_signature"] == ["正确选项"]

    submitted = client.post(
        f"/api/reviews/{review.json()['id']}/submit",
        json={"elapsed_seconds": 60, "answers": []},
    )
    assert submitted.status_code == 200
    result = client.get(f"/api/reviews/{review.json()['id']}/result")
    assert result.status_code == 200
    assert result.json()["questions"][0]["prompt"] == "修正后的题干"
    assert result.json()["questions"][0]["correct_answers"] == ["B"]


def test_update_quiz_question_rejects_invalid_answers(client):
    book_id, _ = create_source_book(client, "题目校验测试书", "校验测试作者")
    generated = client.post(
        f"/api/books/{book_id}/quizzes",
        json={
            "duration_minutes": 15,
            "difficulty": "medium",
            "single_count": 1,
            "multiple_count": 0,
            "short_count": 0,
        },
    )
    assert generated.status_code == 202
    quiz_id = wait_for_generation(client, generated.json()["id"])["quiz_id"]

    with SessionLocal() as db:
        question = db.scalars(
            select(Question).where(Question.quiz_id == quiz_id).order_by(Question.position)
        ).first()
        assert question is not None

    response = client.patch(
        f"/api/quizzes/{quiz_id}/questions/{question.id}",
        json={"correct_answers": ["Z"]},
    )

    assert response.status_code == 422


def test_multiple_choice_scores_zero_on_wrong_selection_and_partial_on_missing_selection(client):
    book_id, _ = create_source_book(client, "多选评分测试书", "多选评分作者")
    generated = client.post(
        f"/api/books/{book_id}/quizzes",
        json={
            "duration_minutes": 15,
            "difficulty": "medium",
            "single_count": 0,
            "multiple_count": 1,
            "short_count": 0,
        },
    )
    assert generated.status_code == 202
    quiz_id = wait_for_generation(client, generated.json()["id"])["quiz_id"]

    with SessionLocal() as db:
        question = db.scalars(
            select(Question).where(Question.quiz_id == quiz_id).order_by(Question.position)
        ).one()
        assert question.question_type == "multiple"
        correct_answers = list(question.correct_answers)
        assert len(correct_answers) >= 2
        wrong_answer = next(
            option["id"]
            for option in question.options
            if option["id"] not in correct_answers
        )
        max_score = question.max_score

    partial_review = client.post(f"/api/quizzes/{quiz_id}/reviews")
    assert partial_review.status_code == 200
    partial = client.post(
        f"/api/reviews/{partial_review.json()['id']}/submit",
        json={
            "elapsed_seconds": 60,
            "answers": [
                {
                    "question_id": question.id,
                    "selected_answers": correct_answers[:-1],
                }
            ],
        },
    )
    assert partial.status_code == 200
    partial_body = partial.json()
    expected_partial_score = round(max_score * (len(correct_answers) - 1) / len(correct_answers), 1)
    assert partial_body["answers"][0]["score"] == pytest.approx(expected_partial_score)
    assert partial_body["answers"][0]["is_correct"] is False

    wrong_review = client.post(f"/api/quizzes/{quiz_id}/reviews")
    assert wrong_review.status_code == 200
    wrong = client.post(
        f"/api/reviews/{wrong_review.json()['id']}/submit",
        json={
            "elapsed_seconds": 60,
            "answers": [
                {
                    "question_id": question.id,
                    "selected_answers": [correct_answers[0], wrong_answer],
                }
            ],
        },
    )
    assert wrong.status_code == 200
    wrong_body = wrong.json()
    assert wrong_body["answers"][0]["score"] == 0
    assert wrong_body["answers"][0]["is_correct"] is False


def test_generate_submit_and_avoid_recent_sources(client):
    book_id, _ = create_source_book(client, "复习流程测试书", "复习流程作者")
    distinct_contents = [
        "主动回忆要求学习者脱离材料，从记忆中主动提取答案。",
        "间隔练习通过拉开复习时间，减缓长期记忆的遗忘。",
        "交错练习把不同类型的问题混合起来，训练策略选择能力。",
        "自我解释要求说明推理过程，帮助发现理解中的断点。",
        "生成效应表明自己组织出的答案通常比直接阅读记得更牢。",
        "及时反馈可以纠正错误记忆，避免错误答案被反复强化。",
        "睡眠会参与记忆巩固，连续熬夜不利于长期保持。",
        "情境线索能够帮助提取记忆，但过度依赖单一场景会限制迁移。",
        "目标拆解把复杂任务划分为可检查的小步骤，降低执行负担。",
        "错题复盘应分析错误原因，而不只是重新抄写标准答案。",
    ]
    with SessionLocal() as db:
        chunks = list(
            db.scalars(
                select(ContentChunk)
                .where(ContentChunk.book_id == book_id)
                .order_by(ContentChunk.page_number)
            ).all()
        )
        for chunk, content in zip(chunks, distinct_contents, strict=True):
            chunk.content = content
            chunk.char_count = len(content)
        db.commit()
    payload = {
        "duration_minutes": 15,
        "difficulty": "medium",
        "single_count": 2,
        "multiple_count": 1,
        "short_count": 1,
    }
    generated = client.post(f"/api/books/{book_id}/quizzes", json=payload)
    assert generated.status_code == 202
    task = wait_for_generation(client, generated.json()["id"])
    quiz = client.get(f"/api/quizzes/{task['quiz_id']}").json()
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

    review = client.post(f"/api/quizzes/{quiz['id']}/reviews")
    assert review.status_code == 200
    submitted = client.post(
        f"/api/reviews/{review.json()['id']}/submit",
        json={"elapsed_seconds": 420, "answers": answers},
    )
    assert submitted.status_code == 200
    result = submitted.json()
    assert result["status"] == "submitted"
    assert result["next_review_date"] is not None
    assert result["questions"][-1]["reference_answer"]
    assert result["questions"][-1]["grading_rubric"]
    detail = client.get(f"/api/books/{book_id}")
    assert detail.status_code == 200
    assert detail.json()["stats"]["average_score"] == round(
        result["total_score"] / result["max_score"] * 100, 1
    )

    second = client.post(f"/api/books/{book_id}/quizzes", json=payload)
    assert second.status_code == 202
    second_task = wait_for_generation(client, second.json()["id"])
    second_quiz = client.get(f"/api/quizzes/{second_task['quiz_id']}").json()
    second_sources = {
        evidence["chunk_id"]
        for question in second_quiz["questions"]
        for evidence in question["source_evidence"]
    }
    assert first_sources.isdisjoint(second_sources)

    history = client.get(f"/api/books/{book_id}/history")
    assert history.status_code == 200
    assert len(history.json()) == 1

    reopened = client.post(f"/api/reviews/{review.json()['id']}/reopen")
    assert reopened.status_code == 200
    assert reopened.json()["id"] == review.json()["id"]
    assert reopened.json()["status"] == "in_progress"

    resubmitted = client.post(
        f"/api/reviews/{review.json()['id']}/submit",
        json={"elapsed_seconds": 300, "answers": answers},
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["id"] == review.json()["id"]
    assert resubmitted.json()["elapsed_seconds"] == 300

    another_review = client.post(f"/api/quizzes/{quiz['id']}/reviews")
    assert another_review.status_code == 200
    assert another_review.json()["id"] != review.json()["id"]
    assert another_review.json()["attempt_number"] == 2
    all_reviews = client.get(f"/api/reviews?book_id={book_id}")
    assert [item["attempt_number"] for item in all_reviews.json()] == [2, 1]
    title_results = client.get("/api/reviews", params={"search": "复习流程"})
    assert {item["id"] for item in title_results.json()} == {
        another_review.json()["id"],
        review.json()["id"],
    }
    author_results = client.get("/api/reviews", params={"search": "复习流程作者"})
    assert {item["id"] for item in author_results.json()} == {
        another_review.json()["id"],
        review.json()["id"],
    }
    submitted_results = client.get(
        "/api/reviews", params={"status": "submitted", "book_id": book_id}
    )
    assert [item["id"] for item in submitted_results.json()] == [review.json()["id"]]

    deleted = client.delete(f"/api/reviews/{another_review.json()['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/quizzes/{quiz['id']}").status_code == 200


def test_quiz_generation_switches_between_configured_and_mock_provider(client, monkeypatch):
    book_id, _ = create_source_book(client, "Provider 模式测试书")
    payload = {
        "duration_minutes": 15,
        "difficulty": "medium",
        "single_count": 1,
        "multiple_count": 0,
        "short_count": 0,
    }
    original_mock_generate = MockQuizAiProvider.generate_questions
    calls = {"http": 0, "mock": 0}

    def fake_http_generate(self, **kwargs):
        calls["http"] += 1
        return original_mock_generate(MockQuizAiProvider(), **kwargs)

    def tracked_mock_generate(self, **kwargs):
        calls["mock"] += 1
        return original_mock_generate(self, **kwargs)

    monkeypatch.setattr(HttpQuizAiProvider, "generate_questions", fake_http_generate)
    monkeypatch.setattr(MockQuizAiProvider, "generate_questions", tracked_mock_generate)

    configured = client.put(
        "/api/settings/model",
        json={
            "provider_mode": "openai_compatible",
            "base_url": "https://models.example.com/v1",
            "model_name": "review-model",
            "api_key": "provider-test-secret",
        },
    )
    assert configured.status_code == 200

    real_mode_quiz = client.post(f"/api/books/{book_id}/quizzes", json=payload)
    assert real_mode_quiz.status_code == 202
    wait_for_generation(client, real_mode_quiz.json()["id"])
    assert calls == {"http": 1, "mock": 0}

    switched = client.put(
        "/api/settings/model",
        json={
            "provider_mode": "mock",
            "base_url": "https://models.example.com/v1",
            "model_name": "review-model",
        },
    )
    assert switched.status_code == 200

    mock_mode_quiz = client.post(f"/api/books/{book_id}/quizzes", json=payload)
    assert mock_mode_quiz.status_code == 202
    wait_for_generation(client, mock_mode_quiz.json()["id"])
    assert calls == {"http": 1, "mock": 1}


def test_question_regeneration_avoids_same_type_duplicates(client, monkeypatch):
    book_id, _ = create_source_book(client, "单题重出测试书")
    with SessionLocal() as db:
        chunk_ids = list(
            db.scalars(
                select(ContentChunk.id)
                .where(ContentChunk.book_id == book_id)
                .order_by(ContentChunk.page_number)
            ).all()
        )
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

        def make_single(
            question_id: str,
            position: int,
            prompt: str,
            chunk_id: str,
            correct_answer: str,
        ) -> Question:
            return Question(
                id=question_id,
                quiz_id=quiz.id,
                position=position,
                question_type="single",
                prompt=prompt,
                options=[
                    {"id": "A", "text": f"{prompt} A"},
                    {"id": "B", "text": f"{prompt} B"},
                    {"id": "C", "text": f"{prompt} C"},
                    {"id": "D", "text": f"{prompt} D"},
                ],
                correct_answers=[correct_answer],
                explanation=f"{prompt} 解析",
                knowledge_point=f"{prompt} 知识点",
                difficulty="medium",
                estimated_seconds=45,
                reference_answer=None,
                grading_rubric=[],
                source_chunk_ids=[chunk_id],
                source_evidence=[],
                max_score=30,
            )

        def make_multiple(question_id: str, position: int, chunk_id: str) -> Question:
            return Question(
                id=question_id,
                quiz_id=quiz.id,
                position=position,
                question_type="multiple",
                prompt=f"旧的多选题 {position}",
                options=[
                    {"id": "A", "text": "A"},
                    {"id": "B", "text": "B"},
                    {"id": "C", "text": "C"},
                    {"id": "D", "text": "D"},
                ],
                correct_answers=["A", "B"],
                explanation="多选题解析",
                knowledge_point="多选知识点",
                difficulty="medium",
                estimated_seconds=90,
                reference_answer=None,
                grading_rubric=[],
                source_chunk_ids=[chunk_id],
                source_evidence=[],
                max_score=40,
            )

        q1 = make_single("q1", 1, "旧的单选题 1", chunk_ids[0], "A")
        q2 = make_single("q2", 2, "旧的单选题 2", chunk_ids[1], "B")
        q3 = make_multiple("q3", 3, chunk_ids[2])
        db.add_all([q1, q2, q3])
        db.commit()
        quiz_id = quiz.id

    calls: list[dict] = []

    def fake_generate(self, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return [
                GeneratedQuestion(
                    question_type="single",
                    prompt="旧的单选题 2",
                    options=[
                        {"id": "A", "text": "重复 A"},
                        {"id": "B", "text": "重复 B"},
                        {"id": "C", "text": "重复 C"},
                        {"id": "D", "text": "重复 D"},
                    ],
                    correct_answers=["B"],
                    explanation="重复解析",
                    knowledge_point="旧的单选题 2 知识点",
                    estimated_seconds=45,
                    reference_answer=None,
                    grading_rubric=[],
                    source_chunk_ids=[chunk_ids[1]],
                    source_evidence=[],
                    max_score=30,
                )
            ]
        return [
            GeneratedQuestion(
                question_type="single",
                prompt="重出的单选题",
                options=[
                    {"id": "A", "text": "新 A"},
                    {"id": "B", "text": "新 B"},
                    {"id": "C", "text": "新 C"},
                    {"id": "D", "text": "新 D"},
                ],
                correct_answers=["C"],
                explanation="重出后的解析",
                knowledge_point="重出后的知识点",
                estimated_seconds=45,
                reference_answer=None,
                grading_rubric=[],
                source_chunk_ids=[chunk_ids[3]],
                source_evidence=[],
                max_score=30,
            )
        ]

    monkeypatch.setattr(MockQuizAiProvider, "generate_questions", fake_generate)

    response = client.post(f"/api/quizzes/{quiz_id}/questions/{q1.id}/regenerate")
    assert response.status_code == 200
    body = response.json()
    assert body["prompt"] == "重出的单选题"
    assert body["knowledge_point"] == "重出后的知识点"
    assert body["correct_answers"] == ["C"]
    assert len(calls) == 2
    assert calls[0]["recent_chunk_ids"] == set()
    assert chunk_ids[1] not in {chunk.id for chunk in calls[0]["chunks"]}
    assert calls[0]["question_exclusions"][0]["role"] == "current_question"
    assert calls[0]["question_exclusions"][1]["role"] == "same_type_reference"
    assert calls[0]["question_exclusions"][1]["position"] == 2

    with SessionLocal() as db:
        updated = db.get(Question, "q1")
        untouched_single = db.get(Question, "q2")
        untouched_multiple = db.get(Question, "q3")
        assert updated.prompt == "重出的单选题"
        assert untouched_single.prompt == "旧的单选题 2"
        assert untouched_multiple.prompt == "旧的多选题 3"


def test_question_regeneration_upgrades_to_material_mode_when_quotes_match(client, monkeypatch):
    book_id, _ = create_source_book(client, "补充资料重出测试书")
    with SessionLocal() as db:
        chunk_ids = list(
            db.scalars(
                select(ContentChunk.id)
                .where(ContentChunk.book_id == book_id)
                .order_by(ContentChunk.page_number)
            ).all()
        )
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
        question = Question(
            id="pdf-q1",
            quiz_id=quiz.id,
            position=1,
            question_type="single",
            prompt="翠平此前在游击队中的主要身份是什么？",
            options=[
                {"id": "A", "text": "游击队队员"},
                {"id": "B", "text": "地下党交通员"},
                {"id": "C", "text": "国民党军官"},
                {"id": "D", "text": "普通商人"},
            ],
            correct_answers=["A"],
            explanation="解析",
            knowledge_point="翠平人物身份",
            difficulty="medium",
            estimated_seconds=45,
            source_chunk_ids=[chunk_ids[0]],
            source_evidence=[],
            max_score=100,
        )
        db.add(question)

        material = ResourceMaterial(
            book_id=book_id,
            material_type="dialogue",
            file_format="srt",
            file_name="潜伏字幕.srt",
            file_path="demo://quotes",
            file_size=2048,
            file_hash="material-hash-1",
            parse_status="completed",
        )
        db.add(material)
        db.flush()
        db.add(
            QuoteEntry(
                book_id=book_id,
                material_id=material.id,
                quote_text="翠平说：我此前一直是游击队里的队员。",
                normalized_text="翠平说我此前一直是游击队里的队员",
                content_hash="quote-hash-1",
                speaker="翠平",
                context="翠平向余则成回忆自己此前的游击队队员身份",
                review_status="confirmed",
                enabled_for_generation=True,
            )
        )
        db.commit()
        quiz_id = quiz.id

    calls: list[dict] = []

    def fake_generate(self, **kwargs):
        calls.append(kwargs)
        return [
            GeneratedQuestion(
                question_type="single",
                prompt="翠平向余则成假扮夫妻时，两人的关系设定是什么？",
                options=[
                    {"id": "A", "text": "工作搭档"},
                    {"id": "B", "text": "亲兄妹"},
                    {"id": "C", "text": "上下级"},
                    {"id": "D", "text": "陌生人"},
                ],
                correct_answers=["A"],
                explanation="依据可信台词重出",
                knowledge_point="翠平人物关系",
                estimated_seconds=45,
                reference_answer=None,
                grading_rubric=[],
                source_chunk_ids=[],
                quote_entry_ids=[kwargs["chunks"][0].id],
                source_evidence=[],
                max_score=100,
            )
        ]

    monkeypatch.setattr(MockQuizAiProvider, "generate_questions", fake_generate)

    response = client.post(f"/api/quizzes/{quiz_id}/questions/pdf-q1/regenerate")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert len(calls) == 1, calls
    assert calls[0]["source_mode"] == "material", calls[0]["source_mode"]
    assert all(isinstance(chunk, ContentChunk) is False for chunk in calls[0]["chunks"])

    with SessionLocal() as db:
        updated = db.get(Question, "pdf-q1")
        refreshed_quiz = db.get(Quiz, quiz_id)
        assert updated.source_mode == "material", updated.source_mode
        assert refreshed_quiz.source_mode == "pdf"
    assert body["source_mode"] == "material", body
    assert body["quote_entry_ids"]


def test_question_regeneration_checks_all_question_types_for_same_fact(client, monkeypatch):
    book_id, _ = create_source_book(client, "整卷事实重出测试书")
    with SessionLocal() as db:
        chunk_ids = list(
            db.scalars(
                select(ContentChunk.id)
                .where(ContentChunk.book_id == book_id)
                .order_by(ContentChunk.page_number)
            ).all()
        )
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
        shared_signature = {
            "fact_claim": "翠平在假扮夫妻任务前的真实身份",
            "fact_subject": "翠平",
            "fact_relation": "身份",
            "fact_context": "天津假扮夫妻潜伏任务",
            "answer_signature": ["游击队队员"],
            "question_intent": "identity",
        }
        db.add_all(
            [
                Question(
                    id="whole-q1",
                    quiz_id=quiz.id,
                    position=1,
                    question_type="single",
                    prompt="原来的身份题",
                    options=[
                        {"id": "A", "text": "旧答案"},
                        {"id": "B", "text": "其他答案"},
                    ],
                    correct_answers=["A"],
                    explanation="解析",
                    knowledge_point="人物身份",
                    difficulty="medium",
                    estimated_seconds=45,
                    source_chunk_ids=[chunk_ids[0]],
                    source_evidence=[],
                    max_score=40,
                ),
                Question(
                    id="whole-q2",
                    quiz_id=quiz.id,
                    position=2,
                    question_type="multiple",
                    prompt="另一种题型询问翠平身份",
                    options=[
                        {"id": "A", "text": "游击队队员"},
                        {"id": "B", "text": "其他答案"},
                    ],
                    correct_answers=["A"],
                    explanation="解析",
                    knowledge_point="人物身份",
                    difficulty="medium",
                    estimated_seconds=90,
                    source_chunk_ids=[chunk_ids[1]],
                    source_evidence=[],
                    max_score=60,
                    semantic_signature=shared_signature,
                    fact_claim=shared_signature["fact_claim"],
                ),
            ]
        )
        db.commit()
        quiz_id = quiz.id

    calls: list[dict] = []

    def fake_generate(self, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return [
                GeneratedQuestion(
                    question_type="single",
                    prompt="换一种问法询问翠平的真实身份",
                    options=[
                        {"id": "A", "text": "游击队队员"},
                        {"id": "B", "text": "其他答案"},
                    ],
                    correct_answers=["A"],
                    explanation="重复事实",
                    knowledge_point="人物身份",
                    estimated_seconds=45,
                    reference_answer=None,
                    grading_rubric=[],
                    source_chunk_ids=[chunk_ids[2]],
                    source_evidence=[],
                    max_score=40,
                    fact_claim=shared_signature["fact_claim"],
                    semantic_signature=shared_signature,
                )
            ]
        return [
            GeneratedQuestion(
                question_type="single",
                prompt="天津站接收新任务的地点是什么？",
                options=[
                    {"id": "A", "text": "天津站"},
                    {"id": "B", "text": "上海站"},
                ],
                correct_answers=["A"],
                explanation="新事实",
                knowledge_point="任务地点",
                estimated_seconds=45,
                reference_answer=None,
                grading_rubric=[],
                source_chunk_ids=[chunk_ids[3]],
                source_evidence=[],
                max_score=40,
                fact_claim="天津站接收新任务的地点",
                semantic_signature={
                    "fact_claim": "天津站接收新任务的地点",
                    "fact_subject": "余则成",
                    "fact_relation": "任务地点",
                    "fact_context": "天津站新任务",
                    "answer_signature": ["天津站"],
                    "question_intent": "location",
                },
            )
        ]

    monkeypatch.setattr(MockQuizAiProvider, "generate_questions", fake_generate)
    response = client.post(f"/api/quizzes/{quiz_id}/questions/whole-q1/regenerate")
    assert response.status_code == 200
    assert response.json()["prompt"] == "天津站接收新任务的地点是什么？"
    assert len(calls) == 2
    assert any(
        item["question_type"] == "multiple"
        and item["fact_claim"] == "翠平在假扮夫妻任务前的真实身份"
        for item in calls[0]["question_exclusions"]
    )


def test_generation_retries_semantically_duplicate_questions(client, monkeypatch):
    book_id, _ = create_source_book(client, "语义去重测试书")
    calls: list[dict] = []

    def single_question(prompt: str, fact_claim: str, fact_subject: str, fact_relation: str, fact_context: str, answer: str, source_id: str) -> GeneratedQuestion:
        return GeneratedQuestion(
            question_type="single",
            prompt=prompt,
            options=[
                {"id": "A", "text": answer},
                {"id": "B", "text": "其他答案一"},
                {"id": "C", "text": "其他答案二"},
                {"id": "D", "text": "其他答案三"},
            ],
            correct_answers=["A"],
            explanation="测试解析",
            knowledge_point=fact_claim,
            estimated_seconds=45,
            reference_answer=None,
            grading_rubric=[],
            source_chunk_ids=[source_id],
            source_evidence=[],
            max_score=6,
            fact_claim=fact_claim,
            semantic_signature={
                "fact_claim": fact_claim,
                "fact_subject": fact_subject,
                "fact_relation": fact_relation,
                "fact_context": fact_context,
                "answer_signature": [answer],
                "question_intent": "identity",
            },
        )

    def fake_generate(self, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return [
                single_question(
                    "组织上派翠平到天津与余则成假扮夫妻时，翠平此前的主要身份是？",
                    "翠平在天津假扮夫妻任务前的真实身份",
                    "翠平",
                    "身份",
                    "天津假扮夫妻潜伏任务",
                    "游击队队员",
                    "chunk-1",
                )
            ]
        if len(calls) == 2:
            return [
                single_question(
                    "余则成与翠平假扮夫妻执行潜伏任务，翠平的真实身份是什么？",
                    "翠平成为余则成妻子之前的身份",
                    "翠平",
                    "身份",
                    "余则成翠平假扮夫妻执行潜伏",
                    "游击队队员",
                    "chunk-2",
                )
            ]
        return [
            single_question(
                "天津站中，余则成接到的新任务地点在哪里？",
                "余则成新任务的地点",
                "余则成",
                "任务地点",
                "天津站新任务",
                "天津站",
                "chunk-3",
            )
        ]

    monkeypatch.setattr(MockQuizAiProvider, "generate_questions", fake_generate)
    response = client.post(
        f"/api/books/{book_id}/quizzes",
        json={"single_count": 2, "multiple_count": 0, "short_count": 0},
    )
    assert response.status_code == 202
    task = wait_for_generation(client, response.json()["id"])
    assert len(calls) == 3
    assert calls[1]["question_exclusions"]
    assert calls[1]["question_exclusions"][0]["fact_claim"] == "翠平在天津假扮夫妻任务前的真实身份"

    quiz = client.get(f"/api/quizzes/{task['quiz_id']}")
    assert quiz.status_code == 200
    questions = quiz.json()["questions"]
    assert len(questions) == 2
    assert [question["prompt"] for question in questions] == [
        "组织上派翠平到天津与余则成假扮夫妻时，翠平此前的主要身份是？",
        "天津站中，余则成接到的新任务地点在哪里？",
    ]
    with SessionLocal() as db:
        stored_questions = list(
            db.scalars(
                select(Question).where(Question.quiz_id == task["quiz_id"]).order_by(Question.position)
            ).all()
        )
    assert len({question.fact_key for question in stored_questions}) == 2


def test_generation_retries_fact_already_used_by_historical_quiz(client, monkeypatch):
    book_id, _ = create_source_book(client, "跨试卷事实去重测试书")
    shared_signature = {
        "fact_claim": "翠平在天津假扮夫妻任务前的真实身份",
        "fact_subject": "翠平",
        "fact_relation": "身份",
        "fact_context": "天津假扮夫妻潜伏任务",
        "answer_signature": ["游击队队员"],
        "question_intent": "identity",
    }
    with SessionLocal() as db:
        chunk_ids = list(
            db.scalars(
                select(ContentChunk.id)
                .where(ContentChunk.book_id == book_id)
                .order_by(ContentChunk.page_number)
            ).all()
        )
        historical_quiz = Quiz(
            book_id=book_id,
            title="历史试卷",
            difficulty="medium",
            duration_minutes=15,
            status="ready",
            source_mode="pdf",
            max_score=100,
        )
        db.add(historical_quiz)
        db.flush()
        historical_question = Question(
            quiz_id=historical_quiz.id,
            position=1,
            question_type="single",
            prompt="组织派翠平到天津前，她在游击队中的身份是什么？",
            options=[
                {"id": "A", "text": "游击队队员"},
                {"id": "B", "text": "机要秘书"},
                {"id": "C", "text": "天津站特务"},
                {"id": "D", "text": "普通商人"},
            ],
            correct_answers=["A"],
            explanation="翠平此前是游击队队员。",
            knowledge_point="人物身份",
            difficulty="medium",
            estimated_seconds=45,
            source_chunk_ids=[chunk_ids[0]],
            source_evidence=[],
            max_score=100,
            fact_claim=shared_signature["fact_claim"],
            semantic_signature=shared_signature,
        )
        db.add(historical_question)
        db.commit()
        historical_question_id = historical_question.id

    calls: list[dict] = []

    def generated_question(*, duplicate: bool) -> GeneratedQuestion:
        signature = shared_signature if duplicate else {
            "fact_claim": "余则成接收新任务的地点",
            "fact_subject": "余则成",
            "fact_relation": "任务地点",
            "fact_context": "天津站新任务",
            "answer_signature": ["天津站"],
            "question_intent": "location",
        }
        return GeneratedQuestion(
            question_type="single",
            prompt=(
                "余则成与翠平假扮夫妻时，翠平此前的真实身份是什么？"
                if duplicate
                else "余则成接收新任务的地点在哪里？"
            ),
            options=[
                {"id": "A", "text": signature["answer_signature"][0]},
                {"id": "B", "text": "错误答案一"},
                {"id": "C", "text": "错误答案二"},
                {"id": "D", "text": "错误答案三"},
            ],
            correct_answers=["A"],
            explanation="测试解析",
            knowledge_point="人物身份" if duplicate else "任务地点",
            estimated_seconds=45,
            reference_answer=None,
            grading_rubric=[],
            source_chunk_ids=[chunk_ids[1] if duplicate else chunk_ids[2]],
            source_evidence=[],
            max_score=100,
            fact_claim=signature["fact_claim"],
            semantic_signature=signature,
        )

    def fake_generate(self, **kwargs):
        calls.append(kwargs)
        return [generated_question(duplicate=len(calls) == 1)]

    monkeypatch.setattr(MockQuizAiProvider, "generate_questions", fake_generate)
    response = client.post(
        f"/api/books/{book_id}/quizzes",
        json={"single_count": 1, "multiple_count": 0, "short_count": 0},
    )
    assert response.status_code == 202
    task = wait_for_generation(client, response.json()["id"])

    assert len(calls) == 2
    assert calls[0]["question_exclusions"][0]["role"] == "historical_question"
    assert calls[0]["question_exclusions"][0]["fact_claim"] == shared_signature["fact_claim"]
    quiz = client.get(f"/api/quizzes/{task['quiz_id']}")
    assert quiz.status_code == 200
    assert quiz.json()["questions"][0]["prompt"] == "余则成接收新任务的地点在哪里？"
    with SessionLocal() as db:
        historical_question = db.get(Question, historical_question_id)
        assert historical_question is not None
        assert historical_question.fact_key
        assert historical_question.semantic_signature["fact_subject"] == "翠平"


def test_book_without_pdf_uses_model_knowledge_mode_with_real_provider(client, monkeypatch):
    created = client.post(
        "/api/books",
        json={"title": "解忧杂货店", "author": "东野圭吾"},
    )
    assert created.status_code == 201
    book_id = created.json()["id"]

    configured = client.put(
        "/api/settings/model",
        json={
            "provider_mode": "openai_compatible",
            "base_url": "https://models.example.com/v1",
            "model_name": "review-model",
            "api_key": "provider-test-secret",
        },
    )
    assert configured.status_code == 200

    def fake_http_generate(self, **kwargs):
        assert kwargs["source_mode"] == "model_knowledge"
        assert kwargs["book_title"] == "解忧杂货店"
        return [
            GeneratedQuestion(
                question_type="single",
                prompt="浪矢杂货店主要通过什么方式回应来信？",
                options=[
                    {"id": "A", "text": "书信咨询"},
                    {"id": "B", "text": "电话咨询"},
                    {"id": "C", "text": "面对面授课"},
                    {"id": "D", "text": "广播节目"},
                ],
                correct_answers=["A"],
                explanation="题目依据模型对作品设定的知识生成。",
                knowledge_point="浪矢杂货店",
                estimated_seconds=45,
                reference_answer=None,
                grading_rubric=[],
                source_chunk_ids=[],
                source_evidence=[],
                max_score=6,
            )
        ]

    monkeypatch.setattr(HttpQuizAiProvider, "generate_questions", fake_http_generate)
    generated = client.post(
        f"/api/books/{book_id}/quizzes",
        json={"single_count": 1, "multiple_count": 0, "short_count": 0},
    )
    assert generated.status_code == 202
    task = wait_for_generation(client, generated.json()["id"])
    assert task["source_mode"] == "model_knowledge"

    quiz = client.get(f"/api/quizzes/{task['quiz_id']}")
    assert quiz.status_code == 200
    assert quiz.json()["source_mode"] == "model_knowledge"
    assert quiz.json()["max_score"] == 100
    assert quiz.json()["questions"][0]["max_score"] == 100
    assert quiz.json()["questions"][0]["source_evidence"] == []


def test_pre_generation_is_idempotent_and_requires_available_source(client, monkeypatch):
    book_id, _ = create_source_book(client, "预生成测试书")
    started: list[tuple[object, tuple[str, ...]]] = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            started.append((target, args))
            assert daemon is True

        def start(self):
            return None

    monkeypatch.setattr("app.services.pre_generation.threading.Thread", FakeThread)

    first = client.post(f"/api/books/{book_id}/pre-generation")
    assert first.status_code == 202
    assert first.json()["status"] == "pending"
    assert len(started) == 1
    generation_task_id = first.json()["task_id"]

    duplicate = client.post(f"/api/books/{book_id}/pre-generation")
    assert duplicate.status_code == 202
    assert duplicate.json()["status"] == "pending"
    assert len(started) == 1

    blocked = client.post(
        f"/api/books/{book_id}/quizzes",
        json={"duration_minutes": 15, "single_count": 1, "multiple_count": 0, "short_count": 0},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] in {
        "该书正在后台预生成测试，请等待本次任务完成",
        "该书已有出题任务正在进行，请等待本次任务完成",
    }

    with SessionLocal() as db:
        stored_book = db.get(Book, book_id)
        stored_book.pre_generation_status = "processing"
        db.commit()
        recovered = recover_pre_generation_tasks(db)
        db.refresh(stored_book)
        assert generation_task_id in recovered
        assert stored_book.pre_generation_status == "pending"

    without_pdf = client.post(
        "/api/books",
        json={"title": "没有原文的书", "author": "测试作者"},
    )
    assert without_pdf.status_code == 201
    switched_to_mock = client.put(
        "/api/settings/model",
        json={"provider_mode": "mock", "base_url": "", "model_name": ""},
    )
    assert switched_to_mock.status_code == 200
    unavailable = client.post(f"/api/books/{without_pdf.json()['id']}/pre-generation")
    assert unavailable.status_code == 409
    assert unavailable.json()["detail"] == (
        "没有 PDF 时需要启用已配置的大模型，当前模拟接口不支持书籍知识出题"
    )


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


def test_model_configuration_keeps_api_key_secret(client):
    with SessionLocal() as db:
        stored = db.get(ModelConfiguration, "default")
        if stored:
            db.delete(stored)
            db.commit()

    default_response = client.get("/api/settings/model")
    assert default_response.status_code == 200
    assert default_response.json()["provider_mode"] == "mock"
    assert default_response.json()["api_key_configured"] is False
    assert "api_key" not in default_response.json()

    secret = "test-secret-key"
    saved = client.put(
        "/api/settings/model",
        json={
            "provider_mode": "openai_compatible",
            "base_url": "https://models.example.com/v1",
            "model_name": "review-model",
            "api_key": secret,
            "timeout_ms": 90_000,
            "temperature": 0.4,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["provider_mode"] == "openai_compatible"
    assert saved.json()["api_key_configured"] is True
    assert secret not in saved.text

    loaded = client.get("/api/settings/model")
    assert loaded.status_code == 200
    assert loaded.json()["base_url"] == "https://models.example.com/v1"
    assert loaded.json()["model_name"] == "review-model"
    assert loaded.json()["api_key_configured"] is True
    assert secret not in loaded.text

    cleared = client.put(
        "/api/settings/model",
        json={
            "provider_mode": "mock",
            "base_url": "https://models.example.com/v1",
            "model_name": "review-model",
            "clear_api_key": True,
            "timeout_ms": 90_000,
            "temperature": 0.4,
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["api_key_configured"] is False


def test_model_configuration_validates_real_provider_fields(client):
    missing_url = client.put(
        "/api/settings/model",
        json={"provider_mode": "openai_compatible", "model_name": "review-model"},
    )
    assert missing_url.status_code == 422
    assert missing_url.json()["detail"] == "真实模型模式需要填写接口地址"

    missing_model = client.put(
        "/api/settings/model",
        json={
            "provider_mode": "openai_compatible",
            "base_url": "https://models.example.com/v1",
        },
    )
    assert missing_model.status_code == 422
    assert missing_model.json()["detail"] == "真实模型模式需要填写模型名称"

    invalid_url = client.put(
        "/api/settings/model",
        json={
            "provider_mode": "openai_compatible",
            "base_url": "models.example.com/v1",
            "model_name": "review-model",
        },
    )
    assert invalid_url.status_code == 422
    assert invalid_url.json()["detail"] == "接口地址必须以 http:// 或 https:// 开头"


def test_model_configuration_can_load_incomplete_stored_values(client):
    with SessionLocal() as db:
        stored = db.get(ModelConfiguration, "default")
        if stored is None:
            stored = ModelConfiguration(id="default")
            db.add(stored)
        stored.provider_mode = "openai_compatible"
        stored.base_url = ""
        stored.model_name = ""
        db.commit()

    response = client.get("/api/settings/model")
    assert response.status_code == 200
    assert response.json()["provider_mode"] == "openai_compatible"

    client.put(
        "/api/settings/model",
        json={
            "provider_mode": "mock",
            "base_url": "",
            "model_name": "",
            "clear_api_key": True,
        },
    )


def test_model_connection_uses_form_values_and_saved_api_key(client, monkeypatch):
    saved = client.put(
        "/api/settings/model",
        json={
            "provider_mode": "mock",
            "base_url": "https://saved.example.com/v1",
            "model_name": "saved-model",
            "api_key": "saved-secret",
        },
    )
    assert saved.status_code == 200

    captured: dict[str, object] = {}

    class FakeResponse:
        is_success = True
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "连接成功"}}]}

    class FakeClient:
        def __init__(self, timeout: float):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, url: str, *, headers: dict, json: dict):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.routers.settings.httpx.Client", FakeClient)
    response = client.post(
        "/api/settings/model/test",
        json={
            "base_url": "https://current.example.com/v1/",
            "model_name": "current-model",
            "timeout_ms": 12_000,
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["model_name"] == "current-model"
    assert response.json()["model_response"] == "连接成功"
    assert captured["url"] == "https://current.example.com/v1/chat/completions"
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer saved-secret",
    }
    assert captured["timeout"] == 12
    assert captured["json"]["model"] == "current-model"


def test_model_connection_validates_required_fields(client):
    missing_url = client.post(
        "/api/settings/model/test",
        json={"base_url": "", "model_name": "review-model"},
    )
    assert missing_url.status_code == 422
    assert missing_url.json()["detail"] == "请先填写接口地址"

    missing_model = client.post(
        "/api/settings/model/test",
        json={"base_url": "https://models.example.com/v1", "model_name": ""},
    )
    assert missing_model.status_code == 422
    assert missing_model.json()["detail"] == "请先填写模型名称"


def test_model_connection_records_failed_result(client, monkeypatch):
    class FakeResponse:
        is_success = False
        status_code = 401
        text = ""

        @staticmethod
        def json():
            return {"error": {"message": "鉴权失败"}}

    class FakeClient:
        def __init__(self, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.routers.settings.httpx.Client", FakeClient)
    response = client.post(
        "/api/settings/model/test",
        json={
            "base_url": "https://models.example.com/v1",
            "model_name": "review-model",
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["message"] == "模型接口返回 401：鉴权失败"
    assert response.json()["tested_at"]
    with SessionLocal() as db:
        stored = db.get(ModelConfiguration, "default")
        assert stored is not None
        assert stored.last_test_status == "failed"
        assert stored.last_test_message == "模型接口返回 401：鉴权失败"
        assert stored.last_tested_at is not None
