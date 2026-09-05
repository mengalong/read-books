from types import SimpleNamespace

from app.services.quiz_generation import (
    HISTORICAL_FACT_PROMPT_LIMIT,
    _historical_question_exclusions,
    _question_exclusion_payload,
    _source_focus_for_question,
)
from app.models import ContentChunk
from app.services.quiz_provider import TrustedQuoteSource


def make_question(index: int, *, topic: str = "主动回忆") -> SimpleNamespace:
    return SimpleNamespace(
        position=index,
        question_type="single",
        question_subtype="general",
        prompt=f"第 {index} 题：{topic}的关键事实是什么？",
        options=[{"id": "A", "text": "合上书本主动提取"}],
        correct_answers=["A"],
        explanation="说明核心事实",
        knowledge_point=topic,
        reference_answer=None,
        source_chunk_ids=[f"chunk-{index}"],
        quote_entry_ids=[],
        fact_key=f"人物|行为|{topic}|合上书本主动提取-{index}",
        fact_claim=f"{topic}需要主动提取",
        semantic_signature={
            "fact_key": f"人物|行为|{topic}|合上书本主动提取-{index}",
            "fact_claim": f"{topic}需要主动提取",
            "fact_subject": topic,
            "fact_relation": "需要",
            "fact_context": "复习过程",
            "answer_signature": ["合上书本主动提取"],
        },
    )


def test_question_exclusion_payload_is_compact():
    payload = _question_exclusion_payload(make_question(1))

    assert payload["fact_claim"] == "主动回忆需要主动提取"
    assert payload["answer_signature"] == ["合上书本主动提取"]
    assert "prompt" not in payload
    assert "source_chunk_ids" not in payload
    assert "semantic_signature" not in payload


def test_historical_exclusions_are_relevant_and_capped():
    questions = [make_question(index, topic="间隔练习" if index == 1 else f"主题{index}") for index in range(1, 20)]

    exclusions = _historical_question_exclusions(questions, relevance_text="间隔练习如何安排复习节奏")

    assert len(exclusions) <= HISTORICAL_FACT_PROMPT_LIMIT
    assert exclusions[0]["fact_claim"] == "间隔练习需要主动提取"


def test_combined_source_focus_defaults_to_seventy_twenty_ten():
    content = ContentChunk(
        id="chunk-1",
        book_id="book-1",
        pdf_id="pdf-1",
        page_number=1,
        sequence=1,
        content="剧情内容",
        char_count=4,
    )
    quote = TrustedQuoteSource(
        id="quote-1",
        material_id="material-1",
        file_name="台词.csv",
        material_type="quote_sheet",
        content="一条台词",
        source_segment_ids=[],
    )
    focuses = [
        _source_focus_for_question("combined", [content, quote], position, 10)
        for position in range(1, 11)
    ]

    assert focuses == ["content"] * 7 + ["dialogue"] * 2 + ["integrated"]
