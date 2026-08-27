#!/usr/bin/env python3
"""Record controls proven by a live TestClient walk of the DeleteMe clone."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile

TOOLS = pathlib.Path(__file__).resolve().parent
CLONE = TOOLS.parent / "clone"

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="deleteme-ledger-"))
os.environ.setdefault("SEED", "1")
sys.path.insert(0, str(CLONE))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402

TAG = re.compile(r"<[^>]+>")

# url, label, selector, raw markup probe, visible text, form action, session
ENTRIES = (
    ("/?index=1", "Join Now", "a[href='/privacy-protection-plans/']", 'href="/privacy-protection-plans/"', "Join Now", None, False),
    ("/privacy-protection-plans/", "1 Year", "[data-term-tab='1y']", 'data-term-tab="1y"', "1 Year", None, False),
    ("/privacy-protection-plans/", "2 Years", "[data-term-tab='2y']", 'data-term-tab="2y"', "2 Years", None, False),
    ("/privacy-protection-plans/", "Start Protection — 1 Person", "[data-term-group='2y'] a[data-start-protection='2-1']", 'data-start-protection="2-1"', "Start Protection", None, False),
    ("/pricing/", "Single size filter", "[uk-filter-control=\"filter: [data-plan='single']; group: plan\"]", "filter: [data-plan='single']; group: plan", "Single", None, False),
    ("/checkout?plan=standard&term=1&qty=1", "First name", "#dm-first-name", 'id="dm-first-name"', "First Name", "/checkout", False),
    ("/checkout?plan=standard&term=1&qty=1", "Sandbox outcome", "input[name='scenario']", 'name="scenario"', "Simulated approval", "/checkout", False),
    ("/checkout?plan=standard&term=1&qty=1", "Purchase and start deleting", "[data-checkout-submit]", "data-checkout-submit", "Purchase & Start Deleting", "/checkout", False),
    ("/login", "Email", "form[action='/login'] input[name='email']", 'name="email"', "Email", "/login", False),
    ("/login", "Password", "form[action='/login'] input[name='password']", 'name="password"', "Password", "/login", False),
    ("/login", "Continue with Google", "button:has-text('Continue with Google')", "Continue with Google", "Continue with Google", None, False),
    ("/login", "Forgot Password", "a[href='/password/forgot']", 'href="/password/forgot"', "Forgot Password?", None, False),
    ("/password/forgot", "Reset address", "form[action='/password/forgot'] input[name='email']", 'name="email"', "Email Address", "/password/forgot", False),
    ("/password/forgot", "Back to sign in", "a[href='/login']", 'href="/login"', "Back to sign in", None, False),
    ("/account", "Pause subscription", "button[data-subscription-action='pause']", 'data-subscription-action="pause"', "Pause", "/account/subscription/sub-primary-0001/pause", True),
    ("/account", "Cancel subscription", "button[data-subscription-action='cancel']", 'data-subscription-action="cancel"', "Cancel", "/account/subscription/sub-primary-0001/cancel", True),
    ("/account/profile", "Save removal profile", "[data-removal-profile-submit]", "data-removal-profile-submit", "Save removal profile", "/account/profile", True),
    ("/account/plan", "Change plan", "[data-plan-change-submit]", "data-plan-change-submit", "Change plan", "/account/plan", True),
)

CREDENTIALS = {
    "email": "avery.quill@example.invalid",
    "password": "OfflineClone!2026",
}


def visible_text(markup: str) -> str:
    return re.sub(r"\s+", " ", TAG.sub(" ", markup)).replace("&amp;", "&").strip()


def main() -> int:
    anonymous = TestClient(app_module.app, base_url="https://clone.local")
    signed_in = TestClient(app_module.app, base_url="https://clone.local")
    response = signed_in.post("/login", data=CREDENTIALS, follow_redirects=False)
    if response.status_code != 303:
        raise SystemExit("could not establish the seeded subscriber session")

    cache: dict[tuple[str, bool], str] = {}
    rows = []
    for url, control, selector, markup_probe, text_probe, action, session in ENTRIES:
        key = (url, session)
        if key not in cache:
            answer = (signed_in if session else anonymous).get(url)
            if answer.status_code != 200:
                raise SystemExit(f"{url}: expected 200, got {answer.status_code}")
            cache[key] = answer.text
        document = cache[key]
        if markup_probe not in document:
            raise SystemExit(f"{url}: raw-markup proof missing: {markup_probe!r}")
        if text_probe not in visible_text(document):
            raise SystemExit(f"{url}: visible-text proof missing: {text_probe!r}")
        index = document.index(markup_probe)
        rows.append({
            "url": url,
            "control": control,
            "selector": selector,
            "requires_session": session,
            "visible_text_proof": text_probe,
            "raw_markup_proof": document[max(0, index - 120):index + 200],
            "form_action": action,
        })

    payload = {
        "schema_version": "deleteme.interaction-ledger.v1",
        "recorded_from": "live clone (TestClient walk of clone/app.py)",
        "capture_id": "2026-08-20.deleteme-r1",
        "note": "Account controls are clearly labelled clone-local inference because authenticated source states were unavailable. Browser-backed selectors are also exercised by clone/tests/test_operability.py.",
        "entries": rows,
    }
    (TOOLS / "interaction-ledger.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "entries": len(rows),
        "routes": len({row["url"] for row in rows}),
        "mutations": len([row for row in rows if row["form_action"]]),
    }, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
