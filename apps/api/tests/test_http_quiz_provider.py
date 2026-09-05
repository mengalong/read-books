import json

import pytest

from app.models import ContentChunk, Question, Quiz
from app.services.model_config import EffectiveModelConfiguration
from app.services.model_usage import new_usage_context
from app.services.prompt_config import DEFAULT_PROMPTS, PromptTemplateDefinition
from app.services.quiz_provider import (
    HttpQuizAiProvider,
    MockQuizAiProvider,
    TrustedPlotSource,
    TrustedQuoteSource,
    key_sentence,
)
from app.services.question_dedup import asks_for_precise_location


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


def make_trusted_quote() -> TrustedQuoteSource:
    return TrustedQuoteSource(
        id="quote-1",
        material_id="material-1",
        file_name="潜伏台词.csv",
        material_type="quote_sheet",
        content="会议现在开始",
        source_segment_ids=["segment-1"],
        speaker="吴站长",
        context="吴站长在站内会议上宣布开始",
        season_number=1,
        episode_number=1,
        start_ms=10_000,
        end_ms=12_000,
    )


def make_trusted_plot() -> TrustedPlotSource:
    return TrustedPlotSource(
        id="plot-1",
        event_id="s01e01-event-001",
        material_id="plot-material-1",
        file_name="潜伏剧情梗概.json",
        material_type="plot_summary",
        content="组织安排身份掩护，人物接受任务并进入新的行动阶段。",
        season_number=1,
        episode_number=1,
        sequence=1,
        title="任务安排",
        cause="任务需要新的身份安排。",
        action="人物接受并执行身份掩护安排。",
        result="人物进入新的行动阶段。",
        future_impact="为后续合作和冲突埋下基础。",
        characters=["余则成", "翠平"],
        source_refs=["src-001"],
        confidence="confirmed",
    )


