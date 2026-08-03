from __future__ import annotations

import hashlib
import re
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.models import (
    AuditLog,
    Book,
    ModelConfiguration,
    ModelUsageRecord,
    PromptTemplate,
    QuizGenerationTask,
    User,
    UserSession,
    Workspace,
    WorkspaceMember,
)

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
PASSWORD_HASH = PasswordHash.recommended()


@dataclass(frozen=True)
class AuthIdentity:
    user: User
    workspace: Workspace
    session: UserSession


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("用户名需为 3-80 位小写字母、数字、点、下划线或连字符")
    return normalized


def validate_password(password: str, username: str = "") -> None:
    if len(password) < 8 or len(password) > 128:
        raise ValueError("密码长度需为 8-128 位")
    if username and password.casefold() == username.casefold():
        raise ValueError("密码不能与用户名相同")
    categories = sum(
        bool(pattern.search(password))
        for pattern in (
            re.compile(r"[a-z]"),
            re.compile(r"[A-Z]"),
            re.compile(r"[0-9]"),
            re.compile(r"[^a-zA-Z0-9]"),
        )
    )
    if categories < 3:
        raise ValueError("密码需包含大小写字母、数字或符号中的至少三类")


def hash_password(password: str) -> str:
    return PASSWORD_HASH.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return PASSWORD_HASH.verify(password, password_hash)
    except (TypeError, ValueError):
        return False


def generate_temporary_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        try:
            validate_password(password)
        except ValueError:
            continue
        return password


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_personal_workspace(db: Session, user_id: str) -> Workspace | None:
    return db.scalar(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            WorkspaceMember.user_id == user_id,
            Workspace.status == "active",
        )
        .order_by(WorkspaceMember.created_at)
        .limit(1)
    )


def create_user_with_workspace(
    db: Session,
    *,
    username: str,
    display_name: str,
    password: str,
    role: str = "user",
    must_change_password: bool = True,
) -> tuple[User, Workspace]:
    normalized_username = normalize_username(username)
    validate_password(password, normalized_username)
    if role not in {"admin", "user"}:
        raise ValueError("不支持该用户角色")
    if db.scalar(select(User.id).where(User.username == normalized_username)):
        raise ValueError("用户名已存在")

    clean_display_name = display_name.strip()
    if not clean_display_name:
        raise ValueError("显示名称不能为空")
    user = User(
        username=normalized_username,
        display_name=clean_display_name,
        password_hash=hash_password(password),
        role=role,
        status="active",
        must_change_password=must_change_password,
    )
    db.add(user)
    db.flush()
    workspace = Workspace(
        name=f"{clean_display_name}的工作空间",
        workspace_type="personal",
        status="active",
        created_by_user_id=user.id,
    )
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.flush()
    return user, workspace


def add_audit_log(
    db: Session,
    *,
    actor_user_id: str | None,
    action: str,
    target_type: str,
    target_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
            ip_address=ip_address,
        )
    )


def backfill_legacy_ownership(db: Session, admin: User, workspace: Workspace) -> None:
    db.execute(
        update(Book)
        .where(Book.workspace_id.is_(None))
        .values(workspace_id=workspace.id, created_by_user_id=admin.id)
    )
    db.execute(
        update(QuizGenerationTask)
        .where(QuizGenerationTask.created_by_user_id.is_(None))
        .values(created_by_user_id=admin.id)
    )
    db.execute(
        update(ModelUsageRecord)
        .where(ModelUsageRecord.workspace_id.is_(None))
        .values(workspace_id=workspace.id, user_id=admin.id)
    )
    db.execute(
        update(ModelConfiguration)
        .where(ModelConfiguration.updated_by_user_id.is_(None))
        .values(scope_type="platform", updated_by_user_id=admin.id)
    )
    db.execute(
        update(PromptTemplate)
        .where(PromptTemplate.updated_by_user_id.is_(None))
        .values(scope_type="platform", updated_by_user_id=admin.id)
    )


def ensure_initial_admin(db: Session, settings: Settings) -> User | None:
    username = (settings.initial_admin_username or "").strip()
    password = settings.initial_admin_password or ""
    if not username and not password:
        return None
    if not username or not password:
        raise RuntimeError("INITIAL_ADMIN_USERNAME 和 INITIAL_ADMIN_PASSWORD 必须同时配置")

    normalized_username = normalize_username(username)
    admin = db.scalar(select(User).where(User.username == normalized_username))
    if admin is None:
        admin, workspace = create_user_with_workspace(
            db,
            username=normalized_username,
            display_name=settings.initial_admin_display_name,
            password=password,
            role="admin",
            must_change_password=True,
        )
        add_audit_log(
            db,
            actor_user_id=admin.id,
            action="admin.bootstrap",
            target_type="user",
            target_id=admin.id,
        )
    else:
        if admin.role != "admin":
            raise RuntimeError("初始管理员用户名已被非管理员账户占用")
        workspace = get_personal_workspace(db, admin.id)
        if workspace is None:
            workspace = Workspace(
                name=f"{admin.display_name}的工作空间",
                workspace_type="personal",
                status="active",
                created_by_user_id=admin.id,
            )
            db.add(workspace)
            db.flush()
            db.add(WorkspaceMember(workspace_id=workspace.id, user_id=admin.id, role="owner"))
            db.flush()

    backfill_legacy_ownership(db, admin, workspace)
    db.commit()
    db.refresh(admin)
    return admin


def create_session(
    db: Session,
    user: User,
    settings: Settings,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(48)
    now = utc_now()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        last_seen_at=now,
        user_agent=(user_agent or "")[:500] or None,
        ip_address=(ip_address or "")[:80] or None,
    )
    db.add(session)
    db.flush()
    return token, session


def authenticate_session(db: Session, token: str) -> AuthIdentity | None:
    now = utc_now()
    session = db.scalar(
        select(UserSession)
        .options(selectinload(UserSession.user))
        .where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    )
    if session is None or session.user.status != "active":
        return None
    workspace = get_personal_workspace(db, session.user_id)
    if workspace is None:
        return None
    session.last_seen_at = now
    db.commit()
    return AuthIdentity(user=session.user, workspace=workspace, session=session)


def revoke_user_sessions(db: Session, user_id: str, *, except_session_id: str | None = None) -> None:
    statement = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    if except_session_id:
        statement = statement.where(UserSession.id != except_session_id)
    db.execute(statement)


def verify_login(
    db: Session, username: str, password: str, settings: Settings
) -> tuple[User | None, str | None]:
    try:
        normalized = normalize_username(username)
    except ValueError:
        return None, "用户名或密码错误"
    user = db.scalar(select(User).where(User.username == normalized))
    if user is None or user.status != "active":
        return None, "用户名或密码错误"

    now = utc_now()
    if user.locked_until is not None:
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            return None, "登录失败次数过多，请稍后再试"
        user.locked_until = None
        user.failed_login_count = 0

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_max_failed_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_login_count = 0
        db.commit()
        return None, "用户名或密码错误"

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    return user, None
