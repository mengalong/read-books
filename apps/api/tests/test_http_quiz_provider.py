import json

import pytest

from app.models import ContentChunk, Question
from app.services.model_config import EffectiveModelConfiguration
from app.services.model_usage import new_usage_context
from app.services.prompt_config import DEFAULT_PROMPTS, PromptTemplateDefinition
from app.services.quiz_provider import HttpQuizAiProvider, key_sentence


def make_configuration() -> EffectiveModelConfiguration:
    return EffectiveModelConfiguration(
        provider_mode="openai_compatible",
        base_url="https://models.example.com/v1",
        api_key="provider-secret",
        model_name="review-model",
        timeout_ms=30_000,
        temperature=0.3,
    )


def make_chunks() -> list[ContentChunk]:
    contents = [
        "主动回忆要求读者合上书本，用自己的语言从记忆中提取核心内容。",
        "间隔练习应根据掌握程度调整节奏，薄弱内容需要更早再次出现。",
        "可靠的复习题必须能够追溯到原文，依据不足时不应该自行补全。",
    ]
    return [
        ContentChunk(
            id=f"chunk-{index}",
            book_id="book-1",
            pdf_id="pdf-1",
            page_number=index * 10,
            sequence=index,
            content=content,
            char_count=len(content),
        )
        for index, content in enumerate(contents, start=1)
    ]


def install_chat_responses(monkeypatch, contents: list[str]) -> list[dict]:
    queued = list(contents)
    requests: list[dict] = []

    class FakeResponse:
        is_success = True
        status_code = 200
        text = ""

        def __init__(self, content: str):
            self.content = content

        def json(self):
            return {"choices": [{"message": {"content": self.content}}]}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, url: str, *, headers: dict, json: dict):
            requests.append(
                {"url": url, "headers": headers, "json": json, "timeout": self.timeout}
            )
            return FakeResponse(queued.pop(0))

    monkeypatch.setattr("app.services.quiz_provider.httpx.Client", FakeClient)
    return requests


def generated_payload(source_ids: list[str]) -> dict:
    return {
        "questions": [
            {
                "question_type": "single",
                "prompt": "主动回忆的关键动作是什么？",
                "options": [
                    {"id": "A", "text": "反复浏览"},
                    {"id": "B", "text": "合上书本主动提取"},
                    {"id": "C", "text": "抄写全文"},
                    {"id": "D", "text": "跳过困难内容"},
                ],
                "correct_answers": ["B"],
                "explanation": "原文强调合上书本后主动提取。",
                "knowledge_point": "主动回忆",
                "reference_answer": None,
                "grading_rubric": [],
                "source_chunk_ids": [source_ids[0]],
            },
            {
                "question_type": "multiple",
                "prompt": "关于间隔练习，哪些表述符合原文？",
                "options": [
                    {"id": "A", "text": "按掌握程度调整节奏"},
                    {"id": "B", "text": "薄弱内容更早出现"},
                    {"id": "C", "text": "所有内容固定间隔"},
                    {"id": "D", "text": "只复习熟悉内容"},
                ],
                "correct_answers": ["A", "B"],
                "explanation": "A、B 都能从原文直接得到支持。",
                "knowledge_point": "间隔练习",
                "reference_answer": None,
                "grading_rubric": [],
                "source_chunk_ids": [source_ids[1]],
            },
            {
                "question_type": "short",
                "prompt": "为什么复习题必须保留原文依据？",
                "options": [],
                "correct_answers": [],
                "explanation": "需要避免依据不足时自行补全。",
                "knowledge_point": "原文依据",
                "reference_answer": "可靠题目必须能追溯原文，依据不足时不能自行补全。",
                "grading_rubric": [
                    {"point": "题目可以追溯原文", "keywords": ["追溯", "原文"], "score": 6},
                    {"point": "避免自行补全", "keywords": ["依据不足", "补全"], "score": 4},
                ],
                "source_chunk_ids": [source_ids[2]],
            },
        ]
    }


def test_key_sentence_prefers_long_matching_phrase():
    excerpt = "开头只是交代场景，和题目关系不大。真正相关的是他决定继续坚持音乐创作，并相信歌声能够帮助别人。后面还有补充说明。"

    assert key_sentence(excerpt, "题目要求说明人物为什么继续坚持音乐创作，以及音乐如何帮助别人") == (
        "真正相关的是他决定继续坚持音乐创作，并相信歌声能够帮助别人。"
    )


