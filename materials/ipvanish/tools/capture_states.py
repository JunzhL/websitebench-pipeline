#!/usr/bin/env python3
"""Anonymous interaction-state capture for the IPVanish offline clone.

Captures the interaction-dependent public states that capture_source.py
cannot reach by URL alone, in the same artifact layout
(source-current/<capture_id>/<state_id>/<viewport>/frame-N.png + page.html +
links.json + resources.json + meta.json), so downstream scope-evidence and
calibration tooling treats both alike. The run index is
state-capture-index.json with schema_version
"ipvanish.state-capture-index.v1".

Channel: local headless Playwright Chromium with the ordinary Chrome UA from
capture_source (the SSO, checkout and support subdomains reject the headless
UA; see scope/implement-notes.md).

Safety, in three layers:

1. Network layer -- every browser context aborts non-GET requests, so no
   click in this walk can mutate the source site even if a control tries to
   submit. A consequence worth knowing: the Angular checkout may need a
   non-GET to build its quote, and when that request is aborted the Order
   Summary never paints; such a state is recorded as an error rather than
   relaxing the rule.
2. Payment-surface guard -- assert_fill_allowed() refuses to type into any
   field while the page sits on a payment origin (checkout.ipvanish.com,
   the Zuora hosted-payment iframe), and assert_click_allowed() refuses any
   control whose text matches /subscribe|pay now|place order|complete/i. The
   walker never fills anything on any surface; the guards exist so a later
   edit that tries to fails loudly instead of touching a live payment form.
3. Evidence layer -- the checkout card-form state records iframe URLs
   (query-stripped: Zuora hosted-page URLs carry signature tokens) and the
   field name/id/type inventory only. No field value is ever read or written.

Usage:
    python3 materials/ipvanish/tools/capture_states.py \
        --site-dir materials/ipvanish [--only pricing-monthly,...] [--headed]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from capture_source import (  # noqa: E402
    CAPTURE_ID, CHROME_UA, REGION_JS, census, dismiss_consent,
    hide_scrollbars, resource_census, settle as settle_page, snap_frames,
)

WWW = "https://www.ipvanish.com"
SSO_ORIGIN = "https://sso.ipvanish.com"
CHECKOUT_ORIGIN = "https://checkout.ipvanish.com"
SUPPORT_HOME = "https://support.ipvanish.com/hc/en-us"
NOT_FOUND_URL = f"{WWW}/zzzz-no-match-websitebench"

CHECKOUT_URL = (
    CHECKOUT_ORIGIN + "/checkout/address-payment-method"
    "?flow={flow}&currency=USD&lang=EN"
)

DESKTOP = {"name": "desktop", "width": 1440, "height": 900}
MOBILE = {"name": "mobile", "width": 390, "height": 844}

# Hosts where typing is categorically forbidden: the live checkout and the
# Zuora hosted payment iframe it embeds.
PAYMENT_HOST_FRAGMENTS = ("checkout.ipvanish.com", "zuora", "checkout.com")

# Controls that would place an order. Never clicked, on any surface.
FORBIDDEN_CONTROL_RE = re.compile(
    r"subscribe|pay now|place order|complete", re.IGNORECASE)
FORBIDDEN_CONTROL_JS = "/subscribe|pay now|place order|complete/i"


class WalkError(RuntimeError):
    pass


class CheckoutSafetyError(WalkError):
    """Raised when a step tries to do something the payment mandate forbids."""


def abort_non_get(route) -> None:
    if route.request.method != "GET":
        route.abort()
    else:
        route.continue_()


def strip_query(url: str) -> str:
    """Drop query and fragment. Zuora hosted-page URLs carry signature
    tokens, so only the path may ever be persisted."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, "", ""))


def on_payment_origin(url: str) -> bool:
    host = urllib.parse.urlsplit(url).netloc.casefold()
    return any(fragment in host for fragment in PAYMENT_HOST_FRAGMENTS)


