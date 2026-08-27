#!/usr/bin/env python3
"""Build the served documents of the `deleteme` offline clone.

The candidate never re-templates a marketing page by hand.  Every document it
serves is the *frozen rendered DOM* from
``source-current/2026-08-20.deleteme-r1/<unit>/<viewport>/page.html`` with

  1. every ``<script>`` removed (the source's own runtime never runs here),
  2. every sub-resource reference rewritten onto the local mirror at
     ``/static/assets/<capture-id>/<host>/<path>``,
  3. every off-origin *document* link folded onto a clone-local boundary page,
  4. every mirrored stylesheet re-emitted through the same localisation pass,
     because a pristine mirror payload keeps the source's own absolute and
     root-relative ``url()`` targets and would fetch them from the clone origin
     (or worse, from Google) at runtime, and
  5. every price replaced by a build-time sentinel, so the server derives the
     figure from ``clone/backend/catalogue.py`` and no formatted price string is
     ever hard-coded into a document.

Five defect classes from earlier sites are handled explicitly here rather than
left to review:

* ``data:`` URIs are never split on their own comma (a base64 payload contains
  one; splitting it fabricates a relative candidate that then wins a fallback);
* ``data-src`` / ``data-srcset`` are collected and localised, because this
  source lazy-loads below the fold and those payloads were never *requested*
  during capture even though the asset pass mirrored them from the markup;
* a ``srcset`` candidate whose payload is missing from the mirror is pruned, and
  if pruning empties the attribute the element's plain ``src`` is repaired from
  the widest surviving candidate;
* mirrored stylesheets go through the localisation pass (step 4 above);
* the build fails - it does not warn - if any remote reference survives.

The pass is deterministic and idempotent: outputs are wiped and rewritten from
the frozen capture on every run, never patched in place.

Usage::

    python tools/build_clone_pages.py            # build pages + assets
    python tools/build_clone_pages.py --check    # build into a temp dir, diff
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import html
import json
import pathlib
import re
import shutil
import sys
import urllib.parse

TOOLS = pathlib.Path(__file__).resolve().parent
SITE = TOOLS.parent
CLONE = SITE / "clone"
PAGES = CLONE / "frontend" / "pages"
STATIC = CLONE / "static"
VENDOR_CSS = STATIC / "site" / "vendor"

CAPTURE_ID = "2026-08-20.deleteme-r1"
CAPTURE_ROOT = SITE / "source-current" / CAPTURE_ID
ASSET_MIRROR = SITE / "source-assets" / CAPTURE_ID
ASSET_MANIFEST = SITE / "source-assets" / "manifest.json"
ASSET_PREFIX = f"/static/assets/{CAPTURE_ID}"

# `htmlslice` is the candidate's own slicer; the build uses the same one so the
# shell it writes and the splices the server makes cannot drift apart.
if str(CLONE) not in sys.path:
    sys.path.insert(0, str(CLONE))

# ---------------------------------------------------------------------------
# what gets built
# ---------------------------------------------------------------------------

# (capture unit, served page name, viewport).  One document is served per route
# at every viewport: the captured DOM is the same at 1440, 834 and 390 apart
# from cache-busting query nonces inside tracking URLs that this pass strips
# anyway, and the source's own media queries do the responsive work.
STATES: tuple[tuple[str, str, str], ...] = (
    ("home", "home", "desktop"),
    ("plans", "plans", "desktop"),
    ("pricing", "pricing", "desktop"),
    ("signup-grid", "signup-grid", "desktop"),
    ("scan", "scan", "desktop"),
    ("how-we-work", "how-we-work", "desktop"),
    ("sites-we-remove-from", "sites-we-remove-from", "desktop"),
    ("reviews", "reviews", "desktop"),
    ("about", "about", "desktop"),
    ("security", "security", "desktop"),
    ("international", "international", "desktop"),
    ("how-public-record", "how-public-record", "desktop"),
    ("blog", "blog", "desktop"),
    ("opt-out-guides", "opt-out-guides", "desktop"),
    ("delete-your-account", "delete-your-account", "desktop"),
    ("doxxing", "doxxing", "desktop"),
    ("is-site-safe", "is-site-safe", "desktop"),
    ("is-it-scam", "is-it-scam", "desktop"),
    ("glossary", "glossary", "desktop"),
    ("do-not-call-list", "do-not-call-list", "desktop"),
    ("ai-privacy-settings", "ai-privacy-settings", "desktop"),
    ("data-breaches", "data-breaches", "desktop"),
    ("podcast", "podcast", "desktop"),
    ("permission-slip", "permission-slip", "desktop"),
    ("permission-slip-faq", "permission-slip-faq", "desktop"),
    ("press", "press", "desktop"),
    ("careers", "careers", "desktop"),
    ("help", "help", "desktop"),
    ("policies", "policies", "desktop"),
    ("not-found.not-found", "not-found", "desktop"),
    ("search.no-results", "search", "desktop"),
    # application host (React-Router SPA); the captured DOM is the rendered one
    ("login", "login", "desktop"),
    ("password-forgot", "password-forgot", "desktop"),
    ("checkout-complete", "checkout-complete", "desktop"),
    ("app-not-found.not-found", "app-not-found", "desktop"),
    # the checkout unit captured an expired-session screen, never the form;
    # it is kept as the app-host shell the clone-local form is spliced into.
    ("checkout", "checkout-shell", "desktop"),
)

# Hosts the capture treats as this site.  `static-asset.` is an asset CDN, so it
# is first party for assets but never a document destination.
FIRST_PARTY_HOSTS = frozenset(
    {
        "joindeleteme.com",
        "www.joindeleteme.com",
        "app.joindeleteme.com",
        "help.joindeleteme.com",
        "privacy.joindeleteme.com",
        "static-asset.joindeleteme.com",
        "getabine.zendesk.com",
    }
)

# Single-origin mapping.  The source splits the experience across four hosts;
# the clone serves one.  Keys are matched with and without a trailing slash.
DOCUMENT_ALIASES: dict[str, str] = {
    "https://app.joindeleteme.com/checkout": "/checkout",
    "https://app.joindeleteme.com/checkout/complete": "/checkout/complete",
    "https://app.joindeleteme.com/login": "/login",
    "https://app.joindeleteme.com/password/forgot": "/password/forgot",
    "https://app.joindeleteme.com/": "/account",
    "https://help.joindeleteme.com/hc/en-us": "/help",
    "https://help.joindeleteme.com/": "/help",
    "https://getabine.zendesk.com/hc/en-us": "/help",
    "https://privacy.joindeleteme.com/policies": "/policies",
    "https://privacy.joindeleteme.com/": "/policies",
}

# Per-host fallback folding for anything the alias table does not name.
HOST_FOLD: tuple[tuple[str, str], ...] = (
    ("app.joindeleteme.com", "/account"),
    ("help.joindeleteme.com", "/help"),
    ("getabine.zendesk.com", "/help"),
    ("privacy.joindeleteme.com", "/policies"),
)

INERT_SCHEMES = ("data:", "mailto:", "tel:", "javascript:", "blob:", "about:", "sms:")

KNOWN_ASSET_EXTS = frozenset(
    {
        ".css",
        ".js",
        ".mjs",
        ".json",
        ".map",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".avif",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".mp4",
        ".webm",
        ".pdf",
    }
)
ASSET_PATH_HINT = re.compile(
    r"/wp-(?:content|includes)/|/assets/|/hc/theming_assets/|/hc/assets/"
    r"|/myicons/|/af/\d|/p\.css|^/css2$"
)

URL_ATTRS = (
    "href",
    "src",
    "poster",
    "action",
    "formaction",
    "data-src",
    "data-href",
    "data-bg",
    "data-thumb",
    "data-large_image",
    "xlink:href",
    "cite",
    "background",
)
SRCSET_ATTRS = ("srcset", "imagesrcset", "data-srcset")
ASSET_URL_ATTRS = frozenset(
    {
        "src",
        "poster",
        "data-src",
        "data-bg",
        "data-thumb",
        "data-large_image",
        "background",
    }
)

# Anything whose only job is to open a socket to a remote host.
_DROP_LINK_RELS = frozenset(
    {"preconnect", "dns-prefetch", "prefetch", "preload", "modulepreload", "prerender"}
)

# A reference the clone must never make and cannot mirror.  The build marks it,
# then removes the element that carried it; nothing is substituted from
# elsewhere.  In a stylesheet, where a declaration cannot be removed with a
# regex without corrupting the rule, it points at a deliberately empty
# clone-local stand-in whose only job is to be honest about the hole.
DROP = "\x00websitebench-drop"
ABSENT_ASSET = "/static/site/absent-third-party.svg"

CLONE_HEAD_SENTINEL = "<!--deleteme-clone-head-->"
CLONE_BODY_SENTINEL = "<!--deleteme-clone-body-->"
MAIN_SENTINEL = "<!--deleteme-clone-main-->"

# The static diagnostic's own rule, duplicated so the build fails before the
# diagnostic ever sees the page.
REMOTE_REF = re.compile(
    r"(?i)(?:src|href|action|url)\s*[=(:]\s*[\"']?\s*"
    r"(?:https?:)?//(?!localhost|127\.0\.0\.1)[a-z0-9.-]+\.[a-z]{2,}"
)
MONEY = re.compile(r"\$\s?\d[\d,]*\.\d\d")


# ---------------------------------------------------------------------------
# mirror addressing
# ---------------------------------------------------------------------------


def mirror_relpath(url: str) -> str:
    """Reproduce ``tools/capture_assets.py::local_relpath`` minus the extension
    repair, which depends on a response content type this pass does not have.

    The mirror folds a query string into a short digest suffix, so two srcset
    widths that differ only by query still land in two distinct files; the
    alias index below covers the extension-repair case.
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
    return f"{parts.netloc.casefold()}/{'/'.join(segments)}"


