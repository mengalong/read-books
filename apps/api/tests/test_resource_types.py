from __future__ import annotations

import pytest

from app.database import SessionLocal
from app.models import Book
from app.services.model_config import EffectiveModelConfiguration
from app.services.quiz_provider import ResourceKnowledgeCheckResult
from app.services.resource_verification import refresh_book_model_knowledge
from app.services.quiz_generation import resolve_source_mode


def _openai_like_configuration() -> EffectiveModelConfiguration:
    return EffectiveModelConfiguration(
        provider_mode="openai_compatible",
        base_url="https://models.example.com/v1",
        api_key="provider-secret",
        model_name="review-model",
        timeout_ms=30_000,
        temperature=0.3,
    )


def test_refresh_book_model_knowledge_uses_resource_type(monkeypatch):
    captured: dict[str, str] = {}

    class FakeProvider:
        def verify_resource_content(self, resource_type: str, title: str, author: str, description: str):
            captured.update(
                {
                    "resource_type": resource_type,
                    "title": title,
                    "author": author,
                    "description": description,
                }
            )
            return ResourceKnowledgeCheckResult(
                supported=False,
                message="low: 未能确认真实内容",
                raw_response='{"supported": false}',
            )

    monkeypatch.setattr(
        "app.services.resource_verification.get_effective_model_configuration",
        lambda db, settings: _openai_like_configuration(),
    )
    monkeypatch.setattr(
        "app.services.resource_verification.get_quiz_provider",
        lambda *args, **kwargs: FakeProvider(),
    )

    with SessionLocal() as db:
        book = Book(
            title="霸王别姬",
            author="陈凯歌",
            description="电影资源测试",
            resource_type="movie",
        )
        db.add(book)
        db.commit()
        db.refresh(book)

        result = refresh_book_model_knowledge(db, book, user_id="tester")

        assert captured == {
            "resource_type": "movie",
            "title": "霸王别姬",
            "author": "陈凯歌",
            "description": "电影资源测试",
        }
        assert result.supported is False
        assert book.model_knowledge_supported is False
        assert book.model_knowledge_message == "low: 未能确认真实内容"
        assert book.model_knowledge_checked_at is not None


def test_resolve_source_mode_rejects_unverified_movie(monkeypatch):
    monkeypatch.setattr(
        "app.services.quiz_generation.get_effective_model_configuration",
        lambda db, settings: _openai_like_configuration(),
    )

    with SessionLocal() as db:
        book = Book(
            title="霸王别姬",
            author="陈凯歌",
            description="电影资源测试",
            resource_type="movie",
            model_knowledge_supported=False,
        )
        db.add(book)
        db.commit()
        db.refresh(book)

        with pytest.raises(ValueError, match="尚未通过模型真实内容测试"):
            resolve_source_mode(db, book.id)