def generated_quote_payload(*, speaker: str = "吴站长", quote_id: str = "quote-1") -> dict:
    return {
        "questions": [
            {
                "question_type": "single",
                "question_subtype": "quote_speaker",
                "prompt": "可信资料中的台词“会议现在开始”由谁说出？",
                "options": [
                    {"id": "A", "text": "余则成"},
                    {"id": "B", "text": speaker},
                    {"id": "C", "text": "李涯"},
                    {"id": "D", "text": "谢若林"},
                ],
                "correct_answers": ["B"],
                "explanation": "可信资料明确记录了说话人。",
                "knowledge_point": "吴站长经典台词",
                "reference_answer": None,
                "grading_rubric": [],
                "source_chunk_ids": [],
                "quote_entry_ids": [quote_id],
            }
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
    assert "fact_claim" in requests[0]["json"]["messages"][1]["content"]
    assert "仅更换问法、题型或选项顺序不算新事实" in requests[0]["json"]["messages"][1]["content"]


def test_http_provider_generates_model_knowledge_questions_without_pdf(monkeypatch):
    payload = generated_payload(["unused-source", "unused-source", "unused-source"])
    payload["questions"] = [payload["questions"][0]]
    payload["questions"][0]["source_chunk_ids"] = []
    requests = install_chat_responses(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=[],
        file_names={},
        single_count=1,
        multiple_count=0,
        short_count=0,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
        book_title="解忧杂货店",
        author="东野圭吾",
        source_mode="model_knowledge",
    )

    assert len(questions) == 1
    assert questions[0].source_chunk_ids == []
    assert questions[0].source_evidence == []
    assert "解忧杂货店" in requests[0]["json"]["messages"][1]["content"]
    assert "model_knowledge" in requests[0]["json"]["messages"][1]["content"]


def test_http_provider_validates_trusted_quote_and_rebuilds_evidence(monkeypatch):
    source = make_trusted_quote()
    payload = generated_quote_payload()
    requests = install_chat_responses(
        monkeypatch, [json.dumps(payload, ensure_ascii=False)]
    )
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=[source],
        file_names={},
        single_count=1,
        multiple_count=0,
        short_count=0,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
        book_title="潜伏",
        resource_type="tv_series",
        source_mode="material",
        generation_theme="classic_quotes",
        theme_requirements="仅围绕可信台词出题",
        allowed_question_subtypes=["quote_speaker"],
    )

    assert questions[0].question_subtype == "quote_speaker"
    assert questions[0].quote_entry_ids == ["quote-1"]
    assert questions[0].source_segment_ids == ["segment-1"]
    assert questions[0].source_evidence[0]["material_id"] == "material-1"
    assert questions[0].source_evidence[0]["speaker"] == "吴站长"
    assert "quote-1" in requests[0]["json"]["messages"][1]["content"]
    assert "可信台词资料" in requests[0]["json"]["messages"][0]["content"]


def test_http_provider_validates_trusted_plot_source(monkeypatch):
    source = make_trusted_plot()
    payload = generated_quote_payload(quote_id="unused")
    question = payload["questions"][0]
    question.update(
        {
            "question_subtype": "plot_cause",
            "prompt": "为什么需要安排这次身份掩护？",
            "options": [
                {"id": "A", "text": "任务需要新的身份安排"},
                {"id": "B", "text": "资料没有说明原因"},
                {"id": "C", "text": "人物拒绝执行任务"},
                {"id": "D", "text": "这只是模型推测"},
            ],
            "correct_answers": ["A"],
            "explanation": "剧情资料说明任务需要新的身份安排。",
            "knowledge_point": "身份掩护的任务原因",
            "plot_event_ids": [source.id],
            "quote_entry_ids": [],
            "source_chunk_ids": [],
        }
    )
    requests = install_chat_responses(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=[source],
        file_names={},
        single_count=1,
        multiple_count=0,
        short_count=0,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
        book_title="潜伏",
        resource_type="tv_series",
        source_mode="plot",
    )

    assert questions[0].plot_event_ids == [source.id]
    assert questions[0].source_evidence[0]["plot_event_id"] == source.id
    assert "plot_event_id" in requests[0]["json"]["messages"][1]["content"]


def test_http_provider_accepts_paraphrased_trusted_quote_prompt(monkeypatch):
    source = TrustedQuoteSource(
        id="quote-paraphrase",
        material_id="material-1",
        file_name="潜伏台词.csv",
        material_type="quote_sheet",
        content="什么任务，不就是嫌我脏吗？",
        source_segment_ids=["segment-1"],
        speaker="翠平",
        context="茅房里有热水壶、有盆，把脚也洗一洗。",
    )
    payload = generated_quote_payload(quote_id=source.id)
    question = payload["questions"][0]
    question.update(
        {
            "question_subtype": "quote_context",
            "prompt": "翠平面对让她洗脚的要求时，流露出怎样的情绪？",
            "options": [
                {"id": "A", "text": "觉得被嫌弃并表达不满"},
                {"id": "B", "text": "感到惊喜"},
                {"id": "C", "text": "完全没有情绪"},
                {"id": "D", "text": "主动提出任务"},
            ],
            "correct_answers": ["A"],
            "explanation": "她把对方的要求理解为嫌弃自己，因此用反问表达不满。",
            "knowledge_point": "翠平面对生活要求时的情绪",
            "fact_claim": "翠平因被要求洗脚而觉得受到嫌弃",
            "fact_subject": "翠平",
            "fact_relation": "情绪",
            "fact_context": "被要求洗脚时",
            "answer_signature": ["觉得被嫌弃", "表达不满"],
        }
    )
    requests = install_chat_responses(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=[source],
        file_names={},
        single_count=1,
        multiple_count=0,
        short_count=0,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
        book_title="潜伏",
        resource_type="tv_series",
        source_mode="material",
        generation_theme="classic_quotes",
        theme_requirements="仅围绕可信台词出题",
        allowed_question_subtypes=["quote_context"],
    )

    assert questions[0].prompt.startswith("翠平面对")
    assert questions[0].validation_warnings
    assert "没有逐字使用可信台词" not in requests[0]["json"]["messages"][0]["content"]


def test_repair_prompt_omits_history_and_keeps_referenced_source():
    provider = HttpQuizAiProvider(make_configuration())
    source_material = json.dumps(
        [
            {"quote_entry_id": "11111111-1111-1111-1111-111111111111", "quote": "相关台词"},
            {"quote_entry_id": "22222222-2222-2222-2222-222222222222", "quote": "无关台词"},
        ],
        ensure_ascii=False,
    )
    messages = provider._repair_generation_messages(
        [
            {"role": "system", "content": "系统约束"},
            {
                "role": "user",
                "content": "任务\n已考察事实参考（包含历史题目）：\n[{\"fact_claim\":\"旧事实\"}]\nSOURCE_MATERIAL：\n[...]",
            },
        ],
        '{"quote_entry_ids":["11111111-1111-1111-1111-111111111111"]}',
        "格式错误",
        source_material=source_material,
    )

    content = messages[1]["content"]
    assert "旧事实" not in content
    assert "相关台词" in content
    assert "无关台词" not in content


def test_http_provider_combined_mode_accepts_pdf_and_quote_sources(monkeypatch):
    pdf_source = make_chunks()[0]
    quote_source = make_trusted_quote()
    payload = generated_payload([pdf_source.id, pdf_source.id, pdf_source.id])
    payload["questions"] = [payload["questions"][0]]
    payload["questions"][0].update(
        {
            "prompt": "根据可信台词“会议现在开始”，该句的核心事实是什么？",
            "options": [
                {"id": "A", "text": "反复浏览"},
                {"id": "B", "text": "会议现在开始"},
                {"id": "C", "text": "抄写全文"},
                {"id": "D", "text": "跳过困难内容"},
            ],
            "correct_answers": ["B"],
            "explanation": "可信台词明确记录“会议现在开始”。",
            "knowledge_point": "会议通知",
            "quote_entry_ids": [quote_source.id],
        }
    )
    requests = install_chat_responses(
        monkeypatch, [json.dumps(payload, ensure_ascii=False)]
    )
    provider = HttpQuizAiProvider(make_configuration())

    questions = provider.generate_questions(
        chunks=[pdf_source, quote_source],
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=0,
        short_count=0,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
        book_title="潜伏",
        resource_type="tv_series",
        source_mode="combined",
    )

    assert questions[0].source_chunk_ids == [pdf_source.id]
    assert questions[0].quote_entry_ids == [quote_source.id]
    assert {item["chunk_id"] for item in questions[0].source_evidence} == {
        pdf_source.id,
        quote_source.id,
    }
    assert "combined" in requests[0]["json"]["messages"][1]["content"]
    assert "quote-1" in requests[0]["json"]["messages"][1]["content"]


def test_precise_episode_questions_are_rejected(monkeypatch):
    source = make_trusted_quote()
    payload = generated_quote_payload()
    question = payload["questions"][0]
    question["question_subtype"] = "quote_context"
    question["prompt"] = "可信资料中的台词“会议现在开始”出自哪一集？"
    question["options"] = [
        {"id": "A", "text": "第 1 集"},
        {"id": "B", "text": "第 2 集"},
        {"id": "C", "text": "第 3 集"},
        {"id": "D", "text": "第 4 集"},
    ]
    question["correct_answers"] = ["A"]
    question["fact_relation"] = "集数"
    question["question_intent"] = "episode"
    install_chat_responses(
        monkeypatch,
        [json.dumps(payload, ensure_ascii=False), json.dumps(payload, ensure_ascii=False)],
    )
    provider = HttpQuizAiProvider(make_configuration())

    with pytest.raises(RuntimeError, match="不能询问精确的集数"):
        provider.generate_questions(
            chunks=[source],
            file_names={},
            single_count=1,
            multiple_count=0,
            short_count=0,
            difficulty="medium",
            generation_number=0,
            recent_chunk_ids=set(),
            source_mode="material",
            generation_theme="classic_quotes",
            theme_requirements="对话场景只考察语境",
            allowed_question_subtypes=["quote_context"],
        )

    assert asks_for_precise_location("这句台词发生在哪一集？")
    assert asks_for_precise_location("这句台词反映了什么处境？") is False


def test_http_provider_rejects_untrusted_quote_attribution(monkeypatch):
    source = make_trusted_quote()
    invalid = generated_quote_payload(speaker="错误角色")
    install_chat_responses(
        monkeypatch,
        [json.dumps(invalid, ensure_ascii=False), json.dumps(invalid, ensure_ascii=False)],
    )
    provider = HttpQuizAiProvider(make_configuration())

    with pytest.raises(RuntimeError, match="正确答案与可信资料不一致"):
        provider.generate_questions(
            chunks=[source],
            file_names={},
            single_count=1,
            multiple_count=0,
            short_count=0,
            difficulty="medium",
            generation_number=0,
            recent_chunk_ids=set(),
            source_mode="material",
            generation_theme="classic_quotes",
            theme_requirements="仅围绕可信台词出题",
            allowed_question_subtypes=["quote_speaker"],
        )


def test_mock_provider_respects_selected_quote_angle():
    source = make_trusted_quote()
    questions = MockQuizAiProvider().generate_questions(
        chunks=[source],
        file_names={},
        single_count=1,
        multiple_count=0,
        short_count=0,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
        source_mode="material",
        generation_theme="classic_quotes",
        allowed_question_subtypes=["quote_meaning"],
    )

    assert questions[0].question_subtype == "quote_meaning"


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
    provider.set_question_position(2)

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
    assert events[0].question_position == 2
    assert [message["role"] for message in events[0].request_messages] == ["system", "user"]
    assert events[0].model_response == json.dumps(payload, ensure_ascii=False)


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
    assert "不要让考生回答台词或情节出自哪一集" in requests[0]["json"]["messages"][1]["content"]


def test_http_provider_renders_regeneration_context(monkeypatch):
    chunks = make_chunks()
    payload = generated_payload([chunk.id for chunk in chunks])
    payload["questions"] = [payload["questions"][0]]
    requests = install_chat_responses(monkeypatch, [json.dumps(payload, ensure_ascii=False)])
    provider = HttpQuizAiProvider(make_configuration())

    provider.generate_questions(
        chunks=chunks,
        file_names={"pdf-1": "复习材料.pdf"},
        single_count=1,
        multiple_count=0,
        short_count=0,
        difficulty="medium",
        generation_number=0,
        recent_chunk_ids=set(),
        question_exclusions=[
            {
                "role": "current_question",
                "position": 1,
                "question_type": "single",
                "prompt": "原题干",
                "knowledge_point": "原知识点",
                "source_chunk_ids": ["chunk-1"],
            }
        ],
        regeneration_guidance="请换一个角度重出题目。",
    )

    prompt = requests[0]["json"]["messages"][1]["content"]
    assert "请换一个角度重出题目。" in prompt
    assert "原题干" in prompt


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


def test_http_provider_grades_model_knowledge_answer_without_pdf_evidence(monkeypatch):
    grade_payload = {
        "score": 12,
        "feedback": "回答覆盖了主要情节。",
        "matched_points": ["说明回信方式"],
        "missing_points": [],
    }
    requests = install_chat_responses(
        monkeypatch, [json.dumps(grade_payload, ensure_ascii=False)]
    )
    provider = HttpQuizAiProvider(make_configuration())
    quiz = Quiz(
        id="quiz-model-knowledge",
        book_id="book-1",
        title="模型知识试卷",
        source_mode="model_knowledge",
    )
    question = Question(
        id="question-model-knowledge",
        quiz=quiz,
        position=1,
        question_type="short",
        prompt="浪矢杂货店如何回应咨询？",
        options=[],
        correct_answers=[],
        explanation="依据模型知识生成。",
        knowledge_point="回信方式",
        estimated_seconds=180,
        reference_answer="通过书信回应投递到牛奶箱中的咨询。",
        grading_rubric=[
            {"point": "说明回信方式", "keywords": ["书信"], "score": 20}
        ],
        source_chunk_ids=[],
        source_evidence=[],
        max_score=20,
    )

    provider.grade_short_answer(question, "店主会认真写回信来回应咨询。")

    prompt = requests[0]["json"]["messages"][1]["content"]
    assert "model_knowledge" in prompt
    assert "原文依据：[]" in prompt
