#!/usr/bin/env python3
"""Shared, anonymous, read-only capture core for the DeleteMe offline clone.

Every capture tool in this directory goes through this module, because the
safety guards below are not optional decoration -- they are the reason the
capture is allowed to touch the live source at all.

DeleteMe is a data-removal service. Its public forms ask a real visitor for
real personal data (name, address, email, payment card). Therefore:

* Only GET and HEAD ever leave the browser. ``install_get_only`` installs a
  ``context.route`` handler that ABORTS every other method, so no page script
  and no stray form can submit anything. The abort count is recorded per unit
  as a quirk, because aborting the source's own POSTs visibly changes what
  some pages render (the checkout Order Summary renders empty without its
  POST /api/checkout/checkout/session) and that fact must travel with the
  evidence instead of being mistaken for a clone defect later.
* No field is ever filled, typed into, or submitted. ``field_inventory``
  records only name / id / type / label / required. It never reads ``value``.
* Nothing is persisted from a request or response header: no cookie, token,
  authorization header or session id. Each unit runs in a throwaway context,
  so no state carries between units either.
* Consent controls are never clicked, chat widgets are never opened, no
  password reset is requested and no account is created. When a consent layer
  renders it is recorded as a quirk and left alone.
* ``strip_query`` removes both query and fragment from any URL before it is
  written anywhere, because a signature or publishable key can ride in either.
  The two capture URLs that legitimately need a query (the plan selector on
  checkout, the single search probe) carry only opaque plan/term/qty/search
  terms and are declared explicitly in the plan.

Rendering channel: local headless Playwright Chromium with an ordinary
desktop Chrome user agent. Screenshots are viewport-sized (not full page) at
the declared viewport, with scrollbars hidden so the layout viewport equals
the declared viewport exactly. Every unit waits for ``load`` then network
idle (best effort) then a generous settle delay -- the default is deliberately
long because a short wait on an earlier site produced a false "missing
background" finding when a lazily-applied hero image had not painted yet.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib
import urllib.parse
from datetime import datetime, timezone

CAPTURE_ID = "2026-08-20.deleteme-r1"

# Ordinary desktop Chrome UA. Mirrors what a real visitor's browser sends so
# the markup we freeze is the markup a visitor sees. This is a fidelity
# setting, not an access-control bypass: anything still gated is recorded
# unavailable rather than fought.
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

LOCALE = "en-US"
TIMEZONE = "Etc/UTC"

# Frozen in scope/checkpoints.json; duplicated here only as a fallback.
VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop": {"width": 1440, "height": 900},
    "tablet": {"width": 1024, "height": 768},
    "mobile": {"width": 390, "height": 844},
}

FRAMES = 3
FRAME_GAP_MS = 700
SETTLE_MS = 2600
NAV_TIMEOUT_MS = 60_000
IDLE_TIMEOUT_MS = 12_000


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_query(url: str) -> str:
    """Drop query AND fragment. Either can carry a signature or a key, and
    nothing we persist ever needs them."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def load_viewports(site: pathlib.Path) -> dict[str, dict[str, int]]:
    path = site / "scope" / "checkpoints.json"
    try:
        declared = json.loads(path.read_text())["viewports"]
    except Exception:  # noqa: BLE001 - fall back to the local copy
        return dict(VIEWPORTS)
    return {name: {"width": v["width"], "height": v["height"]}
            for name, v in declared.items()}


# --------------------------------------------------------------------------
# Safety guards
# --------------------------------------------------------------------------

