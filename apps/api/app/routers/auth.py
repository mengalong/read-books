from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_identity, require_admin
from app.models import User
from app.schemas import (
    AdminUserCreateRequest,
    AdminUserCreateResponse,
    AdminUserResponse,
    AdminUserUpdateRequest,
    CurrentUserResponse,
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetResponse,
    WorkspaceResponse,
)
from app.services.auth import (
    AuthIdentity,
    add_audit_log,
    create_session,
    create_user_with_workspace,
    generate_temporary_password,
    get_personal_workspace,
    hash_password,
    revoke_user_sessions,
    validate_password,
    verify_login,
    verify_password,
)

router = APIRouter(tags=["auth"])
settings = get_settings()


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:80]
    return request.client.host[:80] if request.client else None


def to_current_user(identity: AuthIdentity) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=identity.user.id,
        username=identity.user.username,
        display_name=identity.user.display_name,
        role=identity.user.role,
        status=identity.user.status,
        must_change_password=identity.user.must_change_password,
        last_login_at=identity.user.last_login_at,
        workspace=WorkspaceResponse.model_validate(identity.workspace),
    )


def to_admin_user(db: Session, user: User) -> AdminUserResponse:
    workspace = get_personal_workspace(db, user.id)
    if workspace is None:
        raise RuntimeError("用户缺少个人工作空间")
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        workspace=WorkspaceResponse.model_validate(workspace),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/auth/login", response_model=CurrentUserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> CurrentUserResponse:
    user, error = verify_login(db, payload.username, payload.password, settings)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error)
    workspace = get_personal_workspace(db, user.id)
    if workspace is None:
        raise HTTPException(status_code=500, detail="用户工作空间配置异常")
    token, session = create_session(
        db,
        user,
        settings,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    add_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.login",
        target_type="session",
        target_id=session.id,
        ip_address=client_ip(request),
    )
    db.commit()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return to_current_user(AuthIdentity(user=user, workspace=workspace, session=session))


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(get_current_identity),
) -> None:
    identity.session.revoked_at = datetime.now(timezone.utc)
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="auth.logout",
        target_type="session",
        target_id=identity.session.id,
    )
    db.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.get("/auth/me", response_model=CurrentUserResponse)
def current_user(
    identity: AuthIdentity = Depends(get_current_identity),
) -> CurrentUserResponse:
    return to_current_user(identity)


@router.post("/auth/change-password", response_model=CurrentUserResponse)
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(get_current_identity),
) -> CurrentUserResponse:
    if not verify_password(payload.current_password, identity.user.password_hash):
        raise HTTPException(status_code=422, detail="当前密码不正确")
    try:
        validate_password(payload.new_password, identity.user.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if verify_password(payload.new_password, identity.user.password_hash):
        raise HTTPException(status_code=422, detail="新密码不能与当前密码相同")

    identity.user.password_hash = hash_password(payload.new_password)
    identity.user.must_change_password = False
    revoke_user_sessions(db, identity.user.id, except_session_id=identity.session.id)
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="auth.password_changed",
        target_type="user",
        target_id=identity.user.id,
    )
    db.commit()
    db.refresh(identity.user)
    return to_current_user(identity)


@router.get("/admin/users", response_model=list[AdminUserResponse])
def list_users(
    db: Session = Depends(get_db),
    _: AuthIdentity = Depends(require_admin),
) -> list[AdminUserResponse]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [to_admin_user(db, user) for user in users]


@router.post(
    "/admin/users",
    response_model=AdminUserCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: AdminUserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> AdminUserCreateResponse:
    temporary_password = payload.temporary_password or generate_temporary_password()
    try:
        user, _ = create_user_with_workspace(
            db,
            username=payload.username,
            display_name=payload.display_name,
            password=temporary_password,
            role=payload.role,
            must_change_password=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="admin.user_created",
        target_type="user",
        target_id=user.id,
        details={"role": user.role},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return AdminUserCreateResponse(
        user=to_admin_user(db, user), temporary_password=temporary_password
    )


@router.patch("/admin/users/{user_id}", response_model=AdminUserResponse)
def update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> AdminUserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="未找到该用户")
    changes = payload.model_dump(exclude_unset=True)
    if user.id == identity.user.id and changes.get("status") == "disabled":
        raise HTTPException(status_code=409, detail="不能停用当前登录的管理员账户")
    if user.id == identity.user.id and changes.get("role") == "user":
        raise HTTPException(status_code=409, detail="不能降低当前登录管理员的角色")
    for field, value in changes.items():
        setattr(user, field, value.strip() if field == "display_name" else value)
    if changes.get("status") == "disabled":
        revoke_user_sessions(db, user.id)
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="admin.user_updated",
        target_type="user",
        target_id=user.id,
        details=changes,
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return to_admin_user(db, user)


@router.post("/admin/users/{user_id}/reset-password", response_model=PasswordResetResponse)
def reset_user_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> PasswordResetResponse:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="未找到该用户")
    temporary_password = generate_temporary_password()
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    revoke_user_sessions(db, user.id)
    add_audit_log(
        db,
        actor_user_id=identity.user.id,
        action="admin.password_reset",
        target_type="user",
        target_id=user.id,
        ip_address=client_ip(request),
    )
    db.commit()
    return PasswordResetResponse(user_id=user.id, temporary_password=temporary_password)
