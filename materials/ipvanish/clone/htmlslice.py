"""Tag-stack-aware element slicing for captured markup.

Carving a fragment out of rendered DOM with a non-greedy regex produces
unbalanced HTML: the JEFIT run shipped a settings page whose five tab panels
rendered stacked because the panels had been cut that way.  Every carve in this
site walks the tag stack instead, so a slice is always one complete element.
"""

from __future__ import annotations

import re

_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9:-]*)\b[^>]*?(/?)>", re.S)
VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }
)


class SliceError(ValueError):
    """The requested element could not be sliced as one balanced unit."""


def element_span(text: str, start: int) -> tuple[int, int]:
    """Return (start, end) of the element whose opening tag begins at ``start``."""

    opening = _TAG.match(text, start)
    if opening is None:
        raise SliceError(f"no tag begins at offset {start}")
    name = opening.group(2).casefold()
    if opening.group(3) or name in VOID_ELEMENTS:
        return start, opening.end()
    depth = 0
    for match in _TAG.finditer(text, start):
        if match.group(2).casefold() != name:
            continue
        if match.group(1):
            depth -= 1
            if depth == 0:
                return start, match.end()
        elif not match.group(3):
            depth += 1
    raise SliceError(f"unbalanced <{name}> beginning at offset {start}")


def slice_unique(text: str, opening: str) -> str:
    """Slice the one element whose opening tag equals ``opening`` exactly."""

    occurrences = _occurrences(text, opening)
    if len(occurrences) != 1:
        raise SliceError(
            f"expected exactly one {opening!r}, found {len(occurrences)}"
        )
    start, end = element_span(text, occurrences[0])
    return text[start:end]


def _occurrences(text: str, needle: str) -> list[int]:
    found: list[int] = []
    index = text.find(needle)
    while index != -1:
        found.append(index)
        index = text.find(needle, index + 1)
    return found


def replace_nth(text: str, needle: str, replacements: list[str]) -> str:
    """Replace successive occurrences of ``needle``, one per replacement.

    Hard-fails when the occurrence count does not match, so a captured anchor
    that moved is a build error rather than a silently unspliced page.
    """

    positions = _occurrences(text, needle)
    if len(positions) != len(replacements):
        raise SliceError(
            f"{needle!r}: expected {len(replacements)} occurrences, "
            f"found {len(positions)}"
        )
    out: list[str] = []
    cursor = 0
    for position, replacement in zip(positions, replacements):
        out.append(text[cursor:position])
        out.append(replacement)
        cursor = position + len(needle)
    out.append(text[cursor:])
    return "".join(out)


def replace_once(text: str, needle: str, replacement: str) -> str:
    return replace_nth(text, needle, [replacement])


def replace_element(text: str, opening: str, replacement: str) -> str:
    """Swap the one balanced element whose opening tag equals ``opening``."""

    positions = _occurrences(text, opening)
    if len(positions) != 1:
        raise SliceError(
            f"expected exactly one {opening!r} to replace, found {len(positions)}"
        )
    start, end = element_span(text, positions[0])
    return text[:start] + replacement + text[end:]


def replace_inner(text: str, opening: str, replacement: str) -> str:
    """Swap the children of the one element whose opening tag equals ``opening``."""

    positions = _occurrences(text, opening)
    if len(positions) != 1:
        raise SliceError(
            f"expected exactly one {opening!r} to refill, found {len(positions)}"
        )
    start, end = element_span(text, positions[0])
    element = text[start:end]
    closing = element[element.rindex("</"):]
    return text[:start] + opening + replacement + closing + text[end:]


def drop_element(text: str, opening: str) -> str:
    """Remove the one balanced element whose opening tag equals ``opening``."""

    positions = _occurrences(text, opening)
    if len(positions) != 1:
        raise SliceError(
            f"expected exactly one {opening!r} to drop, found {len(positions)}"
        )
    start, end = element_span(text, positions[0])
    return text[:start] + text[end:]
