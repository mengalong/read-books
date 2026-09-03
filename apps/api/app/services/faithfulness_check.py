"""Rule-based faithfulness check for generated questions.

This is a lightweight guard against fabricated facts that runs *after* the existing
ID-existence and quote-verbatim checks in `quiz_provider._validate_questions`. It never
replaces those checks; it only adds an extra layer that flags questions whose answer-bearing
fields (explanation, correct answer text, answer_signature) look almost entirely disconnected
from the source text the question claims to be based on.

Approach: reuse the same bigram/trigram overlap strategy as `question_dedup.token_similarity`
(proven for this codebase's Chinese text) to measure how much of the answer text's vocabulary
also appears in the cited source. Explanations are expected to paraphrase rather than quote
verbatim, so this only flags a very low overlap ratio (near-zero shared vocabulary), which is
a strong signal that the answer references content absent from the cited source. This
intentionally avoids a second model call, per the confirmed lightweight design.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.question_dedup import token_similarity

# 说明：正常题目的 explanation/答案是对原文的复述而非逐字摘录，其与原文的
# bigram/trigram Jaccard 重合度通常在 0.05~0.15 区间（例如"原文强调合上书本后
# 主动提取"复述"合上书本，用自己的语言从记忆中提取核心内容"约为 0.07~0.09）；
# 而完全捏造、与原文毫无关系的内容重合度普遍低于 0.02。阈值设为 0.03，
# 只拦截“几乎完全不沾边”的极端捏造，避免误伤正常的合理复述。
MIN_OVERLAP_RATIO = 0.03


@dataclass(frozen=True)
class FaithfulnessResult:
    passed: bool
    overlap_ratio: float


def check_question_faithfulness(
    *,
    explanation: str,
    correct_answers_text: str,
    answer_signature: list[str],
    source_text: str,
) -> FaithfulnessResult:
    """Check whether answer-bearing fields share meaningful vocabulary with `source_text`.

    `source_text` should be the concatenation of every source chunk/quote the question
    actually cites (i.e. exactly what was already validated as an existing, in-pool source),
    never the understanding-layer summary. Returns `passed=True` when there is nothing to
    check (empty source or empty answer text); otherwise flags the question when its
    combined answer text shares almost no vocabulary overlap with the cited source, which
    indicates the explanation/answer likely references content not present in that source.
    """
    if not source_text.strip():
        return FaithfulnessResult(passed=True, overlap_ratio=1.0)
    answer_text = " ".join(
        part for part in (explanation, correct_answers_text, " ".join(answer_signature)) if part
    ).strip()
    if not answer_text:
        return FaithfulnessResult(passed=True, overlap_ratio=1.0)
    ratio = token_similarity(answer_text, source_text)
    return FaithfulnessResult(passed=ratio >= MIN_OVERLAP_RATIO, overlap_ratio=ratio)


def source_text_for_question(
    raw: dict,
    chunks_by_id: dict,
    source_ids: list[str],
) -> str:
    """Concatenate the content of every already-validated source this question cites."""
    parts: list[str] = []
    for source_id in source_ids:
        source = chunks_by_id.get(source_id)
        if source is None:
            continue
        content = getattr(source, "content", None)
        if content:
            parts.append(str(content))
        # 说话人题（quote_speaker 等子类型）的答案是说话人姓名，姓名本身只存在于
        # `speaker` 元数据字段里，不会出现在 `content` 正文文本中；`context` 同理是
        # 台词的场景/上下文说明。两者都属于该来源本身携带的可信信息，一并纳入比对
        # 文本，避免把“答案取自元数据而非正文”误判为捏造。
        speaker = getattr(source, "speaker", None)
        if speaker:
            parts.append(str(speaker))
        context = getattr(source, "context", None)
        if context:
            parts.append(str(context))
    return "\n".join(parts)
