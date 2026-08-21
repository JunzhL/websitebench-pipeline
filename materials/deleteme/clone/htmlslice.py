"""Tag-stack-aware slicing of a captured document.

The served documents are the source's own rendered DOM.  They are handled as
*strings*, never as templates: the captured CSS contains `){#id`, and one inline
configuration block contains `{{...}}`, so any brace-based templating engine
corrupts them.  Whatever the server has to compute is therefore spliced against
an exact substring of the capture.

The slicer counts a tag stack rather than matching the next closing tag, because
naively taking the next `</div>` truncated a stepper mid-element on an earlier
site and left five tab panels stacked on another.  It also skips `<!-- -->`
comments and quoted attribute values so a `>` inside either cannot end a tag.
"""

from __future__ import annotations

import re

__all__ = [
    "element_span",
    "replace_element",
    "replace_inner",
    "drop_element",
    "replace_once",
    "insert_after",
]

_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_TAG_NAME = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9:-]*)")


def _tag_end(text: str, start: int) -> int:
    """Index just past the `>` that closes the tag opening at `start`."""

    index = start + 1
    quote = ""
    length = len(text)
    while index < length:
        char = text[index]
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == ">":
            return index + 1
        index += 1
    raise ValueError("unterminated tag")


def element_span(document: str, anchor: str) -> tuple[int, int, int]:
    """`(start, inner_start, end)` for the element whose open tag is `anchor`.

    `anchor` must appear exactly once and must be the literal opening-tag
    prefix, e.g. `'<div class="MuiBox-root css-1wkjpkc">'` or an unterminated
    prefix like `'<div class="MuiBox-root css-lwdemk"'`.
    """

    occurrences = document.count(anchor)
    if occurrences != 1:
        raise ValueError(f"anchor appears {occurrences} times, expected 1: {anchor[:80]!r}")
    start = document.index(anchor)
    name_match = _TAG_NAME.match(document, start)
    if name_match is None:
        raise ValueError(f"anchor is not a tag: {anchor[:80]!r}")
    name = name_match.group(2).casefold()
    inner_start = _tag_end(document, start)
    if name in _VOID or document[inner_start - 2 : inner_start] == "/>":
        return start, inner_start, inner_start

    depth = 1
    index = inner_start
    length = len(document)
    open_re = re.compile(rf"<\s*(/?)\s*{re.escape(name)}\b", re.I)
    while index < length:
        if document.startswith("<!--", index):
            close = document.find("-->", index)
            index = length if close == -1 else close + 3
            continue
        match = open_re.search(document, index)
        if match is None:
            raise ValueError(f"unclosed element for anchor {anchor[:80]!r}")
        comment = document.rfind("<!--", index, match.start())
        if comment != -1:
            close = document.find("-->", comment)
            if close != -1 and close > match.start():
                index = close + 3
                continue
        tag_end = _tag_end(document, match.start())
        if match.group(1) == "/":
            depth -= 1
            if depth == 0:
                return start, inner_start, tag_end
        elif document[tag_end - 2 : tag_end] != "/>":
            depth += 1
        index = tag_end
    raise ValueError(f"unclosed element for anchor {anchor[:80]!r}")


def replace_element(document: str, anchor: str, replacement: str) -> str:
    """Replace the whole element, opening and closing tags included."""

    start, _, end = element_span(document, anchor)
    return document[:start] + replacement + document[end:]


def replace_inner(document: str, anchor: str, replacement: str) -> str:
    """Replace only what the element contains, keeping both of its tags."""

    start, inner_start, end = element_span(document, anchor)
    close = document.rfind("<", inner_start, end)
    return document[:inner_start] + replacement + document[close:]


def drop_element(document: str, anchor: str) -> str:
    return replace_element(document, anchor, "")


def replace_once(document: str, needle: str, replacement: str) -> str:
    """Substring replacement that refuses to guess.

    A drifting anchor is a build error, not a silent no-op: an earlier site
    shipped a checkout whose submit button kept a captured disabled state
    because the splice quietly matched nothing.
    """

    count = document.count(needle)
    if count != 1:
        raise ValueError(f"anchor appears {count} times, expected 1: {needle[:80]!r}")
    return document.replace(needle, replacement, 1)


def insert_after(document: str, anchor: str, addition: str) -> str:
    """Insert immediately after the element's opening tag."""

    _, inner_start, _ = element_span(document, anchor)
    return document[:inner_start] + addition + document[inner_start:]