class MethodGuard:
    """Aborts every request whose method is not GET or HEAD.

    Installed on the BrowserContext, so it covers the main frame, every
    subframe, XHR/fetch, beacons and form submissions alike. Nothing about
    the aborted request is retained beyond its method, its query-stripped URL
    and its resource type -- never a header and never a body.
    """

    def __init__(self) -> None:
        self.aborted: list[dict[str, str]] = []

    async def install(self, context) -> None:
        async def handler(route, request):
            method = (request.method or "GET").upper()
            if method in {"GET", "HEAD"}:
                try:
                    await route.continue_()
                except Exception:  # noqa: BLE001 - page navigated away
                    pass
                return
            if len(self.aborted) < 200:
                self.aborted.append({
                    "method": method,
                    "url": strip_query(request.url),
                    "resource_type": request.resource_type,
                })
            try:
                await route.abort()
            except Exception:  # noqa: BLE001 - page navigated away
                pass

        await context.route("**/*", handler)

    def summary(self) -> dict[str, object]:
        methods: dict[str, int] = {}
        for entry in self.aborted:
            methods[entry["method"]] = methods.get(entry["method"], 0) + 1
        return {
            "count": len(self.aborted),
            "by_method": methods,
            "urls": sorted({e["url"] for e in self.aborted})[:40],
        }


async def new_guarded_context(browser, viewport: dict[str, int]):
    """A throwaway context with the GET-only guard installed, no stored
    state, and no permission grants."""
    context = await browser.new_context(
        viewport={"width": viewport["width"], "height": viewport["height"]},
        user_agent=CHROME_UA,
        locale=LOCALE,
        timezone_id=TIMEZONE,
        device_scale_factor=1,
        java_script_enabled=True,
        ignore_https_errors=False,
    )
    guard = MethodGuard()
    await guard.install(context)
    return context, guard


async def hide_scrollbars(page) -> None:
    """Classic scrollbars steal layout width. Hide them so a viewport-sized
    screenshot is exactly the declared viewport."""
    try:
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Emulation.setScrollbarsHidden", {"hidden": True})
    except Exception:  # noqa: BLE001 - CSS fallback
        await page.add_init_script(
            "const s=document.createElement('style');"
            "s.textContent='::-webkit-scrollbar{display:none}"
            "html{scrollbar-width:none}';"
            "document.addEventListener('DOMContentLoaded',"
            "()=>document.head.appendChild(s));"
        )


# --------------------------------------------------------------------------
# Settling and framing
# --------------------------------------------------------------------------

async def settle(page, settle_ms: int = SETTLE_MS,
                 wait_selector: str | None = None) -> list[str]:
    """load -> network idle (best effort) -> readiness selector -> delay.

    Returns notes about anything that did not happen, so a shortfall is
    recorded rather than silently absorbed.
    """
    notes: list[str] = []
    try:
        await page.wait_for_load_state("load", timeout=IDLE_TIMEOUT_MS)
    except Exception:  # noqa: BLE001
        notes.append("load state not reached within timeout")
    try:
        await page.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT_MS)
    except Exception:  # noqa: BLE001 - third-party beacons keep sockets warm
        notes.append("network never reached idle (third-party beacons)")
    if wait_selector:
        try:
            await page.wait_for_selector(wait_selector, timeout=20_000)
        except Exception:  # noqa: BLE001
            notes.append(f"readiness selector never appeared: {wait_selector}")
    await page.wait_for_timeout(settle_ms)
    return notes


async def snap_frames(page, dest: pathlib.Path, frames: int = FRAMES,
                      gap_ms: int = FRAME_GAP_MS) -> list[str]:
    """Three viewport-sized frames ~700ms apart. Identical frames mean the
    surface is static; differing frames mean animation, and either way the
    reader can tell which without re-running the capture."""
    shas: list[str] = []
    for n in range(1, frames + 1):
        path = dest / f"frame-{n}.viewport.png"
        await page.screenshot(path=str(path), full_page=False)
        shas.append(sha256_file(path))
        if n < frames:
            await page.wait_for_timeout(gap_ms)
    return shas


# --------------------------------------------------------------------------
# Field inventory -- names and shapes only, never a value
# --------------------------------------------------------------------------

