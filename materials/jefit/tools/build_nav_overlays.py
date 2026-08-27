#!/usr/bin/env python3
"""Extract the captured header-nav overlays for the clone runtime.

* Desktop Products/Workouts/More popover panels come from the captured
  dropdown-open states (inline headlessui panels).
* The mobile menu comes from the mobile-menu-open capture (mobile viewport),
  localized with the standard Mapper policy.

Output: clone/frontend/nav-overlays.json — the runtime injects a panel next
to its nav button on click, reproducing the captured open state.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re

TOOLS = pathlib.Path(__file__).resolve().parent
SITE = TOOLS.parent

_spec = importlib.util.spec_from_file_location(
    "build_clone_pages", TOOLS / "build_clone_pages.py"
)
_bcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bcp)

EVIDENCE = SITE / "clone" / "frontend" / "evidence"
OUT = SITE / "clone" / "frontend" / "nav-overlays.json"

DIV_TOKEN = re.compile(r"<div\b|</div>")


def match_div(doc: str, open_start: int) -> int:
    depth = 0
    for token in DIV_TOKEN.finditer(doc, open_start):
        if token.group(0) == "<div":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return token.end()
    raise SystemExit("unbalanced div in nav overlay")


def main() -> int:
    overlays: dict[str, str] = {}
    for key, name in (
        ("products", "nav-products-dropdown"),
        ("workouts", "nav-workouts-dropdown"),
        ("more", "nav-more-dropdown"),
    ):
        doc = (EVIDENCE / f"{name}.html").read_text()
        match = re.search(r'<div[^>]*id="headlessui-popover-panel-', doc)
        if match is None:
            raise SystemExit(f"{name}: popover panel not found")
        overlays[key] = doc[match.start() : match_div(doc, match.start())]

    # mobile menu: only the mobile viewport captured this state
    source = (
        SITE
        / "source-current"
        / "2026-08-18.jefit-r1"
        / "mobile-menu-open"
        / "mobile"
        / "page.html"
    )
    report = {
        "rewritten": 0,
        "dropped_tags": [],
        "content_fallback_refs": [],
        "script_blocks_dropped": 0,
        "ld_json_dropped": 0,
        "first_party_localized": 0,
        "external_boundaries": [],
    }
    mapper = _bcp.Mapper(report)
    mobile = _bcp.rewrite_document(source.read_text(), mapper, report)
    dialog = re.search(r'<div[^>]*role="dialog"', mobile)
    if dialog is None:
        # fall back to the portal root if the dialog is portal-hosted
        portal = mobile.find('<div id="headlessui-portal-root">')
        if portal < 0:
            raise SystemExit("mobile menu: no dialog and no portal")
        overlays["mobile-menu"] = mobile[portal : match_div(mobile, portal)]
    else:
        overlays["mobile-menu"] = mobile[
            dialog.start() : match_div(mobile, dialog.start())
        ]
    remote = _bcp.remaining_remote("".join(overlays.values()))
    OUT.write_text(json.dumps(overlays, sort_keys=True))
    print({k: len(v) for k, v in overlays.items()}, "remote:", len(remote))
    return 0 if not remote else 1


if __name__ == "__main__":
    raise SystemExit(main())
