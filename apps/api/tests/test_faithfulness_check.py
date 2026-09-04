"""Unit tests for the rule-based faithfulness check."""

from __future__ import annotations

from app.services.faithfulness_check import (
    check_question_faithfulness,
    source_text_for_question,
)


def test_paraphrased_answer_passes():
    result = check_question_faithfulness(
        explanation="原文强调合上书本后主动提取。",
        correct_answers_text="合上书本主动提取",
        answer_signature=[],
        source_text="主动回忆要求读者合上书本，用自己的语言从记忆中提取核心内容。",
    )

    assert result.passed is True


def test_speaker_name_from_metadata_passes():
    result = check_question_faithfulness(
        explanation="可信资料明确记录了说话人。",
        correct_answers_text="吴站长",
        answer_signature=[],
        source_text="会议现在开始\n吴站长\n吴站长在站内会议上宣布开始",
    )

    assert result.passed is True


def test_fabricated_answer_is_rejected():
    result = check_question_faithfulness(
        explanation="这是一段完全虚构的内容，讲述了主角发明了时间机器。",
        correct_answers_text="时间机器",
        answer_signature=[],
        source_text="会议现在开始\n吴站长\n吴站长在站内会议上宣布开始",
    )

    assert result.passed is False
    assert result.severity == "fail"


def test_low_lexical_overlap_paraphrase_is_a_warning_not_a_failure():
    result = check_question_faithfulness(
        explanation="她把对方的要求理解为嫌弃自己，因此用反问表达不满。",
        correct_answers_text="觉得被嫌弃",
        answer_signature=["表达不满"],
        source_text="什么任务，不就是嫌我脏吗？\n翠平\n茅房里有热水壶、有盆，把脚也洗一洗。",
    )

    assert result.passed is True
    assert result.severity == "warning"
    assert result.is_warning is True


def test_empty_source_text_always_passes():
    result = check_question_faithfulness(
        explanation="任意解析文本",
        correct_answers_text="任意答案",
        answer_signature=[],
        source_text="",
    )

    assert result.passed is True


def test_source_text_for_question_includes_speaker_and_context():
    class FakeSource:
        content = "会议现在开始"
        speaker = "吴站长"
        context = "吴站长在站内会议上宣布开始"

    text = source_text_for_question({}, {"quote-1": FakeSource()}, ["quote-1"])

    assert "会议现在开始" in text
    assert "吴站长" in text
    assert "在站内会议上宣布开始" in text


def test_source_text_for_question_skips_missing_sources():
    text = source_text_for_question({}, {}, ["missing-id"])

    assert text == ""
