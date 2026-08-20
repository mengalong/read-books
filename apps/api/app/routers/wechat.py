from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_admin
from app.models import ExamShare, WechatLoginConfiguration
from app.schemas import WechatLoginConfigurationResponse, WechatLoginConfigurationUpdate
from app.services.auth import AuthIdentity, add_audit_log
from app.services.wechat_auth import (
    EffectiveWechatConfig,
    WechatAuthError,
    authenticate_wechat_session,
    build_authorize_url,
    consume_oauth_state,
    create_oauth_state,
    create_wechat_session,
    effective_configuration,
    exchange_wechat_code,
    get_or_create_configuration,
    normalize_callback_base_url,
    resolve_callback_base_url,
    upsert_wechat_user,
    utc_now,
)

router = APIRouter(tags=["wechat-auth"])
settings = get_settings()


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:80]
    return request.client.host[:80] if request.client else None


def to_configuration_response(
    configuration: WechatLoginConfiguration,
) -> WechatLoginConfigurationResponse:
    effective = effective_configuration_from_record(configuration, app_env=settings.app_env)
    return WechatLoginConfigurationResponse(
        id=configuration.id,
        enabled=configuration.enabled,
        required_for_public_exams=configuration.required_for_public_exams,
        app_id=configuration.app_id,
        app_secret_configured=bool(configuration.app_secret),
        callback_base_url=effective.callback_base_url,
        callback_url=effective.callback_url,
        configuration_complete=effective.configuration_complete,
        created_at=configuration.created_at,
        updated_at=configuration.updated_at,
    )


def effective_configuration_from_record(
    configuration: WechatLoginConfiguration,
    *,
    app_env: str,
) -> EffectiveWechatConfig:
    return EffectiveWechatConfig(
        enabled=configuration.enabled,
        required_for_public_exams=configuration.required_for_public_exams,
        app_id=configuration.app_id.strip(),
        app_secret=(configuration.app_secret or "").strip(),
        callback_base_url=resolve_callback_base_url(
            configuration.callback_base_url,
            app_env=app_env,
        ),
    )


@router.get(
    "/settings/wechat-login",
    response_model=WechatLoginConfigurationResponse,
)
def get_wechat_login_configuration(
    db: Session = Depends(get_db),
    _: AuthIdentity = Depends(require_admin),
) -> WechatLoginConfigurationResponse:
    configuration = get_or_create_configuration(db, settings)
    db.commit()
    return to_configuration_response(configuration)


@router.patch(
    "/settings/wechat-login",
    response_model=WechatLoginConfigurationResponse,
)
def update_wechat_login_configuration(
    payload: WechatLoginConfigurationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> WechatLoginConfigurationResponse:
    configuration = get_or_create_configuration(db, settings)
    app_id = payload.app_id.strip()
    app_secret = (payload.app_secret or "").strip() or configuration.app_secret
    try:
        callback_base_url = normalize_callback_base_url(
            payload.callback_base_url,
            app_env=settings.app_env,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.enabled and (not app_id or not app_secret or not callback_base_url):
        raise HTTPException(
            status_code=422,
            detail="启用微信登录前必须填写 AppID、AppSecret 和回调基础地址",
        )
    configuration.enabled = payload.enabled
    configuration.required_for_public_exams = (
        payload.required_for_public_exams if payload.enabled else False
    )
    configuration.app_id = app_id
    configuration.app_secret = app_secret
    configuration.callback_base_url = callback_base_url
    configuration.updated_by_user_id = identity.user.id
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="settings.wechat_login_updated",
        target_type="wechat_login_configuration",
        target_id=configuration.id,
        details={
            "enabled": configuration.enabled,
            "required_for_public_exams": configuration.required_for_public_exams,
            "app_id": configuration.app_id,
            "callback_base_url": configuration.callback_base_url,
            "app_secret_updated": bool(payload.app_secret and payload.app_secret.strip()),
        },
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(configuration)
    return to_configuration_response(configuration)


@router.get("/public/wechat/login")
def start_wechat_login(
    request: Request,
    share_code: str = Query(min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if db.query(ExamShare.id).filter(ExamShare.share_code == share_code).scalar() is None:
        raise HTTPException(status_code=404, detail="考试链接不存在或已经失效")
    configuration = effective_configuration(db, settings)
    if not configuration.login_available:
        raise HTTPException(status_code=409, detail="微信登录尚未完成配置")
    state, browser_nonce = create_oauth_state(
        db,
        settings,
        share_code=share_code,
        ip_address=client_ip(request),
    )
    response = RedirectResponse(build_authorize_url(configuration, state), status_code=307)
    response.set_cookie(
        key=settings.wechat_oauth_cookie_name,
        value=browser_nonce,
        max_age=settings.wechat_oauth_state_ttl_minutes * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/api/public/wechat",
    )
    return response


@router.get("/public/wechat/callback")
def finish_wechat_login(
    request: Request,
    code: str = Query(min_length=1, max_length=500),
    state: str = Query(min_length=1, max_length=500),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        oauth_state = consume_oauth_state(
            db,
            state=state,
            browser_nonce=request.cookies.get(settings.wechat_oauth_cookie_name),
        )
    except WechatAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    configuration = effective_configuration(db, settings)
    target = f"{configuration.callback_base_url}/exams/{oauth_state.share_code}"
    try:
        profile = exchange_wechat_code(configuration, code)
        user = upsert_wechat_user(db, profile)
        token, _ = create_wechat_session(
            db,
            user,
            settings,
            user_agent=request.headers.get("user-agent"),
            ip_address=client_ip(request),
        )
        db.commit()
    except WechatAuthError as exc:
        response = RedirectResponse(
            f"{target}?wechat_error={quote(str(exc), safe='')}",
            status_code=303,
        )
        response.delete_cookie(settings.wechat_oauth_cookie_name, path="/api/public/wechat")
        return response
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        key=settings.wechat_session_cookie_name,
        value=token,
        max_age=settings.wechat_session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(settings.wechat_oauth_cookie_name, path="/api/public/wechat")
    return response


@router.post("/public/wechat/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_wechat(response: Response, request: Request, db: Session = Depends(get_db)) -> None:
    token = request.cookies.get(settings.wechat_session_cookie_name)
    identity = authenticate_wechat_session(db, token) if token else None
    if identity:
        identity.session.revoked_at = utc_now()
        db.commit()
    response.delete_cookie(
        settings.wechat_session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
