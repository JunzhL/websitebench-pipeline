#!/usr/bin/env python3
"""Extract the questionnaire step panels from the localized signup captures.

The signup page swaps one panel region per step (progress bar + question).
Each step's panel is recovered mechanically as the contiguous region where
that step's document differs from the step-01 document (common prefix/suffix
diff). Output: clone/frontend/signup-steps.json with the step-01 panel bounds
in the base document plus every step's panel HTML, so the server renders the
base page and the clone runtime swaps panels client-side exactly as the
source SPA does (URL stays /signup).
"""
from __future__ import annotations

import json
import pathlib
import re

SITE = pathlib.Path(__file__).resolve().parents[1]
PAGES = SITE / "clone" / "frontend" / "pages"
EVIDENCE = SITE / "clone" / "frontend" / "evidence"
OUT = SITE / "clone" / "frontend" / "signup-steps.json"


def bounds(base: str, other: str) -> tuple[int, int, int]:
    """(prefix_len, base_suffix_start, other_suffix_start)."""

    prefix = 0
    limit = min(len(base), len(other))
    while prefix < limit and base[prefix] == other[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < limit - prefix
        and base[len(base) - 1 - suffix] == other[len(other) - 1 - suffix]
    ):
        suffix += 1
    return prefix, len(base) - suffix, len(other) - suffix


VOID_TAGS = frozenset(
    "img br hr input meta link source path circle rect use stop polygon line "
    "ellipse area col embed track wbr".split()
)
TAG_RE = re.compile(r"<!--.*?-->|<(/?)([a-zA-Z][\w-]*)([^>]*?)(/?)>", re.S)


def snap_outward(doc: str, lo: int, hi: int) -> tuple[int, int]:
    """Return the content range of the innermost element containing [lo, hi).

    A naive character diff lands mid-token (inside ``<!--$-->``, inside a
    class attribute), which yields malformed markers and unparsable panels.
    Resolving the enclosing element instead makes the slot a whole run of
    sibling nodes: boundaries sit between nodes by construction, the region
    reparses unchanged through ``template.innerHTML``, and the inserted
    comment markers become real comment nodes.
    """

    stack: list[tuple[str, int]] = []
    best: tuple[int, int] | None = None
    for match in TAG_RE.finditer(doc):
        if match.group(0).startswith("<!--"):
            continue
        closing, name, _attrs, self_closing = match.groups()
        name = name.lower()
        if name in VOID_TAGS or self_closing:
            continue
        if not closing:
            stack.append((name, match.end()))
            continue
        while stack:
            open_name, content_start = stack.pop()
            content_end = match.start()
            if open_name != name:
                continue  # unclosed element (HTML is lenient); keep unwinding
            if content_start <= lo and content_end >= hi:
                if best is None or content_start > best[0]:
                    best = (content_start, content_end)
            break
    if best is None:
        raise SystemExit("panel slot: no element encloses the diff region")
    return best


def well_formed(panel: str) -> bool:
    return (
        panel.startswith("<")
        and panel.rstrip().endswith(">")
        and panel.count("<!--") == panel.count("-->")
    )


def normalize(doc: str) -> str:
    # Capture-time chrome state that is not questionnaire content and must not
    # widen the swap region: the keyboard-focus artifact on <html>, and the
    # cookie-banner's `inert` attribute (present once the banner has been
    # dismissed in that capture context — the clone runtime owns that state).
    # The diff runs over the body only; heads differ merely in per-step image
    # preload hints, irrelevant once the page is loaded.
    doc = doc.replace(' data-headlessui-focus-visible=""', "")
    # `inert` appears exactly once per signup document, on the cookie banner
    # (verified), and its position varies with attribute order across captures.
    doc = doc.replace(' inert=""', "")
    # Empty React streaming placeholders: `<div hidden=""><!--$--><!--/$-->`
    # and `<div hidden="">` are the same invisible node.
    doc = doc.replace('<div hidden=""><!--$--><!--/$--></div>', '<div hidden=""></div>')
    return doc[doc.find("<body") :]


def main() -> int:
    base = normalize((PAGES / "signup.html").read_text())
    docs = {}
    for index in range(2, 18):
        name = f"signup-step-{index:02d}"
        docs[index] = normalize((EVIDENCE / f"{name}.html").read_text())

    # union of differing regions across all steps, so one panel slot covers
    # every step swap
    lo = len(base)
    hi = 0
    spans = {}
    for index, doc in docs.items():
        prefix, base_end, other_end = bounds(base, doc)
        spans[index] = (prefix, base_end, other_end)
        lo = min(lo, prefix)
        hi = max(hi, base_end)
    # Snap the union region outward to real tag boundaries before slicing:
    # boundaries inside a tag or attribute make every panel malformed.
    lo, hi = snap_outward(base, lo, hi)
    panels = {1: base[lo:hi]}
    for index, doc in docs.items():
        prefix, base_end, other_end = spans[index]
        # widen this doc's span to the union bounds: the prefix region is
        # identical across docs up to `prefix >= lo`, so base[lo:prefix] is
        # shared verbatim; same for the suffix side.
        head = base[lo:prefix]
        tail = base[base_end:hi]
        panels[index] = head + doc[prefix:other_end] + tail
    malformed = sorted(k for k, v in panels.items() if not well_formed(v))
    if malformed:
        raise SystemExit(f"panel slot: malformed panels {malformed}")
    if base.count(panels[1]) != 1:
        raise SystemExit(
            "panel slot: step-1 panel is not uniquely locatable in the page"
        )
    payload = {
        # Offset-free contract: the server locates the slot by matching the
        # step-1 panel string, so these offsets are informational only.
        "panel_start": lo,
        "panel_end": hi,
        "panels": {str(k): v for k, v in sorted(panels.items())},
    }
    OUT.write_text(json.dumps(payload, sort_keys=True))
    sizes = {k: len(v) for k, v in panels.items()}
    print("panel slot:", lo, hi, "sizes:", sizes)
    print("panel-1 head:", panels[1][:60])
    print("panel-1 tail:", panels[1][-60:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