def test_http_provider_generates_validated_questions(monkeypatch):
    chunks = make_chunks()
    payload = generated_payload([chunk.id for chunk in chunks])
    requests = install_chat_responses(
        monkeypatch,
        [f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"],
    )
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=chunks,
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=1,
        short_count=1,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
    )

    assert [question.question_type for question in questions] == ["single", "multiple", "short"]
    assert [question.max_score for question in questions] == [6, 10, 20]
    assert questions[2].reference_answer
    assert sum(item["score"] for item in questions[2].grading_rubric) == 20
    assert questions[0].source_evidence == [
        {
            "chunk_id": "chunk-1",
            "file_name": "复习材料.pdf",
            "page_number": 10,
            "excerpt": chunks[0].content,
            "highlight": chunks[0].content,
            "support": "题目与答案依据由后端从该 PDF 原文片段重建。",
        }
    ]
    assert requests[0]["url"] == "https://models.example.com/v1/chat/completions"
    assert requests[0]["headers"]["Authorization"] == "Bearer provider-secret"
    assert requests[0]["timeout"] == 30
    assert "max_tokens" not in requests[0]["json"]
    assert "chunk-1" in requests[0]["json"]["messages"][1]["content"]


def test_http_provider_reports_usage_for_each_model_call(monkeypatch):
    chunks = make_chunks()
    payload = generated_payload([chunk.id for chunk in chunks])
    install_chat_responses(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
    events = []
    provider = HttpQuizAiProvider(
        make_configuration(),
        usage_context=new_usage_context("manual_quiz_generation", "生成测试"),
        usage_recorder=events.append,
    )

    provider.generate_questions(
        chunks=chunks,
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=1,
        short_count=1,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
    )

    assert len(events) == 1
    assert events[0].phase == "quiz_generation"
    assert events[0].call_number == 1
    assert events[0].status == "success"


def test_http_provider_rejects_unknown_source(monkeypatch):
    chunks = make_chunks()
    payload = generated_payload([chunk.id for chunk in chunks])
    payload["questions"][0]["source_chunk_ids"] = ["invented-source"]
    requests = install_chat_responses(
        monkeypatch,
        [json.dumps(payload, ensure_ascii=False), json.dumps(payload, ensure_ascii=False)],
    )
    provider = HttpQuizAiProvider(make_configuration())

    with pytest.raises(RuntimeError, match="引用了未提供的原文片段"):
        provider.generate_questions(
            chunks=chunks,
            file_names={"pdf-1": "复习材料.pdf"},
            single_count=1,
            multiple_count=1,
            short_count=1,
            difficulty="medium",
            generation_number=0,
            recent_chunk_ids=set(),
        )
    assert len(requests) == 2


def test_http_provider_accepts_common_field_aliases(monkeypatch):
    chunks = make_chunks()
    payload = generated_payload([chunk.id for chunk in chunks])
    first = payload["questions"][0]
    first["question"] = first.pop("prompt")
    first["analysis"] = first.pop("explanation")
    first["topic"] = first.pop("knowledge_point")
    requests = install_chat_responses(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=chunks,
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=1,
        short_count=1,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
    )

    assert questions[0].prompt == "主动回忆的关键动作是什么？"
    assert questions[0].explanation == "原文强调合上书本后主动提取。"
    assert questions[0].knowledge_point == "主动回忆"
    assert len(requests) == 1


def test_http_provider_accepts_content_parts(monkeypatch):
    chunks = make_chunks()
    payload = generated_payload([chunk.id for chunk in chunks])
    requests = install_chat_responses(
        monkeypatch,
        [[{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]],
    )
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=chunks,
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=1,
        short_count=1,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
    )

    assert len(questions) == 3
    assert len(requests) == 1


def test_http_provider_explains_empty_content_after_token_limit(monkeypatch):
    chunks = make_chunks()
    requests = install_chat_responses(monkeypatch, [None])

    class FakeResponse:
        is_success = True
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": None, "reasoning_content": "正在分析原文"},
                    }
                ],
            }

    class FakeClient:
        def __init__(self, timeout: float):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, *args, **kwargs):
            requests.append(kwargs["json"])
            return FakeResponse()

    monkeypatch.setattr("app.services.quiz_provider.httpx.Client", FakeClient)
    provider = HttpQuizAiProvider(make_configuration())

    with pytest.raises(RuntimeError, match="模型服务在自身输出上限处结束"):
        provider.generate_questions(
            chunks=chunks,
            file_names={"pdf-1": "复习材料.pdf"},
            single_count=1,
            multiple_count=0,
            short_count=0,
            difficulty="medium",
            generation_number=0,
            recent_chunk_ids=set(),
        )


def test_http_provider_fills_optional_text_from_valid_source(monkeypatch):
    chunks = make_chunks()
    payload = generated_payload([chunk.id for chunk in chunks])
    payload["questions"][0].pop("explanation")
    payload["questions"][0].pop("knowledge_point")
    install_chat_responses(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=chunks,
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=1,
        short_count=1,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
    )

    assert questions[0].explanation == HttpQuizAiProvider.DEFAULT_EXPLANATION
    assert questions[0].knowledge_point == "主动回忆要求读者合上书本"


