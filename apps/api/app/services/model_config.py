from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import ModelConfiguration

DEFAULT_CONFIGURATION_ID = "default"


@dataclass(frozen=True)
class EffectiveModelConfiguration:
    provider_mode: str
    base_url: str
    api_key: str | None
    model_name: str
    timeout_ms: int
    temperature: float
    created_at: datetime | None = None
    updated_at: datetime | None = None


def get_effective_model_configuration(
    db: Session, settings: Settings
) -> EffectiveModelConfiguration:
    stored = db.get(ModelConfiguration, DEFAULT_CONFIGURATION_ID)
    if stored is None:
        return EffectiveModelConfiguration(
            provider_mode="mock" if settings.mock_mode else "openai_compatible",
            base_url=settings.llm_base_url or "",
            api_key=settings.llm_api_key,
            model_name=settings.llm_model or "",
            timeout_ms=settings.llm_timeout_ms,
            temperature=settings.llm_temperature,
        )

    api_key = settings.llm_api_key if stored.api_key is None else stored.api_key or None
    return EffectiveModelConfiguration(
        provider_mode=stored.provider_mode,
        base_url=stored.base_url,
        api_key=api_key,
        model_name=stored.model_name,
        timeout_ms=stored.timeout_ms,
        temperature=stored.temperature,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )
