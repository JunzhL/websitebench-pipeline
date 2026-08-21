"""Invariants `plan-arithmetic-matches-source` and
`single-person-strikethrough-is-hidden-not-absent`.

Every figure on the grid is reconciled against the frozen capture, and against
the catalogue that produced it.  Both checks have a negative control, because a
price test that only compares the page to the catalogue would pass happily while
both were wrong together.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from conftest import SITE_ROOT, catalogue

CAPTURE = SITE_ROOT / "source-current" / "2026-08-20.deleteme-r1"

# Read straight off the frozen plan grid, not from the catalogue.
FROZEN = {
    "price1Year1Person": {
        "new-price": "$10.75",
        "original-price": "$10.75",
        "annual-price": "$129.00/year",
        "disclaimer": "Billed at $129.00 annually.",
    },
    "price1Year2People": {
        "new-price": "$19.08",
        "original-price": "$21.50",
        "annual-price": "$229.00/year",
        "disclaimer": "Billed at $229.00 annually.",
    },
    "price1Year4People": {
        "new-price": "$27.42",
        "original-price": "$43.00",
        "annual-price": "$329.00/year",
        "disclaimer": "Billed at $329.00 annually.",
    },
    "price2Years1Person": {
        "new-price": "$8.71",
        "original-price": "$8.71",
        "biennial-price": "$209.00/2 years",
        "disclaimer": "Billed at $209.00 every 2 years.",
    },
    "price2Years2People": {
        "new-price": "$14.54",
        "original-price": "$17.42",
        "biennial-price": "$349.00/2 years",
        "disclaimer": "Billed at $349.00 every 2 years.",
    },
    "price2Years4People": {
        "new-price": "$20.79",
        "original-price": "$34.83",
        "biennial-price": "$499.00/2 years",
        "disclaimer": "Billed at $499.00 every 2 years.",
    },
}

PLAN_PAGES = ("/privacy-protection-plans/", "/pricing/", "/signup/", "/scan/")
PRICE_ELEMENT = re.compile(
    r'class="[^"]*\b(price(?:1Year|2Years)(?:1Person|2People|4People))'
    r'-(new-price|original-price|annual-price|biennial-price|disclaimer)\b[^"]*"[^>]*>'
    r"([^<]*)<"
)


def test_every_card_matches_the_frozen_arithmetic(client: TestClient) -> None:
    # 1. The catalogue reproduces the capture.
    for key, fields in FROZEN.items():
        for field, expected in fields.items():
            assert catalogue.field_value(key, field) == expected, (key, field)

    # 2. The catalogue derives, rather than stores, each figure.
    for plan in catalogue.PLANS:
        months = plan.term_years * 12
        cents = round(plan.charge_minor / months)
        assert abs(int(plan.monthly_display[1:].replace(".", "")) - cents) <= 1
        assert plan.total_display == f"${plan.charge_minor // 100}.00"

    # 3. Every served page renders those and only those.
    seen = 0
    for route in PLAN_PAGES:
        body = client.get(route).text
        assert "wb:price" not in body, route
        for key, field, text in PRICE_ELEMENT.findall(body):
            expected = FROZEN[key].get(field)
            assert expected is not None, (route, key, field)
            assert text.strip() == expected, (route, key, field, text)
            seen += 1
    assert seen >= 60, seen

    # 4. No page carries a money literal the catalogue did not produce.
    known = {value for fields in FROZEN.values() for value in fields.values()}
    known_money = set()
    for value in known:
        known_money.update(re.findall(r"\$\d[\d,]*\.\d\d", value))
    for route in PLAN_PAGES:
        for found in re.findall(r"\$\d[\d,]*\.\d\d", client.get(route).text):
            assert found in known_money, (route, found)


def test_detects_a_wrong_monthly_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: break the derivation and the assertion must fail.

    A green arithmetic suite has to mean "the numbers are right", not "the
    comparison never ran".
    """

    real = catalogue.per_month

    def broken(total_minor: int, months: int) -> str:
        return real(total_minor, months + 1)

    monkeypatch.setattr(catalogue, "per_month", broken)
    with pytest.raises(AssertionError):
        for key, fields in FROZEN.items():
            for field, expected in fields.items():
                assert catalogue.field_value(key, field) == expected, (key, field)

    monkeypatch.undo()
    # ... and it passes again once the defect is removed.
    assert catalogue.field_value("price1Year2People", "new-price") == "$19.08"


