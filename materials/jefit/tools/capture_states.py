#!/usr/bin/env python3
"""Anonymous interaction-state capture for the JEFIT offline clone.

Captures the interaction-dependent public states that capture_source.py
cannot reach by URL alone, in the same artifact layout
(source-current/<capture_id>/<state_id>/<viewport>/frame-N.png + page.html +
links.json + resources.json + meta.json), so downstream scope-evidence and
calibration tooling treats both alike.

Safety: every browser context aborts non-GET requests at the network layer,
so no click in this walk can mutate the source site even if a control tries
to submit. Validation states therefore show exactly what an anonymous
browser renders client-side. No credential, email, or personal field is ever
filled; the signup questionnaire walk stops at the first step that asks for
identity data (email/username/password) and records where it stopped.

Usage:
    python3 materials/jefit/tools/capture_states.py \
        --site-dir materials/jefit [--only exercises-filter-abs,...] [--headed]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from capture_source import (  # noqa: E402
    REGION_JS, census, dismiss_consent, hide_scrollbars, resource_census,
    snap_frames,
)

ORIGIN = "https://www.jefit.com"

IDENTITY_MARKERS = (
    "email", "e-mail", "username", "user name", "password", "phone",
    "first name", "last name", "full name",
)


class WalkError(RuntimeError):
    pass


def abort_non_get(route):
    if route.request.method != "GET":
        route.abort()
    else:
        route.continue_()


def write_state(page, out_root: pathlib.Path, state_id: str, vp: dict,
                note: str, frames: int = 3) -> dict:
    dest = out_root / state_id / vp["name"]
    dest.mkdir(parents=True, exist_ok=True)
    shas = snap_frames(page, dest, frames)
    (dest / "page.html").write_text(page.content())
    (dest / "links.json").write_text(json.dumps(census(page), indent=2))
    (dest / "resources.json").write_text(
        json.dumps(resource_census(page), indent=2))
    regions = page.evaluate(REGION_JS)
    meta = {
        "checkpoint": state_id, "family": "interaction-state",
        "priority": "P1", "viewport": vp["name"],
        "requested_url": None, "final_url": page.url,
        "http_status": None, "title": page.title(),
        "body_text_len": len(page.eval_on_selector("body", "e=>e.innerText")),
        "frames": frames, "frame_sha256": shas,
        "frames_identical": len(set(shas)) == 1,
        "link_count": None, "resource_count": None,
        "engine": "local-playwright", "nav_fallback": None,
        "consent_action": None, "regions": regions,
        "interaction": note,
    }
    (dest / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"  ok {state_id}/{vp['name']} -> {page.url}")
    return meta


DESKTOP = {"name": "desktop", "width": 1440, "height": 900}
MOBILE = {"name": "mobile", "width": 390, "height": 844}


def goto(page, path: str, settle_ms: int, vp: dict = DESKTOP) -> None:
    # Explicit viewport per navigation: a failed mobile step must not leak
    # its viewport into subsequent desktop states.
    if page.viewport_size["width"] != vp["width"]:
        page.set_viewport_size({"width": vp["width"], "height": vp["height"]})
    page.goto(f"{ORIGIN}{path}", wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(settle_ms)
    dismiss_consent(page)


def click_text(page, text: str, exact: bool = True) -> None:
    page.get_by_text(text, exact=exact).first.click()
    page.wait_for_timeout(1500)


def step_exercises_filter(page, out, settle):
    goto(page, "/exercises", settle)
    click_text(page, "Abs")
    page.wait_for_timeout(1200)
    return write_state(page, out, "exercises-filter-abs", DESKTOP,
                       "clicked muscle filter 'Abs'; count drops, "
                       "'FILTERS n / CLEAR FILTERS' chips appear")


def step_exercises_no_results(page, out, settle):
    goto(page, "/exercises", settle)
    click_text(page, "Abs")
    click_text(page, "EZ Curl Bar")
    page.wait_for_timeout(1200)
    return write_state(page, out, "exercises-no-results", DESKTOP,
                       "muscle 'Abs' + equipment 'EZ Curl Bar' => "
                       "'0 EXERCISES FOUND' empty grid")


def step_nav_products(page, out, settle):
    goto(page, "/", settle)
    click_text(page, "Products")
    page.wait_for_timeout(800)
    return write_state(page, out, "nav-products-dropdown", DESKTOP,
                       "opened 'Products' primary-nav dropdown")


def step_nav_workouts(page, out, settle):
    goto(page, "/", settle)
    click_text(page, "Workouts")
    page.wait_for_timeout(800)
    return write_state(page, out, "nav-workouts-dropdown", DESKTOP,
                       "opened 'Workouts' primary-nav dropdown")


def step_nav_more(page, out, settle):
    goto(page, "/", settle)
    click_text(page, "More")
    page.wait_for_timeout(800)
    return write_state(page, out, "nav-more-dropdown", DESKTOP,
                       "opened 'More' primary-nav dropdown")


def step_mobile_menu(page, out, settle):
    goto(page, "/", settle, vp=MOBILE)
    clicked = page.evaluate(
        """() => {
          const scope = document.querySelector('header, nav') || document;
          const btn = Array.from(scope.querySelectorAll('button'))
            .find(b => b.offsetParent && (b.querySelector('svg') ||
                  /menu/i.test(b.getAttribute('aria-label') || b.innerText)));
          if (!btn) return false; btn.click(); return true;
        }""")
    if not clicked:
        raise WalkError("mobile menu button not found")
    page.wait_for_timeout(1000)
    meta = write_state(page, out, "mobile-menu-open", MOBILE,
                       "opened hamburger menu at 390x844")
    page.set_viewport_size({"width": DESKTOP["width"], "height": DESKTOP["height"]})
    return meta


def step_dark_mode(page, out, settle):
    goto(page, "/", settle)
    page.locator("footer input[type=checkbox], footer [role=switch]").first.click()
    page.wait_for_timeout(1500)
    return write_state(page, out, "home-dark-mode", DESKTOP,
                       "toggled footer Dark Mode switch on /")


def step_login_validation(page, out, settle):
    goto(page, "/login", settle)
    # The submit button is a React-controlled element that detaches during
    # Playwright's actionability retries; dispatch the click in-page instead.
    page.evaluate(
        """() => {
          const btn = Array.from(document.querySelectorAll('button'))
            .find(b => b.offsetParent && /log in/i.test(b.innerText));
          if (btn) btn.click();
          else document.querySelector('form')?.requestSubmit?.();
        }""")
    page.wait_for_timeout(1500)
    return write_state(page, out, "login-validation-empty", DESKTOP,
                       "clicked Log In with both fields empty (non-GET "
                       "requests aborted); records client-side validation")


def step_forgot_validation(page, out, settle):
    goto(page, "/login/forgot-password", settle)
    page.get_by_role("button", name="Send reset link").first.click()
    page.wait_for_timeout(1500)
    return write_state(page, out, "forgot-password-validation-empty", DESKTOP,
                       "clicked 'Send reset link' with empty email (non-GET "
                       "aborted); records client-side validation")


def step_build_routine_validation(page, out, settle):
    goto(page, "/build-routine", settle)
    # 'Save' renders as an anchor-styled control, not a button role.
    page.evaluate(
        """() => {
          const el = Array.from(document.querySelectorAll('button, a, [role=button]'))
            .find(e => e.offsetParent && e.innerText.trim() === 'Save');
          el?.click();
        }""")
    page.wait_for_timeout(1500)
    return write_state(page, out, "build-routine-validation-empty", DESKTOP,
                       "clicked Save with empty routine name (non-GET "
                       "aborted); records client-side validation")


def step_signup_questionnaire(page, out, settle):
    """Walk the public signup questionnaire by choosing the FIRST visible
    option at each step, capturing every distinct step, stopping before any
    identity/credential entry. Never creates an account."""
    goto(page, "/signup", settle)
    metas = [write_state(page, out, "signup-step-01", DESKTOP,
                         "initial /signup render")]
    for n in range(2, 21):
        fields = page.eval_on_selector_all(
            "input, textarea",
            "els=>els.filter(e=>e.offsetParent).map(e=>((e.placeholder||'')+' '+"
            "(e.name||'')+' '+(e.type||'')+' '+(e.getAttribute('aria-label')||''))"
            ".toLowerCase())")
        if any(m in f for f in fields for m in IDENTITY_MARKERS):
            print(f"  stop: step {n - 1} asks for identity data; walk ends")
            break
        before = page.evaluate("()=>document.body.innerText.slice(0,400)")
        # Steps with numeric inputs (goal weight, height/weight) need every
        # visible field filled with a synthetic value before Continue; a unit
        # toggle chip alone does not advance them.
        filled = page.evaluate(
            """() => {
              const inputs = Array.from(document.querySelectorAll(
                'input[type=number], input[inputmode=numeric], input[inputmode=decimal], [role=spinbutton]'))
                .filter(e => e.offsetParent);
              if (!inputs.length) return null;
              const set = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
              const used = [];
              for (const inp of inputs) {
                const lo = parseFloat(inp.min ?? inp.getAttribute('aria-valuemin'));
                const hi = parseFloat(inp.max ?? inp.getAttribute('aria-valuemax'));
                let v = 70;
                if (!Number.isNaN(lo) && !Number.isNaN(hi))
                  v = Math.round((lo + hi) / 2);
                else if (!Number.isNaN(hi)) v = Math.min(70, Math.floor(hi / 2) || 1);
                set.call(inp, String(v));
                inp.dispatchEvent(new Event('input', {bubbles: true}));
                inp.dispatchEvent(new Event('change', {bubbles: true}));
                used.push(v);
              }
              return 'numeric[' + used.join(',') + ']';
            }""")
        clicked = filled or page.evaluate(
            """() => {
              const all = Array.from(document.querySelectorAll(
                'button, [role=button], [role=radio], [role=option], [role=checkbox]'))
                .filter(b => b.offsetParent && b.innerText.trim().length > 0
                        && !/accept|customize|log in|sign in|google|apple|facebook/i
                          .test(b.innerText));
              const radios = all.filter(b => ['radio', 'option', 'checkbox']
                .includes(b.getAttribute('role')));
              const cont = all.find(b => /^continue$/i.test(b.innerText.trim()));
              // Some steps use bare cursor-pointer divs (e.g. target zones).
              const chips = Array.from(document.querySelectorAll('div.cursor-pointer'))
                .filter(d => d.offsetParent && d.innerText.trim().length > 0
                        && d.innerText.trim().length < 40
                        && !d.querySelector('div.cursor-pointer'));
              const pick = radios[0] || chips[0] || all.find(
                b => !/^(continue|back)$/i.test(b.innerText.trim()));
              const labels = [];
              if (pick) { pick.click(); labels.push(pick.innerText.trim().slice(0, 40)); }
              return labels.length ? labels.join('+') : null;
            }""")
        if clicked is not None:
            page.wait_for_timeout(700)
            cont = page.evaluate(
                """() => {
                  const c = Array.from(document.querySelectorAll('button'))
                    .find(b => b.offsetParent && /^continue$/i.test(b.innerText.trim()));
                  if (!c || c.disabled) return false; c.click(); return true;
                }""")
            if cont:
                clicked += "+Continue"
        if clicked is None:
            print(f"  stop: no clickable option at step {n - 1}")
            break
        page.wait_for_timeout(1600)
        after = page.evaluate("()=>document.body.innerText.slice(0,400)")
        if after == before:
            print(f"  stop: step did not advance after clicking '{clicked}'")
            break
        metas.append(write_state(
            page, out, f"signup-step-{n:02d}", DESKTOP,
            f"advanced questionnaire by choosing '{clicked}'"))
    if "/signup/results" in page.url:
        # The analysis animation resolves into the results/account screen;
        # wait it out and capture whatever renders. Never fill anything here.
        page.wait_for_timeout(12000)
        metas.append(write_state(
            page, out, "signup-results", DESKTOP,
            "waited out the 'Analyzing your answers' animation on "
            "/signup/results; captured the resolved view without entering "
            "any data"))
        advanced = page.evaluate(
            """() => {
              const c = Array.from(document.querySelectorAll('button'))
                .find(b => b.offsetParent && /^continue$/i.test(b.innerText.trim()));
              if (!c || c.disabled) return false; c.click(); return true;
            }""")
        if advanced:
            page.wait_for_timeout(2500)
            metas.append(write_state(
                page, out, "signup-account-create", DESKTOP,
                "clicked Continue on the results view and captured the "
                "account-creation entry (identity fields, terms links, "
                "verification guidance) WITHOUT filling or submitting "
                "anything"))
    return metas


STEPS = [
    ("exercises-filter-abs", step_exercises_filter),
    ("exercises-no-results", step_exercises_no_results),
    ("nav-products-dropdown", step_nav_products),
    ("nav-workouts-dropdown", step_nav_workouts),
    ("nav-more-dropdown", step_nav_more),
    ("mobile-menu-open", step_mobile_menu),
    ("home-dark-mode", step_dark_mode),
    ("login-validation-empty", step_login_validation),
    ("forgot-password-validation-empty", step_forgot_validation),
    ("build-routine-validation-empty", step_build_routine_validation),
    ("signup-questionnaire", step_signup_questionnaire),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-dir", default="materials/jefit")
    ap.add_argument("--only", default="", help="comma-separated state ids")
    ap.add_argument("--settle-ms", type=int, default=4000)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s} or None
    site_dir = pathlib.Path(args.site_dir)
    plan = json.loads(
        (site_dir / "scope" / "source-capture-plan.json").read_text())
    out_root = site_dir / "source-current" / plan["capture_id"]

    records: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        try:
            ctx = browser.new_context(
                viewport={"width": DESKTOP["width"], "height": DESKTOP["height"]},
                locale="en-US", timezone_id="Etc/UTC")
            ctx.route("**/*", abort_non_get)
            page = ctx.new_page()
            hide_scrollbars(page)
            for state_id, fn in STEPS:
                if only and state_id not in only:
                    continue
                try:
                    result = fn(page, out_root, args.settle_ms)
                    records.extend(result if isinstance(result, list)
                                   else [result])
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! {state_id}: {exc}", file=sys.stderr)
                    records.append({"checkpoint": state_id,
                                    "engine": "local-playwright",
                                    "error": str(exc)[:200]})
        finally:
            browser.close()

    index_path = out_root / "state-capture-index.json"
    if index_path.is_file():
        fresh = {(r.get("checkpoint"), r.get("viewport")) for r in records}
        previous = json.loads(index_path.read_text()).get("captures", [])
        records = [r for r in previous
                   if (r.get("checkpoint"), r.get("viewport")) not in fresh
                   ] + records
    index_path.write_text(json.dumps(
        {"schema_version": "jefit.state-capture-index.v1",
         "capture_id": plan["capture_id"], "captures": records}, indent=2))
    print(f"\nwrote {len(records)} state records -> {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
