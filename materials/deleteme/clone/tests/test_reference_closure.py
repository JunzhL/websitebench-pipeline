"""Invariants `every-image-has-a-renderable-source` and
`local-reference-closure`.

Two failure modes from earlier sites are asserted here, both of which passed
every other gate at the time:

* jefit advertised 36 responsive widths it could not serve. At device pixel
  ratio 1 the browser picked a width that existed; at 2 and 3 it picked one that
  did not, and static closure, the live diagnostic, the pixel oracle and a blind
  review all ran at ratio 1 and all reported clean.
* ipvanish answered 291 references with local 404s - mostly lazy-loaded images
  never requested during capture - because the closure check only flagged
  *external* references and the oracle only compared the viewport crop.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import CLONE_ROOT, JOURNEY_ROUTES, SITE_ROOT, SUBSCRIBER_ROUTES

STATIC = CLONE_ROOT / "static"
MIRROR = STATIC / "assets" / "2026-08-20.deleteme-r1"
EXCLUDED = json.loads(
    (SITE_ROOT / "source-assets" / "excluded-requests.json").read_text(encoding="utf-8")
)
BUILD_REPORT = json.loads(
    (CLONE_ROOT / "frontend" / "build-report.json").read_text(encoding="utf-8")
)

ATTR_REF = re.compile(
    r'(?:src|href|poster|action|data-src|data-bg|xlink:href)="([^"]+)"'
)
CSS_REF = re.compile(
    r"""url\(\s*(?:&quot;|&#0?39;|["'])?\s*([^"')]*?)\s*(?:&quot;|&#0?39;|["'])?\s*\)"""
)
SRCSET_ATTR = re.compile(r'(?:srcset|data-srcset|imagesrcset)="([^"]*)"')
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
INERT = ("data:", "#", "mailto:", "tel:", "javascript:", "about:", "blob:")


def _local_refs(text: str) -> set[str]:
    found: set[str] = set()
    for match in ATTR_REF.finditer(text):
        found.add(match.group(1).strip())
    for match in CSS_REF.finditer(text):
        found.add(html.unescape(match.group(1)).strip())
    for match in SRCSET_ATTR.finditer(text):
        value = match.group(1)
        if value.strip().casefold().startswith("data:"):
            continue  # one candidate, not several: a data URI owns its comma
        for candidate in value.split(","):
            candidate = candidate.strip()
            if candidate:
                found.add(candidate.split()[0])
    return {
        ref
        for ref in found
        if ref and not ref.casefold().startswith(INERT) and ref.startswith("/")
    }


def _resolves(ref: str) -> bool:
    if not ref.startswith("/static/"):
        return True  # a route, answered by the app, not by the filesystem
    return (STATIC / ref[len("/static/") :].split("?")[0]).is_file()


def _served_documents(client: TestClient) -> dict[str, str]:
    from conftest import sign_in

    documents = {route: client.get(route).text for route in JOURNEY_ROUTES}
    sign_in(client)
    for route in SUBSCRIBER_ROUTES:
        documents[route] = client.get(route).text
    return documents


def test_no_undeclared_local_reference_fails(client: TestClient) -> None:
    documents = _served_documents(client)
    for path in sorted((STATIC / "site").rglob("*.css")):
        documents[str(path.relative_to(CLONE_ROOT))] = path.read_text(encoding="utf-8")

    broken: list[tuple[str, str]] = []
    total = 0
    for where, text in documents.items():
        for ref in _local_refs(text):
            total += 1
            if not _resolves(ref):
                broken.append((where, ref))
    assert total > 1500, f"only {total} references examined; the probe looks inert"
    assert not broken, broken[:20]


def test_declared_holes_are_still_real() -> None:
    """Negative control for the declaration path.

    Every third-party reference the build removed must belong to an origin the
    frozen evidence actually declares.  A build that quietly dropped a *first
    party* payload and called it excluded would pass a naive closure check and
    fail this one.
    """

    declared = {entry["origin"] for entry in EXCLUDED["excluded_origins"]}
    assert declared, "no excluded origins are declared at all"
    removed = BUILD_REPORT["third_party_references_removed"]
    assert removed, "the build removed nothing; the control cannot discriminate"
    for reference in removed:
        origin = reference.split("/", 1)[0]
        assert origin in declared, (origin, reference)
        assert not origin.endswith("joindeleteme.com"), reference

    # The control fires on a planted first-party 'exclusion'.
    planted = "joindeleteme.com/wp-content/uploads/2024/01/deletemeregistered.png"
    with pytest.raises(AssertionError):
        origin = planted.split("/", 1)[0]
        assert origin in declared, (origin, planted)


def test_every_image_element_has_a_working_source(client: TestClient) -> None:
    documents = _served_documents(client)
    dead: list[tuple[str, str]] = []
    examined = 0
    for where, text in documents.items():
        for tag in IMG_TAG.findall(text):
            examined += 1
            candidates: list[str] = []
            src = re.search(r'\bsrc="([^"]*)"', tag)
            if src:
                candidates.append(src.group(1))
            data_src = re.search(r'\bdata-src="([^"]*)"', tag)
            if data_src:
                candidates.append(data_src.group(1))
            for attribute in ("srcset", "data-srcset"):
                found = re.search(rf'\b{attribute}="([^"]*)"', tag)
                if not found:
                    continue
                value = found.group(1)
                if value.strip().casefold().startswith("data:"):
                    candidates.append(value)
                    continue
                candidates.extend(
                    entry.strip().split()[0]
                    for entry in value.split(",")
                    if entry.strip()
                )
            usable = [
                item
                for item in candidates
                if item
                and (item.casefold().startswith("data:") or _resolves(item))
            ]
            if candidates and not usable:
                dead.append((where, tag[:160]))
    assert examined > 500, f"only {examined} image elements examined"
    assert not dead, dead[:10]


def test_no_advertised_srcset_width_is_missing(client: TestClient) -> None:
    """At ratio 2 or 3 the browser picks the widest candidate, so *every*
    advertised width has to exist - not merely the one ratio 1 would pick."""

    documents = _served_documents(client)
    missing: list[tuple[str, str]] = []
    widths = 0
    for where, text in documents.items():
        for value in SRCSET_ATTR.findall(text):
            if value.strip().casefold().startswith("data:"):
                continue
            for entry in value.split(","):
                entry = entry.strip()
                if not entry:
                    continue
                url = entry.split()[0]
                widths += 1
                if not _resolves(url):
                    missing.append((where, entry))
    assert widths > 40, f"only {widths} srcset candidates examined"
    assert not missing, missing[:20]


def test_detects_a_stripped_srcset_with_a_dead_src(client: TestClient) -> None:
    """Negative control: the image probe must fail on a broken element.

    This is the jefit defect exactly: a `src` that cannot be served and a
    `srcset` whose candidates cannot be served either.
    """

    body = client.get("/").text
    first = IMG_TAG.search(body)
    assert first is not None
    # The jefit shape exactly: a src the mirror cannot answer, and a srcset
    # whose every advertised width is missing too.
    damaged = (
        body[: first.start()]
        + '<img src="/static/assets/does-not-exist.png" '
        'srcset="/static/assets/does-not-exist-800.png 800w, '
        '/static/assets/does-not-exist-1600.png 1600w">'
        + body[first.end() :]
    )
    assert damaged != body

    def probe(text: str) -> list[str]:
        dead = []
        for tag in IMG_TAG.findall(text):
            candidates = re.findall(r'\b(?:src|data-src)="([^"]*)"', tag)
            for attribute in ("srcset", "data-srcset"):
                found = re.search(rf'\b{attribute}="([^"]*)"', tag)
                if found and not found.group(1).strip().casefold().startswith("data:"):
                    candidates.extend(
                        entry.strip().split()[0]
                        for entry in found.group(1).split(",")
                        if entry.strip()
                    )
            usable = [
                item
                for item in candidates
                if item and (item.casefold().startswith("data:") or _resolves(item))
            ]
            if candidates and not usable:
                dead.append(tag[:80])
        return dead

    assert not probe(body), "the clean document already fails the probe"
    assert probe(damaged), "the probe did not notice an unservable image"


def test_the_mirror_is_byte_identical_to_the_frozen_evidence() -> None:
    """The served mirror is a copy, never a re-encoding."""

    manifest = json.loads(
        (SITE_ROOT / "source-assets" / "manifest.json").read_text(encoding="utf-8")
    )
    import hashlib

    checked = 0
    for asset in manifest["assets"]:
        runtime = SITE_ROOT / asset["runtime_path"]
        assert runtime.is_file(), asset["runtime_path"]
        if checked % 25 == 0:  # a full hash of 38 MB every run is not free
            digest = hashlib.sha256(runtime.read_bytes()).hexdigest()
            assert digest == asset["sha256"], asset["runtime_path"]
        checked += 1
    assert checked == len(manifest["assets"])
