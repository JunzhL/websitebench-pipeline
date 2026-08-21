#!/usr/bin/env python3
"""Capture deterministic candidate viewports for the acceptance review packet."""

from __future__ import annotations

import argparse
import pathlib

from playwright.sync_api import sync_playwright

VIEWPORTS = {
    "desktop": (1440, 900),
    "tablet": (1024, 768),
    "mobile": (390, 844),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as driver:
        browser = driver.chromium.launch(
            headless=True,
            args=["--font-render-hinting=slight", "--disable-webrtc"],
        )
        try:
            for name, (width, height) in VIEWPORTS.items():
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                    locale="en-US",
                    timezone_id="Etc/UTC",
                )
                page = context.new_page()
                page.goto(args.base_url.rstrip("/") + "/", wait_until="networkidle")
                page.wait_for_timeout(400)
                page.screenshot(path=str(args.out / f"home-{name}.png"))
                context.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
