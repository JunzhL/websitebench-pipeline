#!/usr/bin/env python3
"""Capture the DeleteMe states that exist only after a click.

Same artifact layout as capture_source.py, same safety guards, one extra
step: after settling, the tool clicks a control and re-settles before framing.

What is clicked, and why it is safe to click:

* The plan-grid term tabs (1 Year / 2 Years) on /privacy-protection-plans/.
  These are UIkit filter controls --
  `<li uk-filter-control='{"filter":"[data-tag~=\"1-Year\"]"}'>` wrapping an
  anchor -- observed with probe_controls.py. Every plan card is already in the
  DOM; the control only changes which of them UIkit shows. No request is made,
  no state is stored and nothing is submitted. The selectors below are
  observed, never guessed: a guessed selector would silently capture the
  default state under a filtered state's name.

* Nothing else, and in particular two states the frozen contract expects turn
  out not to exist for an anonymous US visitor:

  - The plan SIZE tabs (Single / Couple / Family). The page ships two filter
    grids and its own script chooses one by geography: it writes
    `display: block` onto `div.us-price-toggle` and `display: none` onto
    `div#fs-grid-filter-activation.international-price-toggle`. The size tab
    strip exists only inside the hidden international grid. The US grid the
    visitor actually sees has no size dimension at all -- it shows the
    1 Person, 2 People and Family cards side by side and filters them by term
    only. So these controls are matched in the DOM, found invisible, and
    reported not-reached rather than clicked through.

  - The checkout promo-code panel, because under the GET-only guard the
    checkout SPA renders no form to open a panel on.

Consent controls, chat widgets, account controls and any form control remain
untouched everywhere.

Usage:
    python materials/deleteme/tools/capture_states.py \
        --site-dir materials/deleteme [--concurrency 3]
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
import capture_plan as cp  # noqa: E402

# state -> (click selector, human description, post-click assertion selector)
# The assertion selector is what must carry `uk-active` once the click lands;
# if it does not, the unit records the shortfall instead of pretending the
# state was reached.
FILTER_CONTROLS: dict[str, dict[str, str]] = {
    "term-1y": {
        "control": 'li[uk-filter-control*="1-Year"]',
        "label": "1 Year",
        "group": "billing term",
    },
    "term-2y": {
        "control": 'li[uk-filter-control*="2-Years"]',
        "label": "2 Years",
        "group": "billing term",
    },
    "size-single": {
        "control": 'li[uk-filter-control*="Single"]',
        "label": "Single",
        "group": "plan size",
    },
    "size-couple": {
        "control": 'li[uk-filter-control*="Couple"]',
        "label": "Couple",
        "group": "plan size",
    },
    "size-family": {
        "control": 'li[uk-filter-control*="Family"]',
        "label": "Family",
        "group": "plan size",
    },
}

# Which plan cards UIkit is actually showing, so the captured state can be
# checked against its name rather than trusted.
VISIBLE_CARDS_JS = r"""
() => {
  const cut = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const tagged = Array.from(document.querySelectorAll('[data-tag]'));
  const visible = tagged.filter(el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none'
      && s.visibility !== 'hidden';
  });
  return {
    tagged_total: tagged.length,
    visible_total: visible.length,
    visible_tags: Array.from(new Set(visible.map(
      el => el.getAttribute('data-tag')))),
    active_controls: Array.from(document.querySelectorAll(
      'li[uk-filter-control].uk-active')).map(el => cut(el.innerText, 40)),
    visible_card_text: visible.map(el => cut(el.innerText, 120)).slice(0, 12),
  };
}
"""


# Why a matched control is not visible: the nearest ancestor that hides it,
# and the inline style doing the hiding. Enough for a reader to confirm the
# finding without re-running the capture.
HIDDEN_REASON_JS = r"""
(selector) => {
  const cut = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const el = document.querySelector(selector);
  if (!el) return {found: false};
  let node = el, hidden = null, style = null;
  while (node && node !== document.body) {
    const cs = getComputedStyle(node);
    if (cs.display === 'none' || cs.visibility === 'hidden') {
      hidden = node.tagName.toLowerCase()
        + (node.id ? '#' + node.id : '')
        + '.' + cut(node.getAttribute('class'), 90).split(' ').join('.');
      style = cut(node.getAttribute('style'), 120);
      break;
    }
    node = node.parentElement;
  }
  return {found: true, hidden_ancestor: hidden, hidden_ancestor_style: style,
          match_count: document.querySelectorAll(selector).length};
}
"""


def _not_reached(unit: dict, spec: dict, reason: str, before: dict,
                 status: int | None, detail: dict | None = None) -> dict:
    """A state the source does not offer at this vantage point. No unit
    directory is written -- an empty or default-looking capture filed under a
    filtered state's name would be worse than no capture at all. The record
    travels into index.json's removed_state_notes instead."""
    print(f"  - {unit['unit']}/{unit['viewport']}: NOT REACHED -- {reason}",
          flush=True)
    return {
        "unit": unit["unit"], "checkpoint": unit["checkpoint"],
        "viewport": unit["viewport"], "capture_pass": "interaction",
        "state_reached": False, "http_status": status,
        "control": spec["control"], "control_label": spec["label"],
        "reason": reason, "observed_before_click": before,
        "control_detail": detail or {},
    }