def assert_fill_allowed(page, field: str) -> None:
    """Hard guard. This walker fills nothing anywhere; on a payment origin
    filling is not merely skipped, it is an error."""
    if on_payment_origin(page.url):
        raise CheckoutSafetyError(
            f"refusing to fill '{field}' on payment origin {page.url}")


def assert_click_allowed(label: str) -> None:
    if FORBIDDEN_CONTROL_RE.search(label or ""):
        raise CheckoutSafetyError(
            f"refusing to click order-placing control '{label}'")


def write_state(page, out_root: pathlib.Path, state_id: str, vp: dict,
                note: str, frames: int = 3, requested_url: str | None = None,
                http_status: int | None = None) -> dict:
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
        "requested_url": requested_url, "final_url": page.url,
        "http_status": http_status, "title": page.title(),
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


def goto(page, url: str, settle_ms: int, vp: dict = DESKTOP,
         wait_selector: str | None = None):
    """Navigate with an explicit viewport. The viewport is always asserted
    from the requested state's own descriptor: a failed mobile step must not
    leak its 390px viewport into subsequent desktop states."""
    current = page.viewport_size or {}
    if (current.get("width"), current.get("height")) != (vp["width"],
                                                         vp["height"]):
        page.set_viewport_size({"width": vp["width"], "height": vp["height"]})
    target = url if url.startswith("http") else f"{WWW}{url}"
    resp = page.goto(target, wait_until="domcontentloaded", timeout=60000)
    settle_page(page, settle_ms, wait_selector, target)
    dismiss_consent(page)
    return resp


# Generic in-page clicker. Many controls on this site are bare inline
# elements (the billing-period tabs are unwrapped <strong>, the checkout
# payment rows are <li>), so the click walks up from the text node to the
# nearest sizeable ancestor. Order-placing controls are refused in JS too,
# not only in Python.
JS_CLICK_LABEL = """
(args) => {
  const FORBID = %s;
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
  const needle = args.pattern.toLowerCase();
  const roots = document.querySelectorAll(args.selector);
  const hits = Array.from(roots).filter(e => {
    if (!e.offsetParent) return false;
    const t = norm(e.textContent).toLowerCase();
    if (!t || t.length > args.maxLen) return false;
    return args.exact ? t === needle : t.includes(needle);
  });
  if (!hits.length) return null;
  // Deepest match wins: never click a wrapper that merely contains the label.
  let target = hits.find(e => !hits.some(o => o !== e && e.contains(o)))
               || hits[0];
  if (FORBID.test(norm(target.textContent))) return 'refused';
  for (let i = 0; i < 5; i++) {
    const r = target.getBoundingClientRect();
    if (r.width >= args.minWidth && r.height >= args.minHeight) break;
    if (!target.parentElement) break;
    target = target.parentElement;
    if (FORBID.test(norm(target.textContent))) return 'refused';
  }
  target.scrollIntoView({block: 'center'});
  target.click();
  const cls = typeof target.className === 'string'
    ? target.className.trim().split(/\\s+/).filter(Boolean).join('.') : '';
  return target.tagName.toLowerCase() + (cls ? '.' + cls : '');
}
""" % FORBIDDEN_CONTROL_JS


def click_label(page, label: str, selector: str = "strong, span, a, button,"
                " li, div, [role=button], [role=tab]", exact: bool = True,
                min_width: int = 60, min_height: int = 24,
                max_len: int = 80) -> str:
    """Click the element carrying `label`, escalating to its nearest sizeable
    ancestor when the label itself has no clickable box. Returns a descriptor
    of what was clicked."""
    assert_click_allowed(label)
    clicked = page.evaluate(JS_CLICK_LABEL, {
        "pattern": label, "selector": selector, "exact": exact,
        "minWidth": min_width, "minHeight": min_height, "maxLen": max_len})
    if clicked == "refused":
        raise CheckoutSafetyError(
            f"click target for '{label}' resolved onto an order-placing "
            "control; refused")
    if not clicked:
        raise WalkError(f"no visible element matching '{label}'")
    page.wait_for_timeout(1200)
    return clicked


