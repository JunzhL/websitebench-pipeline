#!/usr/bin/env python3
"""Promote safe localized copies of external-ref assets to the vendor tree.

A few pristine mirror payloads carry external url()/@import references (the
Google Fonts stylesheet, legacy theme CSS) or an inert external-href
``<metadata>`` block (Simple-Line-Icons.svg). The pristine copies under
``clone/static/assets/`` stay byte-exact; this script writes localized
copies to ``clone/static/site/vendor/`` and repoints every candidate
reference at them:

* CSS: reuse build_localized_css.localize() — url()/@import references map
  onto captured mirror equivalents; uncaptured legacy payloads localize onto
  their deterministic mirror path (a local 404, the recorded known
  difference — never a remote request).
* SVG: strip only the inert ``<metadata>...</metadata>`` block; glyphs are
  untouched.

Every vendor copy must pass websitebench.offline_clone.assets.inspect_asset
before it is used. Report printed as JSON.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
SITE = TOOLS.parent
CLONE = SITE / "clone"
VENDOR = CLONE / "static" / "site" / "vendor"

sys.path.insert(0, str(SITE.parents[1] / "src"))
from websitebench.offline_clone.assets import inspect_asset  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_bcp = _load("build_clone_pages")
_css = _load("build_localized_css")

METADATA_BLOCK = re.compile(r"<metadata>.*?</metadata>", re.S)


def pristine_fails(path: pathlib.Path) -> bool:
    try:
        inspect_asset(path)
    except ValueError:
        return True
    return False


def main() -> int:
    manifest = json.loads((SITE / "source-assets" / "manifest.json").read_text())
    VENDOR.mkdir(parents=True, exist_ok=True)
    promotions = []
    replacements: dict[str, str] = {}
    for asset in manifest["assets"]:
        runtime = SITE / asset["runtime_path"]
        if not runtime.is_file() or not pristine_fails(runtime):
            continue
        rel = asset["runtime_path"].split(f"assets/{_bcp.CAPTURE_ID}/", 1)[1]
        suffix = runtime.suffix.casefold()
        if suffix == ".css":
            report = {"mapped": 0, "missing_payloads": []}
            payload = _css.localize(
                runtime.read_text(encoding="utf-8", errors="replace"),
                rel,
                report,
            ).encode("utf-8")
            note = (
                f"{report['mapped']} refs localized, "
                f"{len(report['missing_payloads'])} point at uncaptured "
                "legacy payloads (local 404s, recorded known difference)"
            )
        elif suffix == ".svg":
            text = runtime.read_text(encoding="utf-8", errors="replace")
            stripped = METADATA_BLOCK.sub("", text, count=1)
            if stripped == text:
                raise SystemExit(f"{rel}: no <metadata> block to strip")
            payload = stripped.encode("utf-8")
            note = "inert <metadata> block stripped; glyphs untouched"
        else:
            raise SystemExit(f"{rel}: unsupported external-ref asset type")
        digest = hashlib.sha256(payload).hexdigest()[:16]
        destination = VENDOR / f"localized-{digest}{suffix}"
        destination.write_bytes(payload)
        inspect_asset(destination)  # must independently satisfy the inspector
        old_pristine = "/" + asset["runtime_path"].removeprefix("clone/")
        vendor_url = f"/static/site/vendor/{destination.name}"
        replacements[old_pristine] = vendor_url
        if suffix == ".css":
            # documents currently link the /static/css/ localized copy
            replacements[f"{_bcp.CSS_PREFIX}/{rel}"] = vendor_url
            duplicate = _bcp.CSS_ROOT / rel
            if duplicate.is_file():
                duplicate.unlink()
        promotions.append(
            {
                "runtime_path": asset["runtime_path"],
                "vendor": vendor_url,
                "bytes": len(payload),
                "inspect": "passed",
                "note": note,
            }
        )

    changed = 0
    for path in sorted(CLONE.rglob("*")):
        if not path.is_file() or "/static/assets/" in path.as_posix():
            continue
        if path.suffix not in {".html", ".css", ".js", ".json"}:
            continue
        try:
            before = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        after = before
        for old, new in replacements.items():
            after = after.replace(old, new)
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed += 1

    print(
        json.dumps(
            {
                "promoted": promotions,
                "rewritten_files": changed,
            },
            indent=1,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
