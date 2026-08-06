from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any, Iterable


QUIZ_TOTAL_SCORE = 100.0
QUESTION_TYPE_WEIGHTS = {
    "single": Decimal("6"),
    "multiple": Decimal("10"),
    "short": Decimal("20"),
}


def _allocate_weighted_scores(
    weights: list[Decimal], total_score: float, decimal_places: int
) -> list[float]:
    if not weights or any(weight <= 0 for weight in weights):
        raise ValueError("分值权重必须是非空的正数列表")
    scale = 10**decimal_places
    total_units = int(
        (Decimal(str(total_score)) * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    if total_units <= 0:
        raise ValueError("试卷总分必须大于零")

    total_weight = sum(weights)
    exact_units = [Decimal(total_units) * weight / total_weight for weight in weights]
    allocated_units = [
        int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in exact_units
    ]
    remaining_units = total_units - sum(allocated_units)
    priority = sorted(
        range(len(weights)),
        key=lambda index: (
            exact_units[index] - allocated_units[index],
            weights[index],
            -index,
        ),
        reverse=True,
    )
    for index in priority[:remaining_units]:
        allocated_units[index] += 1
    return [units / scale for units in allocated_units]


def allocate_question_scores(
    question_types: Iterable[str], total_score: float = QUIZ_TOTAL_SCORE
) -> list[float]:
    types = list(question_types)
    try:
        weights = [QUESTION_TYPE_WEIGHTS[question_type] for question_type in types]
    except KeyError as exc:
        raise ValueError(f"不支持的题型：{exc.args[0]}") from exc
    return _allocate_weighted_scores(weights, total_score, decimal_places=1)


def normalize_rubric_scores(
    grading_rubric: list[dict[str, Any]], max_score: float
) -> list[dict[str, Any]]:
    if not grading_rubric:
        return []
    weights: list[Decimal] = []
    for item in grading_rubric:
        try:
            weight = Decimal(str(item.get("score", 0)))
        except (InvalidOperation, ValueError):
            weight = Decimal("0")
        weights.append(weight if weight > 0 else Decimal("1"))
    scores = _allocate_weighted_scores(weights, max_score, decimal_places=2)
    return [
        {**item, "score": score}
        for item, score in zip(grading_rubric, scores, strict=True)
    ]