PRICES_JS = """
() => (document.body.innerText.match(/\\$\\s?[\\d,]+(?:\\.\\d{2})?/g) || [])
        .slice(0, 40)
"""


def visible_prices(page) -> list[str]:
    return page.evaluate(PRICES_JS)


def activate_billing_tab(page, label: str, expect_change: bool) -> str:
    """Activate one billing-period tab on /pricing/ and verify the rendered
    prices actually changed. The tab labels are bare <strong> elements with
    no wrapping control, so the click goes to the nearest sizeable ancestor
    via in-page JS."""
    before = visible_prices(page)
    clicked = click_label(page, label, selector="strong, span, a, button,"
                          " li, div, [role=tab]", min_width=80,
                          min_height=28, max_len=40)
    changed = False
    for _ in range(16):
        if visible_prices(page) != before:
            changed = True
            break
        page.wait_for_timeout(500)
    if expect_change and not changed:
        raise WalkError(
            f"clicked '{label}' ({clicked}) but the visible prices did not "
            "change; refusing to capture a mislabelled state")
    page.wait_for_timeout(800)
    suffix = "prices changed" if changed else "prices unchanged (default tab)"
    return f"clicked billing-period tab '{label}' via {clicked}; {suffix}"


def step_pricing_tab(state_id: str, label: str, expect_change: bool):
    def step(page, out, settle):
        goto(page, "/pricing/", settle)
        note = activate_billing_tab(page, label, expect_change)
        return write_state(page, out, state_id, DESKTOP, note,
                           requested_url=f"{WWW}/pricing/")
    return step


def step_pricing_features(page, out, settle):
    goto(page, "/pricing/", settle)
    clicked = click_label(page, "View All Features", exact=False,
                          min_width=80, min_height=20, max_len=40)
    page.wait_for_timeout(1500)
    return write_state(
        page, out, "pricing-features-expanded", DESKTOP,
        f"clicked the 'View All Features' expander via {clicked}; "
        "full feature comparison revealed",
        requested_url=f"{WWW}/pricing/")


# Astra primary-nav dropdowns open on hover. A real pointer hover is tried
# first (it triggers the CSS :hover rules faithfully); the JS fallback
# dispatches the pointer events and adds Astra's hover classes. The parent
# item is a real link, so it is never clicked -- that would navigate away.
JS_OPEN_NAV = """
(label) => {
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const scope = document.querySelector(
    '#ast-desktop-header, .main-header-menu, #masthead, header') || document;
  const item = Array.from(scope.querySelectorAll('a')).find(
    a => a.offsetParent && norm(a.textContent) === norm(label));
  if (!item) return null;
  const li = item.closest('li') || item.parentElement;
  for (const type of ['pointerover', 'pointerenter', 'mouseover',
                      'mouseenter', 'focus']) {
    const ev = type.startsWith('pointer')
      ? new PointerEvent(type, {bubbles: true})
      : new (type === 'focus' ? FocusEvent : MouseEvent)(type, {bubbles: true});
    item.dispatchEvent(ev);
    if (li) li.dispatchEvent(ev);
  }
  if (li) li.classList.add('ast-menu-hover', 'hover', 'focus');
  const sub = li && li.querySelector('ul, .sub-menu, .astra-full-megamenu-wrapper');
  if (sub) {
    sub.style.removeProperty('display');
    sub.classList.add('toggled-on');
  }
  const r = item.getBoundingClientRect();
  return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
          submenu: !!sub};
}
"""