def test_http_provider_repairs_invalid_json_once(monkeypatch):
    chunks = make_chunks()
    payload = generated_payload([chunk.id for chunk in chunks])
    requests = install_chat_responses(
        monkeypatch,
        ["这里不是 JSON", json.dumps(payload, ensure_ascii=False)],
    )
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=chunks,
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=1,
        short_count=1,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
    )

    assert len(questions) == 3
    assert len(requests) == 2
    repair_prompt = requests[1]["json"]["messages"][1]["content"]
    assert "真实模型返回的内容不是有效 JSON" in repair_prompt
    assert "这里不是 JSON" in repair_prompt
    assert "SOURCE_MATERIAL" in repair_prompt


def test_http_provider_repairs_structural_error_once(monkeypatch):
    chunks = make_chunks()
    invalid_payload = generated_payload([chunk.id for chunk in chunks])
    invalid_payload["questions"][0].pop("prompt")
    valid_payload = generated_payload([chunk.id for chunk in chunks])
    requests = install_chat_responses(
        monkeypatch,
        [
            json.dumps(invalid_payload, ensure_ascii=False),
            json.dumps(valid_payload, ensure_ascii=False),
        ],
    )
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=chunks,
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=1,
        short_count=1,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
    )

    assert questions[0].prompt == "主动回忆的关键动作是什么？"
    assert len(requests) == 2


def test_http_provider_rejects_invalid_repair_without_third_request(monkeypatch):
    chunks = make_chunks()
    invalid_payload = generated_payload([chunk.id for chunk in chunks])
    invalid_payload["questions"][0]["source_chunk_ids"] = ["invented-source"]
    requests = install_chat_responses(
        monkeypatch,
        [
            "not-json",
            json.dumps(invalid_payload, ensure_ascii=False),
        ],
    )
    provider = HttpQuizAiProvider(make_configuration())

    with pytest.raises(RuntimeError, match="修正失败.*引用了未提供的原文片段"):
        provider.generate_questions(
            chunks=chunks,
            file_names={"pdf-1": "复习材料.pdf"},
            single_count=1,
            multiple_count=1,
            short_count=1,
            difficulty="medium",
            generation_number=0,
            recent_chunk_ids=set(),
        )

    assert len(requests) == 2


def test_http_provider_uses_custom_generation_prompt(monkeypatch):
    chunks = make_chunks()
    payload = generated_payload([chunk.id for chunk in chunks])
    requests = install_chat_responses(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
    custom_generation = PromptTemplateDefinition(
        prompt_type="generation",
        system_prompt="自定义系统 {{difficulty}}",
        user_prompt="自定义用户 {{single_count}}/{{multiple_count}}/{{short_count}}/{{duration_minutes}} {{source_material}}",
        version=1,
        template_id="custom-generation",
        is_active=True,
    )
    provider = HttpQuizAiProvider(
        make_configuration(),
        {"generation": custom_generation, "grading": DEFAULT_PROMPTS["grading"]},
    )

    provider.generate_questions(
        chunks=chunks,
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=1,
        short_count=1,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
        duration_minutes=20,
    )

    assert requests[0]["json"]["messages"][0]["content"] == "自定义系统 medium"
    assert requests[0]["json"]["messages"][1]["content"].startswith("自定义用户 1/1/1/20")


def test_http_provider_grades_short_answer(monkeypatch):
    grade_payload = {
        "score": 16.5,
        "feedback": "回答覆盖了主要观点，但可以进一步说明依据不足时的处理。",
        "matched_points": ["题目可以追溯原文"],
        "missing_points": ["避免自行补全"],
    }
    install_chat_responses(monkeypatch, [json.dumps(grade_payload, ensure_ascii=False)])
    provider = HttpQuizAiProvider(make_configuration())
    question = Question(
        id="question-1",
        quiz_id="quiz-1",
        position=1,
        question_type="short",
        prompt="为什么复习题必须保留原文依据？",
        options=[],
        correct_answers=[],
        explanation="需要避免无依据补全。",
        knowledge_point="原文依据",
        estimated_seconds=180,
        reference_answer="可靠题目必须能追溯原文，依据不足时不能自行补全。",
        grading_rubric=[
            {"point": "题目可以追溯原文", "keywords": ["追溯"], "score": 10},
            {"point": "避免自行补全", "keywords": ["补全"], "score": 10},
        ],
        source_chunk_ids=["chunk-3"],
        source_evidence=[{"excerpt": "可靠的复习题必须能够追溯到原文。"}],
        max_score=20,
    )

    result = provider.grade_short_answer(question, "复习题需要能够回到原文核对。")

    assert result.score == 16.5
    assert result.is_correct is True
    assert result.matched_points == ["题目可以追溯原文"]
    assert result.missing_points == ["避免自行补全"]
