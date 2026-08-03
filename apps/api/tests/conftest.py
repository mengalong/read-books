import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

test_root = Path(tempfile.mkdtemp(prefix="read-books-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{test_root / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(test_root / "uploads")
os.environ["PARSED_DIR"] = str(test_root / "parsed")
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["MOCK_MODE"] = "true"

from app.main import app  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services.auth import create_user_with_workspace  # noqa: E402

TEST_ADMIN_USERNAME = "test-admin"
TEST_ADMIN_PASSWORD = "TestAdmin1!"


def ensure_default_test_admin() -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == TEST_ADMIN_USERNAME).one_or_none()
        if user is None:
            create_user_with_workspace(
                db,
                username=TEST_ADMIN_USERNAME,
                display_name="测试管理员",
                password=TEST_ADMIN_PASSWORD,
                role="admin",
                must_change_password=False,
            )
            db.commit()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        ensure_default_test_admin()
        response = test_client.post(
            "/api/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        assert response.status_code == 200
        yield test_client
