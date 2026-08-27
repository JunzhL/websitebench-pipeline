"""Shared fixtures.

The writable-directory environment is set at *import* time, before `app` is
imported, because the app binds its database path at import time too.  Getting
that order wrong is what put a database inside a read-only candidate root on an
earlier site.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

CLONE_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = CLONE_ROOT.parent
sys.path.insert(0, str(CLONE_ROOT))

_TMP = tempfile.mkdtemp(prefix="deleteme-clone-tests-")
os.environ["DATA_DIR"] = _TMP
os.environ.setdefault("WEBSITEBENCH_DELETEME_ADMIN_TOKEN", "deleteme-test-admin")
os.environ.setdefault("SEED", "1")
os.environ.setdefault("TZ", "Etc/UTC")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
from backend import catalogue  # noqa: E402
from backend import db  # noqa: E402

PRIMARY = db.PRIMARY
ISOLATION = db.ISOLATION
PRIMARY_SUBSCRIPTION = db.PRIMARY_SUBSCRIPTION
ISOLATION_SUBSCRIPTION = db.ISOLATION_SUBSCRIPTION

# Every synthetic buyer this suite invents.  `.invalid` can never resolve.
BUYER = {
    "firstName": "Robin",
    "lastName": "Vale",
    "email": "robin.vale@example.invalid",
    "address": "9 Placeholder Court, Springfield, EX 00003",
}

# Routes a frozen journey walks, plus the two not-found behaviours and search.
JOURNEY_ROUTES: tuple[str, ...] = (
    "/",
    "/privacy-protection-plans/",
    "/pricing/",
    "/signup/",
    "/scan/",
    "/how-we-work/",
    "/sites-we-remove-from/",
    "/reviews/",
    "/about-us/",
    "/security/",
    "/blog/",
    "/blog/opt-out-guides/",
    "/help",
    "/policies",
    "/login",
    "/password/forgot",
    "/password/set",
    "/checkout?plan=standard&term=1&qty=1",
    "/checkout?term=2&qty=4",
    "/checkout/complete",
    "/?s=zzzz-no-match-websitebench",
    "/zzzz-no-match-websitebench/",
    "/account/zzzz-no-such-route",
)

SUBSCRIBER_ROUTES: tuple[str, ...] = (
    "/account",
    "/account/profile",
    "/account/reports",
    "/account/billing",
    "/account/plan",
)


def make_client() -> TestClient:
    # An https base URL: the session cookie is `__Host-` (Secure), and the test
    # transport has to be allowed to keep it.
    return TestClient(app_module.app, base_url="https://clone.local")


def sign_in(client: TestClient, who: dict | None = None) -> None:
    account = who or PRIMARY
    client.get("/login")
    response = client.post(
        "/login",
        data={"email": account["email"], "password": account["password"]},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.status_code


def purchase(client: TestClient, *, term: int = 1, qty: int = 1, attempt: str = "1"):
    return client.post(
        "/checkout",
        data={
            **BUYER,
            "term": str(term),
            "qty": str(qty),
            "scenario": "sandbox-approved",
            "agree_billing": "yes",
            "agree_terms": "yes",
            "attempt": attempt,
        },
        follow_redirects=False,
    )


@pytest.fixture()
def client() -> TestClient:
    return make_client()


@pytest.fixture()
def fresh_state(client: TestClient) -> TestClient:
    db.reset()
    app_module._page_cache.clear()
    return make_client()


@pytest.fixture()
def subscriber(fresh_state: TestClient) -> TestClient:
    sign_in(fresh_state)
    return fresh_state


__all__ = [
    "BUYER",
    "CLONE_ROOT",
    "ISOLATION",
    "ISOLATION_SUBSCRIPTION",
    "JOURNEY_ROUTES",
    "PRIMARY",
    "PRIMARY_SUBSCRIPTION",
    "SITE_ROOT",
    "SUBSCRIBER_ROUTES",
    "app_module",
    "catalogue",
    "db",
    "make_client",
    "purchase",
    "sign_in",
]
