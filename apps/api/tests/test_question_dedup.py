from __future__ import annotations

from types import SimpleNamespace

from app.services.question_dedup import build_question_signature, questions_test_same_fact


def option_payload(answer: str) -> list[dict[str, str]]:
    return [
        {"id": "A", "text": answer},
        {"id": "B", "text": "地下党交通员"},
        {"id": "C", "text": "国民党军官"},
        {"id": "D", "text": "普通商人"},
    ]


def test_deduplicates_different_wording_for_same_fact_without_model_fields():
    first = SimpleNamespace(
        question_type="single",
        question_subtype="general",
        prompt="在电视剧《潜伏》中，组织上派翠平到天津与余则成假扮夫妻时，翠平此前在游击队中的主要身份是？",
        options=option_payload("游击队队员"),
        correct_answers=["A"],
        knowledge_point="人物身份",
        reference_answer=None,
    )
    second = SimpleNamespace(
        question_type="single",
        question_subtype="general",
        prompt="在电视剧《潜伏》中，余则成与翠平假扮夫妻执行潜伏任务，翠平的真实身份是什么？",
        options=option_payload("游击队队员"),
        correct_answers=["A"],
        knowledge_point="人物身份",
        reference_answer=None,
    )

    first_signature = build_question_signature(first)
    second_signature = build_question_signature(second)

    assert first_signature["fact_key"] == second_signature["fact_key"]
    assert questions_test_same_fact(first, second)


def test_keeps_same_subject_questions_when_relation_and_answer_differ():
    identity = {
        "fact_claim": "翠平在假扮夫妻任务前的真实身份",
        "fact_subject": "翠平",
        "fact_relation": "身份",
        "fact_context": "天津假扮夫妻任务",
        "answer_signature": ["游击队队员"],
        "question_intent": "identity",
    }
    relationship = {
        "fact_claim": "翠平与余则成在任务中的关系",
        "fact_subject": "翠平",
        "fact_relation": "人物关系",
        "fact_context": "天津假扮夫妻任务",
        "answer_signature": ["工作搭档"],
        "question_intent": "relation",
    }

    assert not questions_test_same_fact(identity, relationship)


def test_same_fact_detected_when_context_wording_varies():
    first = {
        "fact_claim": "翠平在天津执行假扮夫妻潜伏任务前的真实身份",
        "fact_subject": "翠平",
        "fact_relation": "身份",
        "fact_context": "天津与余则成假扮夫妻",
        "answer_signature": ["游击队身份"],
        "question_intent": "identity",
    }
    second = {
        "fact_claim": "翠平成为余则成妻子潜入天津之前的身份",
        "fact_subject": "翠平",
        "fact_relation": "身份",
        "fact_context": "余则成翠平假扮夫妻执行潜伏",
        "answer_signature": ["游击队身份"],
        "question_intent": "identity",
    }

    assert questions_test_same_fact(first, second)
