#!/usr/bin/env python3
"""Reconcile source-assets/manifest.json with the closure inspector.

The capture pass records what the browser reported; the closure checker
(`websitebench.offline_clone.assets.inspect_asset`) re-derives mime type and
intrinsic dimensions from the retained bytes and reports a finding whenever the
two disagree. This tool makes the manifest say what the bytes say:

* mime_type and dimensions are taken from the inspector, not from the wire;
* assets whose payload is an HTML response shell (the source answered 404 with a
  page) are removed from the manifest and recorded in unresolved-references.json,
  because a shell is not the asset it claims to be;
* assets the inspector rejects outright — pristine CSS carrying external
  references, and icon-font SVGs that have no intrinsic dimensions to declare —
  are demoted to evidence-only (priority p2, required false, no referencing
  candidate file) rather than deleted, so the captured bytes stay auditable. A
  demoted CSS file must be replaced in the candidate by a localized vendor copy;
  that promotion belongs to the build, not here.

Idempotent: re-running after a fresh capture converges to the same manifest.
"""
from __future__ import annotations

import argparse
import json
import pathlib

from websitebench.offline_clone.assets import inspect_asset

DEMOTION_REASON = (
    "pristine capture copy the closure inspector rejects (external runtime "
    "reference, or an icon-font SVG with no intrinsic dimensions). Retained as "
    "evidence; the candidate must reference a localized vendor copy instead."
)


def is_html_shell(path: pathlib.Path) -> bool:
    head = path.read_bytes()[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def reconcile(site: pathlib.Path) -> dict[str, int]:
    manifest_path = site / "source-assets" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    stats = {"mime_synced": 0, "dimensions_synced": 0, "shells_removed": 0,
             "demoted": 0, "kept": 0}
    kept: list[dict] = []
    shells: list[dict] = []

    for asset in manifest["assets"]:
        source = site / asset["source_path"]
        if not source.is_file():
            continue
        if asset["mime_type"].startswith("text/html") or is_html_shell(source):
            shells.append(asset)
            for relative in (asset["source_path"], asset["runtime_path"]):
                target = site / relative
                if target.is_file():
                    target.unlink()
            stats["shells_removed"] += 1
            continue
        try:
            observed = inspect_asset(source)
        except ValueError:
            asset["priority"] = "p2"
            asset["required"] = False
            asset["referenced_by"] = []
            stats["demoted"] += 1
            kept.append(asset)
            continue
        mime = observed.get("mime_type")
        if mime and asset.get("mime_type") != mime:
            asset["mime_type"] = mime
            stats["mime_synced"] += 1
        dimensions = observed.get("dimensions")
        if dimensions and asset.get("dimensions") != dimensions:
            asset["dimensions"] = dimensions
            stats["dimensions_synced"] += 1
        kept.append(asset)

    manifest["assets"] = kept
    stats["kept"] = len(kept)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    if shells:
        unresolved_path = site / "source-assets" / "unresolved-references.json"
        unresolved = json.loads(unresolved_path.read_text())
        key = "unresolved" if "unresolved" in unresolved else "references"
        unresolved.setdefault(key, [])
        unresolved[key].extend(
            {"url": asset["source_url"],
             "referenced_by": asset.get("referenced_by", []),
             "failure": "source answered with an HTML response shell instead of "
                        "the asset; the shell was discarded, not retained as an "
                        "asset"}
            for asset in shells)
        unresolved_path.write_text(json.dumps(unresolved, indent=2) + "\n")
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", default="materials/ipvanish")
    args = parser.parse_args()
    stats = reconcile(pathlib.Path(args.site_dir))
    print(json.dumps(stats, indent=2, sort_keys=True))
    if stats["demoted"]:
        print(f"\nnote: {stats['demoted']} asset(s) demoted to evidence-only.\n"
              f"      {DEMOTION_REASON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
