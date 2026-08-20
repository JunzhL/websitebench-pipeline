"""Shared fixtures: one isolated database per test session.

``DATA_DIR`` must be set before ``app`` is imported -- the module binds the
seam's database path at import time -- so it happens here, at conftest import,
before any test module loads.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

CLONE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLONE_ROOT))

_TMP = tempfile.mkdtemp(prefix="ipvanish-clone-tests-")
os.environ["DATA_DIR"] = _TMP
os.environ.setdefault("WEBSITEBENCH_IPVANISH_ADMIN_TOKEN", "ipvanish-test-admin")
os.environ.setdefault("SEED", "1")

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
from backend import db  # noqa: E402

PRIMARY = {
    "email": "avery.sandoval@example.invalid",
    "password": "Vanish-Demo-2026!",
}
ISOLATION = {
    "email": "morgan.reyes@example.invalid",
    "password": "Isolate-Demo-2026!",
}
PRIMARY_SUBSCRIPTION = "sub_primary_annual"
ISOLATION_SUBSCRIPTION = "sub_isolation_biennial"


def make_client() -> TestClient:
    # https base_url: the session cookie is __Host- (Secure) and the test
    # transport has to retain it.
    return TestClient(app_module.app, base_url="https://clone.local")


def sign_in(client: TestClient, who: dict | None = None) -> None:
    who = who or PRIMARY
    response = client.post("/login", data=dict(who), follow_redirects=False)
    assert response.status_code == 303, response.text
    assert response.headers["location"] == "/account/"


@pytest.fixture()
def client() -> TestClient:
    return make_client()


@pytest.fixture()
def fresh_state(client: TestClient) -> TestClient:
    """Deterministically reseeded database plus an anonymous client."""

    db.reset()
    return client


@pytest.fixture()
def subscriber(fresh_state: TestClient) -> TestClient:
    sign_in(fresh_state)
    return fresh_state
