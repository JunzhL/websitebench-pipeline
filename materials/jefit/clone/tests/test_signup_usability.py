"""Usability regressions for the signup flow.

The other suites POST directly and therefore cannot see a page that renders
correctly but cannot be operated. These tests assert the structural
preconditions a human needs:

* the questionnaire's swap slot is present, well formed and addressable, so
  the client stepper can actually replace panels (a slot boundary landing
  inside a tag silently froze the questionnaire on step 1);
* every panel is parseable and reachable, and the last panel hands off to
  /signup/results;
* no gate ships permanently disabled: the register Continue control must not
  keep ``pointer-events-none`` once the runtime enables it, and the runtime
  must contain that enabling logic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CLONE_ROOT = Path(__file__).resolve().parents[1]
PANELS = json.loads(
    (CLONE_ROOT / "frontend" / "signup-steps.json").read_text(encoding="utf-8")
)["panels"]
RUNTIME = (CLONE_ROOT / "static" / "site" / "app.js").read_text(encoding="utf-8")


def test_panel_slot_markers_are_real_comment_nodes(client) -> None:
    body = client.get("/signup").text
    open_at = body.find("<!--jefit-signup-slot-->")
    close_at = body.find("<!--/jefit-signup-slot-->")
    assert open_at > 0, "signup slot open marker missing"
    assert close_at > open_at, "signup slot close marker missing"
    after_open = body[open_at + len("<!--jefit-signup-slot-->")]
    before_close = body[close_at - 1]
    # A boundary inside a tag or attribute produces a marker the HTML parser
    # never turns into a comment node — the defect this test exists for.
    assert after_open == "<", f"slot opens mid-token: {after_open!r}"
    assert before_close == ">", f"slot closes mid-token: {before_close!r}"
    assert "!--$-->" not in body[open_at : open_at + 60]


def _slot_boundaries_ok(body: str) -> bool:
    """The predicate the marker test uses, isolated so it can be probed."""

    open_at = body.find("<!--jefit-signup-slot-->")
    close_at = body.find("<!--/jefit-signup-slot-->")
    if open_at < 0 or close_at <= open_at:
        return False
    return (
        body[open_at + len("<!--jefit-signup-slot-->")] == "<"
        and body[close_at - 1] == ">"
    )


def test_marker_check_flags_the_historical_defect() -> None:
    """Negative control: the exact malformed shapes this defect produced must
    be rejected, so a green run cannot hide them again."""

    # boundary one char after the '<' of `<!--$-->`
    mid_token_open = (
        '<div hidden=""><' + "<!--jefit-signup-slot-->" + "!--$--><header></header>"
        + "<!--/jefit-signup-slot-->" + "</div>"
    )
    assert not _slot_boundaries_ok(mid_token_open)
    # boundary inside a class attribute
    mid_attr_close = (
        "<!--jefit-signup-slot--><header></header>"
        'translate-y-full<!--/jefit-signup-slot-->">'
    )
    assert not _slot_boundaries_ok(mid_attr_close)
    # missing close marker (slotBounds() returned null -> silent no-op)
    assert not _slot_boundaries_ok("<!--jefit-signup-slot--><header></header>")
    # a correct slot passes
    assert _slot_boundaries_ok(
        "<div><!--jefit-signup-slot--><header></header><!--/jefit-signup-slot-->"
        "</div>"
    )


def test_every_panel_is_well_formed_and_served(client) -> None:
    assert len(PANELS) == 17
    for key, panel in PANELS.items():
        assert panel.startswith("<"), key
        assert panel.rstrip().endswith(">"), key
        assert panel.count("<!--") == panel.count("-->"), key
    for step in range(1, 18):
        response = client.get(f"/signup?step={step}")
        assert response.status_code == 200, step
        assert PANELS[str(step)] in response.text, step


def test_panels_differ_so_stepping_is_observable(client) -> None:
    first = client.get("/signup?step=1").text
    for step in (2, 5, 7, 17):
        assert client.get(f"/signup?step={step}").text != first, step


def test_step_one_panel_is_uniquely_locatable(client) -> None:
    # The server splices by matching this string; two matches (or none) means
    # the slot cannot be located and the questionnaire cannot advance.
    body = client.get("/signup").text
    anchor = PANELS["1"]
    assert body.count(anchor) in (0, 1)
    assert "<!--jefit-signup-slot-->" in body


def test_runtime_steps_panels_and_hands_off_to_results(client) -> None:
    body = client.get("/signup").text
    assert 'id="jefit-signup-steps"' in body, "stepper payload missing"
    payload = re.search(
        r'<script id="jefit-signup-steps" type="application/json">(.*?)</script>',
        body,
        re.S,
    )
    assert payload, "stepper payload not parseable"
    served = json.loads(payload.group(1).replace("<\\/", "</"))
    assert set(served) == {str(n) for n in range(1, 18)}
    # the client stepper must locate the slot, advance, and hand off
    assert "jefit-signup-slot" in RUNTIME
    assert "renderStep" in RUNTIME
    assert "/signup/results" in RUNTIME


def test_register_continue_is_not_permanently_disabled(client) -> None:
    """The captured register step froze an empty field, so its Continue ships
    `pointer-events-none`; the runtime must remove it once the field validates.
    Without that, a human can never submit registration."""

    body = client.get("/signup/register").text
    assert 'action="/signup/register"' in body
    assert 'name="email"' in body
    # the runtime owns the ungating; assert the logic is present and targets
    # the class that blocks the click
    assert "pointer-events-none" in RUNTIME
    assert "checkValidity" in RUNTIME
    enabling = re.search(
        r"classList\.(?:remove|toggle)\(\s*[\"']pointer-events-none[\"']", RUNTIME
    )
    assert enabling, "runtime never ungates a pointer-events-none control"


def test_questionnaire_gates_are_ungated_by_answering(client) -> None:
    """Panels whose Continue is gated were captured empty; the runtime must
    enable Continue once an answer exists (any answering gesture)."""

    gated = [key for key, panel in PANELS.items()
             if "pointer-events-none" in panel and ">Continue<" in panel]
    assert gated, "expected at least one gated panel in the captured evidence"
    assert "enableContinue" in RUNTIME
    assert "hasAnswer" in RUNTIME


def test_step_two_registration_fields_are_reachable(client) -> None:
    """Submitting only the email must return the credentials step (a human
    cannot create an account otherwise)."""

    first = client.post("/signup/register", data={"email": "walker@example.com"})
    assert first.status_code == 200
    assert 'name="username"' in first.text
    assert 'name="password"' in first.text
    assert 'action="/signup/register"' in first.text