def load_asset_index() -> dict[str, str]:
    """key -> mirror-relative path actually on disk.

    Two keys per asset: the exact ``mirror_relpath`` of its source URL, and the
    extensionless stem, because ``capture_assets`` appends a real extension when
    the source URL carried none (``/css2?...`` -> ``css2.q<digest>.css``).
    """

    manifest = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
    index: dict[str, str] = {}
    marker = f"assets/{CAPTURE_ID}/"
    for asset in manifest["assets"]:
        runtime = asset["runtime_path"]
        _, _, relative = runtime.partition(marker)
        if not relative:
            raise SystemExit(f"asset runtime_path outside the mirror: {runtime}")
        index[relative] = relative
        stem = relative.rsplit(".", 1)[0]
        index.setdefault(stem, relative)
        index.setdefault(mirror_relpath(asset["source_url"]), relative)
    return index


def slugify(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    tail = re.sub(r"[^a-z0-9]+", "-", (parts.path + parts.query).casefold()).strip("-")
    host = re.sub(r"[^a-z0-9]+", "-", parts.netloc.casefold()).strip("-")
    base = f"{host}-{tail}".strip("-")[:60].strip("-")
    return f"{base}-{hashlib.sha256(url.encode()).hexdigest()[:8]}"


# ---------------------------------------------------------------------------
# the rewriter
# ---------------------------------------------------------------------------


class Rewriter:
    _SRCSET_SPLIT = re.compile(r"\s*,\s*")
    _CSS_URL = re.compile(r"""url\(\s*(?P<q>['"]?)(?P<target>[^'")]+)(?P=q)\s*\)""")
    _CSS_IMPORT = re.compile(r"""@import\s+(?P<q>['"])(?P<target>[^'"]+)(?P=q)""")
    _CSS_PROVENANCE = re.compile(r"/\*#\s*source(?:Mapping)?URL=[^*]*\*/")

    def __init__(self, base_url: str, assets: dict[str, str]) -> None:
        self.base = base_url
        self.assets = assets
        self.external: dict[str, str] = {}
        self.missing: set[str] = set()
        self.uncaptured_first_party: set[str] = set()
        self.mapped = 0
        self.dropped_css = 0

    # -- classification ----------------------------------------------------
    def resolve(self, raw: str, *, force_asset: bool = False) -> str:
        value = raw.strip()
        if not value or value.startswith("#"):
            return raw
        if value.casefold().startswith(INERT_SCHEMES):
            return raw
        try:
            absolute = urllib.parse.urljoin(self.base, value)
        except ValueError:
            return raw
        parts = urllib.parse.urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            return raw
        if force_asset or self._looks_like_asset(parts):
            return self.asset_url(absolute)
        return self.document_url(absolute)

    @staticmethod
    def _looks_like_asset(parts: urllib.parse.SplitResult) -> bool:
        suffix = pathlib.PurePosixPath(parts.path).suffix.casefold()
        if suffix in KNOWN_ASSET_EXTS:
            return True
        return bool(ASSET_PATH_HINT.search(parts.path))

    # -- assets ------------------------------------------------------------
    def asset_url(self, absolute: str) -> str:
        key = mirror_relpath(absolute)
        resolved = self.assets.get(key)
        if resolved is None:
            # `capture_assets` appends a real extension when the URL had none.
            resolved = self.assets.get(key.rsplit(".", 1)[0])
        if resolved is not None:
            self.mapped += 1
            return f"{ASSET_PREFIX}/{resolved}"
        parts = urllib.parse.urlsplit(absolute)
        if parts.netloc.casefold() in FIRST_PARTY_HOSTS:
            # Not mirrored, but it is this site's own path: answer it the way
            # the clone answers any unknown path of its own rather than
            # inventing a mirror entry that will never exist.
            self.uncaptured_first_party.add(key)
            query = f"?{parts.query}" if parts.query else ""
            return f"{parts.path or '/'}{query}"
        # A third-party payload the capture deliberately never fetched: the
        # consent platform, an ad pixel, live Maps.  Pointing it at a mirror
        # path would answer a local 404 for ever; the reference is removed and
        # recorded instead.
        self.missing.add(key)
        return DROP

    def asset_is_mirrored(self, raw: str) -> bool:
        value = raw.strip()
        if not value or value.casefold().startswith(INERT_SCHEMES):
            return True
        if value.startswith(ASSET_PREFIX):
            key = value[len(ASSET_PREFIX) + 1 :].split("?", 1)[0]
            return (ASSET_MIRROR / key).is_file()
        return True

    # -- documents ---------------------------------------------------------
    def document_url(self, absolute: str) -> str:
        parts = urllib.parse.urlsplit(absolute)
        fragment = f"#{parts.fragment}" if parts.fragment else ""
        query = f"?{parts.query}" if parts.query else ""
        bare = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, parts.query, "")
        )
        # Alias on the path alone: the plan grid's CTA carries the selection in
        # the query (`?plan=...&term=1&qty=1`) and must still fold onto
        # `/checkout`, which is exactly the mapping the P0 journey walks.
        path_only = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, "", "")
        )
        for candidate in (path_only, path_only.rstrip("/"), path_only.rstrip("/") + "/"):
            if candidate in DOCUMENT_ALIASES:
                return DOCUMENT_ALIASES[candidate] + query + fragment
        host = parts.netloc.casefold()
        if host not in FIRST_PARTY_HOSTS:
            slug = slugify(bare)
            self.external[slug] = bare
            return f"/external/{slug}"
        for prefix, root in HOST_FOLD:
            if host == prefix:
                tail = parts.path if parts.path not in ("", "/") else ""
                return f"{root}{tail}{query}{fragment}"
        return f"{parts.path or '/'}{query}{fragment}"

    # -- srcset ------------------------------------------------------------
    def srcset(self, value: str) -> str:
        """Rewrite a srcset, one candidate at a time.

        A ``data:`` URI carries its own comma (``data:image/gif;base64,R0lGO...``)
        so splitting the attribute on commas turns one candidate into two bogus
        ones and resolves the base64 tail as a relative path.  On an earlier
        site those bogus candidates then won the missing-src fallback and
        overwrote the element's real ``data-src``, so fifty images could never
        render.  A value that *is* a bare data URI is returned untouched.
        """

        if value.strip().casefold().startswith("data:"):
            return value
        out: list[str] = []
        for entry in self._SRCSET_SPLIT.split(value.strip()):
            if not entry:
                continue
            if entry.casefold().startswith("data:"):
                out.append(entry)
                continue
            pieces = entry.split(None, 1)
            url = self.resolve(pieces[0], force_asset=True)
            if url == DROP:
                continue
            out.append(url if len(pieces) == 1 else f"{url} {pieces[1]}")
        return ", ".join(out)

    # -- css ---------------------------------------------------------------
    def css(self, text: str) -> str:
        def _url(match: re.Match[str]) -> str:
            target = match.group("target").strip()
            # A `style="..."` attribute in serialised HTML carries `&quot;`
            # where CSS would carry `"`.  Splitting on the literal quote alone
            # swallowed the entity into the URL and produced a reference no
            # mirror could ever answer.
            entity = ""
            for candidate in ("&quot;", "&#34;", "&#039;", "&#39;", "&apos;"):
                if target.startswith(candidate) and target.endswith(candidate):
                    entity = candidate
                    target = target[len(candidate) : -len(candidate)].strip()
                    break
            if target.casefold().startswith(INERT_SCHEMES):
                return match.group(0)
            local = self.resolve(target, force_asset=True)
            if local == DROP:
                local = ABSENT_ASSET
                self.dropped_css += 1
            if entity:
                return f"url({entity}{local}{entity})"
            return f'url("{local}")'

        def _import(match: re.Match[str]) -> str:
            target = match.group("target").strip()
            if target.casefold().startswith(INERT_SCHEMES):
                return match.group(0)
            local = self.resolve(target, force_asset=True)
            if local == DROP:
                return "/* websitebench: third-party import removed */"
            return f'@import "{local}"'

        text = self._CSS_PROVENANCE.sub("", text)
        text = self._CSS_URL.sub(_url, text)
        return self._CSS_IMPORT.sub(_import, text)


