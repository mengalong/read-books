from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, MutableMapping
from typing import Any


SIGNATURE_FIELDS = (
    "fact_claim",
    "fact_subject",
    "fact_relation",
    "fact_context",
    "answer_signature",
    "question_intent",
)

_QUESTION_NOISE_PATTERNS = (
    re.compile(r"(?:在)?(?:电视剧|电影|小说)《[^》]+》(?:中|里)?"),
    re.compile(r"(?:根据|结合)(?:第?\d+页|原文|材料|资料)[^，。；：:]*[，。；：:]?"),
    re.compile(r"(?:下列|以下)(?:哪一项|哪些|哪种|哪句话|哪种说法)[^？?：:]*[？?：:]?"),
    re.compile(r"(?:请问|请判断|请说明|请概括|关于|正确的是|错误的是)"),
)

_PRECISE_LOCATION_PATTERNS = (
    re.compile(r"(?:哪一集|第几集|哪一话|第几话|哪一章|第几章)"),
    re.compile(r"(?:出自|来自|发生在|出现于|位于)[^？?。；\n]{0,18}(?:第?\d+集|哪一集|第几集|哪一话|哪一章)"),
    re.compile(r"(?:具体|准确|精确)(?:时间|时间点|时间码|集数|出处|位置)"),
    re.compile(r"(?:哪分钟|几分几秒|第?\d+分(?:钟)?(?:第?\d+秒)?)"),
)

_PRECISE_LOCATION_RELATIONS = {
    "集数",
    "哪一集",
    "第几集",
    "时间点",
    "时间码",
    "出处位置",
    "来源位置",
    "episode",
    "episode_number",
    "timestamp",
    "timecode",
}