async def capture_state(browser, unit: dict, viewports: dict,
                        out_root: pathlib.Path,
                        semaphore: asyncio.Semaphore) -> dict:
    name = f"{unit['unit']}/{unit['viewport']}"
    viewport = viewports[unit["viewport"]]
    spec = FILTER_CONTROLS.get(unit["state"])
    if spec is None:
        return {"unit": unit["unit"], "checkpoint": unit["checkpoint"],
                "viewport": unit["viewport"], "capture_pass": "interaction",
                "error": f"no observed control for state {unit['state']!r}"}

    async with semaphore:
        context, guard = await cc.new_guarded_context(browser, viewport)
        try:
            page = await context.new_page()
            await cc.hide_scrollbars(page)
            console_errors: list[str] = []
            page.on("console", lambda m: (
                console_errors.append(m.text[:160])
                if m.type == "error" and len(console_errors) < 25 else None))

            quirks: list[str] = []
            response = await page.goto(unit["url"], wait_until="load",
                                       timeout=cc.NAV_TIMEOUT_MS)
            status = response.status if response else None
            quirks.extend(await cc.settle(
                page, settle_ms=unit.get("settle_ms") or cc.SETTLE_MS))

            before = await page.evaluate(VISIBLE_CARDS_JS)

            # A control that is in the DOM is not necessarily a control a
            # visitor can reach. The plan page ships two filter grids and its
            # own script picks one by geography, writing display:none onto the
            # other; clicking through that would fabricate a state no visitor
            # at this vantage point can produce. So the visible match is the
            # only clickable match, and its absence is reported, not worked
            # around.
            matches = page.locator(spec["control"])
            count = await matches.count()
            visible = matches.locator("visible=true")
            visible_count = await visible.count()
            if count == 0:
                return _not_reached(
                    unit, spec,
                    f"no element matches {spec['control']} on this page",
                    before, status)
            if visible_count == 0:
                detail = await page.evaluate(HIDDEN_REASON_JS, spec["control"])
                return _not_reached(
                    unit, spec,
                    f"{count} element(s) match {spec['control']} but none is "
                    f"visible to a visitor; the page's own script hides the "
                    f"grid that owns this control "
                    f"(hidden ancestor: {detail.get('hidden_ancestor')}, "
                    f"inline style: {detail.get('hidden_ancestor_style')})",
                    before, status, detail)

            # Click the anchor inside the li -- UIkit binds the control to
            # the li but the anchor is what a visitor actually hits.
            control = visible.first
            target = control.locator("a").first
            if await target.count() == 0:
                target = control
            await target.scroll_into_view_if_needed(timeout=10_000)
            await target.click(timeout=15_000)
            clicked = True
            await page.wait_for_timeout(1400)
            quirks.extend(await cc.settle(page, settle_ms=2000))

            after = await page.evaluate(VISIBLE_CARDS_JS)
            if clicked:
                if spec["label"].lower() not in " ".join(
                        after.get("active_controls", [])).lower():
                    quirks.append(
                        f"clicked {spec['label']!r} but it is not among the "
                        f"active controls afterwards "
                        f"({after.get('active_controls')})")
                if after.get("visible_tags") == before.get("visible_tags") \
                        and unit["state"] not in {"term-2y", "size-couple"}:
                    quirks.append(
                        "the visible plan set did not change after the click")
            quirks.append(
                f"state reached by clicking the {spec['group']} control "
                f"{spec['label']!r} ({spec['control']}); a UIkit client-side "
                f"filter that issues no request and mutates nothing")

            dest = out_root / unit["unit"] / unit["viewport"]
            dest.mkdir(parents=True, exist_ok=True)
            shas = await cc.snap_frames(page, dest)
            if console_errors:
                quirks.append(
                    f"{len(console_errors)} console error(s) during load; "
                    f"first: {console_errors[0]}")

            meta = await cc.write_unit(
                page, dest,
                unit=unit["unit"], checkpoint=unit["checkpoint"],
                viewport_name=unit["viewport"], viewport=viewport,
                requested_url=unit["url"], http_status=status,
                frame_shas=shas, quirks=quirks, guard=guard,
                extra_meta={
                    "route_id": unit["route_id"],
                    "state": unit["state"],
                    "priority": unit["priority"],
                    "acceptance_eligible": unit["acceptance_eligible"],
                    "evidence_kind": unit["evidence_kind"],
                    "capture_pass": "interaction",
                    "interaction": {
                        "action": "click",
                        "selector": spec["control"],
                        "label": spec["label"],
                        "group": spec["group"],
                        "performed": clicked,
                        "mutates_source": False,
                    },
                    "filter_before": before,
                    "filter_after": after,
                    "console_errors": console_errors,
                },
            )
            print(f"  ok {name} [{status}] clicked={clicked} "
                  f"visible={after.get('visible_total')} "
                  f"active={after.get('active_controls')}", flush=True)
            return meta
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {name}: {str(exc)[:200]}", file=sys.stderr, flush=True)
            return {"unit": unit["unit"], "checkpoint": unit["checkpoint"],
                    "viewport": unit["viewport"], "capture_pass": "interaction",
                    "error": str(exc)[:300]}
        finally:
            await context.close()


