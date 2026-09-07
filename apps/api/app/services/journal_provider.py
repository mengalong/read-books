from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from time import perf_counter
from typing import Any

import httpx

from app.config import Settings
from app.services.model_config import EffectiveModelConfiguration
from app.services.model_usage import (
    ModelUsageContext,
    ModelUsageEvent,
    record_model_usage,
    token_counts,
)
from app.services.quiz_provider import extract_response_text, parse_json_object


ITEM_TYPES = {"todo", "idea", "want_read", "want_watch"}


@dataclass(frozen=True)
class JournalOrganization:
    journal_text: str
    highlights: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)


def _compact(text: str, limit: int = 180) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean if len(clean) <= limit else f"{clean[:limit].rstrip()}……"


def _inferred_type(content: str) -> str | None:
    if re.search(r"想读|要读|书籍|书《|读《", content):
        return "want_read"
    if re.search(r"想看|要看|电影|电视剧|剧集|看《", content):
        return "want_watch"
    if re.search(r"灵感|想到|想法|突然发现|可以做|点子", content):
        return "idea"
    if re.search(r"待办|todo|记得|需要|明天|后天|下周|联系|发送|处理|完成", content, re.I):
        return "todo"
    return None


def _mock_organization(captures: list[dict[str, Any]], local_date: date) -> JournalOrganization:
    if not captures:
        return JournalOrganization(
            journal_text=f"{local_date.isoformat()} 还没有快速记录。",
            highlights=[],
            items=[],
        )

    ordered = sorted(captures, key=lambda item: str(item.get("captured_at") or ""))
    journal_lines = [f"今天记录了 {len(ordered)} 件事情："]
    highlights: list[str] = []
    items: list[dict[str, Any]] = []
    for capture in ordered:
        content = _compact(str(capture.get("content") or ""))
        if not content:
            continue
        journal_lines.append(f"- {content}")
        if len(highlights) < 3:
            highlights.append(content)
        capture_type = str(capture.get("capture_type") or "note")
        item_type = capture_type if capture_type in ITEM_TYPES else _inferred_type(content)
        if item_type:
            items.append(
                {
                    "item_type": item_type,
                    "title": content,
                    "description": "",
                    "source_capture_ids": [capture["id"]],
                    "confidence": 1.0 if capture_type in ITEM_TYPES else 0.65,
                    "due_date": None,
                }
            )
    return JournalOrganization("\n".join(journal_lines), highlights, items)


class JournalAiProvider:
    def __init__(
        self,
        configuration: EffectiveModelConfiguration,
        usage_context: ModelUsageContext | None = None,
        settings: Settings | None = None,
    ):
        self.configuration = configuration
        self.usage_context = usage_context
        self.settings = settings
        self._call_number = 0

    def organize_day(
        self, captures: list[dict[str, Any]], local_date: date
    ) -> JournalOrganization:
        raise NotImplementedError


class MockJournalAiProvider(JournalAiProvider):
    def organize_day(
        self, captures: list[dict[str, Any]], local_date: date
    ) -> JournalOrganization:
        return _mock_organization(captures, local_date)


