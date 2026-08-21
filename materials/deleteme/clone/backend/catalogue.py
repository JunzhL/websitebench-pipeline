"""The plan catalogue, in integer minor units.

Every figure the clone shows is derived from this table at request time.  No
formatted price string exists anywhere in a served document: the build pass
replaces each captured price with a sentinel and the server fills it from here,
so a catalogue change cannot leave a stale number behind and a stale number
cannot be mistaken for evidence.

The arithmetic, reconciled against the frozen capture
(``source-current/2026-08-20.deleteme-r1/plans/desktop/page.html``):

===========  ===  =========  ==========  =========  ==============  ==========
card         qty  term       charged     base       shown /mo       comparison
===========  ===  =========  ==========  =========  ==============  ==========
``1 Person``   1  1 year     ``12900``   ``12900``  129.00/12=10.75  10.75
``2 People``   2  1 year     ``22900``   ``25800``  229.00/12=19.08  21.50
``Family``     4  1 year     ``32900``   ``51600``  329.00/12=27.42  43.00
``1 Person``   1  2 years    ``20900``   ``20900``  209.00/24= 8.71   8.71
``2 People``   2  2 years    ``34900``   ``41800``  349.00/24=14.54  17.42
``Family``     4  2 years    ``49900``   ``83600``  499.00/24=20.79  34.83
===========  ===  =========  ==========  =========  ==============  ==========

The base is the single-person price of the same term multiplied by the head
count, which is why quantity one earns no quantity discount and why the source
renders the 1-Person comparison price with ``visibility: hidden`` instead of
removing it.

``Business`` is the grid's fourth card.  It carries no price and no checkout
link on the source - it is a sales-contact tier - so it has no catalogue entry
and the checkout refuses it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CURRENCY = "USD"
PRODUCT_ID = "prod_UJ03ZGKxM0BiGF"  # the identifier the source's own CTA carries

# term_years -> the single-person charge that sets the undiscounted base
_BASE_BY_TERM = {1: 12900, 2: 20900}

TERM_WORD = {1: "One year", 2: "Two years"}
RENEWAL_COPY = {1: "Renews annually.", 2: "Renews every two years."}


def money(minor: int) -> str:
    """``12900`` -> ``$129.00``. Integer arithmetic only; never a float."""

    sign = "-" if minor < 0 else ""
    minor = abs(minor)
    return f"{sign}${minor // 100}.{minor % 100:02d}"


def per_month(total_minor: int, months: int) -> str:
    """The figure the card shows: the whole charge divided by the months in it.

    Rounded to two decimals, half away from zero, which is what reproduces every
    captured value including ``329.00 / 12 = 27.4166... -> $27.42``.
    """

    value = (Decimal(total_minor) / Decimal(100) / Decimal(months)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"${value}"


@dataclass(frozen=True)
class Plan:
    """One purchasable cell of the grid."""

    key: str
    quantity: int
    term_years: int
    charge_minor: int
    person_label: str
    years_label: str

    @property
    def months(self) -> int:
        return self.term_years * 12

    @property
    def base_minor(self) -> int:
        """The undiscounted price: one person's charge, times the head count."""

        return _BASE_BY_TERM[self.term_years] * self.quantity

    @property
    def discount_minor(self) -> int:
        return self.base_minor - self.charge_minor

    @property
    def has_quantity_discount(self) -> bool:
        return self.discount_minor > 0

    # -- rendered figures --------------------------------------------------
    @property
    def monthly_display(self) -> str:
        return per_month(self.charge_minor, self.months)

    @property
    def comparison_display(self) -> str:
        return per_month(self.base_minor, self.months)

    @property
    def total_display(self) -> str:
        return money(self.charge_minor)

    @property
    def period_display(self) -> str:
        """``$129.00/year`` or ``$499.00/2 years``, as the source writes it."""

        suffix = "/year" if self.term_years == 1 else "/2 years"
        return f"{self.total_display}{suffix}"

    @property
    def disclaimer(self) -> str:
        if self.term_years == 1:
            return f"Billed at {self.total_display} annually."
        return f"Billed at {self.total_display} every {self.term_years} years."

    @property
    def summary_line(self) -> str:
        """The order-summary sentence, assembled the way the source's own
        checkout bundle assembles it."""

        people = "1 person" if self.quantity == 1 else f"{self.quantity} people"
        return (
            f"{TERM_WORD[self.term_years]} of DeleteMe for {people}. "
            f"{RENEWAL_COPY[self.term_years]}"
        )

    @property
    def checkout_query(self) -> str:
        return f"plan={PRODUCT_ID}&term={self.term_years}&qty={self.quantity}"


def _plan(term_years: int, quantity: int, charge_minor: int, person_label: str) -> Plan:
    term_label = "1 Year" if term_years == 1 else f"{term_years} Years"
    people = "1 Person" if quantity == 1 else f"{quantity} People"
    size = {1: "1Person", 2: "2People", 4: "4People"}[quantity]
    term_key = "1Year" if term_years == 1 else f"{term_years}Years"
    return Plan(
        key=f"price{term_key}{size}",
        quantity=quantity,
        term_years=term_years,
        charge_minor=charge_minor,
        person_label=person_label,
        years_label=f"{term_label}, {people}",
    )


PLANS: tuple[Plan, ...] = (
    _plan(1, 1, 12900, "1 Person"),
    _plan(1, 2, 22900, "2 People"),
    _plan(1, 4, 32900, "Family"),
    _plan(2, 1, 20900, "1 Person"),
    _plan(2, 2, 34900, "2 People"),
    _plan(2, 4, 49900, "Family"),
)

BY_KEY: dict[str, Plan] = {plan.key: plan for plan in PLANS}
BY_SELECTION: dict[tuple[int, int], Plan] = {
    (plan.term_years, plan.quantity): plan for plan in PLANS
}

# The sales-contact tier.  Present on the grid, absent from the catalogue.
UNPRICED_TIERS = ("Business",)


def plan_for(term_years: int, quantity: int) -> Plan | None:
    return BY_SELECTION.get((term_years, quantity))


def field_value(key: str, field: str) -> str:
    """Resolve one build-time price sentinel, ``<!--wb:price:key.field-->``."""

    plan = BY_KEY.get(key)
    if plan is None:
        raise KeyError(f"unknown plan key in a served document: {key!r}")
    if field == "new-price":
        return plan.monthly_display
    if field == "original-price":
        return plan.comparison_display
    if field == "annual-price":
        if plan.term_years != 1:
            raise KeyError(f"{key} is not an annual plan")
        return plan.period_display
    if field == "biennial-price":
        if plan.term_years != 2:
            raise KeyError(f"{key} is not a two-year plan")
        return plan.period_display
    if field == "disclaimer":
        return plan.disclaimer
    raise KeyError(f"unknown price field in a served document: {field!r}")