# ---------------------------------------------------------------------------
# document rewriting
# ---------------------------------------------------------------------------

_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.I | re.S)
_SCRIPT_SELF = re.compile(r"<script\b[^>]*/\s*>", re.I)
_NOSCRIPT = re.compile(r"<noscript\b[^>]*>.*?</noscript\s*>", re.I | re.S)
_BASE_TAG = re.compile(r"<base\b[^>]*>", re.I)
_STYLE_BLOCK = re.compile(r"(<style\b[^>]*>)(.*?)(</style\s*>)", re.I | re.S)
_STYLE_ATTR = re.compile(r"""(\sstyle\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
_IFRAME_TAG = re.compile(r"<iframe\b[^>]*>", re.I)
_SPRITE_USE = re.compile(
    r"""(<use\b[^>]*\sxlink:href\s*=\s*)(["'])https?://[^"'#]*(#[^"']+)\2""", re.I
)
_WIDTH_DESCRIPTOR = re.compile(r"^(\d+)w$")
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)


def _attr_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"""(\s{re.escape(name)}\s*=\s*)(["'])(.*?)\2""", re.I | re.S)


_ATTR_PATTERNS = [(name, _attr_pattern(name)) for name in URL_ATTRS]
_SRCSET_PATTERNS = [(name, _attr_pattern(name)) for name in SRCSET_ATTRS]


def _read_attr(tag: str, name: str) -> str | None:
    match = _attr_pattern(name).search(tag)
    return match.group(3) if match else None


def _set_attr(tag: str, name: str, value: str) -> str:
    pattern = _attr_pattern(name)
    if pattern.search(tag):
        return pattern.sub(
            lambda m: f'{m.group(1)}{m.group(2)}{value}{m.group(2)}', tag, count=1
        )
    return tag[:-1].rstrip() + f' {name}="{value}">'


def _drop_attr(tag: str, name: str) -> str:
    return _attr_pattern(name).sub("", tag, count=1)


def strip_remote_link_hints(document: str) -> str:
    """Remove the tags whose only effect is a socket to a remote host."""

    def _link(match: re.Match[str]) -> str:
        tag = match.group(0)
        rel = (_read_attr(tag, "rel") or "").casefold().split()
        if any(item in _DROP_LINK_RELS for item in rel):
            href = (_read_attr(tag, "href") or "").strip()
            if href.startswith(("http://", "https://", "//")):
                return ""
        return tag

    return _LINK_TAG.sub(_link, document)


_DROPPABLE_ELEMENT = re.compile(
    r"<(?P<name>img|source|track|embed|input|link)\b[^>]*>", re.I
)
_DROPPABLE_CONTAINER = re.compile(
    r"<(?P<name>iframe|video|audio|object|picture)\b[^>]*>", re.I
)


def remove_dropped_references(document: str) -> tuple[str, int]:
    """Delete every element left holding a reference the clone will not make.

    These are the declared third-party origins in
    ``source-assets/excluded-requests.json`` - ad pixels, the consent platform,
    live Maps, live Stripe.  Leaving them pointed at a mirror path that will
    never exist would answer a local 404 on every page view, which is the exact
    defect the ``local-reference-closure`` invariant exists to stop.
    """

    if DROP not in document:
        return document, 0

    removed = 0

    def _void(match: re.Match[str]) -> str:
        nonlocal removed
        if DROP not in match.group(0):
            return match.group(0)
        removed += 1
        return ""

    document = _DROPPABLE_ELEMENT.sub(_void, document)

    from htmlslice import element_span  # noqa: PLC0415

    while True:
        match = _DROPPABLE_CONTAINER.search(document)
        found = None
        for match in _DROPPABLE_CONTAINER.finditer(document):
            if DROP in match.group(0):
                found = match
                break
        if found is None:
            break
        try:
            _, _, end = element_span(document, found.group(0))
        except ValueError:
            end = found.end()
        document = document[: found.start()] + document[end:]
        removed += 1

    # anything left is an attribute on an element worth keeping
    document = re.sub(rf'\s[a-zA-Z:_-]+="{re.escape(DROP)}"', "", document)
    document = document.replace(DROP, "")
    return document, removed


def prune_uncaptured_images(document: str, rewriter: Rewriter) -> str:
    """Drop advertised responsive widths the mirror cannot serve.

    A browser at device pixel ratio 1 picks a width that exists; at 2 or 3 it
    picks the one that does not, and the image breaks in a way static closure,
    a viewport-crop pixel oracle and a ratio-1 review all miss.  If pruning
    empties a srcset the element keeps its plain ``src``; if the ``src`` itself
    is missing it falls back to the widest surviving candidate rather than to
    an unrelated payload.
    """

    def _img(match: re.Match[str]) -> str:
        tag = match.group(0)
        for name in ("srcset", "data-srcset", "imagesrcset"):
            value = _read_attr(tag, name)
            if not value or value.strip().casefold().startswith("data:"):
                continue
            kept: list[str] = []
            for entry in value.split(","):
                entry = entry.strip()
                if not entry:
                    continue
                url = entry.split(None, 1)[0]
                if rewriter.asset_is_mirrored(url):
                    kept.append(entry)
            if kept:
                tag = _set_attr(tag, name, ", ".join(kept))
            else:
                tag = _drop_attr(tag, name)
        for src_name, set_name in (("src", "srcset"), ("data-src", "data-srcset")):
            src = _read_attr(tag, src_name)
            if src is None or rewriter.asset_is_mirrored(src):
                continue
            widest: tuple[int, str] | None = None
            for name in (set_name, "srcset", "data-srcset"):
                value = _read_attr(tag, name)
                if not value or value.strip().casefold().startswith("data:"):
                    continue
                for entry in value.split(","):
                    pieces = entry.strip().split(None, 1)
                    if not pieces:
                        continue
                    width_match = (
                        _WIDTH_DESCRIPTOR.match(pieces[1].strip())
                        if len(pieces) > 1
                        else None
                    )
                    width = int(width_match.group(1)) if width_match else 0
                    if widest is None or width > widest[0]:
                        widest = (width, pieces[0])
            if widest is not None:
                tag = _set_attr(tag, src_name, widest[1])
        return tag

    return _IMG_TAG.sub(_img, document)


def localise_iframes(document: str, rewriter: Rewriter) -> str:
    """An iframe is a real request; an off-origin one never leaves the clone."""

    def _iframe(match: re.Match[str]) -> str:
        tag = match.group(0)
        src = (_read_attr(tag, "src") or "").strip()
        if src.startswith("/external/"):
            return _set_attr(tag, "src", src.replace("/external/", "/embed/", 1))
        return tag

    return _IFRAME_TAG.sub(_iframe, document)


def rewrite_document(
    text: str, base_url: str, rewriter: Rewriter
) -> tuple[str, int, int]:
    scripts = len(_SCRIPT.findall(text)) + len(_SCRIPT_SELF.findall(text))
    text = _SCRIPT.sub("", text)
    text = _SCRIPT_SELF.sub("", text)
    # `<noscript>` bodies are exactly the tracking pixels the source falls back
    # to when its own runtime is gone, which is the state this clone ships in.
    text = _NOSCRIPT.sub("", text)
    text = _BASE_TAG.sub("", text)
    text = strip_remote_link_hints(text)
    text = _SPRITE_USE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(2)}", text)

    for name, pattern in _ATTR_PATTERNS:
        text = pattern.sub(
            lambda m: (
                f"{m.group(1)}{m.group(2)}"
                f"{rewriter.resolve(m.group(3), force_asset=name in ASSET_URL_ATTRS)}"
                f"{m.group(2)}"
            ),
            text,
        )
    for _, pattern in _SRCSET_PATTERNS:
        text = pattern.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{rewriter.srcset(m.group(3))}{m.group(2)}",
            text,
        )
    text = _STYLE_BLOCK.sub(
        lambda m: f"{m.group(1)}{rewriter.css(m.group(2))}{m.group(3)}", text
    )
    text = _STYLE_ATTR.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{rewriter.css(m.group(3))}{m.group(2)}", text
    )
    text, dropped = remove_dropped_references(text)
    text = prune_uncaptured_images(text, rewriter)
    text = localise_iframes(text, rewriter)
    return text, scripts, dropped


