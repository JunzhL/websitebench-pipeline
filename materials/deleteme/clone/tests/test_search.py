"""Invariant `search-empty-state-is-silent`.

A no-match search on the source answers HTTP 200 with the heading `Search`, an
H2 echoing the term in curly quotes, and an empty results region carrying **no
message at all**.  Trace ht-15 asks to verify a no-results message; the source
has none, and inventing one would be the cleanest possible way to fail this run
dishonestly.  So the assertion is the absence, and the negative control proves
the absence is actually checked.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

TERM = "zzzz-no-match-websitebench"

# Strings a well-meaning implementer would invent. None may appear.
INVENTED = (
    "no results",
    "nothing found",
    "no matches",
    "sorry, we could not find",
    "we couldn't find",
    "0 results",
    "try another search",
    "did you mean",
)


def _results_region(body: str) -> str:
    """Everything between the echoed-term heading and the end of that section.

    `<style>` and `<script>` bodies are removed first: the source's own empty
    region contains one builder-widget style block, which is markup, not a
    message to the visitor.
    """

    match = re.search(r"Search results for [‘'][^<]*[’']\s*</h2>", body)
    assert match, "the echoed-term heading is missing"
    tail = body[match.end() :]
    end = tail.find("</main>")
    region = tail[: end if end != -1 else 4000]
    region = re.sub(r"<style\b.*?</style>", " ", region, flags=re.S | re.I)
    return re.sub(r"<script\b.*?</script>", " ", region, flags=re.S | re.I)


def test_no_match_query_renders_a_silent_empty_state(client: TestClient) -> None:
    response = client.get(f"/?s={TERM}")
    assert response.status_code == 200
    body = response.text

    # The heading, exactly as the source writes it.
    assert re.search(r"<h1[^>]*>\s*Search\s*</h1>", body, re.S)

    # The echo, in the source's curly single quotes - not straight ones.
    assert f"Search results for ‘{TERM}’" in body
    assert f"Search results for '{TERM}'" not in body

    # The term also reaches the form field, so the query survives the round trip.
    assert f'value="{TERM}"' in body

    # And the region carries no message of any kind.
    region = _results_region(body)
    text = re.sub(r"<[^>]+>", " ", region)
    assert not text.strip(), repr(text[:200])
    lowered = body.casefold()
    for invented in INVENTED:
        assert invented not in lowered, invented


def test_the_query_is_echoed_and_escaped(client: TestClient) -> None:
    response = client.get("/?s=%3Cscript%3Ealert(1)%3C/script%3E")
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_the_home_page_exposes_no_search_form(client: TestClient) -> None:
    """The form lives on blog and archive pages, not on the entry page."""

    home = client.get("/").text
    assert 'name="s"' not in home
    blog = client.get("/blog/").text
    assert 'role="search"' in blog or 'name="s"' in blog


def test_detects_an_invented_no_results_message(client: TestClient) -> None:
    """Negative control: plant the message and the assertion must fail."""

    body = client.get(f"/?s={TERM}").text

    def probe(text: str) -> None:
        region = _results_region(text)
        stripped = re.sub(r"<[^>]+>", " ", region)
        assert not stripped.strip(), repr(stripped[:200])
        lowered = text.casefold()
        for invented in INVENTED:
            assert invented not in lowered, invented

    probe(body)  # clean

    damaged = body.replace(
        f"Search results for ‘{TERM}’",
        f"Search results for ‘{TERM}’",
        1,
    )
    anchor = re.search(r"Search results for ‘[^<]*’\s*</h2>", damaged)
    damaged = (
        damaged[: anchor.end()]
        + "<p>No results found. Try another search.</p>"
        + damaged[anchor.end() :]
    )
    with pytest.raises(AssertionError):
        probe(damaged)
