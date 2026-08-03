from sqlalchemy import select

from app.database import SessionLocal
from app.models import User
from app.services.auth import create_user_with_workspace


ADMIN_USERNAME = "admin-auth"
ADMIN_PASSWORD = "InitialAdmin1!"
ADMIN_NEW_PASSWORD = "ChangedAdmin2!"


def ensure_test_admin() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.username == ADMIN_USERNAME)):
            return
        create_user_with_workspace(
            db,
            username=ADMIN_USERNAME,
            display_name="认证测试管理员",
            password=ADMIN_PASSWORD,
            role="admin",
            must_change_password=True,
        )
        db.commit()


def test_login_first_password_change_and_admin_user_management(client):
    ensure_test_admin()
    client.cookies.clear()

    login = client.post(
        "/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    assert login.json()["workspace"]["name"] == "认证测试管理员的工作空间"

    blocked = client.get("/api/admin/users")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    changed = client.post(
        "/api/auth/change-password",
        json={
            "current_password": ADMIN_PASSWORD,
            "new_password": ADMIN_NEW_PASSWORD,
        },
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False

    created = client.post(
        "/api/admin/users",
        json={
            "username": "reader-one",
            "display_name": "第一位读者",
            "role": "user",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["user"]["username"] == "reader-one"
    assert body["user"]["workspace"]["name"] == "第一位读者的工作空间"
    assert body["temporary_password"]

    users = client.get("/api/admin/users")
    assert users.status_code == 200
    assert {item["username"] for item in users.json()} >= {
        ADMIN_USERNAME,
        "reader-one",
    }

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_failed_login_does_not_create_session(client):
    ensure_test_admin()
    client.cookies.clear()
    response = client.post(
        "/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": "WrongPassword1!"},
    )
    assert response.status_code == 401
    assert client.get("/api/auth/me").status_code == 401
