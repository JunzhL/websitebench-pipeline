#!/usr/bin/env python3
"""The capture plan: which frozen checkpoint maps to which live source URL.

scope/checkpoints.json is frozen and is the only source of truth for WHICH
units exist, at which viewport, and whether a unit is acceptance-eligible.
This module adds the one thing the frozen contract deliberately does not
carry: the live URL each route id resolves to, and whether reaching the unit
needs a scripted interaction.

Three source hosts are in scope, and the clone folds all three onto one
origin (see scope/routes.json):

  joindeleteme.com          the WordPress marketing tree
  app.joindeleteme.com      the React-Router checkout/login SPA
  help.joindeleteme.com     the Zendesk Guide help centre
  privacy.joindeleteme.com  the policies surface linked from checkout

Deliberate omissions, each recorded in REMOVED_STATE_NOTES rather than
silently dropped:

* help.joindeleteme.com/hc/en-us/requests/new -- the Zendesk ticket form sits
  behind a Cloudflare managed challenge, and it is also the one help surface
  that would submit a support request. Not requested.
* Every account-dashboard state -- DeleteMe issues an account only after a
  real purchase, which this run does not make.
* Every checkout/login/password state that exists only after typing or
  submitting -- filled, validation-empty, credentials-rejected,
  payment-declined, payment-retry, submitted. Nothing is ever typed into or
  submitted on the live source, so these are clone-local by construction and
  the frozen contract already marks them acceptance_eligible false.

Search: robots.txt disallows /*?s= for every agent. The single no-results
checkpoint is fetched exactly once as one user-equivalent page view, and no
other search URL is ever requested.
"""
from __future__ import annotations

import json
import pathlib

MARKETING = "https://joindeleteme.com"
APP = "https://app.joindeleteme.com"
HELP = "https://help.joindeleteme.com"
POLICIES = "https://privacy.joindeleteme.com"

# The plan id used for the one checkout capture. Opaque product identifier
# plus billing term and quantity -- no signature, key or session material,
# so this is the one URL in the plan that legitimately keeps its query.
CHECKOUT_QUERY = "plan=prod_UJ03ZGKxM0BiGF&term=1&qty=1"

# The single robots-honouring search probe.
SEARCH_TERM = "zzzz-no-match-websitebench"

# An unknown marketing path. Extensionless, so the source 301s it to the
# trailing-slash form and then answers a real 404 -- the redirect is part of
# the behaviour being frozen, so it is deliberately not pre-slashed here.
NOT_FOUND_PATH = "/zzzz-no-match-websitebench"

# An unknown application path. The app host answers unknown routes HTTP 200
# with an SPA "Page not found", disagreeing with the marketing host's 404.
APP_NOT_FOUND_PATH = "/account/no-such-route-websitebench-zzz9"

# route_id -> live URL for every navigable route.
ROUTE_URLS: dict[str, str] = {
    "home": f"{MARKETING}/",
    "plans": f"{MARKETING}/privacy-protection-plans/",
    "pricing": f"{MARKETING}/pricing/",
    "signup-grid": f"{MARKETING}/signup/",
    "scan": f"{MARKETING}/scan/",
    "how-we-work": f"{MARKETING}/how-we-work/",
    "sites-we-remove-from": f"{MARKETING}/sites-we-remove-from/",
    "reviews": f"{MARKETING}/reviews/",
    "about": f"{MARKETING}/about-us/",
    "security": f"{MARKETING}/security/",
    "international": f"{MARKETING}/international/",
    "how-public-record": f"{MARKETING}/how-public-record-information-works/",
    "blog": f"{MARKETING}/blog/",
    "opt-out-guides": f"{MARKETING}/blog/opt-out-guides/",
    "delete-your-account": f"{MARKETING}/delete-your-account/",
    "doxxing": f"{MARKETING}/doxxing/",
    "is-site-safe": f"{MARKETING}/is-site-safe/",
    "is-it-scam": f"{MARKETING}/is-it-scam/",
    "glossary": f"{MARKETING}/glossary/",
    "do-not-call-list": f"{MARKETING}/do-not-call-list/",
    "ai-privacy-settings": f"{MARKETING}/ai-privacy-settings/",
    "data-breaches": f"{MARKETING}/data-breaches/",
    "podcast": f"{MARKETING}/podcast/",
    "permission-slip": f"{MARKETING}/permission-slip/",
    "permission-slip-faq": f"{MARKETING}/permission-slip/faq/",
    "press": f"{MARKETING}/press/",
    "careers": f"{MARKETING}/careers/",
    "not-found": f"{MARKETING}{NOT_FOUND_PATH}",
    "search": f"{MARKETING}/?s={SEARCH_TERM}",
    # Separate hosts the clone maps onto its own origin.
    "checkout": f"{APP}/checkout?{CHECKOUT_QUERY}",
    "checkout-complete": f"{APP}/checkout/complete",
    "login": f"{APP}/login",
    "password-forgot": f"{APP}/password/forgot",
    "app-not-found": f"{APP}{APP_NOT_FOUND_PATH}",
    "help": f"{HELP}/hc/en-us",
    "policies": f"{POLICIES}/policies?name=terms-of-service",
}

# Post-navigation readiness selectors for the client-rendered app host, whose
# real content paints well after document load.
WAIT_SELECTORS: dict[str, str] = {
    "checkout": "input",
    "login": "input[type=email], input[autocomplete=email]",
    "password-forgot": "input[type=email], input#email",
    "app-not-found": "h1",
    "checkout-complete": "h1, main",
}