def normalize_fact_text(value: Any) -> str:
    """Normalize Chinese fact fields without attempting to rewrite their meaning."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[\u0000-\u001f]", "", text)
    return text.strip(" \t\r\n，。；：:、,;!?！？（）()[]【】{}\"'‘’“”")


def _meaningful_prompt_text(value: str) -> str:
    text = normalize_fact_text(value)
    for pattern in _QUESTION_NOISE_PATTERNS:
        text = pattern.sub("", text)
    return text


def _ngrams(value: str, sizes: tuple[int, ...] = (2, 3)) -> set[str]:
    text = _meaningful_prompt_text(value)
    tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text))
    for size in sizes:
        tokens.update(
            text[index : index + size]
            for index in range(max(0, len(text) - size + 1))
            if len(text[index : index + size]) == size
        )
    return tokens


def question_keywords(*values: Any) -> set[str]:
    """Extract keyword tokens usable for a lightweight relevance pre-filter.

    Chinese text has no whitespace between words, so a simple regex split would
    return one giant token per phrase. Reuse the bigram/trigram strategy from the
    fact-signature similarity check, but keep only 3-character-and-longer tokens:
    single characters and common two-character function words (e.g. "的", "是")
    would otherwise overlap between almost any two unrelated Chinese sentences.
    """
    keywords: set[str] = set()
    for value in values:
        if not value:
            continue
        keywords.update(token for token in _ngrams(str(value), sizes=(3,)) if len(token) >= 3)
    return keywords


def token_similarity(left: str, right: str) -> float:
    left_tokens = _ngrams(left)
    right_tokens = _ngrams(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def asks_for_precise_location(
    prompt: Any,
    *,
    fact_relation: Any = "",
    question_intent: Any = "",
) -> bool:
    """Return whether a question asks the user to recall an exact source location."""
    prompt_text = normalize_fact_text(prompt)
    if any(pattern.search(prompt_text) for pattern in _PRECISE_LOCATION_PATTERNS):
        return True
    relation = normalize_fact_text(fact_relation)
    intent = normalize_fact_text(question_intent)
    return relation in _PRECISE_LOCATION_RELATIONS or intent in _PRECISE_LOCATION_RELATIONS


def _as_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [normalize_fact_text(item) for item in value if normalize_fact_text(item)]
    if value is None:
        return []
    normalized = normalize_fact_text(value)
    return [normalized] if normalized else []


def _get_value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def build_question_signature(
    source: Any,
    *,
    prompt: str | None = None,
    options: list[dict[str, Any]] | None = None,
    correct_answers: list[str] | None = None,
    reference_answer: str | None = None,
    knowledge_point: str | None = None,
) -> dict[str, Any]:
    """Build a stable, explainable signature for the fact a question tests.

    Explicit model fields are preferred. Older prompts remain compatible by falling
    back to the question text, answer options and knowledge point.
    """
    prompt_value = prompt if prompt is not None else _get_value(source, "prompt", "")
    options_value = options if options is not None else _get_value(source, "options", [])
    correct_value = (
        correct_answers
        if correct_answers is not None
        else _get_value(source, "correct_answers", [])
    )
    reference_value = (
        reference_answer
        if reference_answer is not None
        else _get_value(source, "reference_answer", "")
    )
    knowledge_value = (
        knowledge_point
        if knowledge_point is not None
        else _get_value(source, "knowledge_point", "")
    )

    semantic_signature = _get_value(source, "semantic_signature", {})
    if not isinstance(semantic_signature, Mapping):
        semantic_signature = {}

    def signature_value(name: str) -> Any:
        return _get_value(source, name, "") or semantic_signature.get(name, "")

    fact_claim = normalize_fact_text(
        signature_value("fact_claim") or _meaningful_prompt_text(prompt_value or "")
    )
    fact_subject = normalize_fact_text(signature_value("fact_subject"))
    fact_relation = normalize_fact_text(signature_value("fact_relation"))
    fact_context = normalize_fact_text(signature_value("fact_context"))
    question_intent = normalize_fact_text(signature_value("question_intent"))

    option_by_id = {
        str(option.get("id")): str(option.get("text", ""))
        for option in options_value or []
        if isinstance(option, Mapping) and option.get("id") is not None
    }
    answer_signature = _as_list(signature_value("answer_signature"))
    if not answer_signature:
        answer_signature = _as_list(
            [option_by_id.get(str(answer), str(answer)) for answer in correct_value or []]
        )
    if not answer_signature and reference_value:
        answer_signature = _as_list(reference_value)

    # Keep the fallback claim useful for old model prompts while excluding common
    # question-shell words that should not distinguish two facts.
    if not fact_subject:
        fact_subject = normalize_fact_text(_get_value(source, "knowledge_point", ""))
    if not fact_relation:
        fallback_relation = normalize_fact_text(_get_value(source, "question_subtype", ""))
        fact_relation = "" if fallback_relation == "general" else fallback_relation
    if not fact_context:
        fact_context = normalize_fact_text(knowledge_value or "")

    key_parts = [
        fact_subject,
        fact_relation,
        fact_context,
        *sorted(answer_signature),
    ]
    # Always derive the cache key locally. A model-provided key must not be able
    # to opt a candidate out of duplicate detection.
    fact_key = "|".join(part for part in key_parts if part)[:1_000]
    if not fact_key:
        fact_key = fact_claim[:1_000]

    return {
        "fact_claim": fact_claim[:1_000],
        "fact_subject": fact_subject[:300],
        "fact_relation": fact_relation[:300],
        "fact_context": fact_context[:500],
        "answer_signature": answer_signature[:8],
        "question_intent": question_intent[:120],
        "fact_key": fact_key,
    }


def signature_for_question(source: Any) -> dict[str, Any]:
    return build_question_signature(source)


def refresh_question_signature(source: Any) -> dict[str, Any]:
    """Rebuild and persist the derived fact fields on a question-like object."""
    signature = build_question_signature(source)
    values = {
        "fact_key": signature["fact_key"],
        "fact_claim": signature["fact_claim"],
        "semantic_signature": signature,
    }
    if isinstance(source, MutableMapping):
        source.update(values)
    else:
        for name, value in values.items():
            setattr(source, name, value)
    return signature


def _answer_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_answers = set(_as_list(left.get("answer_signature")))
    right_answers = set(_as_list(right.get("answer_signature")))
    if not left_answers or not right_answers:
        return 0.0
    return len(left_answers & right_answers) / len(left_answers | right_answers)


def questions_test_same_fact(left: Any, right: Any) -> bool:
    left_signature = signature_for_question(left)
    right_signature = signature_for_question(right)
    left_key = left_signature["fact_key"]
    right_key = right_signature["fact_key"]
    if left_key and right_key and left_key == right_key:
        return True

    subject_match = bool(
        left_signature["fact_subject"]
        and right_signature["fact_subject"]
        and left_signature["fact_subject"] == right_signature["fact_subject"]
    )
    relation_match = bool(
        left_signature["fact_relation"]
        and right_signature["fact_relation"]
        and left_signature["fact_relation"] == right_signature["fact_relation"]
    )
    answer_similarity = _answer_similarity(left_signature, right_signature)
    context_similarity = token_similarity(
        left_signature["fact_context"], right_signature["fact_context"]
    )
    claim_similarity = token_similarity(
        left_signature["fact_claim"], right_signature["fact_claim"]
    )

    if subject_match and relation_match and (
        answer_similarity >= 0.5 or context_similarity >= 0.42
    ):
        return True
    if answer_similarity >= 0.5 and claim_similarity >= 0.48:
        return True
    return claim_similarity >= 0.72 and (
        subject_match or relation_match or answer_similarity >= 0.34
    )
