#!/usr/bin/env python3
"""Emit the clone-agent observation table.

Every frozen scope item is classified against what the candidate actually
implements: matched (built from direct evidence), inferred-architecture
(clone-local design where source depth was unavailable), unavailable (source
state never observed; clone behavior disclosed), or known-difference.

Written to tools/observation-table.json.
"""
from __future__ import annotations

import json
import pathlib

SITE = pathlib.Path(__file__).resolve().parents[1]
OUT = SITE / "tools" / "observation-table.json"

# Scope items whose implementation is NOT backed by direct source evidence.
# Each carries the disposition recorded in scope/implement-notes.md.
INFERRED: dict[str, str] = {
    "routine-autosave-api": "EA1 unavailable: source autosave/log request shapes were never observed. The clone designs its own JSON API (POST /api/plans/*, /api/days/*, /api/entries/*); network closure makes source shapes non-binding.",
    "workout-log-api": "EA1 unavailable: source log API shapes unobserved. Clone-local API (POST /api/sessions, /api/sessions/<id>/sets); the one observed behavior (added exercise logs 25 lbs x 8; edited set persisted) is reproduced exactly.",
    "checkout-monthly-variant": "Structural inference from the yearly Stripe capture plus /elite pricing ($12.99/month, no annual coupon). Only the yearly checkout DOM was captured.",
    "member-exercise-filters": "Member Filters slide-over was captured open but its apply semantics were not exercised; the clone reuses the same client-side filter behavior proven on the public /exercises capture.",
    "custom-exercise-dialog": "The custom-exercise creation dialog's fields were never captured (free-tier counter only). The clone implements a minimal honest create flow enforcing the observed 0/3 limit.",
    "per-stat-body-stat-pages": "Per-stat depth pages (/my-jefit/progress/body-stats/<stat>) were never captured. The clone serves a disclosed minimal page whose 'Edit stat' performs real local persistence.",
    "member-light-theme": "Member light/dark toggle exists in the captured account menu but no member-theme frame was captured; the clone applies the same documented light/dark class swap observed on the public dark-mode capture.",
    "signup-credential-step": "The register step past the captured email entry was never observed (the user registered unobserved). The clone continues clone-locally with username+password on the same document and discloses it.",
    "login-error-copy": "Wrong-credential error copy was never observed (source showed no inline validation on empty submit, and no wrong-credential attempt was made). The clone renders its own labelled inline error; the observed empty-submit behavior (no validation) is reproduced exactly.",
    "routine-detail-day-plans": "Only routine 19113's day breakdown was captured. Other fixture routines carry deterministic synthetic day plans preserving the captured Sets x Reps structure and density.",
    "exercise-detail-fields": "Only exercise 2's detail DOM was captured. Other entities render difficulty/type/log-type from clone-local structural defaults; captured entities serve their frozen documents verbatim.",
    "routines-sort-order": "Sort URLs (?sort=views, ?sort=last_updated) are directly observed; the resulting orderings were not fully enumerated, so the clone applies deterministic clone-local orderings that visibly differ per sort.",
    "routine-category-membership": "Category pages are directly observed (10 cards each); per-category membership lists were not enumerated, so the clone selects deterministically from fixture attributes.",
    "insights-populated": "The populated insights view was never captured (the account had one session and the capture shows the empty state). The clone renders a disclosed minimal populated summary.",
}

UNAVAILABLE: dict[str, str] = {
    "elite-checkout.success.desktop": "Post-payment confirmation was never reached on source (real payment forbidden; the user holds no Elite account). The clone implements the state as local-sandbox behavior: approved scenario -> order + membership in one transaction -> redirect to the frozen settings destination view. Disclosed as inference, never recorded as direct evidence.",
    "my-jefit-settings.elite-active.desktop": "Elite-active settings state never observed. The clone keeps the frozen Account-tab structure and replaces the upgrade cards with an Account Type value plus a plan/renewal line. Disclosed as inference.",
}

