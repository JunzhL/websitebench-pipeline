#!/usr/bin/env python3
"""Turn the frozen rendered DOM into the candidate's served documents.

The source is a WordPress/Astra marketing tree plus two client-rendered SPAs
(Angular checkout, Next.js SSO).  The clone re-serves their *rendered*
presentation, so the highest-fidelity and least error-prone input is the
captured post-settle DOM rather than hand-transcribed copy.  This tool reads
``source-current/<capture>/<state>/<viewport>/page.html`` and writes a served
document per (state, viewport) into ``clone/frontend/pages/``.

What it changes, and why:

* **Every ``<script>`` element is removed.**  The capture is post-render, so
  the visual state already lives in the markup; re-running the source's own
  JavaScript would either hydrate the SPA over the server-rendered DOM or make
  a runtime request to a third party.  Both are forbidden.  The clone's own
  behaviour is added back as one clone-local bundle.
* **Every URL-bearing attribute and CSS ``url()`` is rewritten to a local
  path.**  Cross-subdomain document links map onto the single-origin path
  table; assets map onto their captured mirror under
  ``/static/assets/<capture>/``.  A reference whose payload was never captured
  is still rewritten to its deterministic mirror path, so it answers a local
  404 instead of leaving the origin -- a recorded known difference, never a
  substitute payload.
* **Third-party documents become a clone-local boundary page** at
  ``/external/<slug>``, so no served document carries a remote href.

Anything the candidate must compute at request time (order totals, session
state, the sandbox selector that replaces the card iframe) is spliced in by
``app.py`` against sentinel comments this tool writes, never by re-parsing the
document at runtime.

Report is printed as JSON.  Idempotent: rerunning replaces the outputs.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import urllib.parse

TOOLS = pathlib.Path(__file__).resolve().parent
SITE = TOOLS.parent
CLONE = SITE / "clone"
PAGES = CLONE / "frontend" / "pages"
CAPTURE_ID = "2026-08-19.ipvanish-r1"
CAPTURE_ROOT = SITE / "source-current" / CAPTURE_ID
ASSET_PREFIX = f"/static/assets/{CAPTURE_ID}"

sys.path.insert(0, str(SITE.parents[1] / "src"))

# --------------------------------------------------------------------------
# single-origin path table (scope/agent-handoff.md)
# --------------------------------------------------------------------------

FIRST_PARTY_HOSTS = {
    "www.ipvanish.com": "",
    "ipvanish.com": "",
    "checkout.ipvanish.com": "",
    "sso.ipvanish.com": "@sso",
    "support.ipvanish.com": "@support",
    "my.ipvanish.com": "@my",
    "account.ipvanish.com": "@my",
}

# Exact source document URLs that map onto a named clone route.
DOCUMENT_ALIASES = {
    "https://sso.ipvanish.com/": "/login",
    "https://sso.ipvanish.com": "/login",
    "https://sso.ipvanish.com/reset-password/": "/login/reset-password",
    "https://sso.ipvanish.com/reset-password": "/login/reset-password",
    "https://www.ipvanish.com/login/": "/login",
    "https://www.ipvanish.com/login": "/login",
    "https://support.ipvanish.com/hc/en-us": "/support",
    "https://support.ipvanish.com/hc/en-us/": "/support",
    "https://support.ipvanish.com/": "/support",
    "https://my.ipvanish.com/": "/account/",
    "https://my.ipvanish.com": "/account/",
}

# Captured states, in build order: (capture dir, served page name, viewport).
#
# One document is served per route regardless of viewport.  The source is a
# single responsive document -- the desktop, tablet and mobile captures of a
# route differ only by lazy-load progress, srcset selection and per-load
# tracking ids, never by structure -- so serving the desktop capture and
# letting the captured media queries do the rest is what the source does.
# `mobile-menu-open` is the one genuinely mobile-only interaction state.
STATES: tuple[tuple[str, str, str], ...] = (
    ("home", "home", "desktop"),
    ("pricing", "pricing", "desktop"),
    ("pricing-2year", "pricing-2year", "desktop"),
    ("pricing-yearly", "pricing-yearly", "desktop"),
    ("pricing-monthly", "pricing-monthly", "desktop"),
    ("nav-product", "nav-product", "desktop"),
    ("nav-apps", "nav-apps", "desktop"),
    ("nav-resources", "nav-resources", "desktop"),
    ("mobile-menu-open", "mobile-menu-open", "mobile"),
    ("why-vpn", "why-vpn", "desktop"),
    ("what-is-a-vpn", "what-is-a-vpn", "desktop"),
    ("servers", "servers", "desktop"),
    ("vpn-features", "vpn-features", "desktop"),
    ("money-back-guarantee", "money-back-guarantee", "desktop"),
    ("coupons", "coupons", "desktop"),
    ("reviews", "reviews", "desktop"),
    ("trust", "trust", "desktop"),
    ("no-log-vpn-policy", "no-log-vpn-policy", "desktop"),
    ("threat-protection", "threat-protection", "desktop"),
    ("secure-browser", "secure-browser", "desktop"),
    ("cloud-storage", "cloud-storage", "desktop"),
    ("vpn-setup-windows", "vpn-setup-windows", "desktop"),
    ("vpn-locations", "vpn-locations", "desktop"),
    ("vpn-for-streaming", "vpn-for-streaming", "desktop"),
    ("resources", "resources", "desktop"),
    ("setup-guides", "setup-guides", "desktop"),
    ("what-is-my-ip-address", "what-is-my-ip-address", "desktop"),
    ("blog", "blog", "desktop"),
    ("tos", "tos", "desktop"),
    ("privacy-policy", "privacy-policy", "desktop"),
    ("partners", "partners", "desktop"),
    ("press", "press", "desktop"),
    ("sso-signin", "sso-signin", "desktop"),
    ("sso-recovery", "sso-recovery", "desktop"),
    ("support-home", "support-home", "desktop"),
    ("checkout-chooser-essential-annual", "checkout-chooser-essential-annual", "desktop"),
    ("checkout-chooser-essential-monthly", "checkout-chooser-essential-monthly", "desktop"),
    ("checkout-chooser-advanced-annual", "checkout-chooser-advanced-annual", "desktop"),
    ("checkout-card-form-essential-annual", "checkout-card-form", "desktop"),
)

# --------------------------------------------------------------------------
# asset index
# --------------------------------------------------------------------------

KNOWN_ASSET_EXTS = {
    ".css", ".js", ".mjs", ".json", ".xml", ".txt", ".map",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav", ".pdf", ".gz", ".br",
}


def _mirror_relpath(url: str) -> str:
    """Reproduce tools/capture_assets.py::local_relpath minus the extension fix.

    The mirror tree collapses the query string into a short digest suffix and
    hashes over-long path segments.  Reproducing that here is what lets a
    document reference resolve onto the byte-exact mirror payload.
    """

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
            segments.append(
                f"h{digest}.{suffix}" if dot and len(suffix) <= 8 else f"h{digest}"
            )
        else:
            segments.append(segment)
    return f"{parts.netloc}/{'/'.join(segments)}"


def load_asset_index() -> tuple[dict[str, str], set[str]]:
    """Map mirror-relative keys onto the runtime path that actually exists."""

    manifest = json.loads(
        (SITE / "source-assets" / "manifest.json").read_text(encoding="utf-8")
    )
    exact: dict[str, str] = {}
    for asset in manifest["assets"]:
        relative = asset["runtime_path"].split(f"assets/{CAPTURE_ID}/", 1)[1]
        exact.setdefault(relative, relative)
        suffix = pathlib.PurePosixPath(relative).suffix
        if suffix:
            # capture_assets appends the true extension when the URL had none
            exact.setdefault(relative[: -len(suffix)], relative)
    promoted = set(exact.values())
    return exact, promoted


# --------------------------------------------------------------------------
# URL classification
# --------------------------------------------------------------------------

INERT_SCHEMES = ("data:", "mailto:", "tel:", "javascript:", "blob:", "about:")


def _slug(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    host = re.sub(r"[^a-z0-9]+", "-", parts.netloc.casefold()).strip("-")
    tail = re.sub(r"[^a-z0-9]+", "-", parts.path.casefold()).strip("-")
    digest = hashlib.sha256(url.encode()).hexdigest()[:8]
    stem = f"{host}-{tail}".strip("-")[:60].strip("-")
    return f"{stem}-{digest}" if stem else digest


class Rewriter:
    """Rewrite one captured document's references onto clone-local paths."""

    def __init__(self, base_url: str, asset_index: dict[str, str]) -> None:
        self.base_url = base_url
        self.assets = asset_index
        self.external: dict[str, str] = {}
        self.missing_assets: set[str] = set()
        # Local URLs the mirror does not hold.  The capture only kept the
        # payloads the browser actually fetched, so a responsive image's other
        # srcset widths are usually absent; leaving them in the attribute makes
        # the browser pick one and render a broken image at a viewport other
        # than the captured one.
        self.uncaptured_urls: set[str] = set()
        self.mapped = 0

    # -- classification ----------------------------------------------------

    def _looks_like_asset(self, url: str) -> bool:
        path = urllib.parse.urlsplit(url).path
        if pathlib.PurePosixPath(path).suffix.casefold() in KNOWN_ASSET_EXTS:
            return True
        return bool(
            re.search(r"/wp-(content|includes)/|/_next/|/assets/|/static/", path)
        )

    def _asset_url(self, url: str) -> str:
        key = _mirror_relpath(url)
        resolved = self.assets.get(key)
        local = f"{ASSET_PREFIX}/{resolved if resolved is not None else key}"
        if resolved is None:
            self.missing_assets.add(key)
            self.uncaptured_urls.add(local)
        else:
            self.mapped += 1
        return local

    def _document_url(self, url: str) -> str:
        stripped = url.split("#", 1)[0]
        alias = DOCUMENT_ALIASES.get(stripped) or DOCUMENT_ALIASES.get(
            stripped.rstrip("/") or "/"
        )
        if alias:
            fragment = url[len(stripped):]
            return alias + fragment
        parts = urllib.parse.urlsplit(url)
        host = parts.netloc.casefold()
        if host not in FIRST_PARTY_HOSTS:
            slug = _slug(url)
            self.external[slug] = url
            return f"/external/{slug}"
        path = parts.path or "/"
        if host == "sso.ipvanish.com":
            path = "/login" + ("" if path in {"", "/"} else path.rstrip("/"))
        elif host == "support.ipvanish.com":
            if path in {"", "/", "/hc/en-us", "/hc/en-us/"}:
                path = "/support"
            elif path.startswith("/hc/en-us"):
                path = "/support" + path[len("/hc/en-us"):]
            else:
                path = "/support" + path
        elif host in {"my.ipvanish.com", "account.ipvanish.com"}:
            path = "/account" + ("/" if path in {"", "/"} else path)
        local = urllib.parse.urlunsplit(("", "", path, parts.query, parts.fragment))
        return local or "/"

    def resolve(self, raw: str) -> str:
        value = raw.strip()
        if not value or value.startswith("#"):
            return raw
        if value.casefold().startswith(INERT_SCHEMES):
            return raw
        absolute = urllib.parse.urljoin(self.base_url, value)
        if not absolute.casefold().startswith(("http://", "https://")):
            return raw
        if self._looks_like_asset(absolute):
            return self._asset_url(absolute)
        return self._document_url(absolute)

    # -- attribute and CSS rewriting --------------------------------------

    _SRCSET_SPLIT = re.compile(r"\s*,\s*")

    def srcset(self, value: str) -> str:
        # A `data:` URI carries its own comma (`data:image/gif;base64,R0lGO...`),
        # so splitting on commas turns one placeholder into two bogus
        # candidates and resolves the base64 tail as a relative path. Every
        # lazy-load placeholder on this source is exactly that shape, and the
        # damage did not stop at the attribute: the bogus candidates then won
        # the `prune_uncaptured_images` fallback and overwrote the element's
        # real `data-src`, leaving images that could never render.
        if value.strip().casefold().startswith("data:"):
            return value
        parts = []
        for entry in self._SRCSET_SPLIT.split(value.strip()):
            if not entry:
                continue
            pieces = entry.split(None, 1)
            url = self.resolve(pieces[0])
            parts.append(url if len(pieces) == 1 else f"{url} {pieces[1]}")
        return ", ".join(parts)

    _CSS_URL = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<target>[^'")]+)(?P=q)\s*\)""")
    _CSS_IMPORT = re.compile(
        r"""@import\s+(?P<q>['"])(?P<target>[^'"]+)(?P=q)""", re.I
    )
    # Inline <style> blocks carry `/*# sourceURL=https://... */` provenance
    # comments.  They are inert, but repointing them at the mirror keeps them
    # truthful for the clone and keeps the closure audit unambiguous.
    _CSS_SOURCE_URL = re.compile(
        r"""(source(?:Mapping)?URL\s*=\s*)(?P<target>[^\s*'"]+)""", re.I
    )

    def css(self, text: str) -> str:
        def _url(match: re.Match[str]) -> str:
            target = match.group("target").strip()
            if target.casefold().startswith("data:"):
                return match.group(0)
            quote = match.group("q")
            return f"url({quote}{self.resolve(target)}{quote})"

        def _import(match: re.Match[str]) -> str:
            quote = match.group("q")
            return f"@import {quote}{self.resolve(match.group('target'))}{quote}"

        def _source(match: re.Match[str]) -> str:
            return f"{match.group(1)}{self.resolve(match.group('target'))}"

        return self._CSS_SOURCE_URL.sub(
            _source, self._CSS_IMPORT.sub(_import, self._CSS_URL.sub(_url, text))
        )


# attributes whose whole value is one URL
URL_ATTRS = (
    "href",
    "src",
    "poster",
    "action",
    "formaction",
    "data-src",
    "data-href",
    "data-bg",
    "data-large_image",
    "data-thumb",
    "xlink:href",
    "cite",
    "background",
)
SRCSET_ATTRS = ("srcset", "imagesrcset", "data-srcset")

_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.I | re.S)
_SCRIPT_SELF = re.compile(r"<script\b[^>]*/\s*>", re.I)
_STYLE_BLOCK = re.compile(r"(<style\b[^>]*>)(.*?)(</style\s*>)", re.I | re.S)
_STYLE_ATTR = re.compile(r"""(\sstyle\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
_META_URL_CONTENT = re.compile(
    r"""(<meta\b[^>]*?\b(?:property|name)\s*=\s*["']"""
    r"""(?:og:image(?::secure_url|:url)?|og:url|twitter:image(?::src)?"""
    r"""|msapplication-TileImage)["'][^>]*?\bcontent\s*=\s*)(["'])(.*?)\2""",
    re.I | re.S,
)
# Served documents are plain strings, never Jinja templates: the captured CSS
# is full of `){#id` sequences and one inline config carries `{{id}}`, so a
# template engine would have to be fought rather than used.  Dynamic content is
# spliced by app.py against HTML-comment sentinels instead.
# An SVG <use> pointing at "<this document's own URL>#symbol" is a same-document
# sprite reference the source serialized absolutely.  Rewriting it as a path
# would make the browser refetch a document to find a symbol already present.
_SPRITE_USE = re.compile(
    r"""(<use\b[^>]*?\b(?:xlink:href|href)\s*=\s*)(["'])"""
    r"""(?:https?:)?//[^"'#]*(#[^"']+)\2""",
    re.I,
)


def _attr_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"""(\s{re.escape(name)}\s*=\s*)(["'])(.*?)\2""", re.I | re.S
    )


_ATTR_PATTERNS = [(name, _attr_pattern(name)) for name in URL_ATTRS]
_SRCSET_PATTERNS = [(name, _attr_pattern(name)) for name in SRCSET_ATTRS]

CLONE_HEAD = (
    '<link rel="stylesheet" href="/static/site/clone.css">'
    "<!--ipvanish-clone-head-->"
)
MAIN_SENTINEL = "<!--ipvanish-clone-main-->"
# Astra does not switch its header layout by media query alone: its frontend
# script stamps `ast-desktop` or `ast-header-break-point` on <body> against a
# configured breakpoint, and its stylesheets key off that class. The desktop
# capture therefore serialized `ast-desktop`, which hid the mobile header's
# Get Started button at every viewport until the clone reproduced the switch.
# The breakpoint is read out of each capture rather than hardcoded.
_ASTRA_BREAKPOINT = re.compile(r'"break_point"\s*:\s*"(\d{2,4})"')


def clone_body(breakpoint: str | None) -> str:
    attribute = f' data-astra-breakpoint="{breakpoint}"' if breakpoint else ""
    return (
        "<!--ipvanish-clone-body-->"
        f'<script src="/static/site/clone.js" defer{attribute}></script>'
    )


_BASE_TAG = re.compile(r"""<base\b[^>]*?\bhref\s*=\s*(["'])(.*?)\1[^>]*>""", re.I)


def document_base(text: str, page_url: str) -> str:
    """The URL relative references actually resolved against on the source.

    The Angular checkout ships `<base href="/">`, so its relative stylesheet
    and chunk references resolve at the origin root rather than beside
    `/checkout/address-payment-method`.  Ignoring that pointed the whole
    checkout stylesheet at a path the mirror does not hold.
    """

    match = _BASE_TAG.search(text)
    if match is None:
        return page_url
    return urllib.parse.urljoin(page_url, match.group(2).strip())


# An <iframe> pointing at the clone's link boundary would load the full
# marketing shell into a 210x120 or 16:9 slot, which paints as a squashed page
# or -- for the YouTube embed on /why-vpn/ -- an empty dark rectangle. Embedded
# boundaries get their own compact panel route instead, sized by the captured
# iframe's own geometry, so the slot says what it is rather than showing a void.
_EMBED_FRAME = re.compile(r"<iframe\b[^>]*>", re.I)


def _embed_boundary(match: re.Match[str]) -> str:
    return match.group(0).replace("/external/", "/embed/")


_IMAGE_TAG = re.compile(r"<(?:img|source)\b[^>]*>", re.I)
_ATTR_VALUE = re.compile(r"""(\s(?:data-)?(?:src|srcset)\s*=\s*)(["'])(.*?)\2""", re.I)
_WIDTH_DESCRIPTOR = re.compile(r"^(\d+)w$")


def prune_uncaptured_images(text: str, rewriter: Rewriter) -> str:
    """Keep only the responsive candidates whose mirror payload exists.

    The capture kept the payloads the browser fetched at the captured viewport,
    so an image's other ``srcset`` widths are usually absent from the mirror.
    Serving the attribute unchanged makes a browser at any other viewport pick
    an absent width and render a broken image -- which is how the tablet and
    mobile home renders lost their logo.  Candidates the mirror does not hold
    are dropped, and a ``src`` whose own payload is absent falls back to the
    widest surviving candidate.  Nothing is substituted from elsewhere: an image
    with no captured payload at all still answers a local 404.
    """

    missing = rewriter.uncaptured_urls
    if not missing:
        return text

    def _rewrite_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        kept_candidates: list[tuple[int, str]] = []

        def _attr(attr: re.Match[str]) -> str:
            prefix, quote, value = attr.group(1), attr.group(2), attr.group(3)
            name = prefix.strip().rstrip("=").strip().casefold()
            if name.endswith("srcset"):
                if value.strip().casefold().startswith("data:"):
                    return attr.group(0)   # see Rewriter.srcset
                survivors = []
                for entry in (part.strip() for part in value.split(",")):
                    if not entry:
                        continue
                    pieces = entry.split(None, 1)
                    if pieces[0] in missing:
                        continue
                    survivors.append(entry)
                    descriptor = pieces[1].strip() if len(pieces) > 1 else ""
                    width = _WIDTH_DESCRIPTOR.match(descriptor)
                    kept_candidates.append(
                        (int(width.group(1)) if width else 0, pieces[0])
                    )
                return f"{prefix}{quote}{', '.join(survivors)}{quote}"
            return attr.group(0)

        tag = _ATTR_VALUE.sub(_attr, tag)

        def _fallback(attr: re.Match[str]) -> str:
            prefix, quote, value = attr.group(1), attr.group(2), attr.group(3)
            name = prefix.strip().rstrip("=").strip().casefold()
            if name.endswith("srcset") or value not in missing or not kept_candidates:
                return attr.group(0)
            widest = max(kept_candidates)[1]
            return f"{prefix}{quote}{widest}{quote}"

        return _ATTR_VALUE.sub(_fallback, tag)

    return _IMAGE_TAG.sub(_rewrite_tag, text)


def rewrite_document(text: str, base_url: str, rewriter: Rewriter) -> tuple[str, int]:
    """Strip source scripts, localize every reference, add the clone bundle."""

    breakpoint_match = _ASTRA_BREAKPOINT.search(text)
    body_bundle = clone_body(
        breakpoint_match.group(1) if breakpoint_match else None
    )
    scripts = len(_SCRIPT.findall(text)) + len(_SCRIPT_SELF.findall(text))
    text = _SCRIPT_SELF.sub("", _SCRIPT.sub("", text))
    # The clone serves one origin at the root, so the source <base> is both
    # unnecessary and (for /checkout/...) actively wrong once paths are local.
    text = re.sub(r"<base\b[^>]*>", "", text, flags=re.I)
    text = _SPRITE_USE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(2)}", text)

    for _name, pattern in _ATTR_PATTERNS:
        text = pattern.sub(
            lambda m: f"{m.group(1)}{m.group(2)}"
            f"{rewriter.resolve(m.group(3))}{m.group(2)}",
            text,
        )
    for _name, pattern in _SRCSET_PATTERNS:
        text = pattern.sub(
            lambda m: f"{m.group(1)}{m.group(2)}"
            f"{rewriter.srcset(m.group(3))}{m.group(2)}",
            text,
        )
    text = _META_URL_CONTENT.sub(
        lambda m: f"{m.group(1)}{m.group(2)}"
        f"{rewriter.resolve(m.group(3))}{m.group(2)}",
        text,
    )
    text = _STYLE_BLOCK.sub(
        lambda m: f"{m.group(1)}{rewriter.css(m.group(2))}{m.group(3)}", text
    )
    text = _STYLE_ATTR.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{rewriter.css(m.group(3))}{m.group(2)}",
        text,
    )

    text = prune_uncaptured_images(text, rewriter)
    text = _EMBED_FRAME.sub(_embed_boundary, text)

    if "</head>" in text:
        text = text.replace("</head>", CLONE_HEAD + "</head>", 1)
    if "</body>" in text:
        text = text.replace("</body>", body_bundle + "</body>", 1)
    else:
        text += body_bundle
    return text, scripts


