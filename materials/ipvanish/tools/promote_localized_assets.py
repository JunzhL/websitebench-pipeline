#!/usr/bin/env python3
"""Promote localized copies of mirrored stylesheets whose references do not serve.

A mirrored stylesheet is byte-exact evidence, and its ``url()`` / ``@import``
targets were written for the *source* origin.  Two kinds of target break once the
clone serves the mirror under ``/static/assets/<capture>/<host>/``:

1. **External references.** ``source-assets/manifest.json`` demotes 23 payloads
   to evidence-only; eighteen are stylesheets holding absolute references
   (Google Fonts, the Astra local-font sheet, WordPress plugin and
   Otter/themeisle sheets).  Serving those bytes would make the browser fetch
   fonts from ``www.ipvanish.com`` at runtime, which the closure invariant
   forbids.  The other five are Font Awesome SVG font files that already satisfy
   ``inspect_asset`` and are referenced by no captured stylesheet, so they stay
   pristine and unpromoted.
2. **Root-relative references.** ``background-image: url(/logo.svg)`` is not
   external, so ``inspect_asset`` passes it and the manifest keeps the payload
   required -- yet it resolves against the clone origin instead of the mirror and
   answers a local 404.  Five required stylesheets carry these, and the payloads
   were all captured: the SSO sign-in wordmark, the checkout wallet and payment
   icons and the marketing OS-icon strip were all failing to paint for this
   reason alone.  A blind review caught the wordmark; this pass fixes the class.

This tool never touches the pristine tree.  For each affected stylesheet it
writes a localized sibling under ``clone/static/site/vendor/`` whose references
point at captured mirrors, verifies the copy independently against
``websitebench.offline_clone.assets.inspect_asset``, and repoints every candidate
reference at it.  A reference whose payload was never captured is localized onto
its deterministic mirror path, where it answers a local 404: a recorded known
difference, never an invented substitute.

Report is printed as JSON, with detail in
``clone/frontend/promotion-report.json``.  Idempotent, and must run after
``build_clone_pages.py``, which rewrites the served documents from scratch.
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


_pages = _load("build_clone_pages")


def pristine_fails(path: pathlib.Path) -> str | None:
    try:
        inspect_asset(path)
    except ValueError as error:
        return str(error)
    return None


# A `url(/logo.svg)` inside a mirrored stylesheet is not an *external* reference,
# so `inspect_asset` passes it and the manifest keeps the payload required. It is
# still broken once served: the clone hosts the mirror under
# /static/assets/<capture>/<host>/, so a root-relative reference resolves against
# the clone origin instead of the mirror and answers a 404. That is how the SSO
# sign-in wordmark (`background-image: url(/logo.svg)`), the checkout wallet
# icons and the marketing OS-icon strip all silently failed to paint while every
# payload sat correctly in the mirror.
_CSS_REFERENCE = re.compile(
    r"""(?:url\(\s*|@import\s+(?:url\(\s*)?)['"]?\s*(?P<target>[^\s'")]+)"""
)


def root_relative_references(text: str) -> list[str]:
    found: set[str] = set()
    for match in _CSS_REFERENCE.finditer(text):
        target = match.group("target").strip()
        if target.startswith("/") and not target.startswith("//"):
            found.add(target)
    return sorted(found)


def main() -> int:
    manifest = json.loads(
        (SITE / "source-assets" / "manifest.json").read_text(encoding="utf-8")
    )
    asset_index, _ = _pages.load_asset_index()
    VENDOR.mkdir(parents=True, exist_ok=True)
    for stale in VENDOR.glob("localized-*"):
        stale.unlink()

    promotions: list[dict[str, object]] = []
    replacements: dict[str, str] = {}
    left_pristine: list[dict[str, str]] = []
    uncaptured: set[str] = set()

    for asset in manifest["assets"]:
        runtime = SITE / asset["runtime_path"]
        source = SITE / asset["source_path"]
        is_css = runtime.suffix.casefold() == ".css"
        reason = pristine_fails(source)
        rooted: list[str] = []
        if is_css and source.is_file():
            rooted = root_relative_references(
                source.read_text(encoding="utf-8", errors="replace")
            )
        if reason is None and not rooted:
            if not asset.get("required"):
                left_pristine.append(
                    {
                        "runtime_path": asset["runtime_path"],
                        "note": "already satisfies inspect_asset and holds no "
                        "root-relative reference; evidence-only in the manifest "
                        "and referenced by no captured stylesheet",
                    }
                )
            continue
        if not is_css:
            raise SystemExit(f"{asset['runtime_path']}: unsupported demoted type")
        if reason is None:
            reason = (
                f"{len(rooted)} root-relative reference(s) that resolve against "
                "the clone origin rather than the mirror"
            )
        # Rewrite relative to the payload's own source URL, exactly as a browser
        # would resolve it.
        rewriter = _pages.Rewriter(asset["source_url"], asset_index)
        payload = rewriter.css(
            source.read_text(encoding="utf-8", errors="replace")
        ).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()[:16]
        destination = VENDOR / f"localized-{digest}.css"
        destination.write_bytes(payload)
        inspect_asset(destination)  # the copy must satisfy the inspector itself
        vendor_url = f"/static/site/vendor/{destination.name}"
        pristine_url = "/" + asset["runtime_path"].removeprefix("clone/")
        replacements[pristine_url] = vendor_url
        uncaptured.update(rewriter.missing_assets)
        promotions.append(
            {
                "runtime_path": asset["runtime_path"],
                "vendor": vendor_url,
                "bytes": len(payload),
                "inspect": "passed",
                "promotion_reason": reason,
                "root_relative_references": len(rooted),
                "references_localized": rewriter.mapped,
                "references_uncaptured": len(rewriter.missing_assets),
            }
        )

    changed = 0
    for path in sorted(CLONE.rglob("*")):
        if not path.is_file() or "/static/assets/" in path.as_posix():
            continue
        if path.suffix.casefold() not in {".html", ".css", ".js", ".json"}:
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

    report = {
        "promoted": promotions,
        "left_pristine": left_pristine,
        "rewritten_files": changed,
        "uncaptured_reference_keys": sorted(uncaptured),
    }
    (CLONE / "frontend" / "promotion-report.json").write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "promoted": len(promotions),
                "left_pristine": len(left_pristine),
                "rewritten_files": changed,
                "uncaptured_reference_keys": len(uncaptured),
            },
            indent=1,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
