"""Invariant `operable-controls` - browser level, real clicks only.

Carried forward from the jefit run, where three separate "renders but is
unusable" defects shipped while API tests, static closure and the pixel oracle
all passed: a submit left `pointer-events: none` from a captured disabled state,
a stepper whose slot markers were split mid-comment, and five tab panels
rendered stacked because the panel splitter ignored the tag stack.

So nothing here asserts the presence of text.  Every claim is made by clicking
the control a visitor would click and reading what changed, and every probe has
a negative control that proves it can fail.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import pytest

from conftest import CLONE_ROOT

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright is required for the operability gate"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def server():
    """The candidate started exactly as the acceptance manual starts it."""

    port = _free_port()
    data_dir = tempfile.mkdtemp(prefix="deleteme-operability-")
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


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as driver:
        instance = driver.chromium.launch(headless=True)
        try:
            yield instance
        finally:
            instance.close()


class Session:
    def __init__(self, page, offsite: list[str], failures: list[str]) -> None:
        self.page = page
        self.offsite = offsite
        self.failures = failures


def _session(browser, *, width: int = 1440, height: int = 900, ratio: int = 1):
    context = browser.new_context(
        viewport={"width": width, "height": height},
        device_scale_factor=ratio,
        locale="en-US",
        timezone_id="Etc/UTC",
    )
    offsite: list[str] = []
    failures: list[str] = []
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
            failures.append(f"{response.status} {response.url}")
            if response.status >= 400
            else None
        ),
    )
    return context, Session(page, offsite, failures)


@pytest.fixture()
def desktop(browser):
    context, session = _session(browser)
    try:
        yield session
    finally:
        context.close()


def _ready(session: Session, url: str) -> None:
    session.page.goto(url, wait_until="load")
    session.page.wait_for_selector("html[data-deleteme-clone='ready']", timeout=15000)


# A control that renders but cannot be used is a defect.  This probe is the
# jefit lesson in one expression.
INERT_PROBE = """
(selector) => {
  const node = document.querySelector(selector);
  if (!node) return {found: false};
  const box = node.getBoundingClientRect();
  const style = getComputedStyle(node);
  return {
    found: true,
    visible: box.width > 0 && box.height > 0 &&
             style.visibility !== 'hidden' && style.display !== 'none' &&
             Number(style.opacity) > 0.05,
    clickable: style.pointerEvents !== 'none',
    enabled: !node.disabled && node.getAttribute('aria-disabled') !== 'true',
  };
}
"""

VISIBLE_TERM_GROUPS = """
() => {
  const out = {'1y': 0, '2y': 0};
  document.querySelectorAll('[data-term-group]').forEach((node) => {
    const box = node.getBoundingClientRect();
    if (box.width > 0 && box.height > 0) out[node.dataset.termGroup] += 1;
  });
  return out;
}
"""


def test_plan_tabs_filter_by_real_click(server, desktop) -> None:
    """The billing-term strip is the grid's only operable filter, and it works.

    The frozen `plans.term-1y` and `plans.term-2y` captures are the oracle: the
    source's own filter shows one term group and hides the other.
    """

    _ready(desktop, f"{server}/privacy-protection-plans/")

    # 2 Years is the default: every `1-Year` group ships `display:none`.
    before = desktop.page.evaluate(VISIBLE_TERM_GROUPS)
    assert before["2y"] == 4, before
    assert before["1y"] == 0, before

    for selector in ("[data-term-tab='1y']", "[data-term-tab='2y']"):
        state = desktop.page.evaluate(INERT_PROBE, selector)
        assert state["found"], selector
        assert state["visible"], (selector, state)
        assert state["clickable"], (selector, state)

    desktop.page.click("[data-term-tab='1y']")
    desktop.page.wait_for_timeout(150)
    after = desktop.page.evaluate(VISIBLE_TERM_GROUPS)
    assert after["1y"] == 4, after
    assert after["2y"] == 0, after

    # The one-year figures are now the ones on screen.
    body = desktop.page.inner_text("body")
    assert "Billed at $129.00 annually." in body
    assert "Billed at $209.00 every 2 years." not in body

    desktop.page.click("[data-term-tab='2y']")
    desktop.page.wait_for_timeout(150)
    restored = desktop.page.evaluate(VISIBLE_TERM_GROUPS)
    assert restored == before, (restored, before)
    assert not desktop.offsite, sorted(set(desktop.offsite))[:5]


def test_the_pricing_grid_filters_on_both_of_its_axes(server, desktop) -> None:
    """`/pricing/` ships a second, newer grid with *two* operable strips -
    billing term and plan size - and both have to work."""

    _ready(desktop, f"{server}/pricing/")
    visible = """
    () => Array.from(document.querySelectorAll('.dm-card'))
      .filter((n) => n.getBoundingClientRect().height > 0)
      .map((n) => `${n.dataset.term}:${n.dataset.plan}`)
    """
    assert desktop.page.evaluate(visible) == ["2y:couple"]

    desktop.page.click("[uk-filter-control=\"filter: [data-plan='single']; group: plan\"]")
    desktop.page.wait_for_timeout(150)
    assert desktop.page.evaluate(visible) == ["2y:single"]

    desktop.page.click("[data-term-tab='1y']")
    desktop.page.wait_for_timeout(150)
    assert desktop.page.evaluate(visible) == ["1y:single"]


def test_start_protection_carries_the_plan(server, desktop) -> None:
    """The P0 selection step: the card labelled `1 Person` carries qty=1."""

    _ready(desktop, f"{server}/privacy-protection-plans/")
    link = desktop.page.locator(
        "[data-term-group='2y'] a[data-start-protection='2-1']"
    ).first
    assert link.is_visible()
    state = desktop.page.evaluate(
        INERT_PROBE, "[data-term-group='2y'] a[data-start-protection='2-1']"
    )
    assert state["visible"] and state["clickable"], state

    # It really is the one-person card, read from the DOM rather than assumed.
    person = link.evaluate(
        "(node) => node.closest('.el-content').querySelector('.person').textContent"
    )
    assert person.strip() == "1 Person"

    link.click()
    desktop.page.wait_for_load_state("load")
    assert "/checkout" in desktop.page.url
    assert "qty=1" in desktop.page.url
    assert "term=2" in desktop.page.url
    desktop.page.wait_for_selector("html[data-deleteme-clone='ready']", timeout=15000)
    summary = desktop.page.inner_text("[data-plan-key='price2Years1Person']")
    assert "Two years of DeleteMe for 1 person." in summary
    assert desktop.page.inner_text("[data-summary-total]") == "$209.00"


def test_checkout_submits_by_real_click(server, desktop) -> None:
    """Fill the form the way a visitor would, then press the button."""

    _ready(desktop, f"{server}/checkout?plan=standard&term=1&qty=1")

    submit = desktop.page.evaluate(INERT_PROBE, "[data-checkout-submit]")
    assert submit["found"] and submit["visible"], submit
    assert submit["clickable"] and submit["enabled"], submit

    # Submitting empty first: the validation is the source's own wording.
    desktop.page.click("[data-checkout-submit]")
    desktop.page.wait_for_load_state("load")
    errors = desktop.page.inner_text("[data-checkout-errors]")
    assert "Please enter your first name" in errors
    assert "Please accept the terms and conditions" in errors
    assert len(desktop.failures) == 1 and desktop.failures[0].startswith("422 ")
    desktop.failures.clear()

    desktop.page.wait_for_selector("html[data-deleteme-clone='ready']", timeout=15000)
    desktop.page.fill("#dm-first-name", "Robin")
    desktop.page.fill("#dm-last-name", "Vale")
    desktop.page.fill("#dm-email", "robin.vale@example.invalid")
    desktop.page.fill("#dm-address", "9 Placeholder Court, Springfield, EX 00003")
    desktop.page.check("input[value='sandbox-approved']")
    desktop.page.check("#dm-agree-billing")
    desktop.page.check("#dm-agree-terms")
    desktop.page.click("[data-checkout-submit]")
    desktop.page.wait_for_url("**/checkout/complete", timeout=15000)

    body = desktop.page.inner_text("body")
    assert "Payment Successful!" in body
    assert "Local sandbox order" in body
    assert not desktop.offsite, sorted(set(desktop.offsite))[:5]
    assert not desktop.failures, sorted(set(desktop.failures))[:5]


def test_the_promo_panel_opens(server, desktop) -> None:
    _ready(desktop, f"{server}/checkout?plan=standard&term=2&qty=1")
    assert desktop.page.locator("[data-promo-panel]").count() == 1
    assert not desktop.page.locator("[data-promo-panel]").is_visible()
    desktop.page.click("[data-promo-toggle]")
    desktop.page.wait_for_timeout(120)
    assert desktop.page.locator("[data-promo-panel]").is_visible()


def test_the_sign_in_form_posts(server, desktop) -> None:
    _ready(desktop, f"{server}/login")
    # The source has no remember-me control and exactly one identity provider.
    body = desktop.page.inner_text("body")
    assert "Continue with Google" in body
    assert "remember" not in body.casefold()
    assert desktop.page.locator("button:has-text('Continue with Apple')").count() == 0

    desktop.page.fill("input[name='email']", "avery.quill@example.invalid")
    desktop.page.fill("input[name='password']", "OfflineClone!2026")
    desktop.page.click("button[type='submit']")
    desktop.page.wait_for_url("**/account", timeout=15000)
    assert "Dashboard" in desktop.page.inner_text("h1")


@pytest.mark.parametrize("ratio", [1, 2, 3])
def test_the_p0_journey_walks_at_every_device_pixel_ratio(
    server, browser, ratio: int
) -> None:
    """Home to confirmation, with no offsite request and no broken payload.

    Ratio matters: a browser at 2 or 3 picks a different `srcset` candidate, and
    that is exactly where an earlier site's images broke while every ratio-1
    gate reported clean.
    """

    context, session = _session(browser, ratio=ratio)
    try:
        _ready(session, f"{server}/")
        session.page.click("a[href='/privacy-protection-plans/']:visible >> nth=0")
        session.page.wait_for_url("**/privacy-protection-plans/", timeout=15000)
        session.page.wait_for_selector(
            "html[data-deleteme-clone='ready']", timeout=15000
        )
        session.page.click("[data-term-group='2y'] a[data-start-protection='2-1']")
        session.page.wait_for_url("**/checkout*", timeout=15000)
        session.page.wait_for_selector(
            "html[data-deleteme-clone='ready']", timeout=15000
        )
        session.page.fill("#dm-first-name", "Robin")
        session.page.fill("#dm-last-name", "Vale")
        session.page.fill("#dm-email", f"robin.vale.{ratio}@example.invalid")
        session.page.fill("#dm-address", "9 Placeholder Court, Springfield, EX 00003")
        session.page.check("input[value='sandbox-approved']")
        session.page.check("#dm-agree-billing")
        session.page.check("#dm-agree-terms")
        session.page.click("[data-checkout-submit]")
        session.page.wait_for_url("**/checkout/complete", timeout=15000)
        assert "Payment Successful!" in session.page.inner_text("body")

        broken = session.page.evaluate(
            """
            () => Array.from(document.images)
              .filter((img) => img.currentSrc && !img.complete)
              .map((img) => img.currentSrc)
            """
        )
        assert not broken, broken[:5]
        assert not session.offsite, sorted(set(session.offsite))[:5]
        assert not session.failures, sorted(set(session.failures))[:5]
    finally:
        context.close()


@pytest.mark.parametrize("route", ["/", "/privacy-protection-plans/", "/pricing/"])
def test_no_image_fails_to_decode_at_ratio_three(server, browser, route: str) -> None:
    """Load every image the page advertises, at the ratio that picks the widest
    `srcset` candidate, and assert each one actually decoded."""

    context, session = _session(browser, ratio=3)
    try:
        _ready(session, f"{server}{route}")
        session.page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        session.page.wait_for_timeout(1200)
        broken = session.page.evaluate(
            """
            () => Array.from(document.images)
              .filter((img) => img.complete && img.naturalWidth === 0)
              .map((img) => img.currentSrc || img.src)
            """
        )
        assert not broken, broken[:8]
        assert not session.failures, sorted(set(session.failures))[:8]
    finally:
        context.close()


def test_detects_a_disabled_control(server, desktop) -> None:
    """Negative control: prove the operability probe can fail.

    Without this, a green operability suite could mean "the controls work" or
    "the probe never looked".  The three defects reproduced here are the three
    that shipped on an earlier site.
    """

    _ready(desktop, f"{server}/checkout?plan=standard&term=1&qty=1")
    clean = desktop.page.evaluate(INERT_PROBE, "[data-checkout-submit]")
    assert clean["visible"] and clean["clickable"] and clean["enabled"], clean

    # 1. `pointer-events: none` left over from a captured disabled state.
    desktop.page.evaluate(
        "() => document.querySelector('[data-checkout-submit]')"
        ".style.pointerEvents = 'none'"
    )
    inert = desktop.page.evaluate(INERT_PROBE, "[data-checkout-submit]")
    assert not inert["clickable"], inert
    with pytest.raises(AssertionError):
        assert inert["clickable"], "the probe did not notice pointer-events: none"

    # 2. A genuinely disabled button.
    desktop.page.evaluate(
        "() => { const n = document.querySelector('[data-checkout-submit]');"
        " n.style.pointerEvents = ''; n.disabled = true; }"
    )
    disabled = desktop.page.evaluate(INERT_PROBE, "[data-checkout-submit]")
    assert disabled["clickable"] and not disabled["enabled"], disabled
    with pytest.raises(AssertionError):
        assert disabled["enabled"], "the probe did not notice a disabled control"

    # 3. A control that renders with zero area.
    desktop.page.evaluate(
        "() => { const n = document.querySelector('[data-checkout-submit]');"
        " n.disabled = false; n.style.display = 'none'; }"
    )
    hidden = desktop.page.evaluate(INERT_PROBE, "[data-checkout-submit]")
    assert not hidden["visible"], hidden

    # ... and the probe returns to clean once the defects are undone.
    desktop.page.reload(wait_until="load")
    desktop.page.wait_for_selector("html[data-deleteme-clone='ready']", timeout=15000)
    restored = desktop.page.evaluate(INERT_PROBE, "[data-checkout-submit]")
    assert restored == clean, (restored, clean)


def test_detects_a_filter_that_stopped_filtering(server, desktop) -> None:
    """Negative control for the tab probe: unwire the control and it must fail."""

    _ready(desktop, f"{server}/privacy-protection-plans/")
    baseline = desktop.page.evaluate(VISIBLE_TERM_GROUPS)
    assert baseline["2y"] == 4 and baseline["1y"] == 0

    # Replace the control with an inert clone, exactly as a lost event listener
    # would leave it.
    desktop.page.evaluate(
        """
        () => {
          const node = document.querySelector("[data-term-tab='1y']");
          node.replaceWith(node.cloneNode(true));
        }
        """
    )
    desktop.page.click("[data-term-tab='1y']")
    desktop.page.wait_for_timeout(150)
    after = desktop.page.evaluate(VISIBLE_TERM_GROUPS)
    with pytest.raises(AssertionError):
        assert after["1y"] == 4, after


def test_no_page_scrolls_sideways_on_a_phone(server, browser) -> None:
    context, session = _session(browser, width=390, height=844, ratio=3)
    try:
        offenders = []
        for route in (
            "/",
            "/privacy-protection-plans/",
            "/checkout?plan=standard&term=2&qty=1",
            "/login",
        ):
            _ready(session, f"{server}{route}")
            scroll_width, client_width = session.page.evaluate(
                "() => [document.documentElement.scrollWidth,"
                " document.documentElement.clientWidth]"
            )
            if scroll_width > client_width + 1:
                offenders.append((route, scroll_width, client_width))
        assert not offenders, offenders
    finally:
        context.close()


def test_clone_local_app_furniture_restores_border_box(server, desktop) -> None:
    """The source app's Emotion runtime supplies a global border-box reset.

    Captured outerHTML cannot retain CSSOM-only rules. Pin the replacement on
    the two clone-local layout roots so Linux and macOS cannot disagree about
    whether 100% width includes horizontal padding.
    """

    _ready(desktop, f"{server}/checkout?plan=standard&term=2&qty=1")
    checkout = desktop.page.evaluate(
        "() => getComputedStyle(document.querySelector('.dm-checkout')).boxSizing"
    )
    field = desktop.page.evaluate(
        "() => getComputedStyle(document.querySelector('#dm-first-name')).boxSizing"
    )
    assert checkout == "border-box"
    assert field == "border-box"


def test_home_restores_captured_responsive_runtime_state(server, browser) -> None:
    expected_background = {
        1024: "deletemehero-wrc-6b31f49e.webp",
        1440: "deletemehero-wrc-e6d8260f.webp",
    }
    for width, height in ((1024, 768), (1440, 900)):
        context, session = _session(browser, width=width, height=height, ratio=1)
        try:
            _ready(session, f"{server}/")
            state = session.page.locator(
                '[data-srcset*="deletemehero-wrc"]:visible'
            ).evaluate(
                "e => ({height: e.getBoundingClientRect().height, "
                "background: getComputedStyle(e).backgroundImage})"
            )
            assert state["height"] == 675
            assert expected_background[width] in state["background"]
        finally:
            context.close()

    context, session = _session(browser, width=390, height=844, ratio=1)
    try:
        _ready(session, f"{server}/")
        gap = session.page.locator(
            "#mobilehero .jdm-button-medium .el-item"
        ).evaluate_all(
            "els => els[1].getBoundingClientRect().top - "
            "els[0].getBoundingClientRect().bottom"
        )
        assert gap == 15
    finally:
        context.close()
