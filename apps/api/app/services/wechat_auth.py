from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.models import (
    WechatLoginConfiguration,
    WechatOAuthState,
    WechatSession,
    WechatUser,
)
from app.services.auth import hash_session_token

WECHAT_CONFIG_ID = "default"
WECHAT_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
WECHAT_ACCESS_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
WECHAT_USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"


@dataclass(frozen=True)
class EffectiveWechatConfig:
    enabled: bool
    required_for_public_exams: bool
    app_id: str
    app_secret: str
    callback_base_url: str

    @property
    def configuration_complete(self) -> bool:
        return bool(self.app_id and self.app_secret and self.callback_base_url)

    @property
    def login_available(self) -> bool:
        return self.enabled and self.configuration_complete

    @property
    def callback_url(self) -> str:
        return f"{self.callback_base_url.rstrip('/')}/api/public/wechat/callback"


@dataclass(frozen=True)
class WechatIdentity:
    user: WechatUser
    session: WechatSession


class WechatAuthError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def normalize_callback_base_url(value: str, *, app_env: str) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("回调基础地址必须是完整的 HTTP 或 HTTPS 地址")
    if app_env == "production" and parsed.scheme != "https":
        raise ValueError("生产环境启用微信登录前必须配置 HTTPS 回调地址")
    return normalized


def get_or_create_configuration(db: Session, settings: Settings) -> WechatLoginConfiguration:
    configuration = db.get(WechatLoginConfiguration, WECHAT_CONFIG_ID)
    if configuration is not None:
        return configuration
    configuration = WechatLoginConfiguration(
        id=WECHAT_CONFIG_ID,
        enabled=settings.wechat_login_enabled,
        required_for_public_exams=settings.wechat_login_required,
        app_id=settings.wechat_app_id.strip(),
        app_secret=settings.wechat_app_secret,
        callback_base_url=(settings.wechat_callback_base_url or settings.web_origin).rstrip("/"),
    )
    db.add(configuration)
    db.flush()
    return configuration


def effective_configuration(db: Session, settings: Settings) -> EffectiveWechatConfig:
    configuration = db.get(WechatLoginConfiguration, WECHAT_CONFIG_ID)
    if configuration is None:
        return EffectiveWechatConfig(
            enabled=settings.wechat_login_enabled,
            required_for_public_exams=settings.wechat_login_required,
            app_id=settings.wechat_app_id.strip(),
            app_secret=(settings.wechat_app_secret or "").strip(),
            callback_base_url=(settings.wechat_callback_base_url or settings.web_origin).rstrip("/"),
        )
    return EffectiveWechatConfig(
        enabled=configuration.enabled,
        required_for_public_exams=configuration.required_for_public_exams,
        app_id=configuration.app_id.strip(),
        app_secret=(configuration.app_secret or "").strip(),
        callback_base_url=configuration.callback_base_url.strip().rstrip("/"),
    )


def create_oauth_state(
    db: Session,
    settings: Settings,
    *,
    share_code: str,
    ip_address: str | None,
) -> tuple[str, str]:
    now = utc_now()
    db.execute(
        delete(WechatOAuthState).where(
            or_(
                WechatOAuthState.expires_at <= now,
                WechatOAuthState.consumed_at.is_not(None),
            )
        )
    )
    state = secrets.token_urlsafe(32)
    browser_nonce = secrets.token_urlsafe(32)
    db.add(
        WechatOAuthState(
            state_hash=hash_session_token(state),
            browser_nonce_hash=hash_session_token(browser_nonce),
            share_code=share_code,
            expires_at=now + timedelta(minutes=settings.wechat_oauth_state_ttl_minutes),
            created_ip_address=(ip_address or "")[:80] or None,
        )
    )
    db.commit()
    return state, browser_nonce


