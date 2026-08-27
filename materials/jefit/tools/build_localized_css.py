#!/usr/bin/env python3
"""Generate localized copies of every mirrored stylesheet.

The vendored mirror under ``clone/static/assets/`` stays byte-exact against
``source-assets/manifest.json``; documents instead link the copies written
here to ``clone/static/css/<capture-id>/<host>/<path>``, in which every
``url()`` / ``@import`` reference is mapped onto the local mirror:

* root-relative references resolve against the stylesheet's own host mirror;
* absolute references on captured hosts resolve onto their mirror path;
* anything that cannot resolve locally is localized onto the deterministic
  mirror path anyway (a local 404, never a remote request) and reported.

Purely mechanical and idempotent; report at
``clone/frontend/css-localize-report.json``.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import posixpath
import re

TOOLS = pathlib.Path(__file__).resolve().parent
SITE = TOOLS.parent

_spec = importlib.util.spec_from_file_location(
    "build_clone_pages", TOOLS / "build_clone_pages.py"
)
_bcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bcp)

CAPTURE_ID = _bcp.CAPTURE_ID
ASSET_ROOT = _bcp.ASSET_ROOT
CSS_ROOT = _bcp.CSS_ROOT
STATIC_PREFIX = _bcp.STATIC_PREFIX
REPORT = SITE / "clone" / "frontend" / "css-localize-report.json"

CSS_URL = re.compile(r"(?is)url\(\s*(['\"]?)([^)'\"]+)\1\s*\)")
CSS_IMPORT = re.compile(r"(?is)@import\s+(['\"])([^'\"]+)\1")


def localize(text: str, css_rel: str, report: dict) -> str:
    host = css_rel.split("/", 1)[0]
    css_dir = posixpath.dirname(css_rel)

    def resolve(raw: str) -> str | None:
        value = raw.strip()
        if not value or value.startswith(("data:", "#", "blob:")):
            return None
        if value.startswith("//"):
            value = "https:" + value
        if value.startswith("/") and not value.startswith("//"):
            value = f"https://{host}{value}"
        if not value.startswith(("http://", "https://")):
            # relative reference: it resolved inside the mirror at the
            # stylesheet's original location, but the localized copy lives
            # under /static/css/, so absolutize onto the mirror path.
            clean = value.split("?", 1)[0].split("#", 1)[0]
            rel = posixpath.normpath(posixpath.join(css_dir, clean))
            local = f"{STATIC_PREFIX}/{rel}"
            if not (ASSET_ROOT / rel).is_file():
                report["missing_payloads"].append(
                    {"reference": value[:200], "local": local}
                )
            report["mapped"] += 1
            return local
        rel = _bcp.mirror_rel(value)
        local = f"{STATIC_PREFIX}/{rel}"
        if not (ASSET_ROOT / rel).is_file():
            report["missing_payloads"].append(
                {"reference": value[:200], "local": local}
            )
        report["mapped"] += 1
        return local

    def url_sub(match: re.Match) -> str:
        mapped = resolve(match.group(2))
        return f"url({mapped})" if mapped else match.group(0)

    def import_sub(match: re.Match) -> str:
        mapped = resolve(match.group(2))
        return f'@import "{mapped}"' if mapped else match.group(0)

    return CSS_IMPORT.sub(import_sub, CSS_URL.sub(url_sub, text))


def main() -> int:
    manifest = json.loads((SITE / "source-assets" / "manifest.json").read_text())
    summary: dict = {"_totals": {"files": 0, "mapped": 0, "missing": 0}}
    for asset in manifest["assets"]:
        if asset.get("mime_type") != "text/css":
            continue
        rel = asset["runtime_path"].split(f"assets/{CAPTURE_ID}/", 1)[1]
        source = ASSET_ROOT / rel
        if not source.is_file():
            summary[rel] = {"error": "missing mirror payload"}
            continue
        report = {"mapped": 0, "missing_payloads": []}
        localized = localize(
            source.read_text(encoding="utf-8", errors="replace"), rel, report
        )
        target = CSS_ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(localized, encoding="utf-8")
        summary[rel] = report
        summary["_totals"]["files"] += 1
        summary["_totals"]["mapped"] += report["mapped"]
        summary["_totals"]["missing"] += len(report["missing_payloads"])
    REPORT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary["_totals"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