# ---------------------------------------------------------------------------
# price sentinels
# ---------------------------------------------------------------------------

PRICE_KEY = r"price(?:1Year|2Years)(?:1Person|2People|4People)"
PRICE_FIELDS = "new-price|original-price|annual-price|biennial-price|disclaimer"
_PRICE_ELEMENT = re.compile(
    rf"""(<(?P<tag>span|strong|p|div|em|b)\b[^>]*\bclass="[^"]*\b"""
    rf"""(?P<key>{PRICE_KEY})-(?P<field>{PRICE_FIELDS})\b[^"]*"[^>]*>)"""
    rf"""(?P<inner>[^<]*)(?P<close></(?P=tag)>)"""
)


def slot_prices(document: str) -> tuple[str, int]:
    """Replace every rendered price with a build-time sentinel.

    The server fills these from ``backend/catalogue.py`` at request time, in
    integer minor units, so no formatted price string is ever hard-coded and a
    catalogue change cannot leave a stale figure in a document.
    """

    count = 0

    def _slot(match: re.Match[str]) -> nonlocal_str:  # type: ignore[valid-type]
        nonlocal count
        count += 1
        token = f"{match.group('key')}.{match.group('field')}"
        return f"{match.group(1)}<!--wb:price:{token}-->{match.group('close')}"

    return _PRICE_ELEMENT.sub(_slot, document), count