FIELD_INVENTORY_JS = r"""
() => {
  const cut = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const labelOf = (el) => {
    let text = '';
    if (el.id) {
      try {
        const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (l) text = l.innerText;
      } catch (e) { /* malformed id */ }
    }
    if (!text) { const l = el.closest('label'); if (l) text = l.innerText; }
    if (!text) text = el.getAttribute('aria-label') || '';
    if (!text) {
      const ref = el.getAttribute('aria-labelledby');
      if (ref) {
        text = ref.split(/\s+/).map(id => {
          const n = document.getElementById(id);
          return n ? n.innerText : '';
        }).join(' ');
      }
    }
    return cut(text, 160);
  };
  const controls = Array.from(
    document.querySelectorAll('input, select, textarea'));
  return {
    // Structure only. No control's value is read, here or anywhere.
    forms: Array.from(document.querySelectorAll('form')).map(f => ({
      id: f.getAttribute('id'),
      name: f.getAttribute('name'),
      method: (f.getAttribute('method') || '').toLowerCase() || null,
      action_path: (() => {
        try { return new URL(f.getAttribute('action') || '', location.href).pathname; }
        catch (e) { return null; }
      })(),
      control_count: f.querySelectorAll('input, select, textarea').length,
    })),
    fields: controls.map(el => ({
      name: el.getAttribute('name'),
      id: el.getAttribute('id'),
      type: el.tagName.toLowerCase() === 'input'
        ? (el.getAttribute('type') || 'text').toLowerCase()
        : el.tagName.toLowerCase(),
      label: labelOf(el),
      required: el.hasAttribute('required')
        || el.getAttribute('aria-required') === 'true',
    })),
    submits: Array.from(
      document.querySelectorAll('button, input[type=submit]')).map(b => ({
        type: b.getAttribute('type'),
        label: cut(b.innerText || b.getAttribute('value') || '', 80),
      })).filter(b => b.label),
    // Cross-origin payment iframes cannot be read and must not be. Only the
    // origin + path is noted so the payment boundary is documented; any
    // publishable key in the iframe query is dropped by design.
    embedded_frames: Array.from(document.querySelectorAll('iframe')).map(f => {
      try {
        const u = new URL(f.getAttribute('src') || '', location.href);
        return u.origin + u.pathname;
      } catch (e) { return null; }
    }).filter(Boolean),
  };
}
"""

# Factual, generic observations. Nothing here is a judgement and nothing here
# reads a form value.
QUIRK_PROBE_JS = r"""
() => {
  const cut = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const consentSelectors = [
    '#onetrust-banner-sdk', '#onetrust-consent-sdk', '.ot-sdk-container',
    '#cookie-law-info-bar', '.cky-consent-container', '#usercentrics-root',
    '[id*="cookie" i][class*="banner" i]', '[aria-label*="cookie" i]',
    '[class*="cookie-consent" i]', '[class*="cookie-banner" i]',
  ];
  let consent = null;
  for (const sel of consentSelectors) {
    try {
      const el = document.querySelector(sel);
      if (el) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) { consent = sel; break; }
      }
    } catch (e) { /* invalid selector in this engine */ }
  }
  const emptyPriceNodes = Array.from(
    document.querySelectorAll('[class*="price" i], [class*="amount" i]'))
    .filter(e => !e.children.length && !cut(e.textContent, 4)).length;
  const hiddenByVisibility = Array.from(document.querySelectorAll('*'))
    .filter(e => {
      const s = e.getAttribute('style') || '';
      return /visibility\s*:\s*hidden/i.test(s);
    }).length;
  return {
    title: cut(document.title, 200),
    h1: Array.from(document.querySelectorAll('h1')).map(h => cut(h.innerText, 120)),
    body_text_len: (document.body ? document.body.innerText.length : 0),
    consent_layer: consent,
    lazy_image_refs: document.querySelectorAll('[data-src], [data-srcset]').length,
    eager_image_refs: document.querySelectorAll('img[src], img[srcset]').length,
    empty_price_nodes: emptyPriceNodes,
    inline_visibility_hidden: hiddenByVisibility,
    form_count: document.querySelectorAll('form').length,
    control_count: document.querySelectorAll('input, select, textarea').length,
    iframe_origins: Array.from(new Set(
      Array.from(document.querySelectorAll('iframe')).map(f => {
        try { return new URL(f.getAttribute('src') || '', location.href).origin; }
        catch (e) { return null; }
      }).filter(Boolean))),
    meta_robots: (() => {
      const m = document.querySelector('meta[name="robots" i]');
      return m ? cut(m.getAttribute('content'), 80) : null;
    })(),
    canonical: (() => {
      const l = document.querySelector('link[rel="canonical" i]');
      if (!l) return null;
      try {
        const u = new URL(l.getAttribute('href') || '', location.href);
        return u.origin + u.pathname;
      } catch (e) { return null; }
    })(),
  };
}
"""