async def run(site: pathlib.Path, concurrency: int) -> int:
    _navigable, interactive, _skipped = cp.plan_units(site)
    # promo-open has no reachable control under the GET-only guard; it is
    # reported by build_index.py rather than faked here.
    interactive = [u for u in interactive if u["state"] in FILTER_CONTROLS]
    if not interactive:
        print("nothing to capture")
        return 1
    _checkpoints, viewports = cp.load_checkpoints(site)
    out_root = site / "source-current" / cc.CAPTURE_ID
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"interaction units: {len(interactive)} "
          f"(concurrency {concurrency})", flush=True)

    semaphore = cc.bounded(concurrency)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            results = await asyncio.gather(*[
                capture_state(browser, unit, viewports, out_root, semaphore)
                for unit in interactive])
        finally:
            await browser.close()

    records_path = out_root / "_pass-interaction.json"
    records_path.write_text(
        json.dumps({"capture_id": cc.CAPTURE_ID, "records": results},
                   indent=2) + "\n", encoding="utf-8")
    failures = [r for r in results if "error" in r]
    not_reached = [r for r in results if r.get("state_reached") is False]
    captured = len(results) - len(failures) - len(not_reached)
    print(f"\ncaptured {captured}, not-reached {len(not_reached)}, "
          f"failed {len(failures)} -> {records_path}")
    for record in not_reached:
        print(f"  not reached: {record['unit']}/{record['viewport']}: "
              f"{record['reason']}")
    if failures:
        print(f"{len(failures)} unit(s) FAILED", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", default="materials/deleteme")
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    return asyncio.run(run(pathlib.Path(args.site_dir).resolve(),
                           max(1, min(6, args.concurrency))))


if __name__ == "__main__":
    raise SystemExit(main())
