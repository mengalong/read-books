from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.services.auth import AuthIdentity, authenticate_session


def get_current_identity(
    request: Request, db: Session = Depends(get_db)
) -> AuthIdentity:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    identity = authenticate_session(db, token) if token else None
    if identity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return identity


def get_optional_identity(
    request: Request, db: Session = Depends(get_db)
) -> AuthIdentity | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    return authenticate_session(db, token) if token else None


def require_ready_identity(
    identity: AuthIdentity = Depends(get_current_identity),
) -> AuthIdentity:
    if identity.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PASSWORD_CHANGE_REQUIRED",
                "message": "首次登录后需要先修改临时密码",
            },
        )
    return identity


def require_admin(identity: AuthIdentity = Depends(require_ready_identity)) -> AuthIdentity:
    if identity.user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return identity
