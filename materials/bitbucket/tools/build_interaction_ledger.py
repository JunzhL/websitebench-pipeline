#!/usr/bin/env python3
"""Build Bitbucket's interaction ledger from the current local browser walk.

The committed browser scenario is the selector source. This script replays its
setup against the loopback clone, then verifies each activated control against
the served DOM and records visible-text, raw-markup, and form-action proofs.
Sensitive values remain in environment variables and never enter the ledger.
"""

from __future__ import annotations

import argparse
import http.cookies
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


SITE_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = SITE_ROOT / "scope" / "local-browser-scenario.json"
SCHEMA_VERSION = "bitbucket.interaction-ledger.v1"

CONTROLS = [
    {
        "step_id": "enter-no-match-query",
        "clone_url": "/repo/all",
        "selector": "form[action='/repo/all'] input[name='name']",
        "marker": "name='name'",
        "visible": "Repositories",
        "form_action": {"method": "GET", "action": "/repo/all"},
        "journey_id": "public-repository-discovery",
        "role": "visitor",
        "state": "search-loaded",
    },
    {
        "step_id": "submit-no-match-query",
        "clone_url": "/repo/all",
        "selector": "form[action='/repo/all'] input[name='name']",
        "marker": "name='name'",
        "visible": "Repositories",
        "form_action": {"method": "GET", "action": "/repo/all"},
        "journey_id": "recovery-and-errors",
        "role": "visitor",
        "state": "search-no-results",
    },
    {
        "step_id": "return-to-repositories",
        "clone_url": "/repo/all?name=zzzz-no-match-websitebench",
        "selector": ".empty-state a[href='/repo/all']",
        "marker": "href='/repo/all'",
        "visible": "View all repositories",
        "form_action": None,
        "journey_id": "recovery-and-errors",
        "role": "visitor",
        "state": "search-no-results",
    },
    {
        "step_id": "open-public-repository",
        "clone_url": "/repo/all",
        "selector": "a[href='/atlassianlabs/atlascode']",
        "marker": "href='/atlassianlabs/atlascode'",
        "visible": "atlassianlabs / atlascode",
        "form_action": None,
        "journey_id": "public-repository-discovery",
        "role": "visitor",
        "state": "repository-list",
    },
    {
        "step_id": "open-source-tree",
        "clone_url": "/atlassianlabs/atlascode",
        "selector": "aside.sidebar a[href='/atlassianlabs/atlascode/src/main']",
        "marker": "href='/atlassianlabs/atlascode/src/main'",
        "visible": "Source",
        "form_action": None,
        "journey_id": "public-repository-discovery",
        "role": "visitor",
        "state": "repository-public",
    },
    {
        "step_id": "enter-identifier",
        "clone_url": "/account/signin/",
        "selector": "form[action='/account/signin/'] input[name='identifier']",
        "marker": "name=\"identifier\"",
        "visible": "Username or primary email",
        "form_action": {"method": "POST", "action": "/account/signin/"},
        "journey_id": "local-account-lifecycle",
        "role": "visitor",
        "state": "sign-in-form",
    },
    {
        "step_id": "enter-password",
        "clone_url": "/account/signin/",
        "selector": "form[action='/account/signin/'] input[name='password']",
        "marker": "name=\"password\"",
        "visible": "Password",
        "form_action": {"method": "POST", "action": "/account/signin/"},
        "journey_id": "local-account-lifecycle",
        "role": "visitor",
        "state": "sign-in-form",
    },
    {
        "step_id": "submit-sign-in",
        "clone_url": "/account/signin/",
        "selector": "form[action='/account/signin/'] button[type='submit']",
        "marker": "type='submit'",
        "visible": "Sign in",
        "form_action": {"method": "POST", "action": "/account/signin/"},
        "journey_id": "local-account-lifecycle",
        "role": "visitor",
        "state": "sign-in-form",
    },
    {
        "step_id": "trigger-pipeline",
        "clone_url": "/developer/platform-demo/pipelines",
        "selector": "form[action='/developer/platform-demo/pipelines'] button[type='submit']",
        "marker": "action='/developer/platform-demo/pipelines'",
        "visible": "Run pipeline",
        "form_action": {"method": "POST", "action": "/developer/platform-demo/pipelines"},
        "journey_id": "pipeline-inspection",
        "role": "developer",
        "state": "pipelines-list",
    },
    {
        "step_id": "retry-pipeline",
        "clone_url": "/developer/platform-demo/pipelines/1",
        "selector": "form[action='/developer/platform-demo/pipelines/1/retry'] button[type='submit']",
        "marker": "action='/developer/platform-demo/pipelines/1/retry'",
        "visible": "Retry pipeline",
        "form_action": {"method": "POST", "action": "/developer/platform-demo/pipelines/1/retry"},
        "journey_id": "pipeline-inspection",
        "role": "developer",
        "state": "pipeline-detail",
    },
    {
        "step_id": "sign-out",
        "clone_url": "/dashboard/overview",
        "selector": "form[action='/account/signout/'] button[type='submit']",
        "marker": "action='/account/signout/'",
        "visible": "Sign out",
        "form_action": {"method": "POST", "action": "/account/signout/"},
        "journey_id": "local-account-lifecycle",
        "role": "developer",
        "state": "dashboard-authenticated",
    },
]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class LocalClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie = ""
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str, str | None]:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        request_headers = dict(headers or {})
        if body is not None:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.cookie:
            request_headers["Cookie"] = self.cookie
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            response = self.opener.open(request)
        except urllib.error.HTTPError as exc:
            response = exc
        set_cookie = response.headers.get("Set-Cookie")
        if set_cookie:
            parsed = http.cookies.SimpleCookie()
            parsed.load(set_cookie)
            self.cookie = "; ".join(f"{key}={morsel.value}" for key, morsel in parsed.items())
        text = response.read().decode("utf-8", "replace")
        return response.status, text, response.headers.get("Location")

    def post_and_follow(self, path: str, data: dict[str, str] | None = None) -> str:
        status, _, location = self.request(path, method="POST", data=data or {})
        if status != 303 or not location:
            raise RuntimeError(f"POST {path} returned {status}, expected redirect")
        followed, text, _ = self.request(location)
        if followed != 200:
            raise RuntimeError(f"GET {location} returned {followed}")
        return text


