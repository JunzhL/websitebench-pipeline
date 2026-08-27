#!/usr/bin/env python3
"""Finalize current asset metadata without rewriting captured evidence bytes.

The capture mirror deliberately retains every response it observed. Some of
those responses are evidence rather than safe runtime assets (for example an
HTML challenge saved behind a CSS URL, a font response whose URL ended in
``.css``, or a pristine stylesheet that still points offsite). Those entries
must remain in the mirror for provenance, but they are not members of the
candidate's required runtime closure: the page builder emits localized vendor
stylesheets and strips or replaces these references.

Valid raster/vector dimensions are derived with the repository's canonical
asset inspector. An entry the inspector rejects, or an SVG with no intrinsic
size, is retained as non-required P2 evidence with no runtime reference edges.
No asset payload is changed.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))

from websitebench.offline_clone.assets import inspect_asset  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site-dir",
        type=pathlib.Path,
        default=pathlib.Path("materials/deleteme"),
    )
    args = parser.parse_args()
    site = args.site_dir.resolve()
    manifest_path = site / "source-assets" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    demoted: list[str] = []
    dimensioned = 0
    for asset in manifest["assets"]:
        source = site / asset["source_path"]
        runtime = site / asset["runtime_path"]
        try:
            source_observed = inspect_asset(source)
            runtime_observed = inspect_asset(runtime)
            if source_observed != runtime_observed:
                raise ValueError("source and runtime metadata differ")
            if source.read_bytes() != runtime.read_bytes():
                raise ValueError("source and runtime bytes differ")
            if source_observed["mime_type"].startswith("image/"):
                dimensions = source_observed["dimensions"]
                if dimensions is None:
                    raise ValueError("image has no intrinsic dimensions")
                if asset.get("dimensions") != dimensions:
                    asset["dimensions"] = dimensions
                    dimensioned += 1
        except (OSError, ValueError):
            asset["priority"] = "p2"
            asset["required"] = False
            asset["referenced_by"] = []
            demoted.append(asset["id"])

    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"assets={len(manifest['assets'])} dimensioned={dimensioned} "
        f"evidence_only={len(demoted)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
