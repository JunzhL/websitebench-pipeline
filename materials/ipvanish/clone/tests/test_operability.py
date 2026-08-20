"""Operability in a real browser, not merely "the endpoint accepts a POST".

Carried over from the JEFIT run, where passing API tests, a clean static
diagnostic and a passing pixel oracle together missed four controls that
rendered but could not be operated.  Every control a frozen journey depends on
is clicked here, at its captured viewport, in Chromium.

The suite also records every request the browser makes and fails on any that
leaves the loopback origin.
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
from pathlib import Path

import pytest

CLONE_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = {"width": 1440, "height": 900}
TABLET = {"width": 1024, "height": 768}
MOBILE = {"width": 390, "height": 844}
FROZEN_VIEWPORTS = (("desktop", DESKTOP), ("tablet", TABLET), ("mobile", MOBILE))
PRIMARY_EMAIL = "avery.sandoval@example.invalid"
PRIMARY_PASSWORD = "Vanish-Demo-2026!"

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright is required for the operability gate"
)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def server():
    """The candidate started exactly as ACCEPTANCE.md and the driver start it."""

    port = _free_port()
    data_dir = tempfile.mkdtemp(prefix="ipvanish-operability-")
    env = dict(
        os.environ,
        DATA_DIR=data_dir,
        SEED="1",
        TZ="Etc/UTC",
        WEBSITEBENCH_IPVANISH_ADMIN_TOKEN="ipvanish-test-admin",
    )
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
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError("the clone exited before answering /healthz")
            try:
                with urllib.request.urlopen(f"{base}/healthz", timeout=1) as answer:
                    if answer.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)
        else:
            raise RuntimeError("the clone never answered /healthz")
        yield base
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            process.kill()


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as driver:
        instance = driver.chromium.launch(headless=True)
        try:
            yield instance
        finally:
            instance.close()


class Page:
    """One page plus the offsite-request ledger recorded while it was open."""

    def __init__(self, page, offsite: list[str]) -> None:
        self.page = page
        self.offsite = offsite


@pytest.fixture()
def desktop(browser):
    yield from _page(browser, DESKTOP)


@pytest.fixture()
def mobile(browser):
    yield from _page(browser, MOBILE)


def _page(browser, viewport):
    context = browser.new_context(
        viewport=viewport, locale="en-US", timezone_id="Etc/UTC"
    )
    offsite: list[str] = []
    page = context.new_page()
    page.on(
        "request",
        lambda request: (
            offsite.append(request.url)
            if not request.url.startswith(("http://127.0.0.1", "data:", "blob:", "about:"))
            else None
        ),
    )
    try:
        yield Page(page, offsite)
    finally:
        context.close()


def _ready(handle: Page, url: str) -> None:
    handle.page.goto(url, wait_until="load")
    handle.page.wait_for_selector("html[data-ipvanish-clone='ready']", timeout=15000)


# -- the operability probe --------------------------------------------------

INERT_PROBE = """
(selectors) => {
  const bad = [];
  for (const selector of selectors) {
    for (const node of document.querySelectorAll(selector)) {
      const box = node.getBoundingClientRect();
      const style = window.getComputedStyle(node);
      const visible =
        style.display !== 'none' &&
        style.visibility !== 'hidden' &&
        style.opacity !== '0' &&
        box.width > 0 &&
        box.height > 0;
      if (!visible) continue;
      if (style.pointerEvents === 'none') bad.push([selector, 'pointer-events:none']);
      if (node.disabled === true) bad.push([selector, 'disabled']);
      if (node.getAttribute('aria-disabled') === 'true') bad.push([selector, 'aria-disabled']);
    }
  }
  return bad;
}
"""

JOURNEY_CONTROLS = [
    ".plan-type-link",
    ".pricing-nav-wrapper .wp-block-column p",
    "a.wp-block-button__link",
    "li.c-payment-method-type-select-card",
    "#ipvanish-sandbox-form input",
    "#ipvanish-sandbox-form select",
    "button[data-clone-action='subscribe']",
    "form[action='/login'] button",
    "form[action='/login/reset-password'] button",
    "[data-clone-action]",
]


def _assert_no_inert_controls(handle: Page) -> None:
    findings = handle.page.evaluate(INERT_PROBE, JOURNEY_CONTROLS)
    assert not findings, findings


def _visible_periods(handle: Page) -> list[str]:
    return handle.page.evaluate(
        """
        () => {
          const panels = {
            biennial: '.pricing-pg-biennial-tab',
            annual: '.pricing-pg-yearly-tab',
            monthly: '.pricing-pg-monthly-tab'
          };
          const shown = [];
          for (const [key, selector] of Object.entries(panels)) {
            for (const node of document.querySelectorAll(selector)) {
              const box = node.getBoundingClientRect();
              if (box.height > 0 && box.width > 0) { shown.push(key); break; }
            }
          }
          return shown;
        }
        """
    )


# -- pricing ----------------------------------------------------------------


def test_billing_tabs_switch_period_by_real_click(server, desktop) -> None:
    _ready(desktop, f"{server}/pricing/")
    assert _visible_periods(desktop) == ["biennial"], "default tab is not 2-Year"
    for label, period, figure in (
        ("Monthly Plan", "monthly", "Renews Monthly at $14.99."),
        ("Yearly Plan", "annual", "$46.68 for the first year."),
        ("2-Year Plan", "biennial", "$59.76 for the first 2 years."),
    ):
        desktop.page.click(f".plan-type-link:has-text('{label}')")
        desktop.page.wait_for_timeout(150)
        assert _visible_periods(desktop) == [period], (label, _visible_periods(desktop))
        assert desktop.page.locator(f"text={figure}").first.is_visible(), label
    _assert_no_inert_controls(desktop)
    assert not desktop.offsite, desktop.offsite[:5]


def test_exactly_one_period_is_visible_after_every_click(server, desktop) -> None:
    _ready(desktop, f"{server}/pricing/")
    for label in ("Yearly Plan", "Monthly Plan", "2-Year Plan", "Monthly Plan"):
        desktop.page.click(f".plan-type-link:has-text('{label}')")
        desktop.page.wait_for_timeout(120)
        shown = _visible_periods(desktop)
        assert len(shown) == 1, (label, shown)


def test_active_tab_marker_follows_the_click(server, desktop) -> None:
    _ready(desktop, f"{server}/pricing/")
    desktop.page.click(".plan-type-link:has-text('Yearly Plan')")
    desktop.page.wait_for_timeout(120)
    assert desktop.page.locator("p.annual-link.active").count() >= 1
    assert desktop.page.locator("p.biennial-link.active").count() == 0


def test_plan_cta_navigates_with_the_right_flow(server, desktop) -> None:
    _ready(desktop, f"{server}/pricing/")
    desktop.page.click(".plan-type-link:has-text('Yearly Plan')")
    desktop.page.wait_for_timeout(120)
    cta = desktop.page.locator(
        ".pricing-pg-yearly-tab a[href*='flow=essential-annual']"
    ).first
    assert cta.is_visible()
    cta.click()
    desktop.page.wait_for_load_state("load")
    assert "flow=essential-annual" in desktop.page.url
    assert desktop.page.locator("text=Order Summary").first.is_visible()
    assert not desktop.offsite, desktop.offsite[:5]


# -- checkout ---------------------------------------------------------------


def test_payment_method_rows_expand_the_registration_form(server, desktop) -> None:
    _ready(
        desktop,
        f"{server}/checkout/address-payment-method?flow=essential-annual"
        "&currency=USD&lang=EN",
    )
    assert desktop.page.locator("#ipvanish-sandbox-form").count() == 0
    desktop.page.click("li.c-payment-method-type-select-card:has-text('Credit card')")
    desktop.page.wait_for_selector("#ipvanish-sandbox-form", timeout=15000)
    assert desktop.page.locator("#input-email").is_visible()
    assert desktop.page.locator("#input-billing-country").is_visible()
    assert desktop.page.locator("#input-billing-postal").is_visible()
    assert desktop.page.locator(
        "input[name='scenario_id'][value='sandbox-approved']"
    ).count() == 1
    _assert_no_inert_controls(desktop)
    assert not desktop.offsite, desktop.offsite[:5]


def test_wallet_rows_are_clickable_and_disclose_their_boundary(
    server, desktop
) -> None:
    _ready(
        desktop,
        f"{server}/checkout/address-payment-method?flow=essential-annual",
    )
    desktop.page.click("li.c-payment-method-type-select-card:has-text('PayPal')")
    desktop.page.wait_for_load_state("load")
    assert "method=paypal" in desktop.page.url
    assert desktop.page.locator("text=third-party wallet").first.is_visible()


def test_registration_form_submits_and_reaches_the_confirmation(
    server, desktop
) -> None:
    _ready(
        desktop,
        f"{server}/checkout/address-payment-method?flow=essential-annual&method=card",
    )
    desktop.page.fill("#input-email", "operability@example.invalid")
    desktop.page.select_option("#input-billing-country", "US")
    desktop.page.fill("#input-billing-postal", "78701")
    desktop.page.check("input[name='scenario_id'][value='sandbox-approved']")
    desktop.page.click("button[data-clone-action='subscribe']")
    desktop.page.wait_for_url("**/checkout/confirmation", timeout=15000)
    assert desktop.page.locator("text=Your IPVanish subscription is active").is_visible()
    assert desktop.page.locator("text=Clone-local view.").first.is_visible()
    assert not desktop.offsite, desktop.offsite[:5]


def test_declined_scenario_keeps_the_form_operable(server, desktop) -> None:
    _ready(
        desktop,
        f"{server}/checkout/address-payment-method?flow=advanced-monthly&method=card",
    )
    desktop.page.fill("#input-email", "declined@example.invalid")
    desktop.page.select_option("#input-billing-country", "CA")
    desktop.page.fill("#input-billing-postal", "M5V 2T6")
    desktop.page.check("input[name='scenario_id'][value='sandbox-declined']")
    desktop.page.click("button[data-clone-action='subscribe']")
    desktop.page.wait_for_selector("text=Simulated decline", timeout=15000)
    assert desktop.page.locator("#ipvanish-sandbox-form").is_visible()
    _assert_no_inert_controls(desktop)


# -- auth -------------------------------------------------------------------


def test_signin_submits_by_real_click(server, desktop) -> None:
    _ready(desktop, f"{server}/login")
    desktop.page.fill("input[name='email']", PRIMARY_EMAIL)
    desktop.page.fill("input[name='password']", PRIMARY_PASSWORD)
    desktop.page.click("form button:has-text('Sign in')")
    desktop.page.wait_for_url("**/account/", timeout=15000)
    assert desktop.page.locator("text=My Account").first.is_visible()
    assert not desktop.offsite, desktop.offsite[:5]


def test_forgot_password_link_reaches_recovery_and_recovery_submits(
    server, desktop
) -> None:
    _ready(desktop, f"{server}/login")
    desktop.page.click("a:has-text('Forgot password?')")
    desktop.page.wait_for_url("**/login/reset-password", timeout=15000)
    assert desktop.page.locator(
        "text=Enter you account email, you will receive a reset password code"
    ).is_visible()
    desktop.page.fill("input[name='username']", PRIMARY_EMAIL)
    desktop.page.click("form button:has-text('Send code')")
    desktop.page.wait_for_selector("text=local outbox", timeout=15000)
    assert desktop.page.locator("a:has-text('Back to sign in')").is_visible()


def test_sign_up_now_reaches_pricing(server, desktop) -> None:
    _ready(desktop, f"{server}/login")
    desktop.page.click("a:has-text('Sign up now!')")
    desktop.page.wait_for_url("**/pricing/", timeout=15000)
    assert desktop.page.locator("text=IPVanish plans & pricing").first.is_visible()


# -- navigation -------------------------------------------------------------


def test_nav_dropdown_opens_on_a_real_click(server, desktop) -> None:
    _ready(desktop, f"{server}/")
    panel = desktop.page.locator("#menu-item-139281 ul.astra-megamenu").first
    desktop.page.click("#menu-item-139281 .dropdown-menu-toggle")
    desktop.page.wait_for_timeout(200)
    assert "ast-hidden" not in (panel.get_attribute("class") or "")
    assert desktop.page.locator(
        "#menu-item-139281 a:has-text('What is a VPN?')"
    ).first.is_visible()


def test_pricing_is_reachable_from_the_primary_nav(server, desktop) -> None:
    _ready(desktop, f"{server}/")
    desktop.page.click("#menu-item-179047 a.menu-link")
    desktop.page.wait_for_url("**/pricing/", timeout=15000)
    assert desktop.page.locator("text=IPVanish plans & pricing").first.is_visible()


def test_mobile_menu_toggle_is_operable(server, mobile) -> None:
    _ready(mobile, f"{server}/")
    toggle = mobile.page.locator("button.menu-toggle").first
    assert toggle.is_visible()
    toggle.click()
    mobile.page.wait_for_timeout(200)
    assert toggle.get_attribute("aria-expanded") == "true"


def test_mobile_pricing_tabs_switch_period(server, mobile) -> None:
    _ready(mobile, f"{server}/pricing/")
    mobile.page.click(".monthly-mobile-link")
    mobile.page.wait_for_timeout(200)
    shown = mobile.page.evaluate(
        """
        () => {
          const map = {
            biennial: '.pricing-pg-mobile-biennial-tab',
            annual: '.pricing-pg-mobile-yearly-tab',
            monthly: '.pricing-pg-mobile-monthly-tab'
          };
          const out = [];
          for (const [key, selector] of Object.entries(map)) {
            for (const node of document.querySelectorAll(selector)) {
              const box = node.getBoundingClientRect();
              if (box.height > 0) { out.push(key); break; }
            }
          }
          return out;
        }
        """
    )
    assert shown == ["monthly"], shown


# -- support ----------------------------------------------------------------


def test_support_search_reaches_the_no_results_state(server, desktop) -> None:
    _ready(desktop, f"{server}/support")
    desktop.page.fill("input[name='query']", "zzzz-no-match-websitebench")
    desktop.page.press("input[name='query']", "Enter")
    desktop.page.wait_for_url("**/support/search**", timeout=15000)
    assert desktop.page.locator("text=No results for").first.is_visible()
    desktop.page.click("a:has-text('See IPVanish plans')")
    desktop.page.wait_for_url("**/pricing/", timeout=15000)


# -- subscriber dashboard (clone-local inference, but operable) -------------


def _sign_in(server, handle: Page) -> None:
    _ready(handle, f"{server}/login")
    handle.page.fill("input[name='email']", PRIMARY_EMAIL)
    handle.page.fill("input[name='password']", PRIMARY_PASSWORD)
    handle.page.click("form button:has-text('Sign in')")
    handle.page.wait_for_url("**/account/", timeout=15000)


def test_dashboard_actions_are_operable(server, desktop) -> None:
    _sign_in(server, desktop)
    for action, expected in (
        ("pause", "paused"),
        ("resume", "active"),
        ("cancel", "canceled"),
        ("reactivate", "active"),
    ):
        button = desktop.page.locator(f"button[data-clone-action='{action}']").first
        assert button.is_visible(), action
        button.click()
        desktop.page.wait_for_url("**/account/", timeout=15000)
        desktop.page.wait_for_selector(
            f"[data-subscription-status='{expected}']", timeout=15000
        )
    _assert_no_inert_controls(desktop)
    assert not desktop.offsite, desktop.offsite[:5]


def test_plan_change_and_billing_contact_submit(server, desktop) -> None:
    _sign_in(server, desktop)
    desktop.page.click(".ipvanish-clone-subnav a:has-text('Change plan')")
    desktop.page.wait_for_url("**/account/plan", timeout=15000)
    desktop.page.select_option("#plan-choice", "advanced-annual")
    desktop.page.check("input[name='scenario_id'][value='sandbox-approved']")
    desktop.page.click("button[data-clone-action='change-plan']")
    desktop.page.wait_for_url("**/account/", timeout=15000)
    assert desktop.page.locator("text=IPVanish Advanced").first.is_visible()

    desktop.page.click(".ipvanish-clone-subnav a:has-text('Billing contact')")
    desktop.page.wait_for_url("**/account/billing-contact", timeout=15000)
    desktop.page.fill("#contact-postal", "10001")
    desktop.page.click("button[data-clone-action='save-contact']")
    desktop.page.wait_for_url("**/account/billing-contact", timeout=15000)
    assert desktop.page.input_value("#contact-postal") == "10001"


def test_billing_history_lists_the_seeded_charges(server, desktop) -> None:
    _sign_in(server, desktop)
    desktop.page.click(".ipvanish-clone-subnav a:has-text('Billing history')")
    desktop.page.wait_for_url("**/account/billing", timeout=15000)
    rows = desktop.page.locator(".ipvanish-clone-table tbody tr")
    assert rows.count() >= 2
    assert desktop.page.locator("text=Clone-local view.").first.is_visible()


# -- the negative control ---------------------------------------------------


def test_detects_a_pointer_events_none_control(server, desktop) -> None:
    """Negative control: prove the probe would fail if a control went inert.

    Without this, a green operability suite could mean "nothing is broken" or
    "the probe never looks at anything".
    """

    _ready(desktop, f"{server}/pricing/")
    _assert_no_inert_controls(desktop)
    desktop.page.evaluate(
        """
        () => {
          const tab = document.querySelector('.plan-type-link');
          tab.style.pointerEvents = 'none';
        }
        """
    )
    findings = desktop.page.evaluate(INERT_PROBE, JOURNEY_CONTROLS)
    assert any(reason == "pointer-events:none" for _, reason in findings), findings

    desktop.page.reload()
    desktop.page.wait_for_selector("html[data-ipvanish-clone='ready']", timeout=15000)
    _assert_no_inert_controls(desktop)
    desktop.page.evaluate(
        """
        () => {
          const form = document.createElement('form');
          form.setAttribute('action', '/login');
          const button = document.createElement('button');
          button.textContent = 'Sign in';
          button.disabled = true;
          button.style.width = '120px';
          button.style.height = '40px';
          form.appendChild(button);
          document.body.appendChild(form);
        }
        """
    )
    findings = desktop.page.evaluate(INERT_PROBE, JOURNEY_CONTROLS)
    assert any(reason == "disabled" for _, reason in findings), findings


# -- horizontal overflow ----------------------------------------------------

# The source does not overflow horizontally at any frozen viewport: the frozen
# full-page captures are exactly 390, 1024 and 1440 pixels wide. A candidate
# that does is a clone defect, and the live diagnostic reported exactly that for
# home at 390 and 1024 before `clone.css` restored the containment that UAG's
# own `max-width: 100%` could not apply through a blockified flex item.
CONTRACTED_ROUTES = ("/", "/pricing/")

# Routes that still overflow, each an un-initialized widget track whose source
# script this clone strips by design (a reviews carousel, a features tab strip,
# a setup-guide gallery). Recorded rather than clipped out of sight; the set is
# asserted so it can shrink but never silently grow.
KNOWN_OVERFLOW = {
    ("tablet", "/vpn-features/threat-protection/"),
    ("tablet", "/secure-browser/"),
    ("tablet", "/cloud-storage/"),
    ("tablet", "/blog/"),
    ("mobile", "/vpn-setup/windows/"),
    ("mobile", "/blog/"),
    # Six entries left this set on 2026-08-20 (desktop+tablet+mobile /reviews/,
    # tablet /what-is-a-vpn/, mobile /vpn-features/, mobile /cloud-storage/).
    # They were originally attributed to stripped JavaScript widgets, and that
    # was wrong: their real cause was images the closure pass never mirrored.
    # The review badges and feature icons had no payload, so the flex rows
    # measured against intrinsic-less <img> boxes. Once the payloads were
    # captured the rows lay out at their true width and fit. The remaining six
    # entries below survived that repair, so for them the widget explanation
    # still stands.
    # These two arrived *with* a fidelity fix rather than despite one. The
    # checkout stylesheet's @font-face rules are root-relative, so before the
    # asset-promotion pass localized them the real Open Sans never loaded and the
    # Angular header's language/currency/support menu measured narrower than the
    # source's. With the correct font the menu row lays out at its true width,
    # which does not fit 390px. The source's checkout was captured at desktop
    # only -- there is no mobile checkout checkpoint -- so there is no evidence
    # of what that header does at 390px, and clipping it would be inventing
    # layout. Desktop and tablet checkout both fit.
    ("mobile", "/checkout/address-payment-method?flow=essential-annual"),
    ("mobile", "/checkout/address-payment-method?flow=essential-annual&method=card"),
}
SWEPT_ROUTES = (
    "/",
    "/pricing/",
    "/pricing/?period=yearly",
    "/pricing/?period=monthly",
    "/why-vpn/",
    "/what-is-a-vpn/",
    "/servers/",
    "/vpn-features/",
    "/vpn-features/threat-protection/",
    "/money-back-guarantee/",
    "/coupons/",
    "/vpn-locations/",
    "/reviews/",
    "/trust/",
    "/no-log-vpn-policy/",
    "/secure-browser/",
    "/cloud-storage/",
    "/vpn-setup/windows/",
    "/vpn-for-streaming/",
    "/resources/",
    "/setup-guides/",
    "/what-is-my-ip-address/",
    "/blog/",
    "/tos/",
    "/privacy-policy/",
    "/partners/",
    "/press/",
    "/support",
    "/support/search?query=zzzz-no-match-websitebench",
    "/login",
    "/login/reset-password",
    "/checkout/address-payment-method?flow=essential-annual",
    "/checkout/address-payment-method?flow=essential-annual&method=card",
    "/zzzz-no-match-websitebench",
)

OVERFLOW_PROBE = (
    "() => [document.documentElement.scrollWidth,"
    " document.documentElement.clientWidth]"
)


@pytest.mark.parametrize(("label", "viewport"), FROZEN_VIEWPORTS)
def test_no_horizontal_overflow_on_contracted_routes(
    server, browser, label, viewport
) -> None:
    """Home and pricing must fit their viewport at every frozen size."""

    context = browser.new_context(
        viewport=viewport, locale="en-US", timezone_id="Etc/UTC"
    )
    try:
        page = context.new_page()
        for route in CONTRACTED_ROUTES:
            page.goto(f"{server}{route}", wait_until="load")
            page.wait_for_selector(
                "html[data-ipvanish-clone='ready']", timeout=15000
            )
            page.wait_for_timeout(400)
            scroll_width, client_width = page.evaluate(OVERFLOW_PROBE)
            assert scroll_width <= client_width + 1, (
                label,
                route,
                scroll_width,
                client_width,
            )
    finally:
        context.close()


def test_the_known_overflow_set_does_not_grow(server, browser) -> None:
    """Every other route, at every frozen viewport, against the recorded set."""

    observed: set[tuple[str, str]] = set()
    for label, viewport in FROZEN_VIEWPORTS:
        context = browser.new_context(
            viewport=viewport, locale="en-US", timezone_id="Etc/UTC"
        )
        try:
            page = context.new_page()
            for route in SWEPT_ROUTES:
                page.goto(f"{server}{route}", wait_until="load")
                page.wait_for_timeout(400)
                scroll_width, client_width = page.evaluate(OVERFLOW_PROBE)
                if scroll_width > client_width + 1:
                    observed.add((label, route))
        finally:
            context.close()
    new = observed - KNOWN_OVERFLOW
    assert not new, f"new horizontal overflow appeared: {sorted(new)}"
    fixed = KNOWN_OVERFLOW - observed
    assert not fixed, (
        "these no longer overflow; remove them from KNOWN_OVERFLOW: "
        f"{sorted(fixed)}"
    )


def test_detects_injected_horizontal_overflow(server, mobile) -> None:
    """Negative control: prove the overflow assertion can fail.

    Without this, a green overflow suite could mean "the page fits" or "the
    probe never measured anything".
    """

    _ready(mobile, f"{server}/")
    scroll_width, client_width = mobile.page.evaluate(OVERFLOW_PROBE)
    assert scroll_width <= client_width + 1, (scroll_width, client_width)
    mobile.page.evaluate(
        """
        () => {
          const wide = document.createElement('div');
          wide.id = 'ipvanish-overflow-probe';
          wide.style.width = '900px';
          wide.style.height = '20px';
          document.body.appendChild(wide);
        }
        """
    )
    mobile.page.wait_for_timeout(150)
    scroll_width, client_width = mobile.page.evaluate(OVERFLOW_PROBE)
    assert scroll_width > client_width + 1, (
        "the probe did not notice a 900px element at a 390px viewport"
    )
    mobile.page.evaluate(
        "() => document.getElementById('ipvanish-overflow-probe').remove()"
    )
    mobile.page.wait_for_timeout(150)
    scroll_width, client_width = mobile.page.evaluate(OVERFLOW_PROBE)
    assert scroll_width <= client_width + 1


def test_no_page_in_a_frozen_journey_makes_an_offsite_request(
    server, desktop
) -> None:
    for path in (
        "/",
        "/pricing/",
        "/checkout/address-payment-method?flow=essential-annual&method=card",
        "/login",
        "/login/reset-password",
        "/support",
        "/why-vpn/",
        "/zzzz-no-match-websitebench",
    ):
        _ready(desktop, f"{server}{path}")
        desktop.page.wait_for_timeout(250)
    assert not desktop.offsite, desktop.offsite[:10]
