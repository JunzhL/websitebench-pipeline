"""Shared fixtures: one isolated database per test session.

The DATA_DIR environment variable must be set before ``app`` is imported
(the module binds the seam database path at import time), so it happens at
conftest import, before any test module loads.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

CLONE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLONE_ROOT))

_TMP = tempfile.mkdtemp(prefix="jefit-clone-tests-")
os.environ["DATA_DIR"] = _TMP
os.environ.setdefault("WEBSITEBENCH_JEFIT_ADMIN_TOKEN", "jefit-test-admin")

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
from backend import db  # noqa: E402

PRIMARY = {"username": "jefitdemo", "password": "Demo-Pass-2026!"}
ISOLATION = {"username": "isotest", "password": "Iso-Pass-2026!"}


def make_client() -> TestClient:
    # https base_url: the session cookie is __Host- (Secure) and the test
    # transport must retain it.
    return TestClient(app_module.app, base_url="https://clone.local")


def login(client: TestClient, who: dict | None = None) -> None:
    who = who or PRIMARY
    response = client.post(
        "/login",
        data={"username": who["username"], "password": who["password"]},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert response.headers["location"] == "/my-jefit"


@pytest.fixture()
def client() -> TestClient:
    return make_client()


@pytest.fixture()
def fresh_state(client: TestClient) -> TestClient:
    """Deterministically reseeded database + anonymous client."""

    db.reset()
    return client


@pytest.fixture()
def member(fresh_state: TestClient) -> TestClient:
    login(fresh_state)
    return fresh_state
