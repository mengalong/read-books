from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import SiteFooterConfiguration

from app.main import app


def reset_site_footer_configuration() -> None:
    with SessionLocal() as db:
        db.query(SiteFooterConfiguration).delete()
        db.commit()


def test_site_footer_configuration_is_public_and_admin_editable(client):
    reset_site_footer_configuration()

    with TestClient(app) as public_client:
        empty = public_client.get("/api/site-footer")
        assert empty.status_code == 200
        assert empty.json()["configuration_complete"] is False
        assert empty.json()["record_number"] == ""
        assert empty.json()["record_url"] == ""

    incomplete = client.put(
        "/api/site-footer",
        json={
            "record_number": "京ICP备12345678号",
            "record_url": "",
        },
    )
    assert incomplete.status_code == 422

    updated = client.put(
        "/api/site-footer",
        json={
            "record_number": "京ICP备12345678号",
            "record_url": "https://beian.miit.gov.cn/",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["configuration_complete"] is True
    assert updated.json()["record_number"] == "京ICP备12345678号"
    assert updated.json()["record_url"] == "https://beian.miit.gov.cn/"

    with TestClient(app) as public_client:
        saved = public_client.get("/api/site-footer")
        assert saved.status_code == 200
        assert saved.json()["configuration_complete"] is True
        assert saved.json()["record_number"] == "京ICP备12345678号"
        assert saved.json()["record_url"] == "https://beian.miit.gov.cn/"