JS_SUBMENU_VISIBLE = """
(label) => {
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const scope = document.querySelector(
    '#ast-desktop-header, .main-header-menu, #masthead, header') || document;
  const item = Array.from(scope.querySelectorAll('a')).find(
    a => norm(a.textContent) === norm(label));
  if (!item) return false;
  const li = item.closest('li');
  if (!li) return false;
  const subs = li.querySelectorAll('ul, .sub-menu, .astra-full-megamenu-wrapper');
  for (const s of subs) {
    const cs = getComputedStyle(s);
    const r = s.getBoundingClientRect();
    if (cs.display !== 'none' && cs.visibility !== 'hidden' &&
        parseFloat(cs.opacity || '1') > 0.05 && r.width > 40 && r.height > 20)
      return true;
  }
  return false;
}
"""


def open_nav_dropdown(page, label: str) -> str:
    info = page.evaluate(JS_OPEN_NAV, label)
    if info is None:
        raise WalkError(f"primary-nav item '{label}' not found")
    how = "js-hover-events"
    page.mouse.move(info["x"], info["y"])
    page.wait_for_timeout(900)
    if not page.evaluate(JS_SUBMENU_VISIBLE, label):
        page.evaluate(JS_OPEN_NAV, label)
        page.wait_for_timeout(900)
        if not page.evaluate(JS_SUBMENU_VISIBLE, label):
            raise WalkError(f"no submenu became visible for '{label}'")
    else:
        how = "pointer-hover"
    return how


def step_nav(state_id: str, label: str):
    def step(page, out, settle):
        goto(page, "/", settle)
        how = open_nav_dropdown(page, label)
        return write_state(
            page, out, state_id, DESKTOP,
            f"opened the '{label}' primary-nav dropdown on / ({how}); the "
            "parent item is a link and is never clicked",
            requested_url=f"{WWW}/")
    return step


JS_MOBILE_MENU = """
() => {
  const scope = document.querySelector(
    '#ast-mobile-header, #masthead, header, nav') || document;
  const cands = Array.from(scope.querySelectorAll(
    '.ast-mobile-menu-trigger, .menu-toggle, button, [role=button], a'));
  const btn = cands.find(b => b.offsetParent && (
    /menu/i.test(b.getAttribute('aria-label') || '') ||
    /menu-toggle|mobile-menu-trigger|hamburger/i.test(
      typeof b.className === 'string' ? b.className : '') ||
    (b.querySelector('svg, .ast-mobile-svg') &&
     !(b.textContent || '').trim())));
  if (!btn) return null;
  btn.click();
  const cls = typeof btn.className === 'string'
    ? btn.className.trim().split(/\\s+/).filter(Boolean).join('.') : '';
  return btn.tagName.toLowerCase() + (cls ? '.' + cls : '');
}
"""


def step_mobile_menu(page, out, settle):
    goto(page, "/", settle, vp=MOBILE)
    clicked = page.evaluate(JS_MOBILE_MENU)
    if not clicked:
        raise WalkError("mobile menu trigger not found")
    page.wait_for_timeout(1200)
    return write_state(
        page, out, "mobile-menu-open", MOBILE,
        f"opened the hamburger menu at 390x844 via {clicked}",
        requested_url=f"{WWW}/")


def step_sso_signin(page, out, settle):
    goto(page, f"{SSO_ORIGIN}/", settle, wait_selector="input[name=email]")
    return write_state(
        page, out, "sso-signin", DESKTOP,
        "loaded the client-rendered sign-in app and waited for "
        "input[name=email] to exist; no field filled, nothing submitted",
        requested_url=f"{SSO_ORIGIN}/")