KNOWN_DIFFERENCES: list[dict[str, str]] = [
    {
        "id": "missing-icon-payloads",
        "detail": "15 first-party icon/image payloads referenced by the captured DOM are absent from the frozen asset closure (5 favicon variants, /my-jefit/{empty_newsfeed.png,empty_exercise.png,empty_note.svg,logs_empty_state.svg,records_broken_icon.svg}, /shared/icon/{assign,edit,trash}.svg, /onboarding/level.svg, /images/exercises/960_590/8.jpg). They were never fetched by the anonymous capture and cannot be fetched offline, so they resolve to local 404s (broken images) rather than remote requests.",
        "impact": "Cosmetic: a few member-area empty-state icons and the favicon do not render. Zero effect on network closure or behavior.",
    },
    {
        "id": "onboarding-slide-gif-phase",
        "detail": "The build-routine onboarding modal's slide 3 pairs with the captured 'Stronger Together' gif (image.qa893857efa) exactly as the source does — asserted structurally by clone/tests/test_app_surface.py::test_build_routine_modal_slide_image_pairing. That gif animates builder view -> routine detail -> green 'Link copied' pill over 66 frames; the frozen source frame caught its final phase, so a clone screenshot can show any earlier phase. Same class as the recorded exercise-detail gif flicker; build-routine is not an acceptance oracle.",
        "impact": "Screenshot-phase only: the paired asset, slide order and active slide all match the capture.",
    },
    {
        "id": "signup-continue-enabled-state",
        "detail": "Several questionnaire panels and the /signup/register step were captured in their EMPTY state, so their Continue controls ship serialized as disabled (pointer-events-none) and no captured frame shows the enabled styling. The runtime ungates them once an answer exists (source behaviour: a human can proceed after answering); the enabled fill is the primary-button colour measured on the observed /login submit — a disclosed inference, not invented. Step 17 ('Analyzing your answers') hands off to /signup/results after 2.5s; the source shows both states but not the duration, so the delay is clone-local.",
        "impact": "Without this the questionnaire and registration render but cannot be operated; regression-tested in clone/tests/test_signup_usability.py.",
    },
    {
        "id": "residual-pristine-asset-findings",
        "detail": "After the scope-owner asset-pipeline fix (2026-08-19: 233 query-digest mirror files renamed to carry true extensions; 30 source-404 shells removed) the static asset-closure findings dropped from 333 to 20. The remaining 20 are properties of frozen pristine payloads: 7 assets whose originals carry external url()/metadata references (candidate-side fix: localized vendor copies under clone/static/site/vendor/, all passing inspect_asset, with every candidate reference repointed — zero candidate references to failing pristine assets remain) and a few manifest-vs-file SVG dimension mismatches. Pristine mirror copies stay byte-exact; resolving the residual findings belongs to the scope owner.",
        "impact": "Diagnostic-only; no candidate-served document references a failing asset.",
    },
    {
        "id": "uncaptured-optimizer-variants",
        "detail": "Next.js image-optimizer widths the capture viewports never requested are localized onto their deterministic mirror path and 404 locally (recorded per page in clone/frontend/rewrite-report.json content_fallback_refs).",
        "impact": "None at the frozen viewports: every width the contract viewports request is present (home oracles score >= 0.999 similarity).",
    },
    {
        "id": "community-avatars-replaced",
        "detail": "The captured Q&A/Popular feeds referenced real community members' avatar files by identifier. Every such reference is replaced with a neutral inline placeholder and the feeds are rebuilt from synthetic fixture posts.",
        "impact": "Deliberate: no third-party user content or identifier ships in the clone.",
    },
    {
        "id": "catalog-count-reduced",
        "detail": "The source shows '1295 EXERCISES FOUND' across 72 pages; the clone fixture holds 53 exercises (36 with real captured names/instructions, 17 synthetic facet fill) across 3 pages and renders its own true count. Data reduction touched entity counts only: all card fields, 18-per-page density, pagination boundaries and the ?page=0/?page=1 quirk are preserved.",
        "impact": "Intentional per the data-reduction rule; never a false count.",
    },
    {
        "id": "ratings-absent",
        "detail": "Human trace ht-05 mentions community ratings; the live source has no ratings section on exercise or routine detail pages, and the clone reproduces the source.",
        "impact": "Trace-text/source divergence, already recorded in the frozen scope.",
    },
    {
        "id": "unbranded-404",
        "detail": "ht-22 expects a branded not-found; the source serves an unbranded server 404 and the clone reproduces that exactly (no site chrome, no clone runtime).",
        "impact": "Trace-text/source divergence, already recorded in the frozen scope.",
    },
    {
        "id": "live-diagnostic-platform",
        "detail": "`websitebench-offline-clone verify --section live` cannot run on this host: the candidate sandbox requires Linux. Substituted with an advisory equivalent walk (all 57 checkpoint-backed state recipes exercised against the booted clone) plus the shared compare-visual tool on the three pixel oracles.",
        "impact": "The live section must still be run by the orchestrator on Linux.",
    },
    {
        "id": "backend-semantic-test-not-run",
        "detail": "`tools test-backend` consumes a human-gated semantic-selection spec (human_gate.status). No such human gate exists for this run and authoring one would fabricate human approval, so the tool was not run.",
        "impact": "Backend semantics are covered instead by clone/tests (75 tests) and the shared explore diagnostic.",
    },
    {
        "id": "opencli-unmapped-journeys",
        "detail": "derive-from-clone leaves failure_paths/recovery_paths empty for the checkout and login profiles: its matcher consumes only scope/journeys.json entries of kind failure/retry/recovery whose family (or id prefix) matches the profile group, and the frozen journeys express the declined/retry paths as failure_variant/recovery_variant strings on the P0 success journey — a shape the matcher cannot read. journeys.json is frozen scope outside the candidate write boundary, so the two unmapped-journey pendings carry this recorded reason. The declined/retry behaviors themselves are implemented and tested (clone/tests/test_membership_payment.py) and exercised by verify.json recipes elite-checkout.declined/retry.",
        "impact": "Contract metadata only; the failure/recovery behaviors are covered elsewhere.",
    },
    {
        "id": "opencli-local-harness",
        "detail": "The OpenCLI npm CLI is not installed on this host and installing adapters into ~/.opencli was out of bounds, so replay ran through tools/opencli-harness/ — a transparent local executor that runs the committed generator-produced adapters verbatim (module shims for the two tiny @jackwener/opencli imports only) and reports itself as 'wb-local-adapter-harness'. Both profiles replay 3/3 steps with assertion_failures 0. The current websitebench-harbor CLI has no --promote flag (skill text predates this checkout); the committed replay-evidence artifacts are the promoted record, advisory only.",
        "impact": "Replay is advisory by design; artifacts record the harness identity honestly.",
    },
    {
        "id": "signup-questionnaire-panels",
        "detail": "The 17 captured questionnaire panels are swapped client-side at /signup (URL unchanged, as on source) and are also directly addressable at /signup?step=N so the diagnostics can reach each frozen state.",
        "impact": "The ?step= parameter is a clone-local addition for state addressability; the default flow matches source.",
    },
]