class HttpJournalAiProvider(JournalAiProvider):
    def _endpoint(self) -> str:
        base_url = self.configuration.base_url.strip()
        if not base_url or not self.configuration.model_name.strip():
            raise RuntimeError("真实模型配置不完整，请填写接口地址和模型名称")
        if not base_url.startswith(("http://", "https://")):
            raise RuntimeError("真实模型接口地址必须以 http:// 或 https:// 开头")
        normalized = base_url.rstrip("/")
        return normalized if normalized.endswith("/chat/completions") else f"{normalized}/chat/completions"

    def _record_usage(
        self,
        phase: str,
        started_at: float,
        status: str,
        body: Any = None,
        error_message: str | None = None,
    ) -> None:
        if self.usage_context is None:
            return
        input_tokens, output_tokens, total_tokens = token_counts(body)
        try:
            record_model_usage(
                ModelUsageEvent(
                    context=self.usage_context,
                    phase=phase,
                    call_number=self._call_number,
                    model_name=self.configuration.model_name.strip(),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    status=status,
                    error_message=error_message[:500] if error_message else None,
                    latency_ms=round((perf_counter() - started_at) * 1_000),
                    # Journal text is private; do not duplicate it in debug logs.
                    request_messages=[],
                    model_response=None,
                )
            )
        except Exception:
            return

    def _chat_completion(self, messages: list[dict[str, str]]) -> str:
        started_at = perf_counter()
        self._call_number += 1
        headers = {"Content-Type": "application/json"}
        if self.configuration.api_key:
            headers["Authorization"] = f"Bearer {self.configuration.api_key}"
        body: Any = None
        try:
            with httpx.Client(timeout=self.configuration.timeout_ms / 1_000) as client:
                response = client.post(
                    self._endpoint(),
                    headers=headers,
                    json={
                        "model": self.configuration.model_name.strip(),
                        "messages": messages,
                        "temperature": self.configuration.temperature,
                        "stream": False,
                    },
                )
        except httpx.TimeoutException as exc:
            message = f"日常整理模型请求超时（当前超时 {round(self.configuration.timeout_ms / 1_000)} 秒）"
            self._record_usage("journal_organization", started_at, "failed", error_message=message)
            raise RuntimeError(message) from exc
        except httpx.RequestError as exc:
            message = f"日常整理模型连接失败：{exc}"
            self._record_usage("journal_organization", started_at, "failed", error_message=message)
            raise RuntimeError(message) from exc

        if not response.is_success:
            try:
                body = response.json()
            except ValueError:
                body = None
            detail = ""
            if isinstance(body, dict):
                error = body.get("error")
                detail = str(error.get("message") if isinstance(error, dict) else error or "")
            message = f"日常整理模型返回 {response.status_code}：{detail[:300] or '请求失败'}"
            self._record_usage("journal_organization", started_at, "failed", body, message)
            raise RuntimeError(message)

        try:
            body = response.json()
        except ValueError as exc:
            message = "日常整理模型未返回有效 JSON"
            self._record_usage("journal_organization", started_at, "failed", error_message=message)
            raise RuntimeError(message) from exc
        content = extract_response_text(body)
        if not content:
            message = "日常整理模型没有返回可用文本"
            self._record_usage("journal_organization", started_at, "failed", body, message)
            raise RuntimeError(message)
        self._record_usage("journal_organization", started_at, "success", body)
        return content

    def organize_day(
        self, captures: list[dict[str, Any]], local_date: date
    ) -> JournalOrganization:
        capture_text = json.dumps(captures, ensure_ascii=False, separators=(",", ":"))
        messages = [
            {
                "role": "system",
                "content": (
                    "你是个人日常整理助手。只能根据用户提供的原始记录整理，不得补写未提及的事实。"
                    "请返回合法 JSON，不要返回 Markdown。日记应自然、克制，保留用户语气。"
                    "明确标记的类型优先于你的推断。待办、灵感、想读、想看都要保留来源记录 ID。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"日期：{local_date.isoformat()}\n原始记录：{capture_text}\n\n"
                    "请返回："
                    '{"journal_text":"日记草稿","highlights":["重点"],"items":['
                    '{"item_type":"todo|idea|want_read|want_watch","title":"归集标题",'
                    '"description":"补充说明","source_capture_ids":["原始记录 ID"],'
                    '"confidence":0.0,"due_date":null}]}。'
                    "confidence 在 0 到 1 之间；无法确认的项目可以省略。"
                    "不要输出心情诊断或人生价值结论。"
                ),
            },
        ]
        payload = parse_json_object(self._chat_completion(messages))
        journal_text = payload.get("journal_text")
        if not isinstance(journal_text, str) or not journal_text.strip():
            raise RuntimeError("日常整理结果缺少日记草稿")
        highlights = payload.get("highlights", [])
        if not isinstance(highlights, list):
            highlights = []
        items = payload.get("items", [])
        if not isinstance(items, list):
            items = []
        return JournalOrganization(
            journal_text=journal_text.strip()[:20_000],
            highlights=[str(item).strip() for item in highlights if str(item).strip()][:10],
            items=[item for item in items if isinstance(item, dict)],
        )


def get_journal_provider(
    settings: Settings,
    configuration: EffectiveModelConfiguration,
    usage_context: ModelUsageContext | None = None,
) -> JournalAiProvider:
    if configuration.provider_mode == "mock":
        return MockJournalAiProvider(configuration, usage_context=usage_context, settings=settings)
    return HttpJournalAiProvider(configuration, usage_context=usage_context, settings=settings)
