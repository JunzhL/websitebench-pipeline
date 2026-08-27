#!/usr/bin/env python3
"""Faithful anonymous source capture for the IPVanish offline clone.

Reads scope/source-capture-plan.json and captures every URL-addressable
checkpoint at each configured viewport into source-current/<capture_id>/.
For each (checkpoint, viewport) it writes N full-page frames (frame-1.png ...),
the rendered HTML, a link census, a runtime resource census (the asset-closure
discovery input), and a per-capture meta.json (final url, title, body length,
frame sha256s and an inter-frame identical flag used for flicker calibration).
The run also emits session-fingerprint.json and capture-index.json
(schema_version "ipvanish.capture-index.v1").

Channel: local headless Playwright Chromium with an ordinary Chrome user
agent (see CHROME_UA). This is the channel selected in the browser-provider
preflight recorded in scope/implement-notes.md: with the default headless UA
`support.ipvanish.com` answers with a Cloudflare 403 interstitial and the
www tree serves UA-dependent markup, so the headless UA yields markup that
does not match what a real visitor sees. Setting an ordinary Chrome UA is a
rendering-fidelity requirement, not an access-control bypass -- anything
still gated is recorded `unavailable` rather than fought. One browser context
covers every viewport so consent state and any experiment assignment stay
constant across the matrix.

The www tree is WordPress/Astra (server-rendered), but the in-scope
subdomains are client-rendered SPAs: `sso.ipvanish.com` is Next.js and
`checkout.ipvanish.com` is Angular, both of which paint their real content
several hundred milliseconds after document load. Every capture therefore
waits for network idle (12s cap) plus a generous settle delay (default
6000ms), with optional per-checkpoint readiness selectors.

Interaction-dependent states (billing-period tabs, nav dropdowns, the
checkout card form, password recovery) are out of scope here --
capture_states.py owns them in the same artifact layout.

Safety: navigation only, GET only, no field is ever filled and nothing is
ever submitted. No cookie, header or token is persisted.

Usage:
    python3 materials/ipvanish/tools/capture_source.py \
        --site-dir materials/ipvanish [--only home,pricing] [--settle-ms 6000]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

# Ordinary desktop Chrome UA. Required: www.ipvanish.com serves UA-dependent
# markup and the support/SSO/checkout subdomains reject the Playwright
# headless UA (Cloudflare 403 "Just a moment..."). Verified in the preflight
# table in scope/implement-notes.md.
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

CAPTURE_ID = "2026-08-19.ipvanish-r1"

# Checkpoints whose state requires scripted interaction; capture_states.py
# owns them in the same artifact layout. Keep in sync with
# capture_states.STATES -- an id must have exactly one owner so the two
# indexes never disagree.
INTERACTIVE_IDS: set[str] = {
    "pricing-2year",
    "pricing-yearly",
    "pricing-monthly",
    "pricing-features-expanded",
    "nav-product",
    "nav-features",
    "nav-solutions",
    "nav-apps",
    "nav-resources",
    "mobile-menu-open",
    "sso-signin",
    "sso-recovery",
    "checkout-chooser-essential-annual",
    "checkout-chooser-essential-monthly",
    "checkout-chooser-advanced-annual",
    "checkout-card-form-essential-annual",
    "support-home",
    "not-found",
}

# Post-navigation readiness selectors for the SPA subdomains, which render
# asynchronously well after network idle. Keys are plan checkpoint ids.
WAIT_SELECTORS: dict[str, str] = {
    "sso-signin": "input[name=email]",
    "sso-reset-password": "input[name=username]",
    "checkout-address-payment-method": "text=Order Summary",
}

# The site runs a Ziff Davis consent manager (cdn.ziffstatic.com), which
# renders its banner either inline or inside an iframe depending on the
# surface; dismiss_consent tries both. Patterns are ordered most- to
# least-specific; Playwright's :has-text() is a case-insensitive substring
# match, so 'Accept' also matches 'Accept All'.
CONSENT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button[aria-label*='Accept']",
    "button:has-text('Accept All Cookies')",
    "button:has-text('Accept')",
    "button:has-text('I Agree')",
    "button:has-text('Agree')",
    "button:has-text('Got it')",
    "button:has-text('OK')",
    "[role=button]:has-text('Accept')",
    "a:has-text('Got it')",
]


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hide_scrollbars(page) -> None:
    """Classic scrollbars consume layout width unlike the overlay scrollbars
    of the release-gate render environment. Hide them so the layout viewport
    equals the declared viewport exactly."""
    try:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Emulation.setScrollbarsHidden", {"hidden": True})
    except Exception:  # noqa: BLE001 - fall back to CSS injection
        page.add_init_script(
            "const s=document.createElement('style');"
            "s.textContent='::-webkit-scrollbar{display:none}"
            "html{scrollbar-width:none}';"
            "document.addEventListener('DOMContentLoaded',()=>"
            "document.head.appendChild(s));")


def _try_consent_frame(frame, tag: str) -> str | None:
    for sel in CONSENT_SELECTORS:
        try:
            btn = frame.locator(sel)
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=5000)
                return f"{tag}{sel}"
        except Exception:  # noqa: BLE001 - try the next pattern
            continue
    return None


def dismiss_consent(page) -> str | None:
    """Accept the Ziff Davis cookie banner once if it renders, in the main
    document or in the consent iframe. Consent persists in the browser
    context, so every later frame of the run shares one banner state.
    Returns the selector that matched (frame-qualified when the button lived
    in an iframe) or None when no banner was present."""
    matched = _try_consent_frame(page, "")
    if matched is None:
        for frame in page.frames:
            if frame is page.main_frame:
                continue
            matched = _try_consent_frame(frame, "frame::")
            if matched:
                break
    if matched:
        page.wait_for_timeout(1200)
    return matched


def census(page) -> list[str]:
    return page.eval_on_selector_all(
        "a[href]",
        "els=>Array.from(new Set(els.map(e=>((e.innerText||'').trim().slice(0,48)"
        "+' :: '+e.getAttribute('href'))))).filter(x=>x && !x.startsWith(' :: #'))",
    )


def resource_census(page) -> list[dict]:
    return page.evaluate(
        "()=>performance.getEntriesByType('resource').map(e=>({"
        "url:e.name, initiator:e.initiatorType,"
        "transfer_size:e.transferSize}))")


# Region probe. The www tree is WordPress with the Astra theme (#masthead,
# #primary, #content, #colophon); the SSO/checkout SPAs use plain
# header/main/footer landmarks. Both sets are probed in order.
REGION_JS = """
() => {
  const pick = sels => {
    for (const s of sels) {
      const e = document.querySelector(s);
      if (e) {
        const r = e.getBoundingClientRect();
        if (r.width > 0 && r.height > 0)
          return {selector: s, x: Math.round(r.x + window.scrollX),
                  y: Math.round(r.y + window.scrollY),
                  width: Math.round(r.width), height: Math.round(r.height)};
      }
    }
    return null;
  };
  return {
    header: pick(['header', '#masthead', '[role=banner]', '.site-header',
                  '.ast-main-header-wrap', '#ast-mobile-header']),
    nav: pick(['#ast-desktop-header nav', '.main-header-menu', 'nav',
               '[role=navigation]', '#ast-hf-mobile-menu']),
    main: pick(['main', '#primary', '#content', '[role=main]',
                '.site-content', '#__next main', 'app-root']),
    footer: pick(['footer', '#colophon', '[role=contentinfo]',
                  '.site-footer']),
    form: pick(['form']),
    document_height: Math.round(Math.max(
      document.documentElement.scrollHeight, document.body.scrollHeight)),
  };
}
"""

FINGERPRINT_JS = """
() => ({
  user_agent: navigator.userAgent,
  platform: navigator.platform,
  languages: navigator.languages,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  device_pixel_ratio: window.devicePixelRatio,
  inner: {width: window.innerWidth, height: window.innerHeight},
})
"""


def snap_frames(page, dest: pathlib.Path, frames: int) -> list[str]:
    shas: list[str] = []
    for n in range(1, frames + 1):
        fp = dest / f"frame-{n}.png"
        page.screenshot(path=str(fp), full_page=True)
        shas.append(sha256_file(fp))
        if n < frames:
            page.wait_for_timeout(700)
    return shas


def settle(page, settle_ms: int, wait_selector: str | None = None,
           label: str = "") -> None:
    """Wait for network idle (12s cap -- the SPA subdomains keep long-poll
    style requests open, so idle is best-effort), then the readiness selector
    if one is declared, then the settle delay."""
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:  # noqa: BLE001 - settle delay still applies
        pass
    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=20000)
        except Exception:  # noqa: BLE001 - capture whatever rendered
            print(f"  ~ {label}: readiness selector not seen", file=sys.stderr)
    page.wait_for_timeout(settle_ms)


def write_capture(page, dest: pathlib.Path, cp: dict, vp_name: str,
                  frames: int, shas: list[str], http_status: int | None,
                  consent: str | None) -> dict:
    (dest / "page.html").write_text(page.content())
    links = census(page)
    (dest / "links.json").write_text(json.dumps(links, indent=2))
    resources = resource_census(page)
    (dest / "resources.json").write_text(json.dumps(resources, indent=2))
    regions = page.evaluate(REGION_JS)
    body_len = len(page.eval_on_selector("body", "e=>e.innerText"))
    meta = {
        "checkpoint": cp["id"], "family": cp["family"],
        "priority": cp["priority"].upper(), "viewport": vp_name,
        "requested_url": cp["url"], "final_url": page.url,
        "http_status": http_status,
        "title": page.title(), "body_text_len": body_len,
        "frames": frames, "frame_sha256": shas,
        "frames_identical": len(set(shas)) == 1,
        "link_count": len(links), "resource_count": len(resources),
        "engine": "local-playwright", "nav_fallback": None,
        "consent_action": consent,
        "regions": regions,
    }
    (dest / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def capture_checkpoint(page, cp: dict, vp: dict, out_root: pathlib.Path,
                       settle_ms: int) -> dict:
    dest = out_root / cp["id"] / vp["name"]
    dest.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({"width": vp["width"], "height": vp["height"]})
    resp = page.goto(cp["url"], wait_until="domcontentloaded", timeout=60000)
    settle(page, settle_ms, WAIT_SELECTORS.get(cp["id"]), cp["id"])
    consent = dismiss_consent(page)
    frames = int(vp.get("frames", 3))
    shas = snap_frames(page, dest, frames)
    status = resp.status if resp else None
    meta = write_capture(page, dest, cp, vp["name"], frames, shas, status,
                         consent)
    flag = "=" if meta["frames_identical"] else "~"
    print(f"  ok {cp['id']}/{vp['name']} [{status}] {flag} "
          f"body={meta['body_text_len']} links={meta['link_count']} "
          f"res={meta['resource_count']} -> {page.url}")
    return meta


def capture(site_dir: pathlib.Path, only: set[str] | None,
            settle_ms: int, headed: bool) -> int:
    plan = json.loads((site_dir / "scope" / "source-capture-plan.json").read_text())
    capture_id = plan.get("capture_id", CAPTURE_ID)
    out_root = site_dir / "source-current" / capture_id
    viewport_by_name = {v["name"]: v for v in plan["viewports"]}
    checkpoints = []
    for cp in plan["checkpoints"]:
        if only and cp["id"] not in only:
            continue
        if cp["id"] in INTERACTIVE_IDS or not cp["url"].startswith("http"):
            if only:
                print(f"skipping {cp['id']}: not URL-addressable here")
            continue
        checkpoints.append(cp)
    if not checkpoints:
        print("nothing to capture")
        return 1

    records: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        try:
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=CHROME_UA,
                locale="en-US", timezone_id="Etc/UTC")
            page = ctx.new_page()
            hide_scrollbars(page)
            fingerprint_written = False
            for cp in checkpoints:
                for vp_name in cp["viewports"]:
                    vp = viewport_by_name[vp_name]
                    try:
                        records.append(capture_checkpoint(
                            page, cp, vp, out_root, settle_ms))
                    except Exception as exc:  # noqa: BLE001
                        print(f"  ! {cp['id']}/{vp_name}: {exc}",
                              file=sys.stderr)
                        records.append({
                            "checkpoint": cp["id"], "viewport": vp_name,
                            "engine": "local-playwright",
                            "error": str(exc)[:200]})
                    if not fingerprint_written:
                        fp = page.evaluate(FINGERPRINT_JS)
                        out_root.mkdir(parents=True, exist_ok=True)
                        (out_root / "session-fingerprint.json").write_text(
                            json.dumps(fp, indent=2))
                        fingerprint_written = True
        finally:
            browser.close()

    index_path = out_root / "capture-index.json"
    if only and index_path.is_file():
        fresh = {(r.get("checkpoint"), r.get("viewport")) for r in records}
        previous = json.loads(index_path.read_text()).get("captures", [])
        records = [r for r in previous
                   if (r.get("checkpoint"), r.get("viewport")) not in fresh
                   ] + records
    index = {"schema_version": "ipvanish.capture-index.v1",
             "capture_id": capture_id, "captures": records}
    index_path.write_text(json.dumps(index, indent=2))
    print(f"\nwrote {len(records)} capture records -> {index_path}")
    failures = [r for r in records if "error" in r]
    if failures:
        print(f"{len(failures)} capture unit(s) failed", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-dir", default="materials/ipvanish")
    ap.add_argument("--only", default="", help="comma-separated checkpoint ids")
    ap.add_argument("--settle-ms", type=int, default=6000,
                    help="settle delay after network idle (SPA subdomains "
                         "need a generous default)")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s} or None
    return capture(pathlib.Path(args.site_dir), only, args.settle_ms,
                   args.headed)


if __name__ == "__main__":
    raise SystemExit(main())
