from pathlib import Path
import time

import fitz
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Book, ContentChunk, ModelConfiguration, PdfDocument, Question
from app.services.model_usage import ModelUsageEvent, new_usage_context, record_model_usage
from app.services.pdf_parser import parse_pdf_document
from app.services.pre_generation import recover_pre_generation_tasks
from app.services.quiz_provider import GeneratedQuestion, HttpQuizAiProvider, MockQuizAiProvider


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
    context = new_usage_context("token_report_test", "Token 统计测试")
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

    review = client.post(f"/api/quizzes/{quiz_id}/reviews")
    assert review.status_code == 200
    review_id = review.json()["id"]
    with SessionLocal() as db:
        questions = db.scalars(
            select(Question).where(Question.quiz_id == quiz_id).order_by(Question.position)
        ).all()
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
