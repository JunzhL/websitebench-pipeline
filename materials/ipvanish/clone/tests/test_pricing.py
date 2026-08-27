"""Plan-catalogue fidelity: the captured figures, and no period mixing."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from backend.catalogue import BY_ID


PANELS = {
    "biennial": "pricing-pg-biennial-tab",
    "annual": "pricing-pg-yearly-tab",
    "monthly": "pricing-pg-monthly-tab",
}
PERIOD_QUERY = {"biennial": "2-year", "annual": "yearly", "monthly": "monthly"}


def _panel(text: str, period: str) -> str:
    """Slice one period's panel out of the served document."""

    from htmlslice import element_span

    marker = f'<div class="wp-block-group {PANELS[period]}'
    start = text.index(marker)
    begin, end = element_span(text, start)
    return text[begin:end]


def test_default_tab_is_the_two_year_plan(client: TestClient) -> None:
    text = client.get("/pricing/").text
    assert "IPVanish plans &amp; pricing" in text
    assert re.search(
        r'<p class="has-text-align-center biennial-link plan-type-link active',
        text,
    )
    for label in ("2-Year Plan", "Yearly Plan", "Monthly Plan"):
        assert f"<strong>{label}</strong>" in text


def test_only_the_requested_period_panel_is_shown(client: TestClient) -> None:
    """Exactly one period's cards visible at a time, at the document level."""

    for period, query in PERIOD_QUERY.items():
        text = client.get(f"/pricing/?period={query}").text
        shown = []
        for other, selector in PANELS.items():
            panel = _panel(text, other)
            opening = panel[: panel.index(">") + 1]
            hidden = "display: none" in opening or "display:none" in opening
            if not hidden:
                shown.append(other)
        assert shown == [period], (period, shown)


@pytest.mark.parametrize(
    ("plan_id", "monthly", "retail", "promo", "renewal"),
    (
        ("essential-biennial", "$2.49", "$359.76", "$59.76 for the first 2 years.", "Renews Yearly at $99.99."),
        ("advanced-biennial", "$3.59", "$431.76", "$86.16 for the first 2 years.", "Renews Yearly at $129.99."),
        ("essential-annual", "$3.89", "$179.88", "$46.68 for the first year.", "Renews Yearly at $99.99."),
        ("advanced-annual", "$5.39", "$215.88", "$64.68 for the first year.", "Renews Yearly at $129.99."),
    ),
)
def test_discounted_cards_render_the_captured_figures(
    client: TestClient,
    plan_id: str,
    monthly: str,
    retail: str,
    promo: str,
    renewal: str,
) -> None:
    plan = BY_ID[plan_id]
    panel = _panel(client.get("/pricing/").text, plan.period)
    for fragment in (monthly, retail, promo, renewal):
        assert fragment in panel, (plan_id, fragment)


def test_monthly_cards_render_the_captured_figures(client: TestClient) -> None:
    panel = _panel(client.get("/pricing/").text, "monthly")
    assert "$14.99" in panel
    assert "$17.99" in panel
    assert "Renews Monthly at $14.99." in panel
    assert "Renews Monthly at $17.99." in panel


def test_risk_free_label_only_on_yearly_and_two_year(client: TestClient) -> None:
    text = client.get("/pricing/").text
    assert "30 days risk free" in _panel(text, "biennial")
    assert "30 days risk free" in _panel(text, "annual")
    assert "30 days risk free" not in _panel(text, "monthly")


def test_money_back_row_absent_from_the_monthly_table(client: TestClient) -> None:
    """The source omits it from the Monthly comparison table; keep it absent."""

    text = client.get("/pricing/").text
    assert "30-day Money-back Guarantee" in _panel(text, "biennial")
    assert "30-day Money-back Guarantee" in _panel(text, "annual")
    assert "30-day Money-back Guarantee" not in _panel(text, "monthly")


def test_feature_rows_include_the_esim_allowance_and_advanced_only_rows(
    client: TestClient,
) -> None:
    panel = _panel(client.get("/pricing/").text, "annual")
    for label in (
        "High-speed VPN",
        "Advanced Privacy Features",
        "Unlimited Devices",
        "Award-winning 24/7 Support",
        "eSIM Data",
        "Threat Protection Pro",
        "Secure Browser",
        "Cloud Backup",
        "Phone Support",
    ):
        assert label in panel, label
    assert ">3GB<" in panel
    assert ">5GB<" in panel


def test_plan_ctas_carry_the_captured_flow_parameters(client: TestClient) -> None:
    text = client.get("/pricing/").text
    for plan_id in (
        "essential-biennial",
        "advanced-biennial",
        "essential-annual",
        "advanced-annual",
        "essential-monthly",
        "advanced-monthly",
    ):
        assert (
            "/checkout/address-payment-method?flow="
            f"{plan_id}&amp;currency=USD&amp;lang=EN" in text
        ), plan_id
    assert ">Get Essential<" in text
    assert ">Get Advanced<" in text


def test_best_protection_ribbon_is_present_in_every_period(
    client: TestClient,
) -> None:
    text = client.get("/pricing/").text
    for period in PANELS:
        assert "Best Protection" in _panel(text, period), period


def test_period_switch_does_not_mix_prices(client: TestClient) -> None:
    """Negative control: no period's document shows another period's figures.

    A monthly-only figure must never appear inside a visible yearly panel, and
    the other way round.  This is the check that would have caught the JEFIT
    run's stacked tab panels.
    """

    signatures = {
        "biennial": ("$2.49", "$359.76"),
        "annual": ("$3.89", "$179.88"),
        "monthly": ("Renews Monthly at $14.99.",),
    }
    for period, query in PERIOD_QUERY.items():
        text = client.get(f"/pricing/?period={query}").text
        visible = _panel(text, period)
        for fragment in signatures[period]:
            assert fragment in visible, (period, fragment)
        for other, fragments in signatures.items():
            if other == period:
                continue
            other_panel = _panel(text, other)
            opening = other_panel[: other_panel.index(">") + 1]
            assert "display: none" in opening or "display:none" in opening, other
