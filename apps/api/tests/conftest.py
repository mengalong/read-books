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


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client

