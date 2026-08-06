import pytest

from app.services.score_allocation import (
    allocate_question_scores,
    normalize_rubric_scores,
)


def test_default_question_counts_keep_existing_type_scores():
    question_types = ["single"] * 5 + ["multiple"] * 3 + ["short"] * 2

    scores = allocate_question_scores(question_types)

    assert scores == [6.0] * 5 + [10.0] * 3 + [20.0] * 2
    assert sum(scores) == pytest.approx(100)


def test_custom_question_counts_are_normalized_to_one_hundred():
    scores = allocate_question_scores(["single", "multiple", "short"])

    assert scores == [16.7, 27.8, 55.5]
    assert sum(scores) == pytest.approx(100)
    assert allocate_question_scores(["single"] * 3) == [33.4, 33.3, 33.3]


def test_short_answer_rubric_keeps_proportions_after_score_allocation():
    rubric = [
        {"point": "要点一", "keywords": ["一"], "score": 6},
        {"point": "要点二", "keywords": ["二"], "score": 4},
    ]

    normalized = normalize_rubric_scores(rubric, 55.5)

    assert [item["score"] for item in normalized] == [33.3, 22.2]
    assert sum(item["score"] for item in normalized) == pytest.approx(55.5)