nonlocal_str = str  # keeps the annotation above readable without a forward ref


# ---------------------------------------------------------------------------
# operability hooks
# ---------------------------------------------------------------------------

_FILTER_CONTROL = re.compile(r"""(<li\b(?P<attrs>[^>]*\suk-filter-control="[^"]*")[^>]*)>""")
_TERM_GROUP = re.compile(
    r"""(<(?:div|li)\b[^>]*\sdata-(?:tag|term)="(?P<tag>1-Year|2-Years|1y|2y)"[^>]*)>"""
)
_CHECKOUT_LINK = re.compile(
    r"""(<a\b[^>]*\shref="(?P<href>/checkout\?[^"]*)"[^>]*)>""", re.I
)
# `uk-filter-control` ships in two notations on this source: a JSON object
# (`{"filter":"[data-tag~=\"1-Year\"]","group":"tags"}`, HTML-escaped) on the
# yootheme grids, and UIkit's shorthand (`filter: [data-term='1y']; group: term`)
# on the newer `/pricing/` grid.  Both name the same thing.
_TERM_IN_CONTROL = re.compile(
    r"""data-tag~=\\?&quot;(?P<a>1-Year|2-Years)\\?&quot;|data-term='(?P<b>1y|2y)'"""
)


def mark_plan_controls(document: str) -> tuple[str, dict[str, int]]:
    """Give the plan grid the stable hooks the frozen verify driver clicks.

    The source drives these strips with UIkit, whose bundle this pass strips, so
    ``static/site/clone.js`` reimplements the same behaviour from the same
    attributes.  Marking is additive: nothing the source shipped is renamed, and
    the hidden size-filter container keeps its ``display:none`` because no
    visitor can operate it.
    """

    counts = {"term_controls": 0, "term_groups": 0, "checkout_links": 0}

    def _control(match: re.Match[str]) -> str:
        term = _TERM_IN_CONTROL.search(match.group("attrs"))
        if term is None:
            return match.group(0)
        counts["term_controls"] += 1
        raw = term.group("a") or term.group("b")
        slug = "1y" if raw in ("1-Year", "1y") else "2y"
        return f'{match.group(1)} data-term-tab="{slug}">'

    def _group(match: re.Match[str]) -> str:
        counts["term_groups"] += 1
        raw = match.group("tag")
        slug = "1y" if raw in ("1-Year", "1y") else "2y"
        return f'{match.group(1)} data-term-group="{slug}">'

    def _link(match: re.Match[str]) -> str:
        counts["checkout_links"] += 1
        href = html.unescape(match.group("href"))
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
        qty = (query.get("qty") or ["1"])[0]
        term = (query.get("term") or ["1"])[0]
        return f'{match.group(1)} data-start-protection="{term}-{qty}">'

    document = _FILTER_CONTROL.sub(_control, document)
    document = _TERM_GROUP.sub(_group, document)
    document = _CHECKOUT_LINK.sub(_link, document)
    return document, counts


