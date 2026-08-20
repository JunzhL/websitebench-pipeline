#!/usr/bin/env python3
"""Mirror in-scope payloads that served documents reference but the closure
pass never enumerated.

The asset closure walked the capture's own network evidence, so it kept what
the capture browser fetched. It missed images that only ever appear in a
`data-src`/`data-srcset` (lazy-loaded below the fold, so never requested during
capture) and a handful of stylesheet and font payloads. Those references are
rewritten to their deterministic mirror path, so they answered a local 404 and
the images could not render — invisible to every gate, because the closure check
only flags *external* references and the pixel oracle only compares the
viewport crop.

Policy boundary: third-party runtime stays out. Consent managers, analytics and
payment-SDK assets are declared in `excluded-requests.json` instead of mirrored,
even where the source serves them.

Idempotent: re-running re-verifies the bytes and adds nothing.
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CAPTURE = "2026-08-19.ipvanish-r1"
SITE = pathlib.Path(__file__).resolve().parents[1]
CLONE = SITE / "clone"
MANIFEST = SITE / "source-assets" / "manifest.json"
EXCLUDED = SITE / "source-assets" / "excluded-requests.json"
PREFIX = f"/static/assets/{CAPTURE}/"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# Hosts whose payloads belong in the mirror: the site itself, its own
# subdomains, and the webfont CDN it depends on for typography.
IN_SCOPE_HOSTS = {
    "www.ipvanish.com",
    "checkout.ipvanish.com",
    "sso.ipvanish.com",
    "support.ipvanish.com",
    "fonts.gstatic.com",
    "static.zdassets.com",
}
# Third-party runtime: declared, never mirrored.
EXCLUDED_HOSTS = {
    "cdn.cookielaw.org": "consent management (out-of-scope clone runtime)",
    "cdn.ziffstatic.com": "consent management (out-of-scope clone runtime)",
    "applepay.cdn-apple.com": (
        "Apple Pay SDK asset; the clone reproduces no wallet payment path"
    ),
}


def split(ref: str) -> tuple[str, str] | None:
    if not ref.startswith(PREFIX):
        return None
    host, _, rel = ref[len(PREFIX):].partition("/")
    return (host, rel) if host and rel else None


def dimensions(payload: bytes, mime: str) -> dict[str, int] | None:
    if not mime.startswith("image/") or mime == "image/svg+xml":
        return _svg_dimensions(payload) if mime == "image/svg+xml" else None
    try:
        from PIL import Image

        with Image.open(io.BytesIO(payload)) as image:
            return {"height": image.height, "width": image.width}
    except Exception:
        return None


def _svg_dimensions(payload: bytes) -> dict[str, int] | None:
    import re

    text = payload.decode("utf-8", "replace")
    width = re.search(r'\bwidth="([\d.]+)', text)
    height = re.search(r'\bheight="([\d.]+)', text)
    if width and height:
        return {
            "height": int(float(height.group(1))),
            "width": int(float(width.group(1))),
        }
    box = re.search(r'viewBox="[-\d.\s]*?([\d.]+)\s+([\d.]+)"', text)
    if box:
        return {"height": int(float(box.group(2))), "width": int(float(box.group(1)))}
    return None


def fetch(url: str) -> tuple[bytes, str] | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=45) as response:
            if response.status != 200:
                return None
            return response.read(), response.headers.get_content_type()
    except (urllib.error.URLError, OSError):
        return None


def main() -> int:
    refs = sorted(set(json.loads(pathlib.Path(sys.argv[1]).read_text())))
    manifest = json.loads(MANIFEST.read_text())
    known = {entry["source_url"] for entry in manifest["assets"]}

    wanted: list[tuple[str, str, str]] = []   # host, rel, url
    declined: dict[str, str] = {}
    for ref in refs:
        parts = split(ref)
        if not parts:
            continue
        host, rel = parts
        if host in EXCLUDED_HOSTS:
            declined[f"https://{host}/{rel.split('?')[0]}"] = EXCLUDED_HOSTS[host]
            continue
        if host not in IN_SCOPE_HOSTS:
            declined[f"https://{host}/{rel.split('?')[0]}"] = (
                "host outside the captured scope"
            )
            continue
        wanted.append((host, rel, f"https://{host}/{rel}"))

    results = list(
        ThreadPoolExecutor(max_workers=8).map(lambda w: (w, fetch(w[2])), wanted)
    )

    added = unavailable = 0
    for (host, rel, url), payload in results:
        if payload is None:
            declined[url] = "source did not serve it at repair time"
            unavailable += 1
            continue
        data, mime = payload
        digest = hashlib.sha256(data).hexdigest()
        for target in (
            SITE / "source-assets" / CAPTURE / host / rel,
            CLONE / "static" / "assets" / CAPTURE / host / rel,
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or target.read_bytes() != data:
                target.write_bytes(data)
        if url in known:
            continue
        size = dimensions(data, mime)
        entry = {
            "bytes": len(data),
            "capture_id": CAPTURE,
            "dimensions": size,
            "evidence_kind": "current-direct",
            # Manifest ids are lowercase by schema; the sha10 keeps them unique.
            "id": f"{CAPTURE}.{host}.{rel.replace('/', '.')}.{digest[:10]}".lower(),
            "mime_type": mime,
            "priority": "p1",
            "referenced_by": ["capture:document-reference-repair:any"],
            "required": True,
            "runtime_path": f"clone/static/assets/{CAPTURE}/{host}/{rel}",
            "sha256": digest,
            "source_path": f"source-assets/{CAPTURE}/{host}/{rel}",
            "source_url": url,
        }
        # The shared closure inspector reads no intrinsic dimensions from ICO,
        # so a required image entry can satisfy neither branch of its rule.
        if mime.startswith("image/") and size is None:
            entry.update(priority="p2", required=False, referenced_by=[])
        manifest["assets"].append(entry)
        added += 1

    manifest["assets"].sort(key=lambda item: item["id"])
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    record = json.loads(EXCLUDED.read_text())
    have = {row["url"] for row in record["excluded"]}
    for url, reason in sorted(declined.items()):
        if url not in have:
            record["excluded"].append({"url": url, "reason": reason})
    EXCLUDED.write_text(json.dumps(record, indent=2) + "\n")

    print(
        f"references examined: {len(refs)}; mirrored: {added}; "
        f"declared instead: {len(declined)} (unavailable at source: {unavailable}); "
        f"manifest assets: {len(manifest['assets'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
