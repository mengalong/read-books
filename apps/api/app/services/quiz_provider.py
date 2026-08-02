from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings
from app.models import ContentChunk, Question


@dataclass
class GeneratedQuestion:
    question_type: str
    prompt: str
    options: list[dict[str, str]]
    correct_answers: list[str]
    explanation: str
    knowledge_point: str
    estimated_seconds: int
    reference_answer: str | None
    grading_rubric: list[dict[str, Any]]
    source_chunk_ids: list[str]
    source_evidence: list[dict[str, Any]]
    max_score: float


@dataclass
class GradeResult:
    score: float
    is_correct: bool
    feedback: str
    matched_points: list[str]
    missing_points: list[str]


class QuizAiProvider(Protocol):
    def generate_questions(
        self,
        chunks: list[ContentChunk],
        file_names: dict[str, str],
        single_count: int,
        multiple_count: int,
        short_count: int,
        difficulty: str,
        generation_number: int,
        recent_chunk_ids: set[str],
    ) -> list[GeneratedQuestion]: ...

    def grade_short_answer(self, question: Question, answer: str) -> GradeResult: ...


def compact_text(text: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean if len(clean) <= limit else f"{clean[:limit].rstrip()}……"


def split_claims(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[。！？；\n]", text) if len(part.strip()) >= 8]
    if len(parts) >= 2:
        return [compact_text(part, 80) for part in parts]
    clean = compact_text(text, 140)
    midpoint = max(1, len(clean) // 2)
    return [clean[:midpoint], clean[midpoint:]]


def knowledge_point(text: str) -> str:
    first = re.split(r"[，。；：]", compact_text(text, 80))[0]
    return first[:18] or "原文核心观点"


def rubric_from_text(text: str, max_score: float) -> list[dict[str, Any]]:
    claims = split_claims(text)[:3]
    point_score = round(max_score / max(len(claims), 1), 2)
    rubrics: list[dict[str, Any]] = []
    for index, claim in enumerate(claims):
        phrases = re.findall(r"[\u4e00-\u9fff]{2,8}", claim)
        keywords = [phrase for phrase in phrases if phrase not in {"不是", "一个", "可以"}]
        rubrics.append(
            {
                "point": claim,
                "keywords": keywords[:4] or [claim[:6]],
                "score": point_score if index < len(claims) - 1 else round(
                    max_score - point_score * (len(claims) - 1), 2
                ),
            }
        )
    return rubrics


class MockQuizAiProvider:
    def generate_questions(
        self,
        chunks: list[ContentChunk],
        file_names: dict[str, str],
        single_count: int,
        multiple_count: int,
        short_count: int,
        difficulty: str,
        generation_number: int,
        recent_chunk_ids: set[str],
    ) -> list[GeneratedQuestion]:
        if not chunks:
            return []

        fresh = [chunk for chunk in chunks if chunk.id not in recent_chunk_ids]
        repeated = [chunk for chunk in chunks if chunk.id in recent_chunk_ids]
        random.Random(generation_number).shuffle(fresh)
        random.Random(generation_number + 97).shuffle(repeated)
        pool = fresh + repeated
        total = single_count + multiple_count + short_count
        chosen = [pool[index % len(pool)] for index in range(total)]

        questions: list[GeneratedQuestion] = []
        cursor = 0
        for index in range(single_count):
            chunk = chosen[cursor]
            cursor += 1
            questions.append(
                self._single_question(chunk, pool, file_names, index + generation_number)
            )
        for index in range(multiple_count):
            chunk = chosen[cursor]
            cursor += 1
            questions.append(
                self._multiple_question(chunk, pool, file_names, index + generation_number)
            )
        for _ in range(short_count):
            chunk = chosen[cursor]
            cursor += 1
            questions.append(self._short_question(chunk, file_names))
        return questions

    def _evidence(
        self, chunk: ContentChunk, file_names: dict[str, str]
    ) -> list[dict[str, Any]]:
        return [
            {
                "chunk_id": chunk.id,
                "file_name": file_names[chunk.pdf_id],
                "page_number": chunk.page_number,
                "excerpt": compact_text(chunk.content, 500),
                "support": "题目与答案均由该段原文直接提炼，未使用原文之外的信息。",
            }
        ]

    def _distractors(self, source: ContentChunk, pool: list[ContentChunk]) -> list[str]:
        candidates = [
            compact_text(chunk.content, 74)
            for chunk in pool
            if chunk.id != source.id and compact_text(chunk.content, 74)
        ]
        fallbacks = [
            "原文认为熟悉材料就等同于已经牢固掌握",
            "原文主张所有内容都应采用完全相同的复习节奏",
            "原文建议脱离材料依据来补全更合理的答案",
        ]
        return (candidates + fallbacks)[:3]

    def _single_question(
        self,
        chunk: ContentChunk,
        pool: list[ContentChunk],
        file_names: dict[str, str],
        offset: int,
    ) -> GeneratedQuestion:
        correct = compact_text(chunk.content, 88)
        raw_options = [correct, *self._distractors(chunk, pool)]
        shift = offset % len(raw_options)
        raw_options = raw_options[shift:] + raw_options[:shift]
        option_ids = ["A", "B", "C", "D"]
        options = [
            {"id": option_id, "text": text}
            for option_id, text in zip(option_ids, raw_options, strict=True)
        ]
        correct_id = option_ids[raw_options.index(correct)]
        return GeneratedQuestion(
            question_type="single",
            prompt=f"根据第 {chunk.page_number} 页的论述，下列哪一项最准确？",
            options=options,
            correct_answers=[correct_id],
            explanation="正确选项是原文观点的直接表述，其余选项来自其他语境或与本段意思相反。",
            knowledge_point=knowledge_point(chunk.content),
            estimated_seconds=45,
            reference_answer=None,
            grading_rubric=[],
            source_chunk_ids=[chunk.id],
            source_evidence=self._evidence(chunk, file_names),
            max_score=6,
        )

    def _multiple_question(
        self,
        chunk: ContentChunk,
        pool: list[ContentChunk],
        file_names: dict[str, str],
        offset: int,
    ) -> GeneratedQuestion:
        correct_claims = split_claims(chunk.content)[:2]
        distractors = self._distractors(chunk, pool)[:2]
        tagged = [(claim, True) for claim in correct_claims] + [
            (claim, False) for claim in distractors
        ]
        random.Random(offset * 17).shuffle(tagged)
        options = [
            {"id": option_id, "text": text}
            for option_id, (text, _) in zip(["A", "B", "C", "D"], tagged, strict=True)
        ]
        correct_answers = [
            option["id"] for option, (_, is_correct) in zip(options, tagged, strict=True) if is_correct
        ]
        return GeneratedQuestion(
            question_type="multiple",
            prompt=f"结合第 {chunk.page_number} 页原文，以下哪些表述有直接依据？",
            options=options,
            correct_answers=correct_answers,
            explanation="正确选项均可在该页原文中直接定位；多选或漏选都会影响得分。",
            knowledge_point=knowledge_point(chunk.content),
            estimated_seconds=90,
            reference_answer=None,
            grading_rubric=[],
            source_chunk_ids=[chunk.id],
            source_evidence=self._evidence(chunk, file_names),
            max_score=10,
        )

    def _short_question(
        self, chunk: ContentChunk, file_names: dict[str, str]
    ) -> GeneratedQuestion:
        reference = compact_text(chunk.content, 300)
        return GeneratedQuestion(
            question_type="short",
            prompt=f"请用自己的话概括第 {chunk.page_number} 页这段内容的核心观点，并说明关键理由。",
            options=[],
            correct_answers=[],
            explanation="评分关注是否覆盖原文核心观点及其关键理由，不要求逐字复述。",
            knowledge_point=knowledge_point(chunk.content),
            estimated_seconds=180,
            reference_answer=reference,
            grading_rubric=rubric_from_text(reference, 20),
            source_chunk_ids=[chunk.id],
            source_evidence=self._evidence(chunk, file_names),
            max_score=20,
        )

    def grade_short_answer(self, question: Question, answer: str) -> GradeResult:
        answer = answer.strip()
        if not answer:
            points = [str(item["point"]) for item in question.grading_rubric]
            return GradeResult(0, False, "本题未作答。", [], points)

        matched: list[str] = []
        missing: list[str] = []
        score = 0.0
        for item in question.grading_rubric:
            point = str(item["point"])
            keywords = [str(keyword) for keyword in item.get("keywords", [])]
            if any(keyword in answer for keyword in keywords):
                matched.append(point)
                score += float(item.get("score", 0))
            else:
                missing.append(point)

        # Mock 评分为合理的同义改写留出一部分表达分；真实 Provider 将做语义评分。
        if len(answer) >= 30:
            score += question.max_score * 0.15
        score = round(min(question.max_score, score), 1)
        ratio = score / question.max_score if question.max_score else 0
        if ratio >= 0.8:
            feedback = "回答覆盖了主要观点，结构也比较完整。"
        elif ratio >= 0.5:
            feedback = "回答抓住了部分核心内容，仍可结合缺失要点补充。"
        else:
            feedback = "回答与原文要点的重合较少，建议对照参考答案重新组织。"
        return GradeResult(score, ratio >= 0.8, feedback, matched, missing)


class HttpQuizAiProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _not_configured(self) -> RuntimeError:
        return RuntimeError(
            "真实模型 Provider 尚未启用，请将 MOCK_MODE 设为 true，或完成模型协议适配"
        )

    def generate_questions(self, *args: Any, **kwargs: Any) -> list[GeneratedQuestion]:
        raise self._not_configured()

    def grade_short_answer(self, question: Question, answer: str) -> GradeResult:
        raise self._not_configured()


def get_quiz_provider(settings: Settings) -> QuizAiProvider:
    if settings.mock_mode:
        return MockQuizAiProvider()
    return HttpQuizAiProvider(settings)