def _comparison_blocks(body: str) -> list[tuple[str, str]]:
    """`(plan key, inline style)` for every rendered comparison price."""

    found = []
    for match in re.finditer(
        r'<(?:span|strong)[^>]*class="[^"]*strike-through[^"]*"([^>]*)>(.{0,400}?)</',
        body,
        re.S,
    ):
        attrs, inner = match.group(1), match.group(2)
        key = re.search(r"(price(?:1Year|2Years)(?:1Person|2People|4People))", inner)
        style = re.search(r'style="([^"]*)"', attrs)
        if key:
            found.append((key.group(1), style.group(1) if style else ""))
    return found


def test_single_card_keeps_a_hidden_comparison_price(client: TestClient) -> None:
    """Quantity one earns no quantity discount, so the source *hides* the
    comparison price rather than removing it - and states the visibility
    explicitly on the discounted cards too."""

    body = client.get("/privacy-protection-plans/").text
    blocks = _comparison_blocks(body)
    assert blocks, "no comparison price found at all"

    for key, style in blocks:
        plan = catalogue.BY_KEY[key]
        if plan.has_quantity_discount:
            assert "visibility: visible" in style, (key, style)
        else:
            assert "visibility: hidden" in style, (key, style)

    # The element exists for every plan, hidden or not.
    assert {key for key, _ in blocks} == set(FROZEN)


def test_detects_a_removed_comparison_price(client: TestClient) -> None:
    """Negative control: strip the element and the assertion must fail."""

    body = client.get("/privacy-protection-plans/").text
    damaged = re.sub(
        r'<(span|strong)[^>]*class="[^"]*strike-through[^"]*"[^>]*>.*?</\1>',
        "",
        body,
        flags=re.S,
    )
    assert damaged != body, "the control did not actually remove anything"
    assert not _comparison_blocks(damaged)
    with pytest.raises(AssertionError):
        blocks = _comparison_blocks(damaged)
        assert blocks, "no comparison price found at all"


def test_the_business_tier_has_no_price_and_no_checkout_link(
    client: TestClient,
) -> None:
    body = client.get("/privacy-protection-plans/").text
    assert "Business" in body
    assert (
        "Protect your executives, critical employees or your entire organization"
        in body
    )
    assert "Contact sales for custom pricing" in body
    # ... and it is not in the catalogue, so it cannot be checked out.
    assert "Business" in catalogue.UNPRICED_TIERS
    assert all(plan.person_label != "Business" for plan in catalogue.PLANS)


def test_the_size_filter_container_is_reproduced_hidden(client: TestClient) -> None:
    """`#fs-grid-filter-activation` is in the markup and `display:none` in the
    page.  "Present in the markup" and "operable" are different claims; the
    clone must reproduce the first without granting the second."""

    body = client.get("/privacy-protection-plans/").text
    match = re.search(r'<div[^>]*id="fs-grid-filter-activation"[^>]*>', body)
    assert match, "the hidden size-filter container is missing"
    assert "display: none" in match.group(0)


def test_the_grid_defaults_to_two_years(client: TestClient) -> None:
    body = client.get("/privacy-protection-plans/").text
    for match in re.finditer(r'<div[^>]*\sdata-tag="(1-Year|2-Years)"[^>]*>', body):
        if match.group(1) == "1-Year":
            assert "display: none" in match.group(0), match.group(0)
        else:
            assert "display: none" not in match.group(0), match.group(0)
