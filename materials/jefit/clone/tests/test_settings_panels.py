"""Settings tab panels must be self-contained and shown one at a time.

Regression cover for a defect the rest of the suite could not see: every panel
was carved out of its own captured page as an unbalanced byte slice, so its
trailing ancestor closers terminated the wrapper element early and ejected the
content into the wrapper's parent. All five panels then rendered stacked as
siblings that `display:none` could not hide (the document grew to five times
the viewport), and the composition was additionally being inserted into the
mobile header's nav, which is hidden at desktop widths.

Text-presence assertions pass vacuously against that shape — every tab's copy
is always in the document — so these tests assert structure instead: one
wrapper per tab, each holding its own content, and the tab-only strings living
inside the right wrapper.
"""

from __future__ import annotations

import re

TABS = ("account", "profile", "privacy", "data-controls", "integrations")
# A string that appears only inside one specific panel.
TAB_MARKERS = {
    "account": "Account Type",
    "profile": "Unit System",
    "privacy": "Email Preferences",
    "data-controls": "Export Data",
    "integrations": "Strava",
}
WRAPPER = re.compile(r'<div data-settings-panel="([a-z-]+)"([^>]*)>')


def _settings_html(member) -> str:
    response = member.get("/my-jefit/settings")
    assert response.status_code == 200
    return response.text


def _wrapper_span(html: str, tab: str) -> str:
    """The markup of one panel wrapper, from its open tag to its matching close."""
    match = re.search(r'<div data-settings-panel="%s"[^>]*>' % re.escape(tab), html)
    assert match, f"no wrapper for {tab}"
    depth = 0
    for token in re.finditer(r"<div\b|</div>", html[match.start():]):
        depth += 1 if token.group(0) == "<div" else -1
        if depth == 0:
            return html[match.start() : match.start() + token.end()]
    raise AssertionError(f"wrapper for {tab} never closes")


def test_every_tab_has_exactly_one_wrapper(member) -> None:
    found = WRAPPER.findall(_settings_html(member))
    keys = [key for key, _ in found]
    assert keys == list(TABS), keys
    assert len(keys) == len(set(keys))


def test_wrappers_are_not_empty(member) -> None:
    """The ejection bug left every wrapper empty (`<div ...></div>`)."""
    html = _settings_html(member)
    for tab in TABS:
        span = _wrapper_span(html, tab)
        inner = span[span.index(">") + 1 : -len("</div>")]
        assert len(inner) > 500, f"{tab} wrapper holds only {len(inner)} chars"


def test_each_tab_marker_lives_inside_its_own_wrapper(member) -> None:
    html = _settings_html(member)
    for tab, marker in TAB_MARKERS.items():
        span = _wrapper_span(html, tab)
        assert marker in span, f"{marker!r} is not inside the {tab} wrapper"
        for other in TABS:
            if other == tab:
                continue
            assert marker not in _wrapper_span(html, other), (
                f"{marker!r} leaked into the {other} wrapper"
            )


def test_non_default_panels_ship_hidden(member) -> None:
    html = _settings_html(member)
    for tab, attrs in WRAPPER.findall(html):
        hidden = "display:none" in attrs.replace(" ", "")
        assert hidden is (tab != "account"), f"{tab} hidden={hidden}"


def test_panels_are_not_composed_into_a_desktop_hidden_container(member) -> None:
    """The composition must not land inside the `lg:hidden` mobile header."""
    html = _settings_html(member)
    first = html.index('<div data-settings-panel="account"')
    header_open = html.rfind("<header", 0, first)
    if header_open < 0:
        return
    header_close = html.find("</header>", header_open)
    assert header_close < first, "panels composed inside a <header>"


def test_tab_bar_is_not_duplicated_outside_wrappers(member) -> None:
    """Each captured panel carries its own tab bar; only the active one shows.

    Every copy must sit inside a wrapper, so hiding a panel hides its bar too.
    """
    html = _settings_html(member)
    spans = "".join(_wrapper_span(html, tab) for tab in TABS)
    total = html.count(">Integrations<")
    inside = spans.count(">Integrations<")
    assert total - inside <= 1, (
        f"{total - inside} tab-bar copies live outside the panel wrappers"
    )