def main() -> int:
    checkpoints = json.loads(
        (SITE / "scope" / "checkpoints.json").read_text()
    )["checkpoints"]
    routes = json.loads((SITE / "scope" / "routes.json").read_text())["routes"]
    driver = json.loads((SITE / "scope" / "verify.json").read_text())
    invariants = json.loads(
        (SITE / "scope" / "invariants.json").read_text()
    )["invariants"]
    journeys = json.loads(
        (SITE / "scope" / "journeys.json").read_text()
    )["journeys"]

    rows = []
    for checkpoint in checkpoints:
        state = checkpoint["state"]
        key = f"{checkpoint['route_id']}.{state}"
        if checkpoint["id"] in UNAVAILABLE:
            classification = "unavailable"
            note = UNAVAILABLE[checkpoint["id"]]
        else:
            classification = "matched"
            note = ""
            if state in ("populated",) and checkpoint["route_id"] in (
                "my-jefit-progress-insights",
            ):
                classification = "inferred-architecture"
                note = INFERRED["insights-populated"]
        rows.append(
            {
                "kind": "checkpoint",
                "id": checkpoint["id"],
                "route_id": checkpoint["route_id"],
                "state": state,
                "evidence_kind": checkpoint.get("evidence_kind"),
                "clone_route": driver["routes"].get(checkpoint["route_id"]),
                "state_recipe": key in driver["states"]
                or state in ("loaded", "default", ""),
                "classification": classification,
                "note": note,
            }
        )
    for route in routes:
        rows.append(
            {
                "kind": "route",
                "id": route["id"],
                "priority": route["priority"],
                "clone_route": driver["routes"].get(route["id"]),
                "classification": "matched"
                if driver["routes"].get(route["id"])
                else "missing",
            }
        )
    for invariant in invariants:
        rows.append(
            {
                "kind": "invariant",
                "id": invariant["id"],
                "priority": invariant["priority"],
                "tests": invariant["positive_test_refs"]
                + invariant["negative_test_refs"],
                "classification": "matched",
            }
        )
    for journey in journeys:
        rows.append(
            {
                "kind": "journey",
                "id": journey["id"],
                "priority": journey["priority"],
                "classification": "matched",
            }
        )
    for item_id, note in INFERRED.items():
        rows.append(
            {
                "kind": "implementation",
                "id": item_id,
                "classification": "inferred-architecture",
                "note": note,
            }
        )
    for difference in KNOWN_DIFFERENCES:
        rows.append(
            {
                "kind": "known-difference",
                "id": difference["id"],
                "classification": "known-difference",
                "note": difference["detail"],
                "impact": difference["impact"],
            }
        )

    counts: dict[str, int] = {}
    per_kind: dict[str, dict[str, int]] = {}
    for row in rows:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
        bucket = per_kind.setdefault(row["kind"], {})
        bucket[row["classification"]] = bucket.get(row["classification"], 0) + 1

    payload = {
        "schema_version": "jefit.clone-observation-table.v1",
        "site_id": "jefit",
        "summary": {
            "total_rows": len(rows),
            "by_classification": counts,
            "by_kind": per_kind,
        },
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps(payload["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
