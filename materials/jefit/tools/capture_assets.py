#!/usr/bin/env python3
"""Asset closure capture for the JEFIT offline clone.

Renders every URL-addressable checkpoint (desktop + mobile) while recording
each network response, saves unique asset payloads under
source-assets/<capture_id>/<host>/<path>, then closes the remainder --
CSS url() references and source-current resources.json entries that did not
fire during the render pass -- and builds source-assets/manifest.json
(offline-clone.assets.v1), mirroring every asset into clone/static/assets/
as an independent byte-identical physical copy.

Channel: jefit.com serves local Playwright Chromium directly (verified in
the browser-provider preflight), so both passes run in one local headless
context -- no Browserbase. Remainder fetches use the context's request API
(GET only, never any other method), with an in-page fetch() fallback from a
page sitting on the source origin for anything the request context cannot
reach.

Safety: no cookies, headers or tokens are ever persisted -- only response
bodies. Query strings never reach saved paths (they are replaced by a short
sha256 digest suffix). Requests to analytics/consent/ad/identity-provider
origins (out-of-scope clone runtime per scope/purpose.json) are never
fetched or mirrored; the observed URLs are logged query-stripped with a
reason in source-assets/excluded-requests.json, because the
offline-clone.assets.v1 schema forbids extra manifest keys. Anything
referenced but unfetchable lands in source-assets/unresolved-references.json.

Usage:
    python3 materials/jefit/tools/capture_assets.py \
        --site-dir materials/jefit [--only home,elite] [--skip-render]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import pathlib
import re
import shutil
import sys
import urllib.parse
from collections import deque
from datetime import datetime, timezone

from playwright.sync_api import BrowserContext, Page, sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from capture_source import (  # noqa: E402
    INTERACTIVE_IDS, dismiss_consent, hide_scrollbars,
)

CAPTURE_ID = "2026-08-18.jefit-r1"
SOURCE_ORIGIN = "https://www.jefit.com/"
FIRST_PARTY_HOSTS = ("jefit.com",)
RENDER_VIEWPORTS = ("desktop", "mobile")
MAX_ASSET_BYTES = 50_000_000

ASSET_TYPES = {
    "text/css": "css",
    "application/javascript": "js",
    "text/javascript": "js",
    "application/x-javascript": "js",
    "font/woff2": "font",
    "font/woff": "font",
    "application/font-woff2": "font",
    "application/font-woff": "font",
    "font/ttf": "font",
    "image/png": "image",
    "image/jpeg": "image",
    "image/gif": "image",
    "image/svg+xml": "image",
    "image/webp": "image",
    "image/avif": "image",
    "image/x-icon": "image",
    "image/vnd.microsoft.icon": "image",
}
# Analytics, ads, consent management, session recording and live
# identity/payment providers: forbidden as clone runtime (see
# scope/purpose.json out_of_scope) and therefore never fetched or mirrored.
# First-party asset hosts (www/cdn.jefit.com), Google Fonts and plain asset
# CDNs (stackpath.bootstrapcdn.com) are deliberately NOT listed here.
EXCLUDE_HOST_FRAGMENTS: dict[str, str] = {
    "google-analytics": "analytics beacon",
    "analytics.google": "analytics beacon",
    "googletagmanager": "tag-manager / analytics loader",
    "amplitude": "product-analytics beacon",
    "hotjar": "session-recording analytics",
    "clarity.ms": "session-recording analytics",
    "facebook": "ad pixel / live identity provider",
    "reddit": "ad pixel",
    "doubleclick": "ad delivery",
    "googlesyndication": "ad delivery",
    "googleadservices": "ad delivery",
    "adtrafficquality": "ad verification beacon",
    "fundingchoicesmessages": "consent management",
    "accounts.google": "live identity provider (clone runtime is local)",
    "appleid.cdn-apple": "live identity provider (clone runtime is local)",
    "js.stripe": "live payment provider (clone runtime is local)",
    "m.stripe": "live payment provider (clone runtime is local)",
    "bat.bing": "ad pixel",
    "tiktok": "ad pixel",
    "snapchat": "ad pixel",
    "www.google.com": "ad / captcha service",
    "www.google.ca": "ad redirect",
}
CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")
MIME_RE = re.compile(r"^[a-z0-9.+-]+/[a-z0-9.+-]+$")
ID_SAFE = re.compile(r"[^a-z0-9._-]+")

FETCH_B64_JS = """async url => {
  try {
    const r = await fetch(url, {method: 'GET', credentials: 'omit'});
    if (!r.ok) return {ok: false, status: r.status};
    const buf = await r.arrayBuffer();
    if (buf.byteLength > 50000000) return {ok: false, status: -2};
    const bytes = new Uint8Array(buf);
    let bin = '';
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk)
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    return {ok: true, status: r.status,
            contentType: r.headers.get('content-type') || '',
            b64: btoa(bin)};
  } catch (e) {
    return {ok: false, status: -1, error: String(e).slice(0, 120)};
  }
}"""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def exclusion_reason(url: str) -> str | None:
    host = urllib.parse.urlsplit(url).netloc.casefold()
    for fragment, reason in EXCLUDE_HOST_FRAGMENTS.items():
        if fragment in host:
            return reason
    return None


def classify(url: str, content_type: str) -> str | None:
    base = content_type.split(";")[0].strip().casefold()
    if base in ASSET_TYPES:
        return ASSET_TYPES[base]
    path = urllib.parse.urlsplit(url).path.casefold()
    for suffix, kind in ((".css", "css"), (".js", "js"), (".woff2", "font"),
                         (".woff", "font"), (".ttf", "font"),
                         (".png", "image"), (".jpg", "image"),
                         (".jpeg", "image"), (".gif", "image"),
                         (".svg", "image"), (".webp", "image"),
                         (".avif", "image"), (".ico", "image")):
        if path.endswith(suffix):
            return kind
    return None


def local_relpath(url: str) -> str:
    """host/path save location; query strings never persist (digest suffix
    only) and over-long segments collapse to a hash."""
    parts = urllib.parse.urlsplit(url)
    path = parts.path.lstrip("/") or "index"
    if path.endswith("/"):
        path += "index"
    if parts.query:
        digest = hashlib.sha256(parts.query.encode()).hexdigest()[:10]
        stem, dot, suffix = path.rpartition(".")
        path = f"{stem}.q{digest}.{suffix}" if dot else f"{path}.q{digest}"
    segments = []
    for segment in path.split("/"):
        if len(segment.encode()) > 140:
            stem, dot, suffix = segment.rpartition(".")
            digest = hashlib.sha256(segment.encode()).hexdigest()[:16]
            segment = (f"h{digest}.{suffix}" if dot and len(suffix) <= 8
                       else f"h{digest}")
        segments.append(segment)
    return f"{parts.netloc}/{'/'.join(segments)}"


def strip_query(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, "", ""))


def manifest_id(rel: str, sha: str) -> str:
    base = ID_SAFE.sub("-", f"{CAPTURE_ID}.{rel.replace('/', '.')}"
                       .casefold())
    return f"{base[:180].strip('._-')}.{sha[:10]}"


def clean_mime(content_type: str) -> str:
    base = content_type.split(";")[0].strip().casefold()
    return base if MIME_RE.match(base) else "application/octet-stream"


def image_dimensions(body: bytes) -> dict | None:
    try:
        from PIL import Image
        with Image.open(io.BytesIO(body)) as im:
            return {"width": im.width, "height": im.height}
    except Exception:  # noqa: BLE001 - SVG/ICO/PIL-absent
        return None


def load_plan(site: pathlib.Path,
              only: set[str] | None) -> tuple[list[dict], list[dict]]:
    plan = json.loads(
        (site / "scope" / "source-capture-plan.json").read_text())
    viewports = [v for v in plan["viewports"] if v["name"] in RENDER_VIEWPORTS]
    pages = []
    for cp in plan["checkpoints"]:
        if only and cp["id"] not in only:
            continue
        if cp["id"] in INTERACTIVE_IDS or not cp["url"].startswith("http"):
            continue
        pages.append(cp)
    return viewports, pages


def load_resource_targets(site: pathlib.Path,
                          only: set[str] | None) -> dict[str, set[str]]:
    """Asset URL -> referenced_by tags, from every captured resources.json."""
    targets: dict[str, set[str]] = {}
    root = site / "source-current" / CAPTURE_ID
    for res_file in sorted(root.glob("*/*/resources.json")):
        viewport = res_file.parent.name
        checkpoint = res_file.parent.parent.name
        if only and checkpoint not in only:
            continue
        for entry in json.loads(res_file.read_text()):
            url = entry.get("url", "")
            if not url.startswith("http"):
                continue
            if classify(url, "") is None:
                continue
            targets.setdefault(url, set()).add(
                f"capture:{checkpoint}:{viewport}")
    return targets


def render_pass(page: Page, viewports: list[dict], pages_list: list[dict],
                record, note_excluded) -> None:
    for vp in viewports:
        page.set_viewport_size({"width": vp["width"],
                                "height": vp["height"]})
        for cp in [c for c in pages_list if vp["name"] in c["viewports"]]:
            page_id = cp["id"]
            responses: list = []

            def handler(resp: object) -> None:
                responses.append(resp)

            page.on("response", handler)
            try:
                page.goto(cp["url"], wait_until="domcontentloaded",
                          timeout=60000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:  # noqa: BLE001 - settle delay follows
                    pass
                page.wait_for_timeout(1500)
                dismiss_consent(page)
                page.mouse.wheel(0, 20000)
                page.wait_for_timeout(800)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {page_id}/{vp['name']}: {str(exc)[:120]}",
                      file=sys.stderr, flush=True)
            page.remove_listener("response", handler)
            for resp in responses:
                try:
                    if resp.status != 200:
                        continue
                    # Classify BEFORE touching the body: response.body()
                    # blocks on still-streaming responses, and those are
                    # never assets.
                    if note_excluded(resp.url):
                        continue
                    content_type = resp.headers.get("content-type", "")
                    tag = f"capture:{page_id}:{vp['name']}"
                    if classify(resp.url, content_type) is None:
                        continue
                    if resp.request.resource_type in {
                        "media", "websocket", "eventsource", "ping",
                    }:
                        continue
                    body = resp.body()
                    if len(body) > MAX_ASSET_BYTES:
                        continue
                    record(resp.url, body, content_type, {tag})
                except Exception:  # noqa: BLE001
                    continue
            print(f"  {page_id}/{vp['name']}: render pass done", flush=True)


def css_references(url: str, body: bytes) -> set[str]:
    targets: set[str] = set()
    text = body.decode("utf-8", errors="replace")
    for match in CSS_URL.finditer(text):
        ref = match.group(1).strip()
        if ref.startswith(("data:", "#")):
            continue
        targets.add(urllib.parse.urljoin(url, ref))
    return targets


def request_fetch(ctx: BrowserContext,
                  url: str) -> tuple[bytes | None, str]:
    """GET-only fetch through the context request API. Returns
    (body, content_type) or (None, failure reason)."""
    try:
        resp = ctx.request.get(url, timeout=30000, max_redirects=5)
    except Exception as exc:  # noqa: BLE001
        return None, f"request-error: {str(exc)[:120]}"
    try:
        if resp.status != 200:
            return None, f"http-status: {resp.status}"
        body = resp.body()
        if not body:
            return None, "empty-body"
        if len(body) > MAX_ASSET_BYTES:
            return None, "oversize"
        return body, resp.headers.get("content-type", "")
    finally:
        resp.dispose()


def close_remainder(ctx: BrowserContext, page: Page,
                    collected: dict[str, dict],
                    targets: dict[str, set[str]], record,
                    note_excluded) -> dict[str, dict]:
    """Fetch everything referenced but not captured, chasing CSS url()
    chains to a fixed point. Returns unresolved url -> details."""
    queue: deque[str] = deque()
    refs: dict[str, set[str]] = {}

    def enqueue(url: str, tags: set[str]) -> None:
        if url in collected:
            collected[url]["referenced_by"].update(tags)
            return
        if note_excluded(url):
            return
        if url not in refs:
            queue.append(url)
        refs.setdefault(url, set()).update(tags)

    for entry in list(collected.values()):
        if entry["kind"] != "css":
            continue
        for target in css_references(entry["url"], entry["body"]):
            enqueue(target, {"capture:css-crawl:any"})
    for url, tags in targets.items():
        enqueue(url, tags)

    # In-page fetch fallback needs a page sitting on the source origin.
    page.goto(SOURCE_ORIGIN, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    unresolved: dict[str, dict] = {}
    got = 0
    while queue:
        url = queue.popleft()
        body, content_type = request_fetch(ctx, url)
        if body is None:
            failure = content_type
            try:
                res = page.evaluate(FETCH_B64_JS, url)
            except Exception:  # noqa: BLE001
                res = {"ok": False, "status": -1}
            if res.get("ok"):
                body = base64.b64decode(res["b64"])
                content_type = res.get("contentType", "")
            else:
                unresolved[url] = {
                    "url": url,
                    "referenced_by": sorted(refs[url]),
                    "failure": failure,
                    "in_page_fetch_status": res.get("status"),
                }
                continue
        record(url, body, content_type, refs[url])
        got += 1
        entry = collected.get(url)
        if entry is not None and entry["kind"] == "css":
            for target in css_references(url, body):
                enqueue(target, {"capture:css-crawl:any"})
    print(f"  remainder closure: +{got}, unresolved {len(unresolved)}",
          flush=True)
    for url in sorted(unresolved):
        print(f"    unresolved: {url}", flush=True)
    return unresolved


def write_outputs(site: pathlib.Path, collected: dict[str, dict],
                  unresolved: dict[str, dict],
                  excluded: dict[str, str]) -> None:
    asset_root = site / "source-assets" / CAPTURE_ID
    runtime_root = site / "clone" / "static" / "assets" / CAPTURE_ID
    for root in (asset_root, runtime_root):
        if root.exists():
            shutil.rmtree(root)
    created_at = utc_now()
    assets = []
    for url in sorted(collected):
        entry = collected[url]
        rel = local_relpath(url)
        source_path = asset_root / rel
        runtime_path = runtime_root / rel
        source_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(entry["body"])
        runtime_path.write_bytes(entry["body"])
        sha = hashlib.sha256(entry["body"]).hexdigest()
        host = urllib.parse.urlsplit(url).netloc.casefold()
        first_party = any(host == h or host.endswith("." + h)
                          for h in FIRST_PARTY_HOSTS)
        priority = ("p0" if entry["kind"] in {"css", "font"} or first_party
                    else "p1")
        assets.append({
            "id": manifest_id(rel, sha),
            "priority": priority,
            "required": True,
            # Query strings and fragments never persist: presigned-CDN
            # queries (X-Amz-*) carry credential material and the manifest
            # schema rejects them; the sha-suffixed local path keeps
            # uniqueness.
            "source_url": strip_query(url),
            "source_path": str(source_path.relative_to(site)),
            "runtime_path": str(runtime_path.relative_to(site)),
            "bytes": len(entry["body"]),
            "sha256": sha,
            "mime_type": clean_mime(entry["content_type"]),
            "referenced_by": sorted(entry["referenced_by"]),
            "dimensions": (image_dimensions(entry["body"])
                           if entry["kind"] == "image" else None),
            "evidence_kind": "current-direct",
            "capture_id": CAPTURE_ID,
        })
    manifest = {
        "schema_version": "offline-clone.assets.v1",
        "snapshot_id": CAPTURE_ID,
        "created_at": created_at,
        "remote_runtime_policy": "forbidden",
        "closure_status": "declared" if assets else "no-assets",
        "no_assets_reason": (None if assets
                             else "capture recorded no asset payloads"),
        "assets": assets,
    }
    manifest_path = site / "source-assets" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2,
                                        sort_keys=True) + "\n")
    unresolved_path = site / "source-assets" / "unresolved-references.json"
    unresolved_path.write_text(json.dumps({
        "schema_version": "offline-clone.unresolved-references.v1",
        "snapshot_id": CAPTURE_ID,
        "created_at": created_at,
        "note": ("URLs referenced by source markup, stylesheets or the "
                 "recorded per-page network evidence that the asset-closure "
                 "pass could not download (request-context GET and in-page "
                 "fetch both failed)."),
        "unresolved": [unresolved[url] for url in sorted(unresolved)],
    }, indent=2) + "\n")
    excluded_path = site / "source-assets" / "excluded-requests.json"
    excluded_path.write_text(json.dumps({
        "capture_id": CAPTURE_ID,
        "created_at": created_at,
        "note": ("Analytics/consent/ad/identity-provider requests observed "
                 "during capture; never fetched or mirrored (out-of-scope "
                 "clone runtime per scope/purpose.json). Logged here, "
                 "query-stripped, because offline-clone.assets.v1 forbids "
                 "extra manifest keys."),
        "excluded": [{"url": url, "reason": excluded[url]}
                     for url in sorted(excluded)],
    }, indent=2) + "\n")
    kinds: dict[str, int] = {}
    for entry in collected.values():
        kinds[entry["kind"]] = kinds.get(entry["kind"], 0) + 1
    total = sum(len(e["body"]) for e in collected.values())
    print(f"assets: {len(assets)}  bytes: {total}  kinds: {kinds}")
    print(f"excluded origins logged: {len(excluded)}  "
          f"unresolved: {len(unresolved)}")
    print(f"manifest -> {manifest_path}")


def run(site: pathlib.Path, only: set[str] | None,
        skip_render: bool) -> int:
    collected: dict[str, dict] = {}
    excluded: dict[str, str] = {}

    def note_excluded(url: str) -> bool:
        reason = exclusion_reason(url)
        if reason is None:
            return False
        excluded.setdefault(strip_query(url), reason)
        return True

    def record(url: str, body: bytes, content_type: str,
               refs: set[str]) -> None:
        if note_excluded(url) or not body:
            return
        kind = classify(url, content_type)
        if kind is None:
            return
        entry = collected.setdefault(url, {
            "url": url, "kind": kind, "content_type": content_type,
            "body": body, "referenced_by": set(),
        })
        entry["referenced_by"].update(refs)

    viewports, pages_list = load_plan(site, only)
    resource_targets = load_resource_targets(site, only)
    if not pages_list and not resource_targets:
        print("nothing to capture")
        return 1
    print(f"plan pages: {len(pages_list)}, "
          f"resources.json targets: {len(resource_targets)}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-US", timezone_id="Etc/UTC")
            page = ctx.new_page()
            hide_scrollbars(page)
            if not skip_render:
                render_pass(page, viewports, pages_list, record,
                            note_excluded)
            unresolved = close_remainder(ctx, page, collected,
                                         resource_targets, record,
                                         note_excluded)
        finally:
            browser.close()

    write_outputs(site, collected, unresolved, excluded)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-dir", default="materials/jefit")
    ap.add_argument("--only", default="",
                    help="comma-separated checkpoint ids (partial manifest)")
    ap.add_argument("--skip-render", action="store_true",
                    help="remainder-closure only, from existing "
                         "resources.json files")
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s} or None
    return run(pathlib.Path(args.site_dir).resolve(), only, args.skip_render)


if __name__ == "__main__":
    raise SystemExit(main())