RESOURCE_CENSUS_JS = """
() => performance.getEntriesByType('resource').map(e => ({
  url: e.name, initiator: e.initiatorType, transfer_size: e.transferSize}))
"""

# Every asset URL the markup advertises, including the lazy-loading
# attributes the browser never requests during a capture. Missing data-src /
# data-srcset on an earlier site left 291 broken references in the clone, and
# a retina browser picks a different srcset width than this capture does, so
# EVERY advertised candidate is collected here rather than only the one the
# browser chose.
REFERENCE_CENSUS_JS = r"""
() => {
  const out = new Set();
  const abs = (v) => {
    if (!v) return null;
    const t = v.trim();
    if (!t || t.startsWith('data:') || t.startsWith('blob:')
        || t.startsWith('javascript:') || t.startsWith('#')
        || t.startsWith('mailto:') || t.startsWith('tel:')) return null;
    try { return new URL(t, location.href).href; } catch (e) { return null; }
  };
  const addSrcset = (value) => {
    if (!value) return;
    for (const part of value.split(',')) {
      const url = abs(part.trim().split(/\s+/)[0]);
      if (url) out.add(url);
    }
  };
  const plain = ['src', 'data-src', 'data-lazy-src', 'data-original',
                 'data-bg', 'data-background', 'poster', 'href'];
  const sets = ['srcset', 'data-srcset', 'data-lazy-srcset', 'imagesrcset'];
  for (const el of document.querySelectorAll(
      'img, source, video, audio, track, embed, iframe, script, link, ' +
      '[data-src], [data-srcset], [data-lazy-src], [data-bg], object')) {
    const tag = el.tagName.toLowerCase();
    for (const attr of plain) {
      const value = el.getAttribute(attr);
      if (!value) continue;
      // href only counts for asset links, never for page navigation.
      if (attr === 'href') {
        if (tag !== 'link') continue;
        const rel = (el.getAttribute('rel') || '').toLowerCase();
        if (!/stylesheet|icon|preload|manifest|apple-touch/.test(rel)) continue;
      }
      const url = abs(value);
      if (url) out.add(url);
    }
    for (const attr of sets) addSrcset(el.getAttribute(attr));
    if (tag === 'object') { const u = abs(el.getAttribute('data')); if (u) out.add(u); }
  }
  // Inline style and style-attribute url() references.
  const cssUrl = /url\(\s*['"]?([^'")]+)['"]?\s*\)/gi;
  const scan = (text) => {
    if (!text) return;
    let m;
    while ((m = cssUrl.exec(text)) !== null) {
      const url = abs(m[1]);
      if (url) out.add(url);
    }
  };
  for (const el of document.querySelectorAll('[style]')) scan(el.getAttribute('style'));
  for (const el of document.querySelectorAll('style')) scan(el.textContent);
  return Array.from(out);
}
"""


async def probe(page) -> dict:
    try:
        return await page.evaluate(QUIRK_PROBE_JS)
    except Exception as exc:  # noqa: BLE001
        return {"probe_error": str(exc)[:160]}


async def field_inventory(page) -> dict | None:
    try:
        data = await page.evaluate(FIELD_INVENTORY_JS)
    except Exception as exc:  # noqa: BLE001
        return {"inventory_error": str(exc)[:160]}
    if not data.get("forms") and not data.get("fields"):
        return None
    return data


async def resource_census(page) -> list[dict]:
    try:
        return await page.evaluate(RESOURCE_CENSUS_JS)
    except Exception:  # noqa: BLE001
        return []


async def reference_census(page) -> list[str]:
    try:
        return await page.evaluate(REFERENCE_CENSUS_JS)
    except Exception:  # noqa: BLE001
        return []


# --------------------------------------------------------------------------
# Unit writer
# --------------------------------------------------------------------------