# ---------------------------------------------------------------------------
# stylesheet localisation
# ---------------------------------------------------------------------------


def localise_stylesheets(pages: dict[str, str], assets: dict[str, str]) -> dict[str, str]:
    """Re-emit every referenced mirror stylesheet through the same pass.

    A pristine mirrored stylesheet passes an external-reference inspector
    because its ``url()`` targets are root-relative - and then answers 404 at
    the clone origin, or worse, reaches Google Fonts for a face.  The mirror
    payload stays byte-exact for evidence; the *served* sheet is a localised
    sibling under ``static/site/vendor``.
    """

    VENDOR_CSS.mkdir(parents=True, exist_ok=True)
    for stale in VENDOR_CSS.glob("localized-*.css"):
        stale.unlink()

    replacements: dict[str, str] = {}
    queue: list[str] = []
    seen: set[str] = set()

    for text in pages.values():
        for match in re.finditer(
            rf"{re.escape(ASSET_PREFIX)}/[^\"')\s]+\.css", text
        ):
            queue.append(match.group(0))

    while queue:
        served = queue.pop()
        if served in seen:
            continue
        seen.add(served)
        relative = served[len(ASSET_PREFIX) + 1 :]
        payload = ASSET_MIRROR / relative
        if not payload.is_file():
            continue
        host = relative.split("/", 1)[0]
        source_base = f"https://{host}/{relative.split('/', 1)[1]}"
        rewriter = Rewriter(source_base, assets)
        localized = rewriter.css(payload.read_text(encoding="utf-8", errors="replace"))
        digest = hashlib.sha256(
            (relative + localized).encode("utf-8", "replace")
        ).hexdigest()[:16]
        name = f"localized-{digest}.css"
        (VENDOR_CSS / name).write_text(localized, encoding="utf-8")
        replacements[served] = f"/static/site/vendor/{name}"
        for match in re.finditer(rf"{re.escape(ASSET_PREFIX)}/[^\"')\s]+\.css", localized):
            queue.append(match.group(0))

    # A localised sheet may itself @import another localised sheet.
    for name in sorted(p.name for p in VENDOR_CSS.glob("localized-*.css")):
        path = VENDOR_CSS / name
        text = path.read_text(encoding="utf-8")
        for served, local in replacements.items():
            text = text.replace(served, local)
        path.write_text(text, encoding="utf-8")

    return replacements


