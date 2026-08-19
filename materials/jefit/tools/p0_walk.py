#!/usr/bin/env python3
"""Real-click walk of task 539 against the clone (adapted from the reviewer's
reference harness). Playwright clicks respect pointer-events and disabled
state, so completing here is evidence a human can complete the journey — not
merely that the API accepts POSTs.

Usage: python3 tools/p0_walk.py <out-dir>
"""
from __future__ import annotations

import os
import pathlib
import signal
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

SITE = pathlib.Path(__file__).resolve().parents[1]
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/p0-walk")
OUT.mkdir(parents=True, exist_ok=True)

EMAIL = "p0.walker@example.invalid"
USERNAME = "p0walker"
PASSWORD = "Synthetic-Pass-0819!"


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def main() -> int:
    port = free_port()
    data = OUT / "data"
    data.mkdir(exist_ok=True)
    env = dict(os.environ, DATA_DIR=str(data), SEED="1", TZ="Etc/UTC")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
            "--port", str(port), "--log-level", "warning",
        ],
        cwd=SITE / "clone",
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    offsite: list[str] = []
    failures: list[str] = []
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{base}/healthz", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                timezone_id="Etc/UTC",
            )
            page = context.new_page()
            page.on(
                "request",
                lambda r: offsite.append(r.url)
                if "127.0.0.1" not in r.url and not r.url.startswith("data:")
                else None,
            )

            def note(label: str, extra: str = "") -> None:
                where = page.url.replace(base, "") or "/"
                print(f"{label}: {where} {extra}".rstrip(), flush=True)

            def accept_cookies() -> None:
                loc = page.get_by_role("button", name="Accept")
                if loc.count() and loc.first.is_visible():
                    loc.first.click()
                    page.wait_for_timeout(250)

            def question() -> str:
                return page.evaluate(
                    """() => {
                      const vis = e => e.offsetParent !== null;
                      const all = Array.from(
                        document.querySelectorAll('p,h1,h2,h3,span,legend')
                      ).filter(vis).map(e => e.textContent.trim());
                      return all.find(t => t.length > 8 && t.endsWith('?'))
                        || all.find(t => t.length > 12) || '';
                    }"""
                )[:52]

            page.goto(f"{base}/", wait_until="load")
            page.wait_for_timeout(600)
            accept_cookies()
            note("01 entry")

            page.get_by_role("link", name="Sign up").first.click()
            page.wait_for_timeout(700)
            accept_cookies()
            note("02 signup entry", f"| q={question()!r}")

            def fingerprint() -> str:
                # Identity of the rendered panel: comparing text is how the
                # walk tells "auto-advanced" from "still on this panel".
                return page.evaluate(
                    """() => {
                      const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_COMMENT
                      );
                      let start = null, end = null, node;
                      while ((node = walker.nextNode())) {
                        if (node.nodeValue === 'jefit-signup-slot') start = node;
                        if (node.nodeValue === '/jefit-signup-slot') end = node;
                      }
                      if (!start || !end) return 'NO-SLOT';
                      const range = document.createRange();
                      range.setStartAfter(start);
                      range.setEndBefore(end);
                      return range.toString().replace(/\\s+/g, ' ').trim().slice(0, 300);
                    }"""
                )

            for index in range(1, 26):
                if "/signup/results" in page.url or "/signup/register" in page.url:
                    break
                if "Analyzing your answers" in page.inner_text("body"):
                    # final panel hands off to /signup/results on its own
                    page.wait_for_url("**/signup/results", timeout=15000)
                    break
                asked = question()
                mark = fingerprint()
                if mark == "NO-SLOT":
                    failures.append("signup panel slot markers are missing")
                    note("   PANEL SLOT MISSING")
                    break
                numeric = page.locator(
                    "input[type=number]:visible, input[inputmode=numeric]:visible, "
                    "input[type=text]:visible"
                )
                options = page.locator(
                    "[role=radio]:visible, [role=checkbox]:visible, "
                    "[role=option]:visible, div.cursor-pointer:visible"
                )
                did = ""
                if options.count():
                    options.first.click()
                    did = f"clicked option (of {options.count()})"
                elif numeric.count():
                    for k in range(min(numeric.count(), 3)):
                        field = numeric.nth(k)
                        low = field.get_attribute("min")
                        high = field.get_attribute("max")
                        value = (
                            str(round((float(low) + float(high)) / 2))
                            if low and high
                            else "70"
                        )
                        field.fill(value)
                    did = f"filled {min(numeric.count(), 3)} field(s)"
                page.wait_for_timeout(400)
                # Single-choice panels carry no Continue and advance on
                # selection (source behaviour), so only press Continue when
                # this panel is still on screen — otherwise the button on
                # screen belongs to the NEXT, still-unanswered panel.
                if mark == fingerprint() and "/signup" == page.url.replace(
                    base, ""
                ).split("?")[0]:
                    cont = page.get_by_role("button", name="Continue")
                    if cont.count() and cont.first.is_visible():
                        try:
                            cont.first.click(timeout=4000)
                            did += " + Continue"
                        except Exception:
                            failures.append(
                                f"panel {index} Continue not clickable"
                            )
                            note(f"   panel{index} CONTINUE NOT CLICKABLE",
                                 f"| q={asked!r}")
                            break
                else:
                    did += " (auto-advanced)"
                page.wait_for_timeout(500)
                print(f"   panel{index}: q={asked!r} {did}", flush=True)
            note("03 questionnaire complete")
            if "/signup" == page.url.replace(base, "").split("?")[0]:
                failures.append("questionnaire never left /signup")

            if "/signup/results" in page.url:
                for _ in range(30):
                    cont = page.get_by_role("button", name="Continue")
                    if cont.count() and cont.first.is_visible():
                        break
                    page.wait_for_timeout(500)
                cont = page.get_by_role("button", name="Continue")
                if cont.count():
                    cont.first.click()
                    page.wait_for_timeout(1200)
                note("04 results -> register")

            page.locator("input[name='email']").first.fill(EMAIL)
            page.wait_for_timeout(250)
            page.get_by_role("button", name="Continue").first.click(timeout=5000)
            page.wait_for_timeout(900)
            note("05 register step 1 (email)")

            page.locator("input[name='username']").first.fill(USERNAME)
            page.locator("input[name='password']").first.fill(PASSWORD)
            page.wait_for_timeout(200)
            clicked = False
            for name in ("Continue", "Create account", "Sign up"):
                button = page.get_by_role("button", name=name)
                if button.count() and button.first.is_visible():
                    button.first.click(timeout=5000)
                    clicked = True
                    break
            if not clicked:
                failures.append("register step 2 has no clickable submit")
            page.wait_for_timeout(1500)
            note("06 account created")
            if "/my-jefit" not in page.url:
                failures.append(f"registration did not land on dashboard ({page.url})")

            upgrade = page.get_by_role("button", name="Upgrade to Elite")
            if not upgrade.count():
                upgrade = page.get_by_text("Upgrade to Elite", exact=False)
            if upgrade.count():
                upgrade.first.click()
                page.wait_for_timeout(800)
            body = page.inner_text("body")
            note("07 plan modal", f"| annual-shown={'52.49' in body}")

            buy = page.get_by_role("link", name="Buy plan")
            if buy.count() >= 2:
                buy.nth(1).click()
                page.wait_for_timeout(1300)
            else:
                failures.append(f"plan modal exposed {buy.count()} Buy plan links")
                page.goto(
                    f"{base}/elite/checkout?isMyJefit=true&sub=yearly",
                    wait_until="load",
                )
                page.wait_for_timeout(800)
            body = page.inner_text("body")
            note("08 checkout",
                 f"| total52.49={'52.49' in body} sandbox={'Simulated' in body}")
            if "sub=yearly" not in page.url:
                failures.append(f"checkout is not the yearly plan ({page.url})")

            page.locator("input[type=radio][value='sandbox-approved']").first.check()
            page.wait_for_timeout(250)
            page.get_by_role("button", name="Subscribe").first.click(timeout=6000)
            page.wait_for_timeout(1800)
            note("09 payment submitted")

            if "/my-jefit/settings" not in page.url:
                page.goto(f"{base}/my-jefit/settings", wait_until="load")
                page.wait_for_timeout(700)
            text = page.inner_text("body")
            elite = "Elite" in text and "renews on" in text
            still_free = "Upgrade your account" in text
            page.screenshot(path=str(OUT / "settings-after-payment.png"),
                            full_page=True)
            note("10 destination view",
                 f"| elite-membership={elite} upgrade-cards-gone={not still_free}")
            if not elite or still_free:
                failures.append("settings does not show the Elite membership")

            # login + forgot-password by real click
            context.clear_cookies()
            page.goto(f"{base}/login", wait_until="load")
            page.wait_for_timeout(500)
            accept_cookies()
            page.locator("input[name='username']").first.fill("jefitdemo")
            page.locator("input[name='password']").first.fill("Demo-Pass-2026!")
            page.get_by_role("button", name="Log In").first.click(timeout=5000)
            page.wait_for_timeout(1200)
            note("11 login by real click")
            if "/my-jefit" not in page.url:
                failures.append(f"login by click did not reach dashboard ({page.url})")

            page.goto(f"{base}/login/forgot-password", wait_until="load")
            page.wait_for_timeout(500)
            accept_cookies()
            page.locator("input[name='email']").first.fill("demo.member@example.com")
            page.get_by_role("button", name="Send reset link").first.click(timeout=5000)
            page.wait_for_timeout(1000)
            sent = "reset code" in page.inner_text("body")
            note("12 forgot-password by real click", f"| confirmation={sent}")
            if not sent:
                failures.append("forgot-password click produced no confirmation")
            browser.close()
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    print(f"\nOFFSITE REQUESTS: {len(offsite)} {offsite[:5]}", flush=True)
    if failures:
        print("WALK FAILURES:", flush=True)
        for item in failures:
            print(f"  - {item}", flush=True)
        return 1
    print("WALK RESULT: task 539 completed end-to-end by real clicks", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
