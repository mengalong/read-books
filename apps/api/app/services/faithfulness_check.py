"""Lightweight source-support signal for generated questions.

Lexical overlap is useful for spotting answers that are completely unrelated to a cited
source, but it is not a semantic truth oracle. In particular, a good explanation may
naturally paraphrase a line of dialogue and therefore share few characters with it. The
result deliberately distinguishes a hard failure from a review warning so that traceability
and attribution checks remain strict without rejecting reasonable paraphrases.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.question_dedup import token_similarity

# 0.03 仍然是“词面支持充分”的参考线；0.01 以下才视为几乎完全无关。
# 中间区间保留为 warning，交给来源/说话人/事实去重等更强约束共同判断。
MIN_OVERLAP_RATIO = 0.03
HARD_FAIL_OVERLAP_RATIO = 0.01


@dataclass(frozen=True)
class FaithfulnessResult:
    passed: bool
    overlap_ratio: float
    severity: str = "pass"
    reason: str | None = None

    @property
    def is_warning(self) -> bool:
        return self.severity == "warning"


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
    if ratio < HARD_FAIL_OVERLAP_RATIO:
        return FaithfulnessResult(
            passed=False,
            overlap_ratio=ratio,
            severity="fail",
            reason="答案与引用来源几乎没有词面或事实线索重合",
        )
    if ratio < MIN_OVERLAP_RATIO:
        return FaithfulnessResult(
            passed=True,
            overlap_ratio=ratio,
            severity="warning",
            reason="答案可能是对引用来源的语义转述，词面重合较低，请人工抽查",
        )
    return FaithfulnessResult(passed=True, overlap_ratio=ratio)


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