# Longer settle for the SPA host and the plan grids, whose prices are injected
# by their own script after load.
SETTLE_OVERRIDES: dict[str, int] = {
    "checkout": 6000,
    "checkout-complete": 6000,
    "login": 5000,
    "password-forgot": 5000,
    "app-not-found": 5000,
    "plans": 4500,
    "pricing": 4500,
    "signup-grid": 4500,
    "help": 4000,
    "policies": 4500,
}

# States reached only by clicking. capture_states.py owns these; an id must
# have exactly one owner so the two passes can never disagree in index.json.
INTERACTIVE_STATES: set[str] = {
    "term-1y", "term-2y", "size-single", "size-couple", "size-family",
    "promo-open",
}

# States that exist only after a value is typed or a form is submitted, or
# behind a purchased account. Never attempted on the live source.
NEVER_ATTEMPTED: dict[str, str] = {
    "filled": "would require typing personal data into the live source's form",
    "validation-empty": "would require submitting the live source's form",
    "credentials-rejected": "would require submitting credentials to the live source",
    "payment-declined": "would require a real card payment on the live source",
    "payment-retry": "would require a real card payment on the live source",
    "submitted": "would require requesting a real password reset",
    "dashboard": "behind an account DeleteMe issues only after a purchase",
    "removal-profile": "behind an account DeleteMe issues only after a purchase",
    "reports": "behind an account DeleteMe issues only after a purchase",
    "billing-history": "behind an account DeleteMe issues only after a purchase",
    "plan-change": "behind an account DeleteMe issues only after a purchase",
    "pause": "behind an account DeleteMe issues only after a purchase",
    "cancel": "behind an account DeleteMe issues only after a purchase",
    "reactivate": "behind an account DeleteMe issues only after a purchase",
    "unavailable": "clone-local route with no live counterpart",
}


def unit_name(checkpoint: dict) -> str:
    """Directory name for a unit: the frozen checkpoint id minus its viewport
    suffix, so the layout is derived from the contract and reversible."""
    cid = checkpoint["id"]
    suffix = "." + checkpoint["viewport"]
    return cid[: -len(suffix)] if cid.endswith(suffix) else cid


def load_checkpoints(site: pathlib.Path) -> tuple[list[dict], dict[str, dict]]:
    data = json.loads((site / "scope" / "checkpoints.json").read_text())
    return data["checkpoints"], data["viewports"]


def plan_units(site: pathlib.Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Split the frozen checkpoints into (navigable, interactive, skipped).

    A navigable unit is reachable by one GET. An interactive unit needs a
    click on a UIkit filter control or the promo-code disclosure. A skipped
    unit is one this run deliberately does not touch, and every skip carries
    its reason into index.json's removed_state_notes.
    """
    checkpoints, _ = load_checkpoints(site)
    navigable: list[dict] = []
    interactive: list[dict] = []
    skipped: list[dict] = []

    for cp in checkpoints:
        route = cp["route_id"]
        state = cp["state"]
        record = {
            "checkpoint": cp["id"],
            "unit": unit_name(cp),
            "route_id": route,
            "state": state,
            "viewport": cp["viewport"],
            "priority": cp["priority"],
            "acceptance_eligible": cp["acceptance_eligible"],
            "evidence_kind": cp["evidence_kind"],
        }
        if cp.get("note"):
            record["contract_note"] = cp["note"]

        if state in NEVER_ATTEMPTED:
            record["reason"] = NEVER_ATTEMPTED[state]
            record["contract_evidence_kind"] = cp["evidence_kind"]
            skipped.append(record)
            continue
        if route not in ROUTE_URLS:
            record["reason"] = f"no live URL is in scope for route {route!r}"
            skipped.append(record)
            continue
        record["url"] = ROUTE_URLS[route]
        record["wait_selector"] = WAIT_SELECTORS.get(route)
        record["settle_ms"] = SETTLE_OVERRIDES.get(route)
        if state in INTERACTIVE_STATES:
            interactive.append(record)
        else:
            navigable.append(record)
    return navigable, interactive, skipped


# Planned surfaces this run deliberately does not capture at all. These are
# not checkpoints; they are neighbours a reader would reasonably expect to
# see, so the reason is recorded next to the evidence.
REMOVED_STATE_NOTES: list[dict[str, str]] = [
    {
        "surface": f"{HELP}/hc/en-us/requests/new",
        "decision": "not requested",
        "reason": "the Zendesk ticket form answers a Cloudflare managed "
                  "challenge, and it is the one help surface whose purpose is "
                  "to submit a support request; the capture is read-only",
    },
    {
        "surface": f"{MARKETING}/?s=<any other term>",
        "decision": "not crawled",
        "reason": "robots.txt disallows /*?s= for every agent; exactly one "
                  "user-equivalent search page view was taken for the frozen "
                  "no-results checkpoint and no other search URL was requested",
    },
    {
        "surface": "the site's cookie/consent banner in its accepted state",
        "decision": "not clicked",
        "reason": "consent controls are never operated, so any post-consent "
                  "third-party origin stays unobserved rather than invented",
    },
    {
        "surface": "the support chat widget",
        "decision": "not opened",
        "reason": "opening it starts a live support conversation",
    },
]
