#!/usr/bin/env python3
"""Asset closure for the DeleteMe offline clone: mirror every in-scope byte.

Reads the reference censuses the capture passes already wrote
(source-current/<capture-id>/*/*/references.json and resources.json), plus a
regex net over each captured page.html, then downloads every in-scope asset
GET-only and writes it byte-exact to
source-assets/<capture-id>/<host>/<path>, with
source-assets/manifest.json in offline-clone.assets.v1 shape.

Three lessons from earlier sites are built in, because each one cost a rebuild:

1. Lazy-loaded images are advertised in `data-src` and `data-srcset` and are
   NEVER requested by the capture browser. Collecting only src/srcset left 291
   broken references in a previous clone. The capture-time census
   (capture_common.REFERENCE_CENSUS_JS) already reads both, and
   `html_references` below re-scans the frozen page.html for any data-*
   attribute that looks like an asset, so a missed attribute name still gets
   caught.

2. Every advertised srcset width is mirrored, not just the one this capture's
   browser chose. A retina viewer picks a different width, and a clone that
   only has the 1x candidate breaks for them.

3. Asset ids are lowercased. The offline-clone.assets.v1 pattern is
   ^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$ and this site serves mixed-case bundle
   names (app.joindeleteme.com/assets/Add-DnqXar8o.js), so the raw path is not
   a legal id. The sha10 suffix is kept, which is also what keeps two paths
   differing only in case from colliding.

Google Fonts is mirrored deliberately: the clone may make no font request
offsite, so both advertised stylesheets (Cairo+Poppins, Poppins+Roboto) and
every fonts.gstatic.com woff2 they reference are downloaded. Adobe Fonts
(use.typekit.net) is mirrored for the same reason. The pristine Google CSS
still names fonts.gstatic.com in its url() rules, so the closure inspector
rejects it and freeze_asset_metadata.py demotes it to evidence-only; replacing
it with a localized vendor copy is the build's job, not this tool's.

Not mirrored, and declared with a reason in
source-assets/excluded-requests.json: consent management, analytics, tag
managers, ad and affiliate networks, HubSpot, Klaviyo, live payment (Stripe),
live Google Maps Places, podcast attribution, and two tags that cannot be
attributed to a vendor from public assets alone (declared by origin rather
than guessed).

runtime_path is DECLARED but not written. This harness writes only under
materials/deleteme/{tools,source-current,source-assets}; materialising the
byte-identical runtime copy under clone/static/ belongs to the candidate
build, which does not exist yet.

Safety: GET only, enforced both by the context route guard and by using only
`request.get`. No cookie, header or token is persisted -- only response
bodies. Neither query nor fragment ever reaches a persisted `source_url`; a
short digest of the query stands in on the local save path instead, because a
CDN query can carry credential material and the manifest schema rejects both.

Usage:
    python materials/deleteme/tools/capture_assets.py \
        --site-dir materials/deleteme
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import pathlib
import re
import shutil
import sys
import urllib.parse
from collections import defaultdict, deque

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from playwright.async_api import async_playwright  # noqa: E402

import capture_common as cc  # noqa: E402

CAPTURE_ID = cc.CAPTURE_ID
SOURCE_ORIGIN = "https://joindeleteme.com/"
MAX_ASSET_BYTES = 50_000_000

# Hosts whose bytes the clone serves itself. First-party DeleteMe hosts, the
# help centre's own theming host, the two font services, the Zendesk Guide
# presentation bundle that the in-scope /help route is built out of, and the
# avatar host the blog renders author images from.
MIRROR_HOSTS: tuple[str, ...] = (
    "joindeleteme.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "use.typekit.net",
    "p.typekit.net",
    "static.zdassets.com",
    "assets.zendesk.com",
    "secure.gravatar.com",
)

FIRST_PARTY_HOSTS: tuple[str, ...] = ("joindeleteme.com",)

# First-party hostnames that are NOT content: the server-side tagging
# endpoint. Excluded despite living under the primary domain.
EXCLUDE_EXACT_HOSTS: dict[str, str] = {
    "tagging.joindeleteme.com":
        "server-side tag manager endpoint (analytics collection, not content)",
}

# Host substring -> reason. Matched against the HOST ONLY, never the whole
# URL: matching a vendor name anywhere in the URL wrongly excluded three
# first-party bundles whose filenames happen to contain a vendor's name
# (privacy.joindeleteme.com/vendor-transcend-io-*.js), which are part of the
# in-scope /policies page rather than a third-party runtime. Path-based
# exclusions must be declared explicitly in EXCLUDE_URL_FRAGMENTS instead.
EXCLUDE_HOST_FRAGMENTS: dict[str, str] = {
    "transcend": "consent management platform (Transcend CMP)",
    "klaviyo": "marketing-automation / email tracking runtime",
    "googletagmanager": "tag manager / analytics loader",
    "google-analytics": "analytics beacon",
    "analytics.google": "analytics beacon",
    "doubleclick": "ad network / conversion pixel",
    "googleadservices": "ad network / conversion pixel",
    "googlesyndication": "ad network",
    "bat.bing.com": "ad network / conversion pixel (Microsoft UET)",
    "connect.facebook.net": "ad pixel / live identity provider",
    "facebook.com": "ad pixel / live identity provider",
    "licdn.com": "ad network / conversion pixel (LinkedIn)",
    "ads.linkedin.com": "ad network / conversion pixel (LinkedIn)",
    "hubspot": "HubSpot marketing/CRM runtime",
    "hsforms": "HubSpot forms runtime",
    "hs-analytics": "HubSpot analytics beacon",
    "hs-banner": "HubSpot consent banner runtime",
    "hs-scripts": "HubSpot loader",
    "hsadspixel": "HubSpot ad pixel",
    "hubapi": "HubSpot API endpoint",
    "js.stripe.com": "live payment provider (clone runtime is local)",
    "m.stripe.com": "live payment provider telemetry",
    "stripe.network": "live payment provider",
    "hcaptcha": "live CAPTCHA provider (challenge cannot be reproduced offline)",
    "perimeterx": "bot-defence / device fingerprinting runtime",
    "px-cloud": "bot-defence / device fingerprinting runtime",
    "maps.googleapis.com": "live Google Maps Places runtime (address autocomplete)",
    "maps.gstatic.com": "live Google Maps sprite host",
    "www.google.com": "conversion / remarketing pixel",
    "podscribe": "podcast attribution beacon",
    "podtrac": "podcast attribution redirect",
    "megaphone.fm": "podcast media host (out-of-scope media runtime)",
    "tvspix": "CTV attribution beacon",
    "mczbf.com": "affiliate-tracking beacon",
    "de33watrk.com": "affiliate-tracking beacon",
    "lever.co": "third-party job-listing API (live service)",
    "d34r8q7sht0t9k.cloudfront.net":
        "unattributed third-party tag (tag.js on an anonymous CloudFront "
        "distribution); declared by origin rather than guessing a vendor",
}

# Full-URL substring -> reason. Only for a path that must be excluded on a
# host whose other bytes ARE mirrored. Kept deliberately short.
EXCLUDE_URL_FRAGMENTS: dict[str, str] = {
    "zdassets.com/ekr/": "live chat widget runtime (Zendesk Web Widget); the "
                         "help centre's own presentation bundle is mirrored, "
                         "the chat runtime is not",
    "zdassets.com/live_chat": "live chat widget runtime",
}

# A resource the browser fetched as data, not as an asset. Never a candidate.
NON_ASSET_INITIATORS = {"xmlhttprequest", "fetch", "beacon", "ping",
                        "navigation", "websocket", "eventsource"}

ASSET_MIME_KINDS = {
    "text/css": "css",
    "text/javascript": "js",
    "application/javascript": "js",
    "application/x-javascript": "js",
    "font/woff2": "font",
    "font/woff": "font",
    "font/ttf": "font",
    "font/otf": "font",
    "application/font-woff": "font",
    "application/font-woff2": "font",
    "application/vnd.ms-fontobject": "font",
    "image/png": "image",
    "image/jpeg": "image",
    "image/gif": "image",
    "image/svg+xml": "image",
    "image/webp": "image",
    "image/avif": "image",
    "image/x-icon": "image",
    "image/vnd.microsoft.icon": "image",
}
EXT_BY_MIME = {
    "text/css": ".css", "text/javascript": ".js",
    "application/javascript": ".js", "application/x-javascript": ".js",
    "font/woff2": ".woff2", "font/woff": ".woff", "font/ttf": ".ttf",
    "font/otf": ".otf", "application/font-woff": ".woff",
    "application/font-woff2": ".woff2",
    "application/vnd.ms-fontobject": ".eot",
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
    "image/svg+xml": ".svg", "image/webp": ".webp", "image/avif": ".avif",
    "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico",
}
EXT_KINDS = {
    ".css": "css", ".js": "js", ".mjs": "js",
    ".woff2": "font", ".woff": "font", ".ttf": "font", ".otf": "font",
    ".eot": "font",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".svg": "image", ".webp": "image", ".avif": "image", ".ico": "image",
    ".bmp": "image",
}
EXT_BY_KIND = {"css": ".css", "js": ".js", "font": ".woff2", "image": ".png"}
KNOWN_EXTS = set(EXT_KINDS) | set(EXT_BY_MIME.values()) | {".jpeg", ".map"}

MIME_RE = re.compile(r"^[a-z0-9.+-]+/[a-z0-9.+-]+$")
ID_UNSAFE = re.compile(r"[^a-z0-9._-]+")
CSS_REF = re.compile(
    r"""(?ix)
    (?: url\(\s* | @import \s+ (?: url\(\s* )? )
    ['"]? \s* ([^'")\s]+)
    """)
# Any attribute whose value could name an asset. Deliberately broad: the point
# is to catch a lazy-loading attribute name nobody thought of.
HTML_ATTR = re.compile(
    r"""(?is)\b((?:data-)?[a-z][a-z0-9_-]*)\s*=\s*["']([^"']{3,2000})["']""")
ATTR_ALLOW = re.compile(
    r"(?i)^(src|srcset|href|poster|data|content|imagesrcset|"
    r"data-[a-z0-9_-]*)$")
ATTR_DENY = re.compile(
    r"(?i)^(data-(?:id|index|tag|name|title|label|text|value|key|type|"
    r"target|toggle|filter|slide|state|count|uk-[a-z-]*|wp-[a-z-]*)|"
    r"content)$")

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
            contentType: r.headers.get('content-type') || '', b64: btoa(bin)};
  } catch (e) { return {ok: false, status: -1, error: String(e).slice(0,120)}; }
}"""


# --------------------------------------------------------------------------
# Classification and paths
# --------------------------------------------------------------------------

def host_of(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.casefold()


def is_first_party(url: str) -> bool:
    host = host_of(url)
    return any(host == h or host.endswith("." + h) for h in FIRST_PARTY_HOSTS)


def exclusion_reason(url: str) -> str | None:
    host = host_of(url)
    if host in EXCLUDE_EXACT_HOSTS:
        return EXCLUDE_EXACT_HOSTS[host]
    for fragment, reason in EXCLUDE_HOST_FRAGMENTS.items():
        if fragment in host:
            return reason
    lowered = url.casefold()
    for fragment, reason in EXCLUDE_URL_FRAGMENTS.items():
        if fragment in lowered:
            return reason
    return None


def is_candidate(url: str, initiator: str | None = None) -> bool:
    """Is this URL worth trying to mirror?

    Extension is a hint, not a requirement: this source serves real assets
    from extensionless paths (Google Fonts stylesheets at /css2?family=...,
    Gravatar avatars at /avatar/<hash>, Zendesk theming assets at
    /hc/theming_assets/<ulid>). Requiring an extension silently dropped all of
    them, so for a host whose bytes the clone serves itself the response
    content type gets the final say instead.
    """
    if not url.startswith(("http://", "https://")):
        return False
    if urllib.parse.urlsplit(url).path in ("", "/"):
        # A bare origin is a preconnect/dns-prefetch hint, not an asset.
        return False
    if initiator and initiator.casefold() in NON_ASSET_INITIATORS:
        return False
    if classify(url) is not None:
        return True
    return in_mirror_scope(url)


def in_mirror_scope(url: str) -> bool:
    host = host_of(url)
    return any(host == h or host.endswith("." + h) for h in MIRROR_HOSTS)


def classify(url: str, content_type: str = "") -> str | None:
    base = content_type.split(";")[0].strip().casefold()
    if base in ASSET_MIME_KINDS:
        return ASSET_MIME_KINDS[base]
    suffix = pathlib.PurePosixPath(
        urllib.parse.urlsplit(url).path.casefold()).suffix
    if suffix in EXT_KINDS:
        return EXT_KINDS[suffix]
    # Google Fonts stylesheets are extensionless (/css2?family=...).
    if "fonts.googleapis.com" in host_of(url) or "typekit.net" in host_of(url):
        return "css"
    return None


def clean_mime(content_type: str, kind: str | None) -> str:
    base = content_type.split(";")[0].strip().casefold()
    if MIME_RE.match(base):
        return base
    return {"css": "text/css", "js": "text/javascript",
            "font": "font/woff2", "image": "image/png"}.get(
        kind or "", "application/octet-stream")


def local_relpath(url: str, content_type: str, kind: str) -> str:
    """host/path save location. Query strings never persist: a short digest of
    the query stands in, so two srcset widths that differ only in the query
    still land in two distinct files."""
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
            segments.append(f"h{digest}.{suffix}" if dot and len(suffix) <= 8
                            else f"h{digest}")
        else:
            segments.append(segment)
    if pathlib.PurePosixPath(segments[-1]).suffix.casefold() not in KNOWN_EXTS:
        base = content_type.split(";")[0].strip().casefold()
        segments[-1] += EXT_BY_MIME.get(base) or EXT_BY_KIND.get(kind, ".bin")
    return f"{parts.netloc.casefold()}/{'/'.join(segments)}"


def manifest_id(rel: str, sha: str) -> str:
    """Lowercase id with a sha10 suffix. The schema pattern is
    ^[a-z0-9]+(?:[a-z0-9._-]*[a-z0-9])?$, and this site serves mixed-case
    bundle names, so lowercasing is mandatory rather than cosmetic; the sha10
    keeps two case-variant paths distinct."""
    base = ID_UNSAFE.sub("-", f"{CAPTURE_ID}.{rel.replace('/', '.')}".casefold())
    return f"{base[:180].strip('._-')}.{sha[:10]}"


# --------------------------------------------------------------------------
# Reference collection
# --------------------------------------------------------------------------

def split_srcset(value: str) -> list[str]:
    out = []
    for part in value.split(","):
        candidate = part.strip().split()
        if candidate:
            out.append(candidate[0])
    return out


def html_references(html: str, base_url: str) -> set[str]:
    """A regex net over the frozen DOM, as a second opinion on the capture-time
    census. Catches a lazy-loading attribute name the census JS did not know
    about -- the failure mode that produced 291 broken references before."""
    found: set[str] = set()

    def absolutize(raw: str) -> None:
        raw = raw.strip()
        if not raw or raw.startswith(("data:", "blob:", "javascript:", "#",
                                      "mailto:", "tel:", "{{", "%7B")):
            return
        try:
            resolved = urllib.parse.urljoin(base_url, raw)
        except ValueError:
            return
        if not resolved.startswith(("http://", "https://")):
            return
        if classify(resolved) is not None:
            found.add(resolved)

    for attr, value in HTML_ATTR.findall(html):
        lowered = attr.casefold()
        if not ATTR_ALLOW.match(lowered) or ATTR_DENY.match(lowered):
            continue
        if "srcset" in lowered or "," in value and " " in value \
                and lowered.endswith("set"):
            for candidate in split_srcset(value):
                absolutize(candidate)
        else:
            absolutize(value)
    for match in CSS_REF.finditer(html):
        absolutize(match.group(1))
    return found


def css_references(url: str, body: bytes) -> set[str]:
    out: set[str] = set()
    text = body.decode("utf-8", errors="replace")
    for match in CSS_REF.finditer(text):
        ref = match.group(1).strip()
        if ref.startswith(("data:", "#")):
            continue
        try:
            out.add(urllib.parse.urljoin(url, ref))
        except ValueError:
            continue
    return out


def collect_references(site: pathlib.Path) -> dict[str, set[str]]:
    """url -> referencing capture tags, from every source of truth on disk."""
    targets: dict[str, set[str]] = defaultdict(set)
    root = site / "source-current" / CAPTURE_ID
    for meta_path in sorted(root.glob("*/*/meta.json")):
        unit = meta_path.parent.parent.name
        viewport = meta_path.parent.name
        tag = f"capture:{unit}:{viewport}"
        meta = json.loads(meta_path.read_text())
        base_url = meta.get("final_url") or meta.get("requested_url") or \
            SOURCE_ORIGIN

        census = meta_path.parent / "references.json"
        if census.is_file():
            for url in json.loads(census.read_text()):
                if is_candidate(url):
                    targets[url].add(tag)
        resources = meta_path.parent / "resources.json"
        if resources.is_file():
            for entry in json.loads(resources.read_text()):
                if is_candidate(entry.get("url", ""), entry.get("initiator")):
                    targets[entry["url"]].add(tag)
        page = meta_path.parent / "page.html"
        if page.is_file():
            for url in html_references(
                    page.read_text(encoding="utf-8", errors="replace"),
                    base_url):
                targets[url].add(tag)
    return targets


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

async def request_fetch(context, url: str) -> tuple[bytes | None, str]:
    try:
        response = await context.request.get(url, timeout=30_000,
                                             max_redirects=5)
    except Exception as exc:  # noqa: BLE001
        return None, f"request-error: {str(exc)[:120]}"
    try:
        if response.status != 200:
            return None, f"http-status: {response.status}"
        body = await response.body()
        if not body:
            return None, "empty-body"
        if len(body) > MAX_ASSET_BYTES:
            return None, "oversize"
        return body, response.headers.get("content-type", "")
    finally:
        await response.dispose()


async def same_origin_fetch(page, url: str, current: dict[str, str]
                            ) -> tuple[dict, str]:
    """In-page GET, from a document on the asset's OWN origin.

    A cross-origin in-page fetch is blocked by CORS, so the fallback used to
    fail on every host but the one the page happened to be sitting on -- which
    is why the Zendesk help-centre theming stylesheet and script looked like
    hard 403s. Parking the fallback page on the asset's origin first turns them
    into ordinary same-origin GETs. This is what any visitor's browser does;
    no credential is sent (`credentials: 'omit'`) and none is persisted.
    """
    parts = urllib.parse.urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if current.get("origin") != origin:
        try:
            await page.goto(origin + "/", wait_until="domcontentloaded",
                            timeout=30_000)
            current["origin"] = origin
        except Exception as exc:  # noqa: BLE001 - keep whatever origin we had
            return {"ok": False, "status": -1}, f"origin-nav: {str(exc)[:80]}"
    try:
        return await page.evaluate(FETCH_B64_JS, url), ""
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": -1}, str(exc)[:80]


async def download_all(context, page, targets: dict[str, set[str]],
                       excluded: dict[str, str]) -> tuple[dict, dict]:
    """Fetch every in-scope reference, chasing CSS url()/@import chains to a
    fixed point. Returns (collected, unresolved)."""
    collected: dict[str, dict] = {}
    unresolved: dict[str, dict] = {}
    refs: dict[str, set[str]] = defaultdict(set)
    queue: deque[str] = deque()
    seen: set[str] = set()

    def note_excluded(url: str) -> bool:
        reason = exclusion_reason(url)
        if reason is None:
            if not in_mirror_scope(url):
                excluded.setdefault(
                    cc.strip_query(url),
                    "third-party origin outside the mirror scope; not part of "
                    "the clone's own bytes")
                return True
            return False
        excluded.setdefault(cc.strip_query(url), reason)
        return True

    def enqueue(url: str, tags: set[str]) -> None:
        if url in collected:
            collected[url]["referenced_by"].update(tags)
            return
        if note_excluded(url):
            return
        refs[url].update(tags)
        if url not in seen:
            seen.add(url)
            queue.append(url)

    for url, tags in targets.items():
        enqueue(url, tags)
    print(f"  queued {len(queue)} in-scope reference(s), "
          f"{len(excluded)} excluded origin URL(s)", flush=True)

    done = 0
    current_origin: dict[str, str] = {}
    while queue:
        url = queue.popleft()
        body, content_type = await request_fetch(context, url)
        if body is None:
            failure = content_type
            result, _detail = await same_origin_fetch(page, url,
                                                      current_origin)
            if result.get("ok"):
                body = base64.b64decode(result["b64"])
                content_type = result.get("contentType", "")
            else:
                unresolved[url] = {
                    "url": cc.strip_query(url),
                    "referenced_by": sorted(refs[url]),
                    "failure": failure,
                    "in_page_fetch_status": result.get("status"),
                }
                continue
        kind = classify(url, content_type)
        if kind is None:
            unresolved[url] = {
                "url": cc.strip_query(url),
                "referenced_by": sorted(refs[url]),
                "failure": f"not an asset content type: "
                           f"{content_type.split(';')[0].strip()!r}",
                "in_page_fetch_status": None,
            }
            continue
        collected[url] = {
            "url": url, "kind": kind, "content_type": content_type,
            "body": body, "referenced_by": set(refs[url]),
        }
        done += 1
        if done % 100 == 0:
            print(f"  fetched {done}, queue {len(queue)}", flush=True)
        if kind == "css":
            for target in css_references(url, body):
                enqueue(target, {f"css:{cc.strip_query(url)}"})

    print(f"  fetched {done} asset(s), unresolved {len(unresolved)}",
          flush=True)
    return collected, unresolved


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def image_dimensions(body: bytes) -> dict | None:
    try:
        import io

        from PIL import Image
        with Image.open(io.BytesIO(body)) as image:
            return {"width": image.width, "height": image.height}
    except Exception:  # noqa: BLE001 - SVG / ICO / unreadable
        return None


def excluded_origins(excluded: dict[str, str]) -> list[dict[str, object]]:
    """One row per origin, with its reason and how many of its URLs were seen.
    The per-URL list stays too, but a reader wants the origin roster first."""
    rollup: dict[str, dict[str, object]] = {}
    for url, reason in excluded.items():
        origin = host_of(url)
        row = rollup.setdefault(
            origin, {"origin": origin, "reason": reason, "urls_observed": 0})
        row["urls_observed"] = int(row["urls_observed"]) + 1
    return [rollup[origin] for origin in sorted(rollup)]


def write_outputs(site: pathlib.Path, collected: dict[str, dict],
                  unresolved: dict[str, dict],
                  excluded: dict[str, str]) -> None:
    asset_root = site / "source-assets" / CAPTURE_ID
    if asset_root.exists():
        shutil.rmtree(asset_root)
    created_at = cc.utc_now()
    assets: list[dict] = []
    used_ids: set[str] = set()

    for url in sorted(collected):
        entry = collected[url]
        rel = local_relpath(url, entry["content_type"], entry["kind"])
        source_path = asset_root / rel
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(entry["body"])
        sha = hashlib.sha256(entry["body"]).hexdigest()

        asset_id = manifest_id(rel, sha)
        if asset_id in used_ids:
            for n in range(2, 100):
                candidate = f"{asset_id}-{n}"
                if candidate not in used_ids:
                    asset_id = candidate
                    break
        used_ids.add(asset_id)

        priority = "p0" if (entry["kind"] in {"css", "font"}
                            or is_first_party(url)) else "p1"
        assets.append({
            "id": asset_id,
            "priority": priority,
            "required": True,
            "source_url": cc.strip_query(url),
            "source_path": str(source_path.relative_to(site)),
            # Declared, not written: the byte-identical runtime copy belongs
            # to the candidate build, which does not exist yet.
            "runtime_path": f"clone/static/assets/{CAPTURE_ID}/{rel}",
            "bytes": len(entry["body"]),
            "sha256": sha,
            "mime_type": clean_mime(entry["content_type"], entry["kind"]),
            "dimensions": (image_dimensions(entry["body"])
                           if entry["kind"] == "image" else None),
            "referenced_by": sorted(entry["referenced_by"]),
            "evidence_kind": "current-direct",
            "capture_id": CAPTURE_ID,
        })

    manifest = {
        "schema_version": "offline-clone.assets.v1",
        "snapshot_id": CAPTURE_ID,
        "created_at": created_at,
        "remote_runtime_policy": "forbidden",
        "closure_status": "declared" if assets else "no-assets",
        "no_assets_reason": (None if assets else
                            "the capture recorded no asset payloads"),
        "assets": assets,
    }
    (site / "source-assets" / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    (site / "source-assets" / "unresolved-references.json").write_text(
        json.dumps({
            "schema_version": "offline-clone.unresolved-references.v1",
            "snapshot_id": CAPTURE_ID,
            "created_at": created_at,
            "note": "URLs referenced by the frozen markup, by a mirrored "
                    "stylesheet, or by the recorded per-unit network evidence "
                    "that this pass could not download as an asset "
                    "(GET request and in-page fetch both failed, or the "
                    "response was not an asset content type). Logged "
                    "query-stripped.",
            "unresolved": [unresolved[u] for u in sorted(unresolved)],
        }, indent=2) + "\n", encoding="utf-8")

    (site / "source-assets" / "excluded-requests.json").write_text(
        json.dumps({
            "schema_version": "offline-clone.excluded-requests.v1",
            "capture_id": CAPTURE_ID,
            "created_at": created_at,
            "note": "Third-party runtime origins observed during capture that "
                    "are deliberately NOT mirrored: consent management, "
                    "analytics and tag managers, ad and affiliate networks, "
                    "HubSpot, Klaviyo, live payment (Stripe), live Google "
                    "Maps Places, podcast/CTV attribution, live chat, and "
                    "tags that cannot be attributed to a vendor from public "
                    "assets alone. None was fetched. Google Fonts and Adobe "
                    "Fonts are deliberately absent from this list: they ARE "
                    "mirrored, because the clone may make no font request "
                    "offsite. Logged query-stripped, in this sidecar rather "
                    "than the manifest, because offline-clone.assets.v1 "
                    "forbids extra keys.",
            "excluded_origins": excluded_origins(excluded),
            "excluded": [{"url": url, "reason": excluded[url]}
                         for url in sorted(excluded)],
        }, indent=2) + "\n", encoding="utf-8")

    kinds: dict[str, int] = defaultdict(int)
    hosts: dict[str, int] = defaultdict(int)
    for entry in collected.values():
        kinds[entry["kind"]] += 1
        hosts[host_of(entry["url"])] += 1
    total = sum(len(e["body"]) for e in collected.values())
    print(f"\nassets mirrored: {len(assets)}  bytes: {total:,}")
    print(f"kinds: {dict(kinds)}")
    print("hosts: " + json.dumps(dict(sorted(hosts.items(),
                                             key=lambda kv: -kv[1])), indent=2))
    print(f"excluded URLs declared: {len(excluded)}  "
          f"unresolved: {len(unresolved)}")


async def run(site: pathlib.Path) -> int:
    targets = collect_references(site)
    if not targets:
        print("no references found -- run capture_source.py first")
        return 1
    print(f"references discovered: {len(targets)}", flush=True)
    excluded: dict[str, str] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context, guard = await cc.new_guarded_context(
                browser, cc.VIEWPORTS["desktop"])
            page = await context.new_page()
            # The in-page fetch fallback needs a document on the source origin.
            await page.goto(SOURCE_ORIGIN, wait_until="load",
                            timeout=cc.NAV_TIMEOUT_MS)
            await page.wait_for_timeout(2000)
            collected, unresolved = await download_all(
                context, page, targets, excluded)
            if guard.summary()["count"]:
                print(f"  note: the GET-only guard aborted "
                      f"{guard.summary()['count']} non-GET request(s) raised "
                      f"by the origin page used for the fetch fallback")
        finally:
            await browser.close()

    write_outputs(site, collected, unresolved, excluded)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", default="materials/deleteme")
    args = parser.parse_args()
    return asyncio.run(run(pathlib.Path(args.site_dir).resolve()))


if __name__ == "__main__":
    raise SystemExit(main())