def step_sso_recovery(page, out, settle):
    goto(page, f"{SSO_ORIGIN}/", settle, wait_selector="input[name=email]")
    # Nothing is typed on the sign-in view either; the recovery view is reached
    # by clicking through, which is the only route that works (the un-slashed
    # /reset-password deep link 403s from its S3 origin).
    click_label(page, "Forgot password?", exact=False, min_width=40,
                min_height=12, max_len=40)
    how = "clicked 'Forgot password?'"
    for _ in range(20):
        if "reset-password" in page.url:
            break
        page.wait_for_timeout(500)
    settle_page(page, settle, "input[name=username]", "sso-recovery")
    if "reset-password" not in page.url:
        # Only the trailing-slash route is served; the un-slashed deep link
        # 403s at its S3 origin, so the slashed URL is the fallback.
        goto(page, f"{SSO_ORIGIN}/reset-password/", settle,
             wait_selector="input[name=username]")
        how = "click did not route; navigated to /reset-password/ directly"
    return write_state(
        page, out, "sso-recovery", DESKTOP,
        f"{how}; recovery view reached at {page.url} (the route requires the "
        "trailing slash -- /reset-password without it 403s)",
        requested_url=f"{SSO_ORIGIN}/reset-password/")


def wait_for_order_summary(page, timeout_ms: int = 45000) -> bool:
    """Wait for the Order Summary; report whether its amounts resolved.

    Returns True when the summary's own line items carry a non-zero total.

    They usually will not, and that is a consequence of policy rather than a
    defect: this walker aborts every non-GET request so source acquisition stays
    read-only, and IPVanish prices a checkout through a non-GET quote request.
    Under GET-only capture the summary therefore renders its product name (which
    embeds the plan's first-period price) while the line items, discount,
    estimated tax and total stay `$0.00`. An interactive probe that allows the
    page's own quote request does resolve them — see the recorded figures in
    scope/implement-notes.md — so the resolved amounts are directly observed
    evidence, they just cannot live in a GET-only frozen capture. The caller
    records which of the two it got instead of failing or pretending.
    """
    deadline = timeout_ms
    while deadline > 0:
        text = page.evaluate("()=>document.body.innerText || ''")
        if "Order Summary" in text:
            tail = text.split("Total due", 1)[-1][:40] if "Total due" in text else ""
            resolved = any(ch.isdigit() and ch != "0" for ch in tail)
            if resolved:
                return True
            page.wait_for_timeout(2000)
            deadline -= 2000
            if deadline <= timeout_ms // 2:
                return False
            continue
        page.wait_for_timeout(1000)
        deadline -= 1000
    raise WalkError(
        "'Order Summary' never appeared at all (the Angular shell did not "
        "render; even the GET-only view should reach this point)")


def step_checkout_chooser(flow: str):
    state_id = f"checkout-chooser-{flow}"

    def step(page, out, settle):
        url = CHECKOUT_URL.format(flow=flow)
        goto(page, url, settle)
        quote_resolved = wait_for_order_summary(page)
        page.wait_for_timeout(1500)
        return write_state(
            page, out, state_id, DESKTOP,
            f"loaded the checkout payment-method chooser for flow={flow}; "
            f"quote_resolved={quote_resolved} — under GET-only capture the "
            "non-GET quote request is aborted, so the summary shows the "
            "product name's first-period price while line items, discount, "
            "estimated tax and total read $0.00 (the resolved figures are "
            "recorded in scope/implement-notes.md from an interactive probe). "
            "No field filled, nothing submitted.",
            requested_url=url)
    return step


# Field inventory: name / id / type only. Values are never read, so no
# card-like or personal data can reach the evidence tree.
# Field inventory for a hosted payment frame. Visible controls are listed
# first: the Zuora hosted page carries ~60 hidden infrastructure inputs ahead of
# the user-facing ones, so a flat cap silently truncated away exactly the fields
# that constitute the evidence. Values are never read — names, ids and types
# only.
JS_FIELD_INVENTORY = """
() => {
  const all = Array.from(document.querySelectorAll('input, select, textarea'))
    .map(e => ({name: e.getAttribute('name') || null, id: e.id || null,
                type: (e.getAttribute('type') || e.tagName).toLowerCase(),
                visible: e.offsetParent !== null}));
  const shown = all.filter(f => f.type !== 'hidden');
  const hidden = all.filter(f => f.type === 'hidden');
  return shown.concat(hidden).slice(0, 140);
}
"""