def consume_oauth_state(
    db: Session,
    *,
    state: str,
    browser_nonce: str | None,
) -> WechatOAuthState:
    record = db.scalar(
        select(WechatOAuthState).where(
            WechatOAuthState.state_hash == hash_session_token(state),
            WechatOAuthState.consumed_at.is_(None),
            WechatOAuthState.expires_at > utc_now(),
        )
    )
    if record is None or not browser_nonce:
        raise WechatAuthError("微信授权状态已失效，请重新发起登录")
    if not secrets.compare_digest(record.browser_nonce_hash, hash_session_token(browser_nonce)):
        raise WechatAuthError("微信授权请求与当前浏览器不匹配")
    record.consumed_at = utc_now()
    db.commit()
    return record


def build_authorize_url(configuration: EffectiveWechatConfig, state: str) -> str:
    return f"{WECHAT_AUTHORIZE_URL}?{urlencode({
        'appid': configuration.app_id,
        'redirect_uri': configuration.callback_url,
        'response_type': 'code',
        'scope': 'snsapi_login',
        'state': state,
    })}#wechat_redirect"


def exchange_wechat_code(configuration: EffectiveWechatConfig, code: str) -> dict[str, str | None]:
    try:
        with httpx.Client(timeout=15) as client:
            token_response = client.get(
                WECHAT_ACCESS_TOKEN_URL,
                params={
                    "appid": configuration.app_id,
                    "secret": configuration.app_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            if token_data.get("errcode") or not token_data.get("access_token") or not token_data.get("openid"):
                raise WechatAuthError(_wechat_error_message(token_data, "微信授权码换取失败"))
            user_response = client.get(
                WECHAT_USERINFO_URL,
                params={
                    "access_token": token_data["access_token"],
                    "openid": token_data["openid"],
                    "lang": "zh_CN",
                },
            )
            user_response.raise_for_status()
            user_data = user_response.json()
            if user_data.get("errcode") or not user_data.get("openid"):
                raise WechatAuthError(_wechat_error_message(user_data, "微信用户信息获取失败"))
    except WechatAuthError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise WechatAuthError(f"微信接口连接失败：{exc}") from exc
    return {
        "openid": str(user_data["openid"]),
        "unionid": str(user_data["unionid"]) if user_data.get("unionid") else None,
        "nickname": str(user_data.get("nickname") or "微信用户")[:120],
        "avatar_url": str(user_data.get("headimgurl") or "") or None,
    }


def _wechat_error_message(payload: dict, fallback: str) -> str:
    code = payload.get("errcode")
    message = payload.get("errmsg")
    return f"{fallback}（{code}: {message}）" if code else fallback


def upsert_wechat_user(db: Session, profile: dict[str, str | None]) -> WechatUser:
    unionid = profile.get("unionid")
    user = db.scalar(select(WechatUser).where(WechatUser.openid == profile["openid"]))
    if user is None and unionid:
        user = db.scalar(select(WechatUser).where(WechatUser.unionid == unionid))
    if user is None:
        user = WechatUser(openid=profile["openid"] or "", unionid=unionid, nickname="微信用户")
        db.add(user)
    user.openid = profile["openid"] or user.openid
    user.unionid = unionid or user.unionid
    user.nickname = (profile.get("nickname") or "微信用户")[:120]
    user.avatar_url = profile.get("avatar_url")
    user.last_login_at = utc_now()
    db.flush()
    return user


def create_wechat_session(
    db: Session,
    user: WechatUser,
    settings: Settings,
    *,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[str, WechatSession]:
    token = secrets.token_urlsafe(48)
    now = utc_now()
    session = WechatSession(
        wechat_user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=now + timedelta(hours=settings.wechat_session_ttl_hours),
        last_seen_at=now,
        user_agent=(user_agent or "")[:500] or None,
        ip_address=(ip_address or "")[:80] or None,
    )
    db.add(session)
    db.flush()
    return token, session


def authenticate_wechat_session(db: Session, token: str) -> WechatIdentity | None:
    now = utc_now()
    session = db.scalar(
        select(WechatSession)
        .options(selectinload(WechatSession.wechat_user))
        .where(
            WechatSession.token_hash == hash_session_token(token),
            WechatSession.revoked_at.is_(None),
            WechatSession.expires_at > now,
        )
    )
    if session is None:
        return None
    session.last_seen_at = now
    db.commit()
    return WechatIdentity(user=session.wechat_user, session=session)
