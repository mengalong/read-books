from __future__ import annotations

import struct
from typing import Any

import httpx

from app.services.model_config import EffectiveModelConfiguration

EMBEDDING_VECTOR_FORMAT = "f"


def pack_embedding(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}{EMBEDDING_VECTOR_FORMAT}", *vector)


def unpack_embedding(payload: bytes) -> list[float]:
    count = len(payload) // struct.calcsize(EMBEDDING_VECTOR_FORMAT)
    return list(struct.unpack(f"<{count}{EMBEDDING_VECTOR_FORMAT}", payload))


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the embedding model is not configured or reachable."""


class HttpEmbeddingClient:
    """Thin OpenAI-compatible /embeddings client reusing the quiz model connection."""

    def __init__(
        self,
        configuration: EffectiveModelConfiguration,
        embedding_model: str,
        timeout_ms: int = 60_000,
    ):
        self.configuration = configuration
        self.embedding_model = embedding_model
        self.timeout_ms = timeout_ms

    def _endpoint(self) -> str:
        base_url = self.configuration.base_url.strip()
        if not base_url:
            raise EmbeddingUnavailableError("真实模型接口地址未配置，无法生成向量")
        normalized = base_url.rstrip("/")
        if normalized.endswith("/chat/completions"):
            normalized = normalized[: -len("/chat/completions")]
        return f"{normalized}/embeddings"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.embedding_model.strip():
            raise EmbeddingUnavailableError("尚未配置向量模型名称")
        headers = {"Content-Type": "application/json"}
        if self.configuration.api_key:
            headers["Authorization"] = f"Bearer {self.configuration.api_key}"
        body: dict[str, Any] = {"model": self.embedding_model.strip(), "input": texts}
        try:
            with httpx.Client(timeout=self.timeout_ms / 1_000) as client:
                response = client.post(self._endpoint(), headers=headers, json=body)
        except httpx.RequestError as exc:
            raise EmbeddingUnavailableError(f"向量接口连接失败：{exc}") from exc
        if not response.is_success:
            raise EmbeddingUnavailableError(f"向量接口返回错误状态码：{response.status_code}")
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingUnavailableError("向量接口返回的结果数量不正确")
        ordered = sorted(data, key=lambda item: item.get("index", 0))
        vectors: list[list[float]] = []
        for item in ordered:
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise EmbeddingUnavailableError("向量接口返回的结果格式不正确")
            vectors.append([float(value) for value in embedding])
        return vectors


def get_embedding_client(
    configuration: EffectiveModelConfiguration,
    embedding_model: str | None,
    timeout_ms: int = 60_000,
) -> HttpEmbeddingClient | None:
    if configuration.provider_mode == "mock" or not embedding_model:
        return None
    return HttpEmbeddingClient(configuration, embedding_model, timeout_ms)
