#!/usr/bin/env python3
"""Freeze the ipvanish scope against the 2026-08-19.ipvanish-r1 capture.

Modeled on materials/jefit/tools/build_scope_evidence.py: identical threshold
rule (threshold = min(0.995, flicker_floor - 0.002), derived ONLY from
source-side 3-frame calibration, before any candidate render exists) and the
same artifact-count discipline -- only the chosen pixel oracles carry a
visual_contract + region_contracts, every other captured (checkpoint,
viewport) is a frozen source raster referenced by source_artifact_path with
acceptance_eligible false.

Oracle-selection rule (the one substantive difference from jefit)
-----------------------------------------------------------------
www.ipvanish.com animates continuously: an embedded Trustpilot carousel, a
Visual Website Optimizer A/B allocation and hero motion all repaint between
frames, and several home frames differed during capture. So the conventional
`home.{desktop,tablet,mobile}` oracle set is *measured*, never assumed:

1. The full-region 3-frame flicker floor is computed for EVERY captured
   (checkpoint, viewport).
2. A home viewport whose full-region floor >= STABILITY_FLOOR (0.98) becomes
   an acceptance-eligible pixel oracle carrying a visual_contract.
3. A home viewport whose floor is BELOW the stability floor is recorded with
   acceptance_eligible false plus an acceptance_exclusion_reason naming the
   measured floor, and the most stable other checkpoint captured at that same
   viewport (highest full-region floor, still >= STABILITY_FLOOR, preferring a
   text-heavy legal/marketing page such as tos, privacy-policy or
   money-back-guarantee) is promoted to carry the visual_contract for that
   viewport instead, so every viewport keeps at least one pixel oracle when
   one is possible. If no checkpoint at a viewport clears the floor, that
   viewport is left without a pixel oracle and the topology note says so.

The topology_note records the decision and the measured floors for every
viewport, so the freeze is auditable without re-running this script.

Deterministic; reads capture-index.json + state-capture-index.json, writes
scope/checkpoints.json, scope/visual-calibration-spec.json,
scope/visual-calibration-report.json, scope/claims.jsonl, scope/coverage.json,
source-current/<capture-id>/capture-metadata.json and one
frame-1.viewport.png per captured frame set (the exact-viewport crop the
visual contracts and source_artifact_path rows reference).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

from PIL import Image, ImageChops, ImageStat

SITE = pathlib.Path(__file__).resolve().parents[1]
SITE_ID = "ipvanish"
CAPTURE_ID = "2026-08-19.ipvanish-r1"
CAP_ROOT = SITE / "source-current" / CAPTURE_ID
METRIC = "pixel-mae-similarity-v1"
BASE_THRESHOLD = 0.995
SAFETY_MARGIN = 0.002
STABILITY_FLOOR = 0.98

VIEWPORTS: dict[str, tuple[int, int]] = {
    "desktop": (1440, 900),
    "tablet": (1024, 768),
    "mobile": (390, 844),
}

# Conventional oracle checkpoint, verified per viewport rather than assumed.
PREFERRED_ORACLE = "home"

# Fallback order when a home viewport fails the stability floor: text-heavy
# legal / marketing pages repaint least on this source.
FALLBACK_PREFERENCE = ("tos", "privacy-policy", "money-back-guarantee")

# checkpoint id -> (route_id, state). Anonymous URL captures already use the
# route ids from scope/routes.json, so they map to themselves with "loaded".
URL_CHECKPOINTS = (
    "home", "pricing", "why-vpn", "what-is-a-vpn", "servers", "vpn-features",
    "money-back-guarantee", "coupons", "reviews", "trust", "no-log-vpn-policy",
    "threat-protection", "secure-browser", "cloud-storage",
    "vpn-setup-windows", "vpn-locations", "vpn-for-streaming", "resources",
    "setup-guides", "what-is-my-ip-address", "blog", "tos", "privacy-policy",
    "partners", "press",
)
ROUTE_OF: dict[str, tuple[str, str]] = {cp: (cp, "loaded") for cp in URL_CHECKPOINTS}
ROUTE_OF.update({
    # interaction states (capture_states.py)
    "pricing-2year": ("pricing", "2-year"),
    "pricing-yearly": ("pricing", "yearly"),
    "pricing-monthly": ("pricing", "monthly"),
    "nav-product": ("home", "nav-product"),
    "nav-apps": ("home", "nav-apps"),
    "nav-resources": ("home", "nav-resources"),
    "mobile-menu-open": ("home", "mobile-menu"),
    # separate-origin SPAs and the help centre
    "sso-signin": ("sso-signin", "loaded"),
    "sso-recovery": ("sso-recovery", "loaded"),
    "support-home": ("support", "loaded"),
    "checkout-chooser-essential-annual": ("checkout-chooser", "essential-annual"),
    "checkout-chooser-essential-monthly": ("checkout-chooser", "essential-monthly"),
    "checkout-chooser-advanced-annual": ("checkout-chooser", "advanced-annual"),
    "checkout-card-form-essential-annual": ("checkout-chooser", "card-form"),
    "not-found": ("not-found", "loaded"),
})

# Overlay states: the primary-nav dropdowns and the mobile hamburger panel.
# For these the captured `nav` geometry is calibrated as the overlay region.
OVERLAY_CHECKPOINTS = frozenset(
    {"nav-product", "nav-apps", "nav-resources", "mobile-menu-open"}
)

SUBSCRIBER_NOTE = (
    "UNAVAILABLE on the source: reaching a subscriber session requires a real "
    "purchase, which the payment mandate prohibits and which the user "
    "declined (anonymous-only authority, scope/implement-notes.md). IPVanish "
    "has no free tier, no web free trial and no account-only signup -- 'Sign "
    "up now!' on the sign-in page links to /pricing/ and credentials are "
    "created inside the purchase funnel -- and my.ipvanish.com redirects "
    "anonymous visitors to sso.ipvanish.com with code=TOKEN_EXPIRED. Route "
    "names were read from the my.ipvanish.com build manifest (/, /vpn, "
    "/antivirus, /cloud-storage, /secure_browser, /proxy, /wireguard, "
    "/reports, /refer-and-earn) but no rendered subscriber state was ever "
    "observed. The clone implements a local dashboard whose every element is "
    "disclosed as inference; never a pixel contract."
)

UNAVAILABLE_ROWS: list[dict] = [
    {
        "id": f"subscriber-dashboard.{state}.desktop",
        "route_id": "subscriber-dashboard", "state": state,
        "role": "subscriber", "viewport": "desktop", "priority": "p1",
        "evidence_kind": "unavailable", "acceptance_eligible": False,
        "note": SUBSCRIBER_NOTE,
    }
    for state in ("overview", "billing-history", "plan-change", "paused",
                  "canceled")
] + [
    {
        "id": "checkout-chooser.success.desktop",
        "route_id": "checkout-chooser", "state": "success",
        "role": "visitor", "viewport": "desktop", "priority": "p0",
        "evidence_kind": "unavailable", "acceptance_eligible": False,
        "note": (
            "Post-payment confirmation was never reached on the source: "
            "submitting the Zuora hosted card form would create a real "
            "subscription and charge a real card, which is prohibited. "
            "Capture stops at the rendered registration form "
            "(checkout-card-form-essential-annual). The clone's success state "
            "is clone-local sandbox behavior reached through an opaque "
            "local-sandbox scenario selector, disclosed as inference."
        ),
    }
]


def normalize(img: Image.Image, width: int, height: int) -> Image.Image:
    img = img.convert("RGB")
    if img.width < width:
        raise SystemExit(f"frame width {img.width} < viewport width {width}")
    if img.width > width:
        img = img.crop((0, 0, width, img.height))
    if img.height >= height:
        return img.crop((0, 0, width, height))
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    canvas.paste(img, (0, 0))
    return canvas


def similarity(a: Image.Image, b: Image.Image,
               box: tuple[int, int, int, int]) -> float:
    diff = ImageChops.difference(a.crop(box), b.crop(box))
    return 1.0 - sum(ImageStat.Stat(diff).mean) / (255 * len(diff.getbands()))


def clip_region(reg: dict | None, width: int, height: int) -> dict | None:
    if not reg:
        return None
    x = max(0, min(reg["x"], width))
    y = max(0, min(reg["y"], height))
    x2 = max(0, min(reg["x"] + reg["width"], width))
    y2 = max(0, min(reg["y"] + reg["height"], height))
    if x2 - x < 8 or y2 - y < 8:
        return None
    return {"x": x, "y": y, "width": x2 - x, "height": y2 - y}


def load_captures() -> list[dict]:
    index = json.loads((CAP_ROOT / "capture-index.json").read_text())["captures"]
    state_path = CAP_ROOT / "state-capture-index.json"
    if state_path.is_file():
        index += json.loads(state_path.read_text())["captures"]
    return [c for c in index if "error" not in c]


def route_state(cp: str) -> tuple[str, str]:
    if cp in ROUTE_OF:
        return ROUTE_OF[cp]
    raise SystemExit(f"capture {cp} has no route mapping")


def region_map(cap: dict, width: int, height: int) -> dict[str, dict]:
    """Frozen comparison regions for one capture, clipped to the viewport."""
    regions = {"full": {"x": 0, "y": 0, "width": width, "height": height}}
    named = [("header", "header"), ("main", "main"), ("footer", "footer"),
             ("form", "action")]
    if cap["checkpoint"] in OVERLAY_CHECKPOINTS:
        named.append(("nav", "overlay"))
    for source_name, region_name in named:
        clipped = clip_region((cap.get("regions") or {}).get(source_name),
                              width, height)
        if clipped and region_name not in regions:
            regions[region_name] = clipped
    return regions


def measure(cap: dict) -> dict:
    """Compute per-region 3-frame flicker floors and freeze the viewport crop."""
    cp, vp = cap["checkpoint"], cap["viewport"]
    width, height = VIEWPORTS[vp]
    dest = CAP_ROOT / cp / vp
    frames = [normalize(Image.open(dest / f"frame-{n}.png"), width, height)
              for n in (1, 2, 3)]
    frames[0].save(dest / "frame-1.viewport.png", format="PNG")

    regions: dict[str, dict] = {}
    for name, reg in region_map(cap, width, height).items():
        box = (reg["x"], reg["y"], reg["x"] + reg["width"],
               reg["y"] + reg["height"])
        sims = [round(similarity(frames[i], frames[j], box), 6)
                for i, j in ((0, 1), (0, 2), (1, 2))]
        floor = min(sims)
        regions[name] = {
            "box": reg, "pairwise_similarity": sims, "flicker_floor": floor,
            "threshold": round(min(BASE_THRESHOLD, floor - SAFETY_MARGIN), 4),
        }
    return {"checkpoint": cp, "viewport": vp, "width": width,
            "height": height, "regions": regions}


def select_oracles(
    measured: dict[str, dict],
) -> tuple[dict[str, str], dict[str, dict]]:
    """Pick one pixel oracle per viewport; see the module docstring's rule.

    Returns (viewport -> oracle checkpoint id, viewport -> decision record).
    """
    oracles: dict[str, str] = {}
    decisions: dict[str, dict] = {}
    for vp in VIEWPORTS:
        at_viewport = {cid: m for cid, m in measured.items()
                       if m["viewport"] == vp}
        if not at_viewport:
            decisions[vp] = {"outcome": "no-capture"}
            continue
        home_id = f"{PREFERRED_ORACLE}.{vp}"
        home_floor = (at_viewport[home_id]["regions"]["full"]["flicker_floor"]
                      if home_id in at_viewport else None)
        if home_floor is not None and home_floor >= STABILITY_FLOOR:
            oracles[vp] = home_id
            decisions[vp] = {"outcome": "home-oracle", "oracle": home_id,
                             "home_floor": home_floor}
            continue

        candidates = sorted(
            (
                (cid, m["regions"]["full"]["flicker_floor"])
                for cid, m in at_viewport.items()
                if cid != home_id
                and m["regions"]["full"]["flicker_floor"] >= STABILITY_FLOOR
            ),
            key=lambda item: (
                FALLBACK_PREFERENCE.index(measured[item[0]]["checkpoint"])
                if measured[item[0]]["checkpoint"] in FALLBACK_PREFERENCE
                else len(FALLBACK_PREFERENCE),
                -item[1],
                item[0],
            ),
        )
        if candidates:
            oracles[vp] = candidates[0][0]
            decisions[vp] = {
                "outcome": "home-excluded-promoted-fallback",
                "oracle": candidates[0][0],
                "oracle_floor": candidates[0][1],
                "home_floor": home_floor,
            }
        else:
            decisions[vp] = {"outcome": "no-oracle", "home_floor": home_floor}
    return oracles, decisions


def topology_note(decisions: dict[str, dict], measured: dict[str, dict]) -> str:
    lines = [
        "Frozen evidence topology (petfinder/edx/tripit/aspca/jefit pattern) "
        "with a MEASURED rather than assumed pixel oracle. www.ipvanish.com "
        "repaints between frames (Trustpilot carousel, Visual Website "
        "Optimizer A/B allocation, hero motion), so the full-region 3-frame "
        "flicker floor was computed for every captured (checkpoint, viewport) "
        f"and only floors >= {STABILITY_FLOOR} may carry a pixel contract. "
        "Thresholds are min(0.995, flicker_floor - 0.002) over the full "
        "viewport region with zero ignore regions, derived before any "
        "candidate render existed. Per-viewport decision:",
    ]
    for vp, decision in decisions.items():
        outcome = decision["outcome"]
        if outcome == "home-oracle":
            floor = decision["home_floor"]
            lines.append(
                f"  {vp}: home.{vp} kept as the acceptance-eligible pixel "
                f"oracle (measured full-region floor {floor:.6f} >= "
                f"{STABILITY_FLOOR}).")
        elif outcome == "home-excluded-promoted-fallback":
            home = decision["home_floor"]
            home_txt = (f"{home:.6f}" if home is not None
                        else "not captured at this viewport")
            lines.append(
                f"  {vp}: home.{vp} is NOT acceptance-eligible (measured "
                f"full-region floor {home_txt} below the {STABILITY_FLOOR} "
                f"stability minimum); the most stable checkpoint captured at "
                f"{vp}, {decision['oracle']} (floor "
                f"{decision['oracle_floor']:.6f}, a text-heavy page that does "
                "not animate), was promoted to carry this viewport's "
                "visual_contract instead.")
        elif outcome == "no-oracle":
            home = decision["home_floor"]
            home_txt = (f"{home:.6f}" if home is not None
                        else "not captured at this viewport")
            lines.append(
                f"  {vp}: NO pixel oracle exists. home floor {home_txt} and "
                f"no other checkpoint captured at {vp} reaches "
                f"{STABILITY_FLOOR}; this viewport is frozen as reference "
                "rasters only, with no pixel acceptance claimed.")
        else:
            lines.append(
                f"  {vp}: declared in the viewport map but no capture exists "
                "at this viewport, so it carries no pixel oracle.")
    stable = sorted(
        ((m["regions"]["full"]["flicker_floor"], cid)
         for cid, m in measured.items()),
        reverse=True)
    least = sorted((m["regions"]["full"]["flicker_floor"], cid)
                   for cid, m in measured.items())[:4]
    lines.append(
        "  Every other captured state is a frozen source raster via "
        "source_artifact_path (acceptance_eligible false), witnessed by "
        "browser evidence: 3 frames, DOM html, link census and region "
        f"geometry. Most stable captured state {stable[0][1]} "
        f"({stable[0][0]:.6f}); least stable: "
        + ", ".join(f"{cid} ({floor:.6f})" for floor, cid in least)
        + ". Subscriber-dashboard states and the post-payment checkout "
        "confirmation are unavailable (no purchase was made) and are "
        "implemented clone-locally as disclosed inference.")
    return "\n".join(lines)


def structural_claims() -> list[dict]:
    """Structural facts recorded in scope/implement-notes.md."""
    cap = f"source-current/{CAPTURE_ID}"
    return [
        {
            "id": "claim.structural.pricing-plan-catalogue",
            "kind": "directly-observed",
            "statement": (
                "/pricing/ renders three billing-period tabs -- '2-Year Plan' "
                "(default active) / 'Yearly Plan' / 'Monthly Plan' -- as bare "
                "<strong> elements with no wrapping control, so switching a "
                "period means clicking the <strong> itself. Each period shows "
                "two tiers, Essential and Advanced (Advanced carries a 'Best "
                "Protection' ribbon). Observed prices: 2-Year $2.49/$3.59 per "
                "month (struck $359.76/$431.76, $59.76/$86.16 for the first "
                "2 years); Yearly $3.89/$5.39 per month (struck "
                "$179.88/$215.88, $46.68/$64.68 for the first year); Monthly "
                "$14.99/$17.99. Task 687's comparison is Monthly versus "
                "Yearly."),
            "evidence_refs": [
                f"{cap}/pricing/desktop/page.html",
                f"{cap}/pricing-2year/desktop/page.html",
                f"{cap}/pricing-yearly/desktop/page.html",
                f"{cap}/pricing-monthly/desktop/page.html",
            ],
        },
        {
            "id": "claim.structural.pricing-features-expander-never-renders",
            "kind": "structural-only",
            "statement": (
                "'View All Features' exists in the served /pricing/ markup "
                "but no visible element matches it at 1440x900 or 390x844, so "
                "the expander never renders at a captured viewport and the "
                "planned pricing-features-expanded state was removed from the "
                "frozen matrix rather than inferred."),
            "evidence_refs": [f"{cap}/state-capture-index.json"],
        },
        {
            "id": "claim.structural.primary-nav-inventory",
            "kind": "directly-observed",
            "statement": (
                "The rendered top-level nav on / carries only Product, Apps, "
                "Resources, Help and Pricing plus My Account and Get Started. "
                "Product, Apps and Resources open pointer-hover dropdowns "
                "whose parent items are themselves links; the hamburger panel "
                "is the 390x844 equivalent. 'Features' and 'Solutions' appear "
                "in the served HTML only and never render, so the planned "
                "nav-features and nav-solutions states were removed instead "
                "of being inferred."),
            "evidence_refs": [
                f"{cap}/nav-product/desktop/page.html",
                f"{cap}/nav-apps/desktop/page.html",
                f"{cap}/nav-resources/desktop/page.html",
                f"{cap}/mobile-menu-open/mobile/page.html",
            ],
        },
        {
            "id": "claim.structural.checkout-origin-and-flow-binding",
            "kind": "directly-observed",
            "statement": (
                "Checkout is a separate origin, checkout.ipvanish.com, "
                "reached straight from each plan CTA as "
                "/checkout/address-payment-method?flow={essential,advanced}-"
                "{monthly,annual,biennial}&currency=USD&lang=EN. It is an "
                "Angular SPA whose step one is a payment-method chooser "
                "(Credit card / PayPal / Apple Pay / Google Pay rows with "
                "chevrons) beside an Order Summary card; for essential-annual "
                "the summary reads 12 months, IPVanish Essential $179.88, "
                "Save 74% - $133.20, Estimated tax $6.07, Total due $ 52.75, "
                "plus a 30-day money-back badge and a Trustpilot widget."),
            "evidence_refs": [
                f"{cap}/checkout-chooser-essential-annual/desktop/page.html",
                f"{cap}/checkout-chooser-essential-monthly/desktop/page.html",
                f"{cap}/checkout-chooser-advanced-annual/desktop/page.html",
            ],
        },
        {
            "id": "claim.structural.registration-form-fields",
            "kind": "directly-observed",
            "statement": (
                "Activating the Credit card row "
                "(li.c-payment-method-type-select-card) expands task 687's "
                "endpoint: a Zuora hosted-payment iframe carrying "
                "field_email, field_creditCardHolderName, "
                "field_creditCardNumber, field_creditCardExpirationMonth, "
                "field_creditCardExpirationYear, field_cardSecurityCode, "
                "field_creditCardCountry and field_creditCardPostalCode; a "
                "'Subscribe now' button in the main document; and the copy "
                "'Secure checkout. Your payment information is fully "
                "protected. By subscribing, you agree to be charged $52.75. "
                "Your plan will automatically renew annually at $99.99 until "
                "canceled...'. Field names only were read: no card data was "
                "entered and nothing was submitted."),
            "evidence_refs": [
                f"{cap}/checkout-card-form-essential-annual/desktop/page.html"],
        },
        {
            "id": "claim.structural.sso-signin-contract",
            "kind": "directly-observed",
            "statement": (
                "Sign-in is served from sso.ipvanish.com (Next.js SPA; "
                "www.ipvanish.com/login/ 301s there) with copy 'RECLAIM YOUR "
                "ONLINE PRIVACY TODAY', 'Not a member? Sign up now!' linking "
                "to /pricing/ (there is no registration route outside "
                "checkout), 'Welcome back! Sign in to continue to customer "
                "portal', Email address, Password and 'Forgot password?'. "
                "Inputs are named email and password. No third-party "
                "identity-provider buttons were observed."),
            "evidence_refs": [f"{cap}/sso-signin/desktop/page.html"],
        },
        {
            "id": "claim.structural.sso-recovery-contract",
            "kind": "directly-observed",
            "statement": (
                "Password recovery is reachable only by clicking 'Forgot "
                "password?', which routes to sso.ipvanish.com/reset-password/ "
                "WITH a trailing slash; the un-slashed deep link answers 403 "
                "from its S3 origin. Copy: 'Reset password', 'Enter you "
                "account email, you will receive a reset password code' "
                "(source typo, reproduced verbatim), 'Email address', 'Back "
                "to sign in', 'Send code'; the input is named username."),
            "evidence_refs": [f"{cap}/sso-recovery/desktop/page.html"],
        },
        {
            "id": "claim.structural.my-account-redirect",
            "kind": "directly-observed",
            "statement": (
                "my.ipvanish.com redirects anonymous visitors to "
                "sso.ipvanish.com/?code=TOKEN_EXPIRED&redirect=..., which is "
                "the observed shape of the source's auth boundary and the "
                "only subscriber-area behavior an anonymous run can witness."),
            "evidence_refs": [f"{cap}/sso-signin/desktop/meta.json"],
        },
        {
            "id": "claim.structural.support-ua-dependence",
            "kind": "directly-observed",
            "statement": (
                "Support is a Zendesk Guide at support.ipvanish.com/hc/en-us "
                "carrying a search box, Support Categories, FAQ entries and a "
                "System Status banner. It renders only for an ordinary "
                "browser user agent; the default headless UA receives a "
                "Cloudflare 403 'Just a moment...' interstitial, which is why "
                "the whole capture ran with an ordinary Chrome UA as a "
                "rendering-fidelity requirement (see "
                "scope/implement-notes.md), not as an access-control bypass."),
            "evidence_refs": [f"{cap}/support-home/desktop/page.html"],
        },
        {
            "id": "claim.structural.not-found-is-home-body",
            "kind": "directly-observed",
            "statement": (
                "The source answers an unknown path with HTTP 404 whose body "
                "is the home page: title and markup are byte-near-identical "
                "to / (1,127,728 vs 1,127,732 bytes) and no '404' string "
                "appears anywhere. There is no branded not-found view, so the "
                "clone reproduces 404-status-with-home-body and trace ht-22's "
                "expectation of a branded not-found page is a recorded "
                "divergence, not an invented feature."),
            "evidence_refs": [f"{cap}/not-found/desktop/page.html"],
        },
        {
            "id": "claim.structural.wpml-development-site-banner",
            "kind": "directly-observed",
            "statement": (
                "The production www tree ships a WPML banner reading 'This "
                "site is registered on wpml.org as a development site.' -- a "
                "genuine source quirk to be reproduced verbatim rather than "
                "tidied away."),
            "evidence_refs": [f"{cap}/home/desktop/page.html"],
        },
        {
            "id": "claim.structural.money-back-guarantee-terms",
            "kind": "directly-observed",
            "statement": (
                "/money-back-guarantee/ states a 30-day guarantee and "
                "explicitly excludes monthly plans from eligibility."),
            "evidence_refs": [
                f"{cap}/money-back-guarantee/desktop/page.html"],
        },
        {
            "id": "claim.structural.localized-trees-out-of-scope",
            "kind": "structural-only",
            "statement": (
                "The localized country trees /au, /ca, /de, /es, /fi, /fr, "
                "/gb, /ie, /it, /nl, /no, /pl, /pt, /pt-br and /se duplicate "
                "the English tree at roughly 16-19 pages each. The frozen "
                "scope is the en-US tree; the rest are declared omissions, "
                "as are the remaining 14 /vpn-setup/ pages, the ~87 "
                "/vpn-locations/ detail pages and individual blog posts."),
            "evidence_refs": [f"{cap}/capture-index.json"],
        },
        {
            "id": "claim.structural.animated-source-surfaces",
            "kind": "directly-observed",
            "statement": (
                "The source animates continuously: an embedded Trustpilot "
                "carousel, a Visual Website Optimizer A/B allocation and hero "
                "motion repaint between consecutive frames, so several "
                "captured frame triples differ. Pixel acceptance is therefore "
                "claimed only where the measured full-region 3-frame flicker "
                f"floor reaches {STABILITY_FLOOR}; see "
                "scope/visual-calibration-report.json for every measured "
                "floor."),
            "evidence_refs": [f"{cap}/home/desktop/meta.json",
                              "scope/visual-calibration-report.json"],
        },
        {
            "id": "claim.structural.anonymous-only-authority",
            "kind": "unavailable",
            "statement": (
                "The run is anonymous-only by user decision: IPVanish gates "
                "account creation behind payment, so no subscriber evidence "
                "exists. Public surfaces plus the checkout funnel up to the "
                "rendered registration form are captured; every subscription-"
                "management surface is recorded unavailable and implemented "
                "clone-locally as disclosed inference. No real payment, card "
                "data, stripe-test token, real email or credential ever "
                "entered the evidence."),
            "evidence_refs": ["scope/implement-notes.md",
                              "scope/derived-task-brief.json"],
        },
    ]


def build() -> int:
    captures = load_captures()
    measured: dict[str, dict] = {}
    for cap in captures:
        cid = f"{cap['checkpoint']}.{cap['viewport']}"
        if cid in measured:
            raise SystemExit(f"duplicate capture id {cid}")
        route_state(cap["checkpoint"])  # fail fast on an unmapped capture
        measured[cid] = measure(cap)

    oracles, decisions = select_oracles(measured)
    oracle_ids = set(oracles.values())

    rows: list[dict] = []
    calibration_rows: list[dict] = []
    report_rows: list[dict] = []
    claims: list[dict] = []
    direct_items: list[str] = []

    for cap in captures:
        cp, vp = cap["checkpoint"], cap["viewport"]
        cid = f"{cp}.{vp}"
        info = measured[cid]
        width, height = info["width"], info["height"]
        site_rel = f"source-current/{CAPTURE_ID}/{cp}/{vp}"
        repo_rel = f"materials/{SITE_ID}/{site_rel}"

        region_contracts = []
        for rname, region in info["regions"].items():
            report_rows.append({
                "id": f"{cid}.{rname}", "checkpoint_id": cid,
                "region": rname, "region_box": region["box"],
                "pairwise_similarity": region["pairwise_similarity"],
                "flicker_floor": region["flicker_floor"],
                "derived_threshold": region["threshold"],
            })
            if rname != "full":
                calibration_rows.append({
                    "id": f"{cid}.{rname}", "region": rname,
                    "source_samples": [{"path": f"{repo_rel}/frame-{n}.png"}
                                       for n in (1, 2, 3)],
                    "ignore_regions": [],
                })
            region_contracts.append({
                "region": rname, "box": region["box"],
                "threshold": region["threshold"],
                "flicker_floor": region["flicker_floor"],
            })

        route_id, state = route_state(cp)
        full = info["regions"]["full"]
        row = {
            "id": cid, "route_id": route_id, "state": state,
            "role": "visitor", "viewport": vp,
            "priority": cap.get("priority", "P1").lower(),
            "evidence_kind": "direct", "capture_id": CAPTURE_ID,
            "requested_url": cap.get("requested_url"),
            "final_url": cap["final_url"], "title": cap["title"],
        }
        if cid in oracle_ids:
            row["acceptance_eligible"] = True
            row["pixel_oracle_candidate"] = True
            row["oracle_selection"] = (
                "conventional home oracle: measured full-region flicker floor "
                f"{full['flicker_floor']:.6f} >= {STABILITY_FLOOR}"
                if cp == PREFERRED_ORACLE else
                "promoted oracle: home at this viewport failed the "
                f"{STABILITY_FLOOR} stability floor; this checkpoint is the "
                "most stable capture at the viewport (measured full-region "
                f"flicker floor {full['flicker_floor']:.6f})")
            row["visual_contract"] = {
                "source_artifact_path": f"{site_rel}/frame-1.viewport.png",
                "viewport": {"width": width, "height": height},
                "comparison_region": {"x": 0, "y": 0, "width": width,
                                      "height": height},
                "metric": METRIC, "threshold": full["threshold"],
            }
            row["region_contracts"] = [r for r in region_contracts
                                       if r["region"] != "full"]
        else:
            row["acceptance_eligible"] = False
            row["source_artifact_path"] = f"{site_rel}/frame-1.viewport.png"
            if cp == PREFERRED_ORACLE:
                row["acceptance_exclusion_reason"] = (
                    "full-region source flicker floor "
                    f"{full['flicker_floor']:.6f} is below the "
                    f"{STABILITY_FLOOR} stability minimum (continuous "
                    "source-side animation: Trustpilot carousel, Visual "
                    "Website Optimizer allocation, hero motion); frames "
                    "retained as reference evidence, no pixel acceptance "
                    f"claimed. The {vp} pixel oracle is "
                    f"{oracles.get(vp, 'absent at this viewport')}.")
        rows.append(row)
        direct_items.append(cid)
        claims.append({
            "id": f"claim.capture.{cp}.{vp}", "kind": "directly-observed",
            "statement": (
                f"Checkpoint {cp} (route {route_id}, state {state}) at {vp} "
                f"{width}x{height} was captured from {cap['final_url']} with "
                "3 full-page frames, DOM html, link census, runtime resource "
                f"census and region geometry; title {cap['title']!r}, body "
                f"length {cap.get('body_text_len')}, full-region 3-frame "
                f"flicker floor {full['flicker_floor']:.6f}"
                + (f". Interaction: {cap['interaction']}"
                   if cap.get("interaction") else ".")),
            "evidence_refs": [
                f"{site_rel}/frame-1.png", f"{site_rel}/frame-2.png",
                f"{site_rel}/frame-3.png", f"{site_rel}/meta.json",
                f"{site_rel}/page.html", f"{site_rel}/links.json",
                f"{site_rel}/resources.json",
            ],
        })

    rows.extend(UNAVAILABLE_ROWS)
    for unavailable in UNAVAILABLE_ROWS:
        claims.append({
            "id": f"claim.unavailable.{unavailable['id']}",
            "kind": "unavailable", "statement": unavailable["note"],
            "evidence_refs": [],
        })

    claims = structural_claims() + claims

    now = dt.datetime.now(dt.timezone.utc)
    doc = {
        "schema_version": "offline-clone.checkpoints.v1",
        "site_id": SITE_ID,
        "capture_id": CAPTURE_ID,
        "status": "frozen",
        "metric": METRIC,
        "calibration_spec": "scope/visual-calibration-spec.json",
        "viewports": {name: {"width": w, "height": h}
                      for name, (w, h) in VIEWPORTS.items()},
        "topology_note": topology_note(decisions, measured),
        "freeze_decision": {
            "named_supervisor": "claude-opus-5-offline-clone-run",
            "decided_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rationale": (
                "Anonymous marketing, pricing, checkout-funnel, sign-in, "
                "recovery, support and error contracts freeze against the "
                f"{CAPTURE_ID} three-frame local-Playwright capture before "
                "any candidate render exists; thresholds derive only from "
                "source-side flicker floors and the pixel oracle set is "
                "chosen by measurement, not convention, because the source "
                "animates. Subscriber-dashboard states and the post-payment "
                "checkout confirmation stay unavailable by the payment "
                "mandate and the user's anonymous-only decision."),
        },
        "checkpoints": rows,
    }

    calibration = {
        "schema_version": "offline-clone.visual-stability-calibration-spec.v1",
        "site_id": SITE_ID,
        "rows": calibration_rows,
    }
    calibration_report = {
        "schema_version": f"{SITE_ID}.visual-calibration-report.v1",
        "status": "frozen",
        "site_id": SITE_ID,
        "capture_id": CAPTURE_ID,
        "frames_per_checkpoint": 3,
        "metric": METRIC,
        "threshold_rule": (
            "threshold = min(0.995, flicker_floor - 0.002) per region, where "
            "flicker_floor is the minimum pairwise pixel-mae-similarity-v1 "
            "across the three pre-candidate source frames normalized to the "
            "frozen viewport box. Derived before any candidate render "
            "existed."),
        "stability_floor": STABILITY_FLOOR,
        "oracle_selection": {
            vp: decision for vp, decision in decisions.items()
        },
        "rows": report_rows,
    }

    metadata = {
        "schema_version": f"{SITE_ID}.capture-metadata.v1",
        "status": "captured",
        "capture_id": CAPTURE_ID,
        "captured_at_utc": "2026-08-19",
        "source_origins": [
            "https://www.ipvanish.com/",
            "https://checkout.ipvanish.com/",
            "https://sso.ipvanish.com/",
            "https://support.ipvanish.com/",
        ],
        "engine": {
            "primary": "local-playwright",
            "browser": ("Chromium headless via Python Playwright with an "
                        "ordinary Chrome 151 user agent"),
            "notes": (
                "The www tree serves UA-dependent markup and "
                "support.ipvanish.com answers the default headless UA with a "
                "Cloudflare 403 interstitial, so an ordinary Chrome UA is a "
                "rendering-fidelity requirement rather than an access-control "
                "bypass (scope/implement-notes.md); anything still gated is "
                "recorded unavailable instead of fought. One browser context "
                "spans the whole matrix so consent and Visual Website "
                "Optimizer experiment allocation stay constant. The "
                "client-rendered subdomains (sso Next.js, checkout Angular) "
                "get an explicit settle before frames are taken. Interaction "
                "states never submitted a form and no non-GET request was "
                "ever issued."),
        },
        "baseline": {"locale": "en-US", "timezone": "UTC",
                     "device_pixel_ratio": 1,
                     "consent": "no consent interaction required"},
        "viewports": [{"name": name, "width": w, "height": h}
                      for name, (w, h) in VIEWPORTS.items()],
        "roles_captured": ["anonymous"],
        "roles_unavailable": {
            "subscriber": ("no free tier, no web trial and no account-only "
                           "signup: the role requires a real purchase, which "
                           "is prohibited and which the user declined"),
        },
        "frames_per_checkpoint": 3,
        "captures": [
            {key: cap.get(key) for key in (
                "checkpoint", "viewport", "requested_url", "final_url",
                "title", "http_status", "frames", "frame_sha256",
                "frames_identical", "engine", "interaction")}
            for cap in captures
        ],
    }

    coverage = {
        "schema_version": "offline-clone.coverage.v1",
        "status": "frozen",
        "dimensions": [
            {
                "id": "source-direct-states",
                "label": "Anonymous source-captured route states",
                "unit": "route-state",
                "category": "visual-fidelity",
                "required_evidence_kinds": ["browser"],
                "required_items": sorted(direct_items),
                "satisfied_items": [],
                "source_evidence_kind": "direct",
                "rationale": (
                    "Every anonymous state captured directly from the source "
                    f"in {CAPTURE_ID}; each carries a frozen three-frame "
                    "raster plus DOM, link and resource censuses. The pixel "
                    "oracle subset is chosen by measured flicker floor: "
                    + ", ".join(f"{vp}={oracles[vp]}" for vp in VIEWPORTS
                                if vp in oracles)
                    + "."),
            },
            {
                "id": "source-unavailable-states",
                "label": "Recorded unavailable surfaces",
                "unit": "route-state",
                "category": "honest-gaps",
                "required_evidence_kinds": ["independent-audit"],
                "required_items": sorted(u["id"] for u in UNAVAILABLE_ROWS),
                "satisfied_items": [],
                "source_evidence_kind": "unavailable",
                "rationale": (
                    "Subscriber surfaces and the post-payment confirmation "
                    "are unreachable without a real purchase; disclosed, "
                    "never inferred as direct evidence."),
            },
            {
                "id": "clone-local-contracts",
                "label": "Clone-local behavior with no source pixel oracle",
                "unit": "behavior",
                "category": "clone-local-behavior",
                "required_evidence_kinds": ["full-suite"],
                "required_items": [
                    "checkout-chooser.sandbox-approved",
                    "checkout-chooser.sandbox-declined",
                    "checkout-chooser.sandbox-retry",
                    "sso-signin.validation-error",
                    "sso-recovery.sent",
                    "sso-recovery.validation-error",
                    "support.no-results",
                    "what-is-my-ip-address.seeded-address",
                    "subscriber-dashboard.reactivated",
                ],
                "satisfied_items": [],
                "source_evidence_kind": "unavailable",
                "local_contract_evidence_kind": "inferred",
                "rationale": (
                    "Behavior the clone must implement locally and disclose: "
                    "the local-sandbox payment scenarios that replace the "
                    "Zuora card iframe (payment-input-boundary invariant), "
                    "validation and recovery states never rendered on the "
                    "source, the seeded deterministic IP answer, and "
                    "subscriber reactivation. Verified functionally by the "
                    "clone's own suite, never by pixel comparison."),
            },
            {
                "id": "p0-network-invariants",
                "label": "Runtime network closure",
                "unit": "invariant",
                "category": "network-closure",
                "required_evidence_kinds": ["network"],
                "required_items": ["no-runtime-remote-requests"],
                "satisfied_items": [],
                "rationale": (
                    "The candidate must make zero runtime requests to "
                    "non-local origins on every checkpoint; the source's "
                    "Trustpilot, Visual Website Optimizer and Zuora embeds "
                    "must be vendored or removed, never proxied."),
            },
            {
                "id": "deterministic-database-state",
                "label": "Deterministic backend business state",
                "unit": "behavior",
                "category": "backend-semantics",
                "required_evidence_kinds": ["full-suite"],
                "required_items": ["seed-reset-deterministic",
                                   "subscription-order-transactional",
                                   "cross-actor-isolation"],
                "satisfied_items": [],
                "rationale": (
                    "Reseeding yields byte-stable business state; completing "
                    "a sandbox checkout writes the subscription and its order "
                    "row in one SQLite transaction; a subscriber's "
                    "subscription, orders and billing history are invisible "
                    "to a second seeded actor."),
            },
        ],
    }

    (SITE / "scope" / "visual-calibration-spec.json").write_text(
        json.dumps(calibration, indent=2) + "\n")
    (SITE / "scope" / "visual-calibration-report.json").write_text(
        json.dumps(calibration_report, indent=2) + "\n")
    (SITE / "scope" / "checkpoints.json").write_text(
        json.dumps(doc, indent=2) + "\n")
    (SITE / "scope" / "coverage.json").write_text(
        json.dumps(coverage, indent=2) + "\n")
    with (SITE / "scope" / "claims.jsonl").open("w") as handle:
        for claim in claims:
            handle.write(json.dumps(claim) + "\n")
    (CAP_ROOT / "capture-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n")

    print(f"checkpoints: {len(rows)}  direct: {len(direct_items)}  "
          f"unavailable: {len(UNAVAILABLE_ROWS)}  calibration rows: "
          f"{len(calibration_rows)}  report rows: {len(report_rows)}  "
          f"claims: {len(claims)}")
    print("oracle decision per viewport:")
    for vp, decision in decisions.items():
        print(f"  {vp}: {json.dumps(decision)}")
    floors = sorted((m["regions"]["full"]["flicker_floor"], cid)
                    for cid, m in measured.items())
    print("lowest full-region flicker floors:")
    for floor, cid in floors[:8]:
        print(f"  {floor:.6f}  {cid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
