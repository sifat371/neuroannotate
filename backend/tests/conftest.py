from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import configure_database
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings.data_dir = tmp_path / "data"
    settings.sample_data_dir = tmp_path / "sample_data"
    configure_database(f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(create_app()) as test_client:
        yield test_client