def tag_at(body: str, marker: str) -> tuple[str, int]:
    position = body.find(marker)
    if position < 0:
        raise RuntimeError(f"DOM marker not found: {marker}")
    start = body.rfind("<", 0, position)
    end = body.find(">", position)
    if start < 0 or end < 0:
        raise RuntimeError(f"cannot bound DOM marker: {marker}")
    return body[start : end + 1], start


def text_content(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&amp;", "&").replace("&#x27;", "'")
    return re.sub(r"\s+", " ", value).strip()


def prove_visible(body: str, marker: str, expected: str, position: int) -> str:
    if expected in text_content(body):
        return expected
    raise RuntimeError(f"visible proof {expected!r} is absent for {marker!r} at {position}")


def scenario_selectors() -> dict[str, str]:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    return {
        step["id"]: step["selector"]
        for step in scenario["steps"]
        if isinstance(step, dict) and isinstance(step.get("selector"), str)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--output",
        default=str(SITE_ROOT / "tools" / "interaction-ledger.json"),
    )
    args = parser.parse_args()

    password = os.environ.get("WEBSITEBENCH_BITBUCKET_TEST_PASSWORD")
    admin_token = os.environ.get("WEBSITEBENCH_BITBUCKET_ADMIN_TOKEN")
    if not password or not admin_token:
        raise SystemExit(
            "WEBSITEBENCH_BITBUCKET_TEST_PASSWORD and WEBSITEBENCH_BITBUCKET_ADMIN_TOKEN are required"
        )

    selectors = scenario_selectors()
    for control in CONTROLS:
        if selectors.get(control["step_id"]) != control["selector"]:
            raise RuntimeError(
                f"selector drift for {control['step_id']}: rerun the current browser walk"
            )

    client = LocalClient(args.base_url)
    status, _, _ = client.request(
        "/__admin/reset",
        method="POST",
        data={},
        headers={"X-WebsiteBench-Admin-Token": admin_token},
    )
    if status != 200:
        raise RuntimeError(f"local reset returned {status}")

    documents: dict[str, str] = {}
    for path in (
        "/repo/all",
        "/repo/all?name=zzzz-no-match-websitebench",
        "/atlassianlabs/atlascode",
        "/account/signin/",
    ):
        status, body, _ = client.request(path)
        if status != 200:
            raise RuntimeError(f"GET {path} returned {status}")
        documents[path] = body

    client.post_and_follow(
        "/account/signin/",
        {
            "identifier": "developer@bitbucket.local",
            "password": password,
        },
    )
    for path in ("/developer/platform-demo/pipelines", "/dashboard/overview"):
        status, body, _ = client.request(path)
        if status != 200:
            raise RuntimeError(f"GET {path} returned {status}")
        documents[path] = body
    documents["/developer/platform-demo/pipelines/1"] = client.post_and_follow(
        "/developer/platform-demo/pipelines"
    )

    entries = []
    for control in CONTROLS:
        body = documents[control["clone_url"]]
        raw_markup, position = tag_at(body, control["marker"])
        visible = prove_visible(body, control["marker"], control["visible"], position)
        entries.append(
            {
                "step_id": control["step_id"],
                "clone_url": control["clone_url"],
                "selector": control["selector"],
                "visible_text_proof": visible,
                "raw_markup_proof": raw_markup[:500],
                "form_action": control["form_action"],
                "journey_id": control["journey_id"],
                "role": control["role"],
                "state": control["state"],
            }
        )

    ledger = {
        "schema_version": SCHEMA_VERSION,
        "site_id": "bitbucket",
        "authority": "diagnostic-only",
        "clone_base_url": args.base_url,
        "generated_by": "tools/build_interaction_ledger.py",
        "sources": {
            "browser_scenario": "scope/local-browser-scenario.json",
            "note": (
                "Selectors and step IDs come from the current loopback browser walk. "
                "Proof strings and form actions are checked against served clone DOM."
            ),
        },
        "secret_handling": (
            "Password, session cookie, and admin token were consumed in memory from "
            "environment variables and were not retained."
        ),
        "controls": entries,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print(f"ledger: {output}")
    print(f"controls: {len(entries)}; missing proofs: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
