"""Isolated GitLab clone test runtime."""

import os
import sys
import tempfile
from pathlib import Path

CLONE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLONE_DIR))

DATABASE_DIR = Path(tempfile.mkdtemp(prefix="gitlab-clone-tests-"))
os.environ["WEBSITEBENCH_SITE_BACKEND_DATABASE"] = str(DATABASE_DIR / "gitlab.sqlite3")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
from backend import domain  # noqa: E402


@pytest.fixture()
def client():
    app_module.AUTH.reset_site_state(
        site_reset=domain.reset,
        seed_accounts=[app_module.DEMO_ACCOUNT],
    )
    with TestClient(app_module.app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture()
def signed_in(client):
    response = client.post(
        "/users/sign_in",
        data={
            "identifier": "developer@gitlab.local",
            "password": "WebsiteBench!2026",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client
