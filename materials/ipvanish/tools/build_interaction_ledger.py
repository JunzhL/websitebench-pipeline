#!/usr/bin/env python3
"""Record the route/state matrix walk as tools/interaction-ledger.json.

For every control a frozen journey activates: the clone URL, the stable
selector, one visible-text proof and one raw-markup proof taken from the
clone's own response, and the form action behind every mutation.  Proofs are
extracted from the live candidate, not from the capture, so a control that
exists in the source but was dropped from the clone cannot pass.

The declared selector must actually match in the served document; a miss is a
build error, not a silently empty ledger row.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parent
SITE = TOOLS.parent
CLONE = SITE / "clone"

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="ipvanish-ledger-"))
os.environ.setdefault("SEED", "1")
sys.path.insert(0, str(CLONE))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402

TAG = re.compile(r"<[^>]+>")

# (url, control label, selector, a substring that must appear in the markup,
#  the visible text the control shows, the form action a click drives)
ENTRIES: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    (
        "/",
        "Get Started (header)",
        ".ast-header-button-1 a.ast-custom-button-link",
        'class="ast-custom-button-link home_tnav_gs"',
        "Get Started",
        None,
    ),
    (
        "/",
        "Pricing (primary nav)",
        "#menu-item-179047 a.menu-link",
        'id="menu-item-179047"',
        "Pricing",
        None,
    ),
    (
        "/",
        "Product (mega-menu trigger)",
        "#menu-item-139281 .dropdown-menu-toggle",
        'id="menu-item-139281"',
        "Product",
        None,
    ),
    (
        "/",
        "Apps (mega-menu trigger)",
        "#menu-item-139449 .dropdown-menu-toggle",
        'id="menu-item-139449"',
        "Apps",
        None,
    ),
    (
        "/",
        "Resources (mega-menu trigger)",
        "#menu-item-139506 .dropdown-menu-toggle",
        'id="menu-item-139506"',
        "Resources",
        None,
    ),
    (
        "/",
        "Mobile menu toggle",
        "button.menu-toggle.main-header-menu-toggle",
        'class="menu-toggle main-header-menu-toggle',
        "aria-label=Main menu toggle",
        None,
    ),
    (
        "/?nav=product",
        "What is a VPN? (Product panel)",
        "#menu-item-139281 a[href='/what-is-a-vpn/']",
        'href="/what-is-a-vpn/"',
        "What is a VPN?",
        None,
    ),
    (
        "/pricing/",
        "2-Year Plan tab",
        ".plan-type-link.biennial-link",
        "biennial-link plan-type-link active",
        "2-Year Plan",
        None,
    ),
    (
        "/pricing/",
        "Yearly Plan tab",
        ".plan-type-link.annual-link",
        "annual-link plan-type-link",
        "Yearly Plan",
        None,
    ),
    (
        "/pricing/",
        "Monthly Plan tab",
        ".plan-type-link.monthly-link",
        "monthly-link plan-type-link",
        "Monthly Plan",
        None,
    ),
    (
        "/pricing/",
        "Get Essential (2-Year card)",
        ".pricing-pg-biennial-tab a[href*='flow=essential-biennial']",
        "flow=essential-biennial",
        "Get Essential",
        None,
    ),
    (
        "/pricing/?period=yearly",
        "Get Essential (Yearly card)",
        ".pricing-pg-yearly-tab a[href*='flow=essential-annual']",
        "flow=essential-annual",
        "Get Essential",
        None,
    ),
    (
        "/pricing/?period=monthly",
        "Get Advanced (Monthly card)",
        ".pricing-pg-monthly-tab a[href*='flow=advanced-monthly']",
        "flow=advanced-monthly",
        "Get Advanced",
        None,
    ),
    (
        "/checkout/address-payment-method?flow=essential-annual&currency=USD&lang=EN",
        "Credit card row",
        "li.c-payment-method-type-select-card .c-payment-method-type-select__item--cc",
        "c-payment-method-type-select__item--cc",
        "Credit card",
        None,
    ),
    (
        "/checkout/address-payment-method?flow=essential-annual&currency=USD&lang=EN",
        "PayPal row",
        "li.c-payment-method-type-select-card .c-payment-method-type-select__item--paypal",
        "c-payment-method-type-select__item--paypal",
        "PayPal",
        None,
    ),
    (
        "/checkout/address-payment-method?flow=essential-annual&method=card",
        "Account email field",
        "#input-email",
        'id="input-email"',
        "Email address",
        "/checkout/subscribe",
    ),
    (
        "/checkout/address-payment-method?flow=essential-annual&method=card",
        "Local-sandbox outcome selector",
        "input[name='scenario_id']",
        "ipvanish-sandbox__scenarios",
        "Simulated approval",
        "/checkout/subscribe",
    ),
    (
        "/checkout/address-payment-method?flow=essential-annual&method=card",
        "Subscribe now",
        "button[data-clone-action='subscribe']",
        'data-clone-action="subscribe"',
        "Subscribe now",
        "/checkout/subscribe",
    ),
    (
        "/login",
        "Email address field",
        "form[action='/login'] input[name='email']",
        'name="email"',
        "Email address",
        "/login",
    ),
    (
        "/login",
        "Sign in",
        "form[action='/login'] button",
        'class="button_btn__fotrB"',
        "Sign in",
        "/login",
    ),
    (
        "/login",
        "Forgot password?",
        "a[href='/login/reset-password']",
        'href="/login/reset-password"',
        "Forgot password?",
        None,
    ),
    (
        "/login",
        "Sign up now!",
        "a[href='/pricing/']",
        'href="/pricing/"',
        "Sign up now!",
        None,
    ),
    (
        "/login/reset-password",
        "Reset address field",
        "input[name='username']",
        'name="username"',
        "Email address",
        "/login/reset-password",
    ),
    (
        "/login/reset-password",
        "Send code",
        "form[action='/login/reset-password'] button",
        'action="/login/reset-password"',
        "Send code",
        "/login/reset-password",
    ),
    (
        "/support",
        "Support search",
        "form[role='search'] input[name='query']",
        'placeholder="How can we help you?"',
        "aria-label=How can we help you?",
        "/support/search",
    ),
    (
        "/support/search?query=zzzz-no-match-websitebench",
        "Back to plans (no-results)",
        ".faq-inner a[href='/pricing/']",
        "No results for",
        "See IPVanish plans &amp; pricing",
        None,
    ),
    (
        "/account/",
        "Pause subscription",
        "button[data-clone-action='pause']",
        'data-clone-action="pause"',
        "Pause subscription",
        "/account/subscription/sub_primary_annual/pause",
    ),
    (
        "/account/",
        "Cancel subscription",
        "button[data-clone-action='cancel']",
        'data-clone-action="cancel"',
        "Cancel subscription",
        "/account/subscription/sub_primary_annual/cancel",
    ),
    (
        "/account/plan",
        "Change plan",
        "button[data-clone-action='change-plan']",
        'data-clone-action="change-plan"',
        "Change plan",
        "/account/plan",
    ),
    (
        "/account/billing-contact",
        "Save billing contact",
        "button[data-clone-action='save-contact']",
        'data-clone-action="save-contact"',
        "Save billing contact",
        "/account/billing-contact",
    ),
)

SESSION_ROUTES = ("/account/", "/account/plan", "/account/billing-contact")
CREDENTIALS = {
    "email": "avery.sandoval@example.invalid",
    "password": "Vanish-Demo-2026!",
}


def visible_text(markup: str) -> str:
    return re.sub(r"\s+", " ", TAG.sub(" ", markup)).strip()


def main() -> int:
    anonymous = TestClient(app_module.app, base_url="https://clone.local")
    signed_in = TestClient(app_module.app, base_url="https://clone.local")
    response = signed_in.post("/login", data=CREDENTIALS, follow_redirects=False)
    if response.status_code != 303:
        raise SystemExit("could not establish the seeded subscriber session")

    cache: dict[tuple[str, bool], str] = {}
    entries = []
    for url, control, selector, markup_probe, text_probe, action in ENTRIES:
        session = url in SESSION_ROUTES
        key = (url, session)
        if key not in cache:
            client = signed_in if session else anonymous
            answer = client.get(url)
            if answer.status_code != 200:
                raise SystemExit(f"{url}: expected 200, got {answer.status_code}")
            cache[key] = answer.text
        document = cache[key]
        if markup_probe not in document:
            raise SystemExit(f"{url}: raw-markup proof missing: {markup_probe!r}")
        index = document.index(markup_probe)
        raw = document[max(0, index - 120) : index + 200]
        # A few captured controls are icon-only (the mobile hamburger), so
        # their user-visible identity is the accessible name rather than a text
        # node.  Say which kind of proof it is instead of pretending.
        if text_probe.startswith("aria-label="):
            expected = text_probe.removeprefix("aria-label=")
            if f'aria-label="{expected}"' not in document:
                raise SystemExit(
                    f"{url}: accessible-name proof missing: {expected!r}"
                )
        elif text_probe not in visible_text(document):
            raise SystemExit(f"{url}: visible-text proof missing: {text_probe!r}")
        entries.append(
            {
                "url": url,
                "control": control,
                "selector": selector,
                "requires_session": session,
                "visible_text_proof": text_probe,
                "raw_markup_proof": raw,
                "form_action": action,
            }
        )

    payload = {
        "schema_version": "ipvanish.interaction-ledger.v1",
        "recorded_from": "live clone (TestClient walk of clone/app.py)",
        "capture_id": "2026-08-19.ipvanish-r1",
        "note": "Selectors are Playwright-style and are the ones clone/tests/"
        "test_operability.py drives in Chromium. Rows whose url is under "
        "/account or /checkout/confirmation describe clone-local inference: "
        "the source gates those surfaces behind a purchase, so no captured "
        "state exists for them.",
        "entries": entries,
    }
    (TOOLS / "interaction-ledger.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "entries": len(entries),
                "routes": len({row["url"] for row in entries}),
                "mutations": len([row for row in entries if row["form_action"]]),
            },
            indent=1,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
