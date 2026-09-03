from __future__ import annotations

from app.services.embedding_client import pack_embedding
from app.services.embedding_index import rank_by_similarity
from app.services.model_config import EffectiveModelConfiguration


class _FakeContentChunk:
    def __init__(self, id_: str, embedding: bytes | None, embedding_model: str | None):
        self.id = id_
        self.embedding = embedding
        self.embedding_model = embedding_model


class _FakeEmbeddingClient:
    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vectors[text] for text in texts]


def make_configuration() -> EffectiveModelConfiguration:
    return EffectiveModelConfiguration(
        provider_mode="openai_compatible",
        base_url="https://models.example.com/v1",
        api_key="secret",
        model_name="review-model",
        timeout_ms=30_000,
        temperature=0.3,
    )


class _FakeSettings:
    llm_embedding_model = "embed-1"
    llm_embedding_timeout_ms = 60_000


def test_rank_by_similarity_orders_candidates_by_cosine_similarity(monkeypatch):
    query_vector = [1.0, 0.0]
    close_vector = [0.99, 0.14]
    far_vector = [0.0, 1.0]

    close = _FakeContentChunk("close", pack_embedding(close_vector), "embed-1")
    far = _FakeContentChunk("far", pack_embedding(far_vector), "embed-1")
    unscored = _FakeContentChunk("unscored", None, None)

    fake_client = _FakeEmbeddingClient({"关键问题": query_vector})
    monkeypatch.setattr(
        "app.services.embedding_index.get_embedding_client", lambda *a, **k: fake_client
    )

    ranked = rank_by_similarity(
        [far, close, unscored],
        "关键问题",
        configuration=make_configuration(),
        settings=_FakeSettings(),
    )

    assert ranked is not None
    assert [item.id for item in ranked] == ["close", "far", "unscored"]


def test_rank_by_similarity_returns_none_without_embedding_client(monkeypatch):
    monkeypatch.setattr(
        "app.services.embedding_index.get_embedding_client", lambda *a, **k: None
    )
    chunk = _FakeContentChunk("chunk-1", pack_embedding([1.0, 0.0]), "embed-1")

    ranked = rank_by_similarity(
        [chunk], "问题", configuration=make_configuration(), settings=_FakeSettings()
    )

    assert ranked is None


def test_rank_by_similarity_returns_none_when_no_candidate_has_matching_model(monkeypatch):
    fake_client = _FakeEmbeddingClient({"问题": [1.0, 0.0]})
    monkeypatch.setattr(
        "app.services.embedding_index.get_embedding_client", lambda *a, **k: fake_client
    )
    stale = _FakeContentChunk("stale", pack_embedding([1.0, 0.0]), "old-model")

    ranked = rank_by_similarity(
        [stale], "问题", configuration=make_configuration(), settings=_FakeSettings()
    )

    assert ranked is None
