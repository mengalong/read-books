from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import WechatLoginConfiguration, WechatOAuthState, WechatSession, WechatUser

from test_exam_sharing import create_exam_share, create_shareable_quiz


def reset_wechat_configuration() -> None:
    with SessionLocal() as db:
        db.query(WechatSession).delete()
        db.query(WechatOAuthState).delete()
        db.query(WechatUser).delete()
        db.query(WechatLoginConfiguration).delete()
        db.commit()


def configure_wechat(client, *, required: bool = False) -> dict:
    response = client.patch(
        "/api/settings/wechat-login",
        json={
            "enabled": True,
            "required_for_public_exams": required,
            "app_id": "wx-test-app-id",
            "app_secret": "wx-test-app-secret",
            "callback_base_url": "http://localhost:3000",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_admin_configures_wechat_without_exposing_secret(client):
    reset_wechat_configuration()
    default = client.get("/api/settings/wechat-login")
    assert default.status_code == 200
    assert default.json()["enabled"] is False
    assert default.json()["app_secret_configured"] is False

    incomplete = client.patch(
        "/api/settings/wechat-login",
        json={
            "enabled": True,
            "required_for_public_exams": True,
            "app_id": "",
            "app_secret": "",
            "callback_base_url": "http://localhost:3000",
        },
    )
    assert incomplete.status_code == 422

    configured = configure_wechat(client, required=True)
    assert configured["configuration_complete"] is True
    assert configured["app_secret_configured"] is True
    assert configured["callback_url"] == "http://localhost:3000/api/public/wechat/callback"
    assert "app_secret" not in configured

    retained = client.patch(
        "/api/settings/wechat-login",
        json={
            "enabled": True,
            "required_for_public_exams": False,
            "app_id": "wx-test-app-id",
            "callback_base_url": "http://localhost:3000",
        },
    )
    assert retained.status_code == 200
    assert retained.json()["app_secret_configured"] is True


def test_wechat_oauth_binds_browser_and_creates_identity(client, monkeypatch):
    reset_wechat_configuration()
    configure_wechat(client)
    _, quiz_id = create_shareable_quiz(client, "微信登录考试测试书")
    share = create_exam_share(client, quiz_id, "微信认证考试")

    def fake_exchange(_configuration, _code):
        return {
            "openid": "wechat-openid-1",
            "unionid": "wechat-unionid-1",
            "nickname": "微信读者",
            "avatar_url": "https://thirdwx.qlogo.cn/avatar.jpg",
        }

    monkeypatch.setattr("app.routers.wechat.exchange_wechat_code", fake_exchange)
    with TestClient(app) as public_client:
        login = public_client.get(
            "/api/public/wechat/login",
            params={"share_code": share["share_code"]},
            follow_redirects=False,
        )
        assert login.status_code == 307
        authorize_url = urlparse(login.headers["location"])
        authorize_query = parse_qs(authorize_url.query)
        assert authorize_url.netloc == "open.weixin.qq.com"
        assert authorize_query["appid"] == ["wx-test-app-id"]
        assert authorize_query["scope"] == ["snsapi_login"]
        state = authorize_query["state"][0]

        missing_nonce = TestClient(app).get(
            "/api/public/wechat/callback",
            params={"code": "temporary-code", "state": state},
            follow_redirects=False,
        )
        assert missing_nonce.status_code == 400

        callback = public_client.get(
            "/api/public/wechat/callback",
            params={"code": "temporary-code", "state": state},
            follow_redirects=False,
        )
        assert callback.status_code == 303
        assert callback.headers["location"].endswith(f"/exams/{share['share_code']}")
        assert get_settings().wechat_session_cookie_name in public_client.cookies

        intro = public_client.get(f"/api/public/exams/{share['share_code']}")
        assert intro.status_code == 200
        assert intro.json()["identity_type"] == "wechat"
        assert intro.json()["participant_name"] == "微信读者"
        assert intro.json()["participant_avatar_url"].endswith("avatar.jpg")

        started = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={},
        )
        assert started.status_code == 201
        attempt = started.json()
        assert attempt["participant_type"] == "wechat"
        assert attempt["participant_name"] == "微信读者"
        assert attempt["participant_avatar_url"].endswith("avatar.jpg")
        assert attempt["access_token"] is None

        repeated = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "冒用名称"},
        )
        assert repeated.status_code == 201
        assert repeated.json()["id"] == attempt["id"]

        submitted = public_client.post(
            f"/api/public/exam-attempts/{attempt['id']}/submit",
            json={"answers": [], "elapsed_seconds": 9},
        )
        assert submitted.status_code == 202
        history = public_client.get(f"/api/public/exams/{share['share_code']}")
        assert history.json()["existing_attempt_id"] == attempt["id"]
        assert history.json()["existing_attempt_status"] == "completed"

        replay = public_client.get(
            "/api/public/wechat/callback",
            params={"code": "temporary-code", "state": state},
            follow_redirects=False,
        )
        assert replay.status_code == 400

    manager = client.get(f"/api/exam-shares/{share['id']}")
    participant = manager.json()["attempts"][0]
    assert participant["participant_type"] == "wechat"
    assert participant["participant_avatar_url"].endswith("avatar.jpg")
    assert "openid" not in participant
    assert "unionid" not in participant


def test_required_wechat_login_blocks_anonymous_attempt(client):
    reset_wechat_configuration()
    configure_wechat(client, required=True)
    _, quiz_id = create_shareable_quiz(client, "强制微信登录测试书")
    share = create_exam_share(client, quiz_id, "仅限微信认证")

    with TestClient(app) as public_client:
        intro = public_client.get(f"/api/public/exams/{share['share_code']}")
        assert intro.status_code == 200
        assert intro.json()["wechat_login_enabled"] is True
        assert intro.json()["wechat_login_required"] is True
        blocked = public_client.post(
            f"/api/public/exams/{share['share_code']}/attempts",
            json={"participant_name": "匿名读者"},
        )
        assert blocked.status_code == 401
        assert blocked.json()["detail"] == "请先完成微信登录认证"

    reset_wechat_configuration()
