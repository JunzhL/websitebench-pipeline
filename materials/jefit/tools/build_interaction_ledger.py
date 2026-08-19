#!/usr/bin/env python3
"""Record the interaction ledger from the live clone.

Each entry names the clone URL, the selector of the activated control, one
visible-text proof and one raw-markup proof taken from the actually served
document, and the form action for every mutation. Written to
tools/interaction-ledger.json.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile

SITE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE / "clone"))
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="jefit-ledger-"))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402

OUT = SITE / "tools" / "interaction-ledger.json"


def snippet(document: str, needle: str, width: int = 220) -> str:
    at = document.find(needle)
    if at < 0:
        raise SystemExit(f"proof needle missing: {needle!r}")
    start = max(0, at - 40)
    return document[start : at + width]


def main() -> int:
    anon = TestClient(app_module.app, base_url="https://clone.local")
    member = TestClient(app_module.app, base_url="https://clone.local")
    login = member.post(
        "/login",
        data={"username": "jefitdemo", "password": "Demo-Pass-2026!"},
        follow_redirects=False,
    )
    assert login.status_code == 302

    entries: list[dict] = []

    def record(url: str, control: str, selector: str, *, client=anon,
               mutation: str | None = None, needle: str | None = None,
               note: str = "") -> None:
        document = client.get(url).text
        probe = needle or control
        entries.append(
            {
                "url": url,
                "control": control,
                "selector": selector,
                "visible_text_proof": re.sub(
                    r"<[^>]+>", " ", snippet(document, probe)
                ).strip()[:200],
                "raw_markup_proof": snippet(document, probe)[:260],
                "form_action": mutation,
                "note": note,
            }
        )

    # --- anonymous surface ---
    record("/", "Accept", 'div[aria-label="Cookie consent"] button',
           needle="Cookie consent",
           note="consent banner; Accept persists clone-local consent")
    record("/", "Products", "header button",
           note="nav dropdown injected from the captured open state")
    record("/exercises", "Abs", "button", needle=">Abs<",
           note="client-side muscle filter over the embedded catalog")
    record("/exercises", "CLEAR FILTERS", "button", needle="CLEAR FILTERS")
    record("/exercises", "Next", 'a[aria-label="Next page"]',
           needle='aria-label="Next page"')
    record("/login", "Log In", 'form[action="/login"] button',
           mutation="/login", needle='action="/login"')
    record("/login/forgot-password", "Send reset link",
           'form[action="/login/forgot-password"] button',
           mutation="/login/forgot-password",
           needle='action="/login/forgot-password"')
    record("/signup", "Continue", "button", needle="Continue",
           note="questionnaire stepper (17 captured panels, client-side)")
    record("/signup/register", "Continue",
           'form[action="/signup/register"] button',
           mutation="/signup/register", needle='action="/signup/register"')

    draft = anon.get("/build-routine", follow_redirects=False)
    draft_url = draft.headers["location"]
    record(draft_url, "Save", "button", needle="Save",
           mutation="/api/build-routine/save",
           note="anonymous draft save -> public /routines/<id>/new-routine")

    # --- member surface ---
    record("/my-jefit", "Create Post +", "button", client=member,
           needle="Create Post", mutation="/api/posts")
    record("/my-jefit", "Upgrade to Elite", "button", client=member,
           needle="Upgrade to Elite",
           note="opens the captured plan modal (Buy plan links to checkout)")
    record("/my-jefit/workouts", "Create Plan", "button", client=member,
           needle="Create Plan", mutation="/api/plans")
    record("/my-jefit/workouts", "plan card menu",
           "button[id^='plan-menu-']", client=member,
           needle='id="plan-menu-',
           note="Edit Plan / Set as current plan / Printable / Delete")
    plans = member.post("/api/plans").json()
    editor_url = f"/my-jefit/workouts/edit?id={plans['id']}"
    record(editor_url, "routine name input", "input[value]", client=member,
           needle='value="New Routine"', mutation="/api/plans/<id>/name",
           note="autosaves; empty name silently keeps the prior name")
    record(editor_url, "Add <exercise>", "button[data-exercise-id]",
           client=member, needle="data-exercise-id",
           mutation="/api/days/<day_id>/exercises",
           note="defaults 3 sets 10 lbs x 8, 60s rest")
    record(editor_url, "Add Day", "button", client=member, needle="Add Day",
           mutation="/api/plans/<id>/days")
    record("/my-jefit/progress/history", "+ Add session", "button",
           client=member, needle="+ Add session", mutation="/api/sessions",
           note="opens the captured Workout Log modal")
    record("/my-jefit/progress/history", "Add <exercise> (log modal)",
           "[data-clone-modal='workout-log'] button[data-exercise-id]",
           client=member, needle='data-clone-modal="workout-log"',
           mutation="/api/sessions/<id>/sets",
           note="logs the default set 25 lbs x 8")
    record("/my-jefit/progress/body-stats", "Edit stat", "a[href^='/my-jefit/progress/body-stats/']",
           client=member, needle="Edit stat",
           mutation="/my-jefit/progress/body-stats/<slug>")
    record("/my-jefit/settings", "Profile (tab)", "nav button",
           client=member, needle="data-settings-panel",
           note="client-side tabs; URL stays /my-jefit/settings")
    record("/my-jefit/settings", "Resend Verification Link", "button",
           client=member, needle="Resend Verification Link",
           mutation="/api/settings/resend-verification")
    record("/my-jefit/settings", "Delete Data", "button", client=member,
           needle="Delete Data", mutation="/api/settings/delete-data")
    record("/my-jefit/settings", "Delete Account", "button", client=member,
           needle="Delete Account", mutation="/api/settings/delete-account")
    record("/my-jefit/settings", "Yearly upgrade card",
           "a[href*='/elite/checkout']", client=member,
           needle="/elite/checkout")
    record("/my-jefit/exercises", "Create custom exercise", "button",
           client=member, needle="Create custom exercise",
           mutation="/api/custom-exercises", note="free-tier limit (n/3)")
    record("/elite/checkout?isMyJefit=true&sub=yearly", "Subscribe",
           'form[action="/elite/checkout"] button[type="submit"]',
           client=member, mutation="/elite/checkout",
           needle='action="/elite/checkout"',
           note="consumes an opaque sandbox scenario id; card fields refused")
    record("/elite/checkout?isMyJefit=true&sub=yearly", "Simulated approval",
           'input[name="scenario_id"]', client=member,
           needle='name="scenario_id"')
    record("/my-jefit", "Sign out", "[data-clone-overlay='account-menu']",
           client=member, needle='data-clone-overlay="account-menu"',
           mutation="/logout")

    payload = {
        "schema_version": "jefit.interaction-ledger.v1",
        "recorded_from": "live clone (TestClient walk)",
        "entries": entries,
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"{len(entries)} ledger entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
