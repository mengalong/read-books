from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select

from app.config import Settings
from app.database import Base, SessionLocal, engine
from app.models import User
from app.services.auth import (
    ensure_initial_admin,
    hash_password,
    normalize_username,
    revoke_user_sessions,
    validate_password,
)


def init_admin(args: argparse.Namespace) -> None:
    password = args.password or getpass.getpass("请输入初始管理员临时密码：")
    confirmation = args.password or getpass.getpass("请再次输入临时密码：")
    if password != confirmation:
        raise SystemExit("两次输入的密码不一致")
    username = normalize_username(args.username)
    validate_password(password, username)

    Base.metadata.create_all(bind=engine)
    settings = Settings(
        initial_admin_username=username,
        initial_admin_password=password,
        initial_admin_display_name=args.display_name,
    )
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username == username))
        if existing is not None and existing.role == "admin":
            existing.password_hash = hash_password(password)
            existing.must_change_password = True
            existing.status = "active"
            existing.failed_login_count = 0
            existing.locked_until = None
            revoke_user_sessions(db, existing.id)
        user = ensure_initial_admin(db, settings)
        if user is None:
            raise SystemExit("管理员初始化失败")
        action = "已重置" if existing else "已创建"
        print(f"{action}初始管理员：{user.username}（首次登录需要修改密码）")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="回卷管理命令")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init-admin", help="创建初始管理员并回填旧数据归属")
    init_parser.add_argument("--username", default="admin", help="管理员账户名")
    init_parser.add_argument("--display-name", default="系统管理员", help="管理员显示名称")
    init_parser.add_argument(
        "--password",
        help="临时密码；省略时安全地交互输入，不建议在共享终端直接传入",
    )
    init_parser.set_defaults(handler=init_admin)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
