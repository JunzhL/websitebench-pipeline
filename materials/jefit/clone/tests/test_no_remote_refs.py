"""Network-closure invariant: no runtime-loadable remote reference ships in
any served document or clone-local asset, and the detector itself is proven
live by a negative probe."""

from __future__ import annotations

import re
from pathlib import Path

from conftest import login

CLONE_ROOT = Path(__file__).resolve().parents[1]

# The diagnostics audit shape: src/href/action attributes and CSS url().
REMOTE_REF = re.compile(
    r"(?i)(?:src|href|action|url)\s*[=(:]\s*[\"']?\s*"
    r"(?:https?:)?//(?!localhost|127\.0\.0\.1)[a-z0-9.-]+\.[a-z]{2,}"
)

SERVED_ROUTES = [
    "/",
    "/elite",
    "/exercises",
    "/exercises?page=2",
    "/exercises/2/barbell-bench-press",
    "/routines",
    "/routines/beginner",
    "/routines/19113/6-weeks-to-six-pack-abs",
    "/login",
    "/login/forgot-password",
    "/signup",
    "/signup/results",
    "/signup/register",
    "/support",
    "/support/faq",
    "/about-us",
    "/community/",
    "/blog",
    "/terms-of-use",
    "/privacy-policy",
    "/press-media",
    "/zzzz-not-found",
]
MEMBER_ROUTES = [
    "/my-jefit",
    "/my-jefit/qa",
    "/my-jefit/popular",
    "/my-jefit/workouts",
    "/my-jefit/progress/history",
    "/my-jefit/progress/body-stats",
    "/my-jefit/progress/insights",
    "/my-jefit/progress/photos",
    "/my-jefit/exercises",
    "/my-jefit/exercises/find",
    "/my-jefit/settings",
    "/elite/checkout?isMyJefit=true&sub=yearly",
]


def test_served_public_documents_have_no_remote_refs(client) -> None:
    for route in SERVED_ROUTES:
        text = client.get(route).text
        hits = REMOTE_REF.findall(text)
        assert not hits, (route, hits[:5])


def test_served_member_documents_have_no_remote_refs(fresh_state) -> None:
    login(fresh_state)
    for route in MEMBER_ROUTES:
        response = fresh_state.get(route)
        assert response.status_code == 200, route
        hits = REMOTE_REF.findall(response.text)
        assert not hits, (route, hits[:5])


def test_clone_local_site_assets_have_no_remote_refs() -> None:
    for path in (CLONE_ROOT / "static" / "site").rglob("*"):
        if path.suffix in {".js", ".css", ".html"}:
            hits = REMOTE_REF.findall(path.read_text())
            assert not hits, (path.name, hits[:5])


def test_localized_css_has_no_remote_refs() -> None:
    css_root = CLONE_ROOT / "static" / "css"
    files = list(css_root.rglob("*"))
    assert files, "localized css tree is missing"
    for path in files:
        if path.is_file():
            hits = REMOTE_REF.findall(
                path.read_text(encoding="utf-8", errors="replace")
            )
            assert not hits, (str(path), hits[:5])


def test_detector_flags_injected_remote_ref() -> None:
    """Negative control: the audit regex must catch a real remote load."""

    poisoned = '<img src="https://evil.example.com/pixel.gif">'
    assert REMOTE_REF.search(poisoned)
    poisoned_css = "body{background:url(//cdn.example.net/x.png)}"
    assert REMOTE_REF.search(poisoned_css)
    clean = '<img src="/static/assets/x.png">'
    assert not REMOTE_REF.search(clean)
