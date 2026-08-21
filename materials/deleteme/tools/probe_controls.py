#!/usr/bin/env python3
"""Read-only discovery of the interaction controls capture_states.py drives.

The plan grid filters client-side with UIkit filter controls
(`uk-filter-control`), and the checkout page has a promo-code disclosure that
expands without a network request. Neither selector is guessable, and
guessing one would mean capturing a state that does not exist. This tool
prints what is actually in the DOM so the selectors in capture_states.py are
observed rather than invented.

It navigates and reads. It clicks nothing, fills nothing and submits nothing;
the GET-only guard is installed exactly as in the capture passes.

Usage:
    python materials/deleteme/tools/probe_controls.py --url <url>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from playwright.async_api import async_playwright  # noqa: E402

import capture_common as cc  # noqa: E402

PROBE_JS = r"""
() => {
  const cut = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const describe = (el) => ({
    tag: el.tagName.toLowerCase(),
    text: cut(el.innerText, 60),
    cls: cut(el.getAttribute('class'), 120),
    id: el.getAttribute('id'),
    uk_filter_control: el.getAttribute('uk-filter-control'),
    data_uk_filter_control: el.getAttribute('data-uk-filter-control'),
    uk_toggle: el.getAttribute('uk-toggle') || el.getAttribute('data-uk-toggle'),
    aria_expanded: el.getAttribute('aria-expanded'),
    parent_cls: cut(el.parentElement && el.parentElement.getAttribute('class'), 120),
    grandparent_cls: cut(
      el.parentElement && el.parentElement.parentElement
        && el.parentElement.parentElement.getAttribute('class'), 120),
  });
  const filters = Array.from(document.querySelectorAll(
    '[uk-filter-control], [data-uk-filter-control]')).map(describe);
  const filterRoots = Array.from(document.querySelectorAll(
    '[uk-filter], [data-uk-filter]')).map(el => ({
      cls: cut(el.getAttribute('class'), 140),
      spec: el.getAttribute('uk-filter') || el.getAttribute('data-uk-filter'),
      item_count: el.querySelectorAll('[class*="uk-"], li').length,
    }));
  const toggles = Array.from(document.querySelectorAll(
    '[uk-toggle], [data-uk-toggle], [aria-expanded]')).map(describe);
  const promo = Array.from(document.querySelectorAll('button, a, [role=button], summary'))
    .filter(el => /promo|coupon|discount|code/i.test(el.innerText || ''))
    .map(describe);
  const tabby = Array.from(document.querySelectorAll('button, a, [role=tab], li'))
    .filter(el => /^(1 year|2 years|single|couple|family)$/i.test(
      cut(el.innerText, 20)))
    .map(describe);
  return {title: cut(document.title, 160), h1: cut(
    (document.querySelector('h1') || {}).innerText, 160),
    filter_roots: filterRoots, filter_controls: filters,
    term_or_size_labels: tabby,
    toggles: toggles.slice(0, 40), promo_candidates: promo};
}
"""


# Every match for one selector, with the visibility and ancestry needed to
# tell a live control apart from a hidden duplicate. The plan grid ships more
# than one filter root (a US grid and an international grid), so "the first
# match" and "the control a visitor can click" are not the same element.
MATCH_JS = r"""
(selector) => {
  const cut = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  return Array.from(document.querySelectorAll(selector)).map((el, i) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    const chain = [];
    let node = el;
    for (let d = 0; d < 8 && node; d++) {
      chain.push(node.tagName.toLowerCase()
        + (node.getAttribute('class') ? '.' + cut(node.getAttribute('class'), 60).split(' ').join('.') : ''));
      node = node.parentElement;
    }
    let hiddenAncestor = null;
    node = el;
    while (node && node !== document.body) {
      const cs = getComputedStyle(node);
      if (cs.display === 'none' || cs.visibility === 'hidden') {
        hiddenAncestor = node.tagName.toLowerCase() + '.'
          + cut(node.getAttribute('class'), 80);
        break;
      }
      node = node.parentElement;
    }
    return {
      index: i, text: cut(el.innerText, 40),
      rect: {w: Math.round(r.width), h: Math.round(r.height),
             top: Math.round(r.top + window.scrollY)},
      display: s.display, visibility: s.visibility,
      anchor_count: el.querySelectorAll('a').length,
      hidden_ancestor: hiddenAncestor,
      chain: chain,
    };
  });
}
"""


async def run_matches(url: str, selector: str, settle_ms: int) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context, _guard = await cc.new_guarded_context(
                browser, cc.VIEWPORTS["desktop"])
            page = await context.new_page()
            await page.goto(url, wait_until="load", timeout=cc.NAV_TIMEOUT_MS)
            await cc.settle(page, settle_ms)
            print(json.dumps(await page.evaluate(MATCH_JS, selector), indent=2))
        finally:
            await browser.close()
    return 0


async def run(url: str, settle_ms: int, wait_selector: str | None) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context, guard = await cc.new_guarded_context(
                browser, cc.VIEWPORTS["desktop"])
            page = await context.new_page()
            response = await page.goto(url, wait_until="load",
                                       timeout=cc.NAV_TIMEOUT_MS)
            await cc.settle(page, settle_ms, wait_selector)
            result = await page.evaluate(PROBE_JS)
            result["http_status"] = response.status if response else None
            result["final_url"] = page.url
            result["non_get_aborted"] = guard.summary()
            print(json.dumps(result, indent=2))
        finally:
            await browser.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--settle-ms", type=int, default=4500)
    parser.add_argument("--wait-selector", default=None)
    parser.add_argument("--selector", default=None,
                        help="report every match for this CSS selector, with "
                             "visibility and ancestry")
    args = parser.parse_args()
    if args.selector:
        return asyncio.run(run_matches(args.url, args.selector,
                                       args.settle_ms))
    return asyncio.run(run(args.url, args.settle_ms, args.wait_selector))


if __name__ == "__main__":
    raise SystemExit(main())
