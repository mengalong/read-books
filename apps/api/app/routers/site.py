from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models import SiteFooterConfiguration
from app.schemas import SiteFooterConfigurationResponse, SiteFooterConfigurationUpdate
from app.services.auth import AuthIdentity

router = APIRouter(tags=["site-footer"])
SITE_FOOTER_CONFIG_ID = "default"


def get_or_create_configuration(db: Session) -> SiteFooterConfiguration:
    configuration = db.get(SiteFooterConfiguration, SITE_FOOTER_CONFIG_ID)
    if configuration is not None:
        return configuration
    configuration = SiteFooterConfiguration(
        id=SITE_FOOTER_CONFIG_ID,
        record_number="",
        record_url="",
    )
    db.add(configuration)
    db.flush()
    return configuration


def normalize_record_url(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("备案号链接必须是完整的 HTTP 或 HTTPS 地址")
    return normalized


def to_response(configuration: SiteFooterConfiguration) -> SiteFooterConfigurationResponse:
    record_number = (configuration.record_number or "").strip()
    record_url = (configuration.record_url or "").strip()
    return SiteFooterConfigurationResponse(
        id=configuration.id,
        record_number=record_number,
        record_url=record_url,
        configuration_complete=bool(record_number and record_url),
        created_at=configuration.created_at,
        updated_at=configuration.updated_at,
    )


@router.get("/site-footer", response_model=SiteFooterConfigurationResponse)
def get_site_footer_configuration(
    db: Session = Depends(get_db),
) -> SiteFooterConfigurationResponse:
    configuration = get_or_create_configuration(db)
    db.commit()
    return to_response(configuration)


@router.put("/site-footer", response_model=SiteFooterConfigurationResponse)
def update_site_footer_configuration(
    payload: SiteFooterConfigurationUpdate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> SiteFooterConfigurationResponse:
    configuration = get_or_create_configuration(db)
    record_number = payload.record_number.strip()
    try:
        record_url = normalize_record_url(payload.record_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if bool(record_number) != bool(record_url):
        raise HTTPException(
            status_code=422,
            detail="备案号和备案号链接需要同时填写，或同时清空",
        )
    configuration.record_number = record_number
    configuration.record_url = record_url
    configuration.updated_by_user_id = identity.user.id
    db.commit()
    db.refresh(configuration)
    return to_response(configuration)
