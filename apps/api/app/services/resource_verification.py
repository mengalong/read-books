from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Book, utc_now
from app.services.model_config import get_effective_model_configuration
from app.services.model_usage import new_usage_context
from app.services.prompt_config import get_effective_prompt_templates
from app.services.quiz_provider import ResourceKnowledgeCheckResult, get_quiz_provider


def refresh_book_model_knowledge(
    db: Session,
    book: Book,
    *,
    user_id: str | None = None,
    settings: Settings | None = None,
) -> ResourceKnowledgeCheckResult:
    settings = settings or get_settings()
    configuration = get_effective_model_configuration(db, settings)
    if configuration.provider_mode == "mock":
        result = ResourceKnowledgeCheckResult(
            supported=None,
            message="当前是模拟模式，未执行真实内容验证；切换真实模型后请重新检查。",
            raw_response=None,
        )
    else:
        provider = get_quiz_provider(
            settings,
            configuration,
            get_effective_prompt_templates(db),
            new_usage_context(
                "resource_verification",
                f"验证《{book.title}》模型知识",
                book_id=book.id,
                user_id=user_id,
                workspace_id=book.workspace_id,
            ),
        )
        try:
            result = provider.verify_resource_content(
                book.resource_type,
                book.title,
                book.author,
                book.description,
            )
        except Exception as exc:
            result = ResourceKnowledgeCheckResult(
                supported=False,
                message=f"模型真实性检查失败：{exc}",
                raw_response=None,
            )

    book.model_knowledge_supported = result.supported
    book.model_knowledge_message = result.message
    book.model_knowledge_checked_at = utc_now()
    return result
