"""Invariant `zero-offsite-requests`.

The source loads 35 non-primary hosts.  None may be reachable from the
candidate - not a font, not a pixel, and not a reference hiding inside a
mirrored stylesheet, which is how the ipvanish rebuild briefly reintroduced
offsite font requests after its mirror grew a new `.css`.

Two independent probes: a regex over everything the clone serves or ships, and
a real browser whose every request is recorded.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import CLONE_ROOT, JOURNEY_ROUTES, SITE_ROOT, SUBSCRIBER_ROUTES, sign_in

# The static diagnostic's own rule, duplicated so this suite fails first.
REMOTE_REF = re.compile(
    r"(?i)(?:src|href|action|url)\s*[=(:]\s*[\"']?\s*"
    r"(?:https?:)?//(?!localhost|127\.0\.0\.1)[a-z0-9.-]+\.[a-z]{2,}"
)
SHIPPED_SUFFIXES = {".html", ".css", ".js", ".svg"}


def test_no_page_in_a_frozen_journey_makes_an_offsite_request(
    client: TestClient,
) -> None:
    routes = list(JOURNEY_ROUTES)
    documents = {route: client.get(route).text for route in routes}
    sign_in(client)
    for route in SUBSCRIBER_ROUTES:
        documents[route] = client.get(route).text

    for route, text in documents.items():
        hits = REMOTE_REF.findall(text)
        assert not hits, (route, hits[:5])
    assert len(documents) >= 25


def test_no_shipped_clone_local_file_carries_a_remote_reference() -> None:
    """Including the localised stylesheet siblings, which is where a newly
    mirrored `.css` reintroduces an offsite font."""

    scanned = 0
    for path in sorted((CLONE_ROOT / "static" / "site").rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in SHIPPED_SUFFIXES:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = REMOTE_REF.findall(text)
        assert not hits, (path.name, hits[:5])
    for path in sorted((CLONE_ROOT / "frontend").rglob("*.html")):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = REMOTE_REF.findall(text)
        assert not hits, (path.name, hits[:5])
    assert scanned > 40, f"only {scanned} shipped files scanned"


def test_no_served_document_references_a_pristine_mirror_stylesheet() -> None:
    """A pristine mirrored stylesheet keeps the source's own absolute `url()`
    targets in its own bytes.  It passes an external-reference inspector,
    because the *page* reference is local - and then fetches a font from Google
    at runtime.  Every stylesheet a page loads must be a localised sibling."""

    offenders = []
    for path in sorted((CLONE_ROOT / "frontend" / "pages").glob("*.html")):
        text = path.read_text(encoding="utf-8")
        for ref in re.findall(r'/static/assets/[^"\')\s]+\.css', text):
            offenders.append((path.name, ref))
    assert not offenders, offenders[:10]


def test_detects_an_injected_offsite_reference() -> None:
    """Negative control: the regex must fire on a planted reference."""

    clean = '<img src="/static/assets/2026-08-20.deleteme-r1/joindeleteme.com/a.png">'
    assert not REMOTE_REF.search(clean)
    for planted in (
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Poppins">',
        '<img src="//static-tracking.klaviyo.com/pixel.gif">',
        "@font-face { src: url(https://fonts.gstatic.com/s/poppins/v1/x.woff2); }",
        '<form action="https://example.com/collect">',
    ):
        assert REMOTE_REF.search(planted), planted


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def live_server():
    playwright_available = True
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:  # pragma: no cover - environment dependent
        playwright_available = False
    if not playwright_available:
        pytest.skip("playwright is required for the browser network ledger")

    port = _free_port()
    data_dir = tempfile.mkdtemp(prefix="deleteme-netclosure-")
    env = dict(os.environ, DATA_DIR=data_dir, SEED="1", TZ="Etc/UTC")
    env.pop("WEBSITEBENCH_SITE_BACKEND_DATABASE", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(CLONE_ROOT),
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    import urllib.error
    import urllib.request

    for _ in range(160):
        try:
            with urllib.request.urlopen(f"{base}/healthz", timeout=1) as response:
                if response.status == 200:
                    break
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    else:  # pragma: no cover
        process.kill()
        pytest.fail("the clone did not become healthy")
    try:
        yield base
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            process.kill()


BROWSER_WALK = (
    "/",
    "/privacy-protection-plans/",
    "/pricing/",
    "/checkout?plan=standard&term=2&qty=1",
    "/login",
    "/help",
    "/checkout/complete",
)


@pytest.mark.parametrize("ratio", [1, 2, 3])
def test_a_real_browser_walk_makes_no_offsite_request(live_server, ratio: int) -> None:
    """The ledger the ratio-1-only gates could not keep.

    Device pixel ratio matters: the browser picks a different `srcset`
    candidate at 2 and 3, and a candidate the mirror lacks is both a broken
    image and, if it were absolute, an offsite request.
    """

    from playwright.sync_api import sync_playwright

    offsite: list[str] = []
    failed: list[str] = []
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=ratio,
            locale="en-US",
            timezone_id="Etc/UTC",
        )
        page = context.new_page()
        page.on(
            "request",
            lambda request: (
                offsite.append(request.url)
                if not request.url.startswith(
                    ("http://127.0.0.1", "data:", "blob:", "about:")
                )
                else None
            ),
        )
        page.on(
            "response",
            lambda response: (
                failed.append(f"{response.status} {response.url}")
                if response.status >= 400
                else None
            ),
        )
        for route in BROWSER_WALK:
            page.goto(f"{live_server}{route}", wait_until="load")
            page.wait_for_selector("html[data-deleteme-clone='ready']", timeout=15000)
            page.wait_for_timeout(250)
        context.close()
        browser.close()

    assert not offsite, sorted(set(offsite))[:10]
    assert not failed, sorted(set(failed))[:10]