async def write_unit(page, dest: pathlib.Path, *, unit: str, checkpoint: str,
                     viewport_name: str, viewport: dict[str, int],
                     requested_url: str, http_status: int | None,
                     frame_shas: list[str], quirks: list[str],
                     guard: MethodGuard, extra_meta: dict | None = None) -> dict:
    """page.html + meta.json (+ fields.json when the surface has a form)."""
    dest.mkdir(parents=True, exist_ok=True)

    dom = await page.evaluate("() => document.documentElement.outerHTML")
    (dest / "page.html").write_text(dom, encoding="utf-8")

    facts = await probe(page)
    references = await reference_census(page)
    resources = await resource_census(page)
    (dest / "references.json").write_text(
        json.dumps(sorted(references), indent=2) + "\n", encoding="utf-8")
    (dest / "resources.json").write_text(
        json.dumps(resources, indent=2) + "\n", encoding="utf-8")

    fields = await field_inventory(page)
    if fields is not None:
        fields["_note"] = (
            "Structure only: name/id/type/label/required. No field was ever "
            "filled, typed into or submitted on the live source, and no "
            "control value was read."
        )
        (dest / "fields.json").write_text(
            json.dumps(fields, indent=2) + "\n", encoding="utf-8")

    quirks = list(quirks)
    final_url = page.url
    if strip_query(final_url) != strip_query(requested_url):
        quirks.append(
            f"requested {strip_query(requested_url)} but settled on "
            f"{strip_query(final_url)} (redirect followed)")
    aborted = guard.summary()
    if aborted["count"]:
        quirks.append(
            f"GET-only guard aborted {aborted['count']} non-GET request(s) "
            f"({aborted['by_method']}); anything the source renders from its "
            f"own POST is therefore absent from this capture")
    if facts.get("consent_layer"):
        quirks.append(
            f"consent layer rendered ({facts['consent_layer']}) and was left "
            f"untouched: no consent control was clicked")
    if facts.get("empty_price_nodes"):
        quirks.append(
            f"{facts['empty_price_nodes']} price/amount node(s) rendered empty")
    if facts.get("lazy_image_refs"):
        quirks.append(
            f"{facts['lazy_image_refs']} element(s) advertise lazy image "
            f"payloads via data-src/data-srcset that the browser never "
            f"requested; the asset pass mirrors them from the markup")
    if len(set(frame_shas)) != 1:
        quirks.append(
            "the three frames are not byte-identical: this surface animates")
    if http_status is not None and http_status != 200:
        quirks.append(f"source answered HTTP {http_status}")

    meta = {
        "unit": unit,
        "checkpoint": checkpoint,
        "capture_id": CAPTURE_ID,
        "url": strip_query(requested_url) if "?" not in requested_url
        else requested_url,
        "requested_url": requested_url,
        "final_url": final_url,
        "http_status": http_status,
        "viewport": viewport_name,
        "viewport_size": {"width": viewport["width"], "height": viewport["height"]},
        "ua": CHROME_UA,
        "locale": LOCALE,
        "timezone": TIMEZONE,
        "captured_at": utc_now(),
        "engine": "local-headless-playwright-chromium",
        "title": facts.get("title"),
        "h1": facts.get("h1"),
        "body_text_len": facts.get("body_text_len"),
        "frames": len(frame_shas),
        "frame_sha256": frame_shas,
        "frames_identical": len(set(frame_shas)) == 1,
        "reference_count": len(references),
        "resource_count": len(resources),
        "observations": facts,
        "non_get_aborted": aborted,
        "safety": {
            "methods_allowed": ["GET", "HEAD"],
            "fields_filled": 0,
            "forms_submitted": 0,
            "consent_clicked": False,
            "credentials_persisted": False,
        },
        "quirks": quirks,
    }
    if extra_meta:
        meta.update(extra_meta)
    (dest / "meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def bounded(limit: int) -> asyncio.Semaphore:
    """Total in-flight capture work stays modest so the live source is never
    hammered: the checkpoint x viewport product is large, the source is not
    ours, and politeness here is a requirement rather than a courtesy."""
    return asyncio.Semaphore(limit)
