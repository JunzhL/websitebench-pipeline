"""The plan catalogue, transcribed from the frozen pricing capture.

Every figure here is read off ``source-current/2026-08-19.ipvanish-r1/pricing``
and its three billing-period interaction states.  Money is held in minor units
so nothing rounds twice.

The checkout order summary is derived from this table, never accepted from the
client.  The derivation is reconstructed from the capture rather than invented:

* The captured order summary's product name embeds the promotional charge
  (``Live - Essential - Annual - $46.68``), and its savings percentage is the
  discount against the *renewal* price, not the retail total --
  ``1 - 46.68/99.99 = 53.3%`` matches the captured ``53%`` and
  ``1 - 64.68/129.99 = 50.2%`` matches the captured ``50%``.
* The estimated-tax rate is 13%: ``46.68 x 1.13 = 52.75``, which reproduces the
  ``Estimated tax $6.07`` / ``Total due $52.75`` pair recorded for
  ``flow=essential-annual``.

The captured chooser itself rendered every amount as ``$0.00`` because the
source's pricing XHR had not resolved when the frame was taken.  Serving that
placeholder would make the "derived server-side" contract untestable, so the
clone serves the derived figures and records the difference.
"""

from __future__ import annotations

from dataclasses import dataclass


CURRENCY = "USD"
# 13%, the rate that reconciles the recorded $6.07 tax on a $46.68 charge.
TAX_RATE_PERCENT = 13

TERM_LABEL = {"monthly": "Monthly", "annual": "Annual", "biennial": "Biennial"}
FIRST_TERM_WORD = {"monthly": "month", "annual": "year", "biennial": "2 years"}
PERIOD_TAB = {"biennial": "2-Year Plan", "annual": "Yearly Plan", "monthly": "Monthly Plan"}
# The pricing page's tab ids, and the query value the clone accepts for each.
PERIOD_BY_QUERY = {
    "2-year": "biennial",
    "biennial": "biennial",
    "yearly": "annual",
    "annual": "annual",
    "monthly": "monthly",
}


@dataclass(frozen=True)
class Plan:
    """One purchasable (tier, billing period) pair."""

    plan_id: str
    tier: str
    period: str
    term_months: int
    # the big "$x.xx /mo" figure on the pricing card
    monthly_minor: int
    # the struck-through retail total, absent on monthly
    retail_minor: int | None
    # what the first term actually costs
    charge_minor: int
    # what every term after the first costs, per year (per month when monthly)
    renewal_minor: int
    promo_copy: str | None
    renewal_copy: str
    risk_free_label: bool

    # -- money derived for the checkout order summary ----------------------

    @property
    def list_minor(self) -> int:
        """The pre-discount line item: the renewal price, or the monthly price."""

        return self.charge_minor if self.period == "monthly" else self.renewal_minor

    @property
    def discount_minor(self) -> int:
        return self.list_minor - self.charge_minor

    @property
    def save_percent(self) -> int:
        if self.discount_minor <= 0:
            return 0
        return round(self.discount_minor * 100 / self.list_minor)

    @property
    def tax_minor(self) -> int:
        return round(self.charge_minor * TAX_RATE_PERCENT / 100)

    @property
    def total_minor(self) -> int:
        return self.charge_minor + self.tax_minor

    @property
    def product_name(self) -> str:
        return (
            f"Live - {self.tier} - {TERM_LABEL[self.period]} - "
            f"{money(self.charge_minor)}"
        )

    @property
    def flow(self) -> str:
        return self.plan_id

    @property
    def has_badge(self) -> bool:
        """The captured chooser shows the 30-day badge on discounted flows only."""

        return self.period != "monthly"

    @property
    def recurring_disclosure(self) -> str:
        return (
            "By clicking the subscribe button you agree to be charged "
            f"{amount(self.charge_minor)} per first {FIRST_TERM_WORD[self.period]}. "
            "Your plan renews automatically until you cancel at any time "
            "through your IPVanish account."
        )


def money(minor: int) -> str:
    return f"${minor // 100}.{minor % 100:02d}"


def amount(minor: int) -> str:
    """The bare figure the captured disclosure uses, with no currency symbol."""

    return f"{minor // 100}.{minor % 100:02d}"


PLANS: tuple[Plan, ...] = (
    Plan(
        plan_id="essential-biennial",
        tier="Essential",
        period="biennial",
        term_months=24,
        monthly_minor=249,
        retail_minor=35976,
        charge_minor=5976,
        renewal_minor=9999,
        promo_copy="$59.76 for the first 2 years.",
        renewal_copy="Renews Yearly at $99.99.",
        risk_free_label=True,
    ),
    Plan(
        plan_id="advanced-biennial",
        tier="Advanced",
        period="biennial",
        term_months=24,
        monthly_minor=359,
        retail_minor=43176,
        charge_minor=8616,
        renewal_minor=12999,
        promo_copy="$86.16 for the first 2 years.",
        renewal_copy="Renews Yearly at $129.99.",
        risk_free_label=True,
    ),
    Plan(
        plan_id="essential-annual",
        tier="Essential",
        period="annual",
        term_months=12,
        monthly_minor=389,
        retail_minor=17988,
        charge_minor=4668,
        renewal_minor=9999,
        promo_copy="$46.68 for the first year.",
        renewal_copy="Renews Yearly at $99.99.",
        risk_free_label=True,
    ),
    Plan(
        plan_id="advanced-annual",
        tier="Advanced",
        period="annual",
        term_months=12,
        monthly_minor=539,
        retail_minor=21588,
        charge_minor=6468,
        renewal_minor=12999,
        promo_copy="$64.68 for the first year.",
        renewal_copy="Renews Yearly at $129.99.",
        risk_free_label=True,
    ),
    Plan(
        plan_id="essential-monthly",
        tier="Essential",
        period="monthly",
        term_months=1,
        monthly_minor=1499,
        retail_minor=None,
        charge_minor=1499,
        renewal_minor=1499,
        promo_copy=None,
        renewal_copy="Renews Monthly at $14.99.",
        risk_free_label=False,
    ),
    Plan(
        plan_id="advanced-monthly",
        tier="Advanced",
        period="monthly",
        term_months=1,
        monthly_minor=1799,
        retail_minor=None,
        charge_minor=1799,
        renewal_minor=1799,
        promo_copy=None,
        renewal_copy="Renews Monthly at $17.99.",
        risk_free_label=False,
    ),
)

BY_ID = {plan.plan_id: plan for plan in PLANS}


def plan_for_flow(flow: str | None) -> Plan | None:
    """Resolve a ``?flow=`` value; the flow parameter binds tier and period."""

    if not isinstance(flow, str):
        return None
    return BY_ID.get(flow.strip().casefold())