def payment_frames(page) -> list[dict]:
    """Query-stripped iframe URLs plus their field inventory."""
    out: list[dict] = []
    for frame in page.frames:
        if frame is page.main_frame:
            continue
        try:
            fields = frame.evaluate(JS_FIELD_INVENTORY)
        except Exception:  # noqa: BLE001 - frame detached or not ready
            fields = []
        out.append({"iframe_url": strip_query(frame.url), "fields": fields})
    return out


#: The user-facing fields of the hosted payment page. The Zuora frame bootstraps
#: in two stages — a scaffold carrying only hidden infrastructure inputs, then
#: the visible form — so waiting for "any field_* input" returns too early and
#: records an inventory with none of the fields a person actually fills.
USER_FACING_FIELDS = ("field_creditCardNumber", "field_email",
                      "field_creditCardHolderName", "field_cardSecurityCode")


def wait_for_card_fields(page, timeout_ms: int = 60000) -> list[dict]:
    deadline = timeout_ms
    while deadline > 0:
        frames = payment_frames(page)
        for entry in frames:
            names = {f.get("name") or f.get("id") or "" for f in entry["fields"]}
            visible = {f.get("name") or f.get("id") or "" for f in entry["fields"]
                       if f.get("type") != "hidden"}
            if names & set(USER_FACING_FIELDS) and visible:
                return frames
        page.wait_for_timeout(1000)
        deadline -= 1000
    raise WalkError(
        "the hosted-payment iframe never rendered a visible user-facing field "
        f"(waited {timeout_ms}ms for one of {USER_FACING_FIELDS})")


def step_checkout_card_form(page, out, settle):
    flow = "essential-annual"
    url = CHECKOUT_URL.format(flow=flow)
    goto(page, url, settle)
    quote_resolved = wait_for_order_summary(page)
    # This surface is a live payment form: nothing is typed here and the
    # 'Subscribe now' button is never clicked (assert_click_allowed rejects it
    # and the in-page clicker refuses it independently). assert_fill_allowed()
    # is deliberately NOT called here — it raises on a payment origin by
    # design, so invoking it as documentation aborts the capture.
    # Expand the Credit-card panel. A Playwright click on the <li> alone does
    # not always expand it, so click in-page on the row element and escalate to
    # the nearest sizeable ancestor (the path that reproducibly expands), then
    # confirm expansion by the 'Subscribe now' control appearing in the main
    # document before enumerating the hosted-payment frame.
    clicked = page.evaluate("""() => {
      const row = document.querySelector('li.c-payment-method-type-select-card')
        || Array.from(document.querySelectorAll('*')).find(e => !e.children.length &&
             /^Credit card$/i.test((e.textContent || '').trim()));
      if (!row) return 'row-not-found';
      let node = row;
      for (let i = 0; i < 6 && node.parentElement; i++) {
        const r = node.getBoundingClientRect();
        if (r.height > 40 && r.width > 300) break;
        node = node.parentElement;
      }
      if (/subscribe|pay now|place order|complete/i.test(node.innerText || '')) {
        return 'refused';
      }
      node.click();
      return 'clicked ' + node.tagName + '.' + String(node.className).slice(0, 40);
    }""")
    if clicked in ("row-not-found", "refused"):
        raise WalkError(f"credit-card row not activated: {clicked}")
    expanded = False
    for _ in range(20):
        page.wait_for_timeout(1000)
        if "Secure checkout" in page.inner_text("body"):
            expanded = True
            break
    if not expanded:
        raise WalkError("credit-card panel never expanded (no 'Secure checkout')")
    frames = wait_for_card_fields(page)
    page.wait_for_timeout(1500)
    note = (
        f"quote_resolved={quote_resolved} (GET-only capture cannot run the non-GET quote request, so line items may read $0.00); "
        f"activated the Credit card row on flow={flow} via {clicked}; the "
        "hosted-payment (Zuora) iframe fields exist. NOTHING was typed and "
        "no order-placing control was clicked. iframes and field names "
        "observed (names/ids only, no values; iframe URLs query-stripped "
        "because they carry signature tokens): "
        + json.dumps(frames, sort_keys=True)
    )
    return write_state(page, out, "checkout-card-form-essential-annual",
                       DESKTOP, note, requested_url=url)