REMOTE_REF = re.compile(
    r"(?i)(?:src|href|action|url)\s*[=(:]\s*[\"']?\s*"
    r"(?:https?:)?//(?!localhost|127\.0\.0\.1)[a-z0-9.-]+\.[a-z]{2,}"
)


def main() -> int:
    asset_index, _ = load_asset_index()
    PAGES.mkdir(parents=True, exist_ok=True)
    for stale in PAGES.glob("*.html"):
        stale.unlink()

    external: dict[str, str] = {}
    missing: dict[str, list[str]] = {}
    report = []
    for state, page, viewport in STATES:
        viewport_dir = CAPTURE_ROOT / state / viewport
        source = viewport_dir / "page.html"
        if not source.is_file():
            raise SystemExit(f"missing capture: {source}")
        meta = json.loads(
            (viewport_dir / "meta.json").read_text(encoding="utf-8")
        )
        base_url = meta.get("final_url") or meta["requested_url"]
        raw = source.read_text(encoding="utf-8", errors="replace")
        rewriter = Rewriter(document_base(raw, base_url), asset_index)
        document, scripts = rewrite_document(raw, base_url, rewriter)
        residue = sorted({m.group(0) for m in REMOTE_REF.finditer(document)})
        if residue:
            raise SystemExit(
                f"{state}/{viewport}: {len(residue)} remote "
                f"references survived rewriting: {residue[:5]}"
            )
        name = f"{page}.html"
        (PAGES / name).write_text(document, encoding="utf-8")
        external.update(rewriter.external)
        if rewriter.missing_assets:
            missing[name] = sorted(rewriter.missing_assets)
        report.append(
            {
                "page": name,
                "state": state,
                "viewport": viewport,
                "base_url": base_url,
                "source_bytes": len(raw),
                "served_bytes": len(document),
                "scripts_removed": scripts,
                "assets_mapped": rewriter.mapped,
                "assets_uncaptured": len(rewriter.missing_assets),
                "external_boundaries": len(rewriter.external),
            }
        )

    # One reusable shell for the clone-local pages the source never served:
    # the captured marketing chrome with an empty <main>, so an inference page
    # sits inside real header/footer/CSS instead of an invented layout.
    sys.path.insert(0, str(CLONE))
    from htmlslice import replace_inner  # noqa: PLC0415

    shell = replace_inner(
        (PAGES / "home.html").read_text(encoding="utf-8"),
        '<main id="main" class="site-main">',
        MAIN_SENTINEL,
    )
    if shell.count(MAIN_SENTINEL) != 1:
        raise SystemExit("shell sentinel was not spliced exactly once")
    (PAGES / "_shell.html").write_text(shell, encoding="utf-8")

    (CLONE / "frontend" / "external-links.json").write_text(
        json.dumps(dict(sorted(external.items())), indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (CLONE / "frontend" / "build-report.json").write_text(
        json.dumps(
            {
                "capture_id": CAPTURE_ID,
                "pages": report,
                "external_boundaries": len(external),
                "uncaptured_references": missing,
            },
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "pages_written": len(report),
                "served_bytes": sum(row["served_bytes"] for row in report),
                "scripts_removed": sum(row["scripts_removed"] for row in report),
                "external_boundaries": len(external),
                "uncaptured_reference_keys": sum(
                    len(value) for value in missing.values()
                ),
            },
            indent=1,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