# ---------------------------------------------------------------------------
# shells
# ---------------------------------------------------------------------------


def build_app_shell(checkout_document: str) -> str:
    """The application-host chrome with its body content replaced by a slot.

    ``/checkout`` and the whole ``/account`` tree are rendered into this shell,
    so they inherit the captured head - title aside - and the mirrored fonts and
    stylesheet the source's own app pages load.
    """

    sys.path.insert(0, str(CLONE))
    from htmlslice import replace_element  # noqa: PLC0415

    document = checkout_document
    # the captured body is an expired-session panel plus a Stripe metrics frame
    for anchor in (
        '<div class="MuiBox-root css-1wkjpkc">',
        '<div class="MuiBox-root css-lwdemk"',
    ):
        if anchor in document:
            document = replace_element(
                document, anchor, MAIN_SENTINEL if anchor.endswith('css-1wkjpkc">') else ""
            )
    document = re.sub(r"<iframe\b[^>]*>.*?</iframe\s*>", "", document, flags=re.I | re.S)
    document = re.sub(r"<iframe\b[^>]*>", "", document, flags=re.I)
    if document.count(MAIN_SENTINEL) != 1:
        raise SystemExit("application shell sentinel was not spliced exactly once")
    return document


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def mirror_assets() -> int:
    """Copy the frozen mirror into the served tree, byte for byte."""

    target = STATIC / "assets" / CAPTURE_ID
    copied = 0
    for source in sorted(ASSET_MIRROR.rglob("*")):
        if not source.is_file():
            continue
        destination = target / source.relative_to(ASSET_MIRROR)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and filecmp.cmp(source, destination, shallow=False):
            continue
        shutil.copy2(source, destination)
        copied += 1
    # drop anything a previous capture left behind
    for existing in sorted(target.rglob("*"), reverse=True):
        relative = existing.relative_to(target)
        if existing.is_file() and not (ASSET_MIRROR / relative).is_file():
            existing.unlink()
        elif existing.is_dir() and not any(existing.iterdir()):
            existing.rmdir()
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="do not re-mirror source-assets into clone/static/assets",
    )
    args = parser.parse_args()

    assets = load_asset_index()
    PAGES.mkdir(parents=True, exist_ok=True)
    for stale in PAGES.glob("*.html"):
        stale.unlink()

    documents: dict[str, str] = {}
    external: dict[str, str] = {}
    missing: set[str] = set()
    uncaptured_first_party: set[str] = set()
    report: list[dict[str, object]] = []

    for unit, name, viewport in STATES:
        directory = CAPTURE_ROOT / unit / viewport
        source = directory / "page.html"
        if not source.is_file():
            raise SystemExit(f"missing capture: {source}")
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        base_url = meta.get("final_url") or meta["requested_url"]
        raw = source.read_text(encoding="utf-8", errors="replace")
        rewriter = Rewriter(base_url, assets)
        document, scripts, dropped = rewrite_document(raw, base_url, rewriter)
        document, prices = slot_prices(document)
        document, controls = mark_plan_controls(document)
        documents[name] = document
        external.update(rewriter.external)
        missing |= rewriter.missing
        uncaptured_first_party |= rewriter.uncaptured_first_party
        report.append(
            {
                "page": name,
                "unit": unit,
                "viewport": viewport,
                "source_url": base_url,
                "source_bytes": len(raw),
                "served_bytes": len(document),
                "scripts_removed": scripts,
                "assets_mapped": rewriter.mapped,
                "third_party_refs_removed": dropped,
                "price_slots": prices,
                **controls,
            }
        )

    replacements = localise_stylesheets(documents, assets)
    for name, text in documents.items():
        for served, local in replacements.items():
            text = text.replace(served, local)
        documents[name] = text

    # the clone-local bundle, spliced once per document
    head = (
        '<link rel="stylesheet" href="/static/site/clone.css">' + CLONE_HEAD_SENTINEL
    )
    body = CLONE_BODY_SENTINEL + '<script src="/static/site/clone.js" defer></script>'
    for name, text in documents.items():
        if "</head>" in text:
            text = text.replace("</head>", head + "</head>", 1)
        else:
            text = head + text
        if "</body>" in text:
            text = text.replace("</body>", body + "</body>", 1)
        else:
            text = text + body
        documents[name] = text

    documents["_app-shell"] = build_app_shell(documents["checkout-shell"])
    del documents["checkout-shell"]

    failures: list[str] = []
    for name, text in sorted(documents.items()):
        for number, line in enumerate(text.splitlines(), start=1):
            hit = REMOTE_REF.search(line)
            if hit:
                failures.append(f"{name}.html:{number} remote reference {hit.group(0)[:80]}")
        money = MONEY.search(text)
        if money and name in {
            "plans",
            "pricing",
            "signup-grid",
            "scan",
            "reviews",
            "_app-shell",
        }:
            index = text.index(money.group(0))
            failures.append(
                f"{name}.html carries a hard-coded price {money.group(0)!r} "
                f"near {text[max(0, index - 90):index + 20]!r}"
            )
    if failures:
        for line in failures[:40]:
            print(f"BUILD FAILED: {line}", file=sys.stderr)
        print(f"BUILD FAILED: {len(failures)} finding(s)", file=sys.stderr)
        return 1

    for name, text in documents.items():
        (PAGES / f"{name}.html").write_text(text, encoding="utf-8")

    (CLONE / "frontend" / "external-links.json").write_text(
        json.dumps(dict(sorted(external.items())), indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    copied = 0 if args.skip_assets else mirror_assets()

    summary = {
        "capture_id": CAPTURE_ID,
        "pages": len(documents),
        "external_boundaries": len(external),
        "localized_stylesheets": len(replacements),
        "assets_copied": copied,
        "third_party_references_removed": sorted(missing),
        "first_party_references_not_mirrored": sorted(uncaptured_first_party),
        "documents": report,
    }
    (CLONE / "frontend" / "build-report.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in summary.items()
                if key != "documents"
            },
            indent=1,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
