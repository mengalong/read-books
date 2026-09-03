"""Compute and store embeddings for trusted material and PDF content, and rank by similarity.

Embeddings are generated lazily and incrementally: `refresh_book_embeddings` only calls the
embedding model for rows that don't have one yet (or whose `embedding_model` no longer matches
the currently configured model), so re-running after new material is uploaded is cheap.

This module never changes what a question is allowed to cite; it only reorders the candidate
pool passed into `generate_questions` so the most semantically relevant, currently-untested
material is offered to the model first.
"""

from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import ContentChunk, MaterialSegment, QuoteEntry
from app.services.embedding_client import (
    EmbeddingUnavailableError,
    cosine_similarity,
    get_embedding_client,
    pack_embedding,
    unpack_embedding,
)
from app.services.model_config import get_effective_model_configuration

logger = logging.getLogger(__name__)

EMBEDDING_BATCH_SIZE = 64


def _rows_needing_embedding(rows: Sequence, embedding_model: str) -> list:
    return [
        row
        for row in rows
        if row.embedding is None or row.embedding_model != embedding_model
    ]


def _embed_rows(client, rows: Sequence, embedding_model: str, db: Session) -> None:
    pending = _rows_needing_embedding(rows, embedding_model)
    for start in range(0, len(pending), EMBEDDING_BATCH_SIZE):
        batch = pending[start : start + EMBEDDING_BATCH_SIZE]
        texts = [row.content if hasattr(row, "content") else row.quote_text for row in batch]
        vectors = client.embed(texts)
        for row, vector in zip(batch, vectors, strict=True):
            row.embedding = pack_embedding(vector)
            row.embedding_model = embedding_model
        db.commit()


def refresh_book_embeddings(book_id: str, *, settings: Settings | None = None) -> None:
    """Backfill embeddings for a book's ContentChunk/MaterialSegment/QuoteEntry rows."""
    settings = settings or get_settings()
    with SessionLocal() as db:
        configuration = get_effective_model_configuration(db, settings)
        client = get_embedding_client(
            configuration, settings.llm_embedding_model, settings.llm_embedding_timeout_ms
        )
        if client is None:
            return
        embedding_model = settings.llm_embedding_model or ""
        try:
            chunks = list(db.scalars(select(ContentChunk).where(ContentChunk.book_id == book_id)).all())
            _embed_rows(client, chunks, embedding_model, db)

            segments = list(
                db.scalars(select(MaterialSegment).where(MaterialSegment.book_id == book_id)).all()
            )
            _embed_rows(client, segments, embedding_model, db)

            quotes = list(db.scalars(select(QuoteEntry).where(QuoteEntry.book_id == book_id)).all())
            _embed_rows(client, quotes, embedding_model, db)
        except EmbeddingUnavailableError:
            logger.exception("向量生成失败，跳过本次索引更新: book=%s", book_id)
            db.rollback()


def rank_by_similarity(
    candidates: list,
    query_text: str,
    *,
    configuration,
    settings: Settings,
) -> list | None:
    """Return `candidates` sorted by embedding similarity to `query_text`.

    Returns None when embeddings are unavailable (unconfigured model, no stored vectors, or
    an API failure), so callers can fall back to their existing selection strategy.
    """
    if not candidates or not query_text.strip():
        return None
    client = get_embedding_client(
        configuration, settings.llm_embedding_model, settings.llm_embedding_timeout_ms
    )
    if client is None:
        return None
    embedding_model = settings.llm_embedding_model or ""
    scored_candidates = [
        candidate
        for candidate in candidates
        if candidate.embedding is not None and candidate.embedding_model == embedding_model
    ]
    if not scored_candidates:
        return None
    try:
        query_vector = client.embed([query_text])[0]
    except EmbeddingUnavailableError:
        logger.exception("查询向量生成失败，回退到原有候选排序")
        return None
    scored = [
        (cosine_similarity(query_vector, unpack_embedding(candidate.embedding)), candidate)
        for candidate in scored_candidates
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    ranked_ids = {candidate.id for _, candidate in scored}
    unscored = [candidate for candidate in candidates if candidate.id not in ranked_ids]
    return [candidate for _, candidate in scored] + unscored