def step_support_home(page, out, settle):
    resp = goto(page, SUPPORT_HOME, settle)
    return write_state(
        page, out, "support-home", DESKTOP,
        "loaded the Zendesk help centre with the ordinary Chrome UA (the "
        "headless UA gets a Cloudflare 403 interstitial here)",
        requested_url=SUPPORT_HOME,
        http_status=resp.status if resp else None)


def step_not_found(page, out, settle):
    resp = goto(page, NOT_FOUND_URL, settle)
    status = resp.status if resp else None
    return write_state(
        page, out, "not-found", DESKTOP,
        f"requested a deliberately unmatched path; HTTP status {status}",
        requested_url=NOT_FOUND_URL, http_status=status)


STATES = [
    ("pricing-2year", step_pricing_tab("pricing-2year", "2-Year Plan", False)),
    ("pricing-yearly", step_pricing_tab("pricing-yearly", "Yearly Plan", True)),
    ("pricing-monthly", step_pricing_tab("pricing-monthly", "Monthly Plan",
                                         True)),
    # Three planned states were removed after direct observation, rather than
    # being captured as mislabelled or empty evidence:
    #   pricing-features-expanded -- 'View All Features ∨' exists in the served
    #     markup but no visible element matches it at 1440x900 or 390x844, so
    #     the expander is never rendered at a captured viewport.
    #   nav-features / nav-solutions -- the rendered top-level nav carries only
    #     Product, Apps, Resources, Help, Pricing (plus My Account / Get
    #     Started); 'Features' and 'Solutions' appear in static HTML only.
    ("nav-product", step_nav("nav-product", "Product")),
    ("nav-apps", step_nav("nav-apps", "Apps")),
    ("nav-resources", step_nav("nav-resources", "Resources")),
    ("mobile-menu-open", step_mobile_menu),
    ("sso-signin", step_sso_signin),
    ("sso-recovery", step_sso_recovery),
    ("checkout-chooser-essential-annual",
     step_checkout_chooser("essential-annual")),
    ("checkout-chooser-essential-monthly",
     step_checkout_chooser("essential-monthly")),
    ("checkout-chooser-advanced-annual",
     step_checkout_chooser("advanced-annual")),
    ("checkout-card-form-essential-annual", step_checkout_card_form),
    ("support-home", step_support_home),
    ("not-found", step_not_found),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-dir", default="materials/ipvanish")
    ap.add_argument("--only", default="", help="comma-separated state ids")
    ap.add_argument("--settle-ms", type=int, default=6000)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s} or None
    site_dir = pathlib.Path(args.site_dir)
    plan_path = site_dir / "scope" / "source-capture-plan.json"
    capture_id = CAPTURE_ID
    if plan_path.is_file():
        capture_id = json.loads(plan_path.read_text()).get(
            "capture_id", CAPTURE_ID)
    out_root = site_dir / "source-current" / capture_id

    records: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        try:
            ctx = browser.new_context(
                viewport={"width": DESKTOP["width"],
                          "height": DESKTOP["height"]},
                user_agent=CHROME_UA,
                locale="en-US", timezone_id="Etc/UTC")
            ctx.route("**/*", abort_non_get)
            page = ctx.new_page()
            hide_scrollbars(page)
            for state_id, fn in STATES:
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
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(
        {"schema_version": "ipvanish.state-capture-index.v1",
         "capture_id": capture_id, "captures": records}, indent=2))
    print(f"\nwrote {len(records)} state records -> {index_path}")
    failures = [r for r in records if "error" in r]
    if failures:
        print(f"{len(failures)} state(s) failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
