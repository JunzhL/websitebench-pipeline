#!/usr/bin/env python3
"""Capture every URL-addressable DeleteMe checkpoint, anonymously and read-only.

Writes, for each (checkpoint, viewport) unit, into
source-current/<capture-id>/<unit>/<viewport>/:

    page.html               document.documentElement.outerHTML after settle
    frame-1..3.viewport.png three viewport-sized frames ~700ms apart
    meta.json               url, final url, status, viewport, ua, locale,
                            timezone, captured_at, quirks
    fields.json             field inventory, where the surface has a form
    references.json         every asset URL the markup advertises
    resources.json          what the browser actually requested

Interaction-dependent states (the plan-grid filter tabs, the checkout promo
panel) belong to capture_states.py, which writes the same layout.

Safety: see capture_common. GET/HEAD only, enforced by an aborting route
handler; no field is ever filled or submitted; no consent control is clicked;
no cookie, token or header is persisted.

Usage:
    python materials/deleteme/tools/capture_source.py \
        --site-dir materials/deleteme [--only home,plans] [--concurrency 6]
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


async def capture_unit(browser, unit: dict, viewports: dict,
                       out_root: pathlib.Path,
                       semaphore: asyncio.Semaphore) -> dict:
    name = f"{unit['unit']}/{unit['viewport']}"
    viewport = viewports[unit["viewport"]]
    async with semaphore:
        context, guard = await cc.new_guarded_context(browser, viewport)
        try:
            page = await context.new_page()
            await cc.hide_scrollbars(page)
            console_errors: list[str] = []
            page.on("console", lambda m: (
                console_errors.append(m.text[:160])
                if m.type == "error" and len(console_errors) < 25 else None))

            status: int | None = None
            quirks: list[str] = []
            try:
                response = await page.goto(unit["url"], wait_until="load",
                                           timeout=cc.NAV_TIMEOUT_MS)
                status = response.status if response else None
                # The 404 probe is expected to travel through a 301 to the
                # trailing-slash form; record the chain rather than flatten it.
                if response is not None:
                    chain = []
                    node = response.request.redirected_from
                    while node is not None and len(chain) < 8:
                        chain.append(cc.strip_query(node.url))
                        node = node.redirected_from
                    if chain:
                        quirks.append(
                            "redirect chain before the captured document: "
                            + " -> ".join(reversed(chain)))
            except Exception as exc:  # noqa: BLE001
                quirks.append(f"navigation raised: {str(exc)[:160]}")

            settle_notes = await cc.settle(
                page,
                settle_ms=unit.get("settle_ms") or cc.SETTLE_MS,
                wait_selector=unit.get("wait_selector"),
            )
            quirks.extend(settle_notes)

            # Lazy images below the fold only paint once scrolled. Scroll to
            # the bottom and back so the markup settles into its real state,
            # then re-settle. Nothing is clicked on the way.
            try:
                await page.evaluate(
                    "async () => {"
                    " const step = window.innerHeight;"
                    " const end = document.body ? document.body.scrollHeight : 0;"
                    " for (let y = 0; y < end; y += step) {"
                    "   window.scrollTo(0, y);"
                    "   await new Promise(r => setTimeout(r, 90));"
                    " }"
                    " window.scrollTo(0, 0);"
                    "}")
                await page.wait_for_timeout(1200)
            except Exception:  # noqa: BLE001 - not every surface scrolls
                pass

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
                    "capture_pass": "navigable",
                    "console_errors": console_errors,
                },
            )
            print(f"  ok {name} [{status}] "
                  f"body={meta.get('body_text_len')} "
                  f"refs={meta.get('reference_count')} "
                  f"quirks={len(meta.get('quirks', []))}", flush=True)
            return meta
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {name}: {str(exc)[:200]}", file=sys.stderr, flush=True)
            return {"unit": unit["unit"], "checkpoint": unit["checkpoint"],
                    "viewport": unit["viewport"], "capture_pass": "navigable",
                    "error": str(exc)[:300]}
        finally:
            await context.close()


async def run(site: pathlib.Path, only: set[str] | None,
              concurrency: int) -> int:
    navigable, _interactive, _skipped = cp.plan_units(site)
    if only:
        navigable = [u for u in navigable
                     if u["route_id"] in only or u["unit"] in only]
    if not navigable:
        print("nothing to capture")
        return 1
    _checkpoints, viewports = cp.load_checkpoints(site)
    out_root = site / "source-current" / cc.CAPTURE_ID
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"navigable units: {len(navigable)} "
          f"(concurrency {concurrency})", flush=True)

    semaphore = cc.bounded(concurrency)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            results = await asyncio.gather(*[
                capture_unit(browser, unit, viewports, out_root, semaphore)
                for unit in navigable])
        finally:
            await browser.close()

    records_path = out_root / "_pass-navigable.json"
    records_path.write_text(
        json.dumps({"capture_id": cc.CAPTURE_ID, "records": results},
                   indent=2) + "\n", encoding="utf-8")
    failures = [r for r in results if "error" in r]
    print(f"\nwrote {len(results)} navigable unit(s) -> {records_path}")
    if failures:
        print(f"{len(failures)} unit(s) FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure['unit']}/{failure['viewport']}: "
                  f"{failure['error']}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", default="materials/deleteme")
    parser.add_argument("--only", default="",
                        help="comma-separated route ids or unit names")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="max units in flight; keep modest (<=6)")
    args = parser.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    concurrency = max(1, min(6, args.concurrency))
    return asyncio.run(run(pathlib.Path(args.site_dir).resolve(), only,
                           concurrency))


if __name__ == "__main__":
    raise SystemExit(main())
