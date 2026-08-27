#!/usr/bin/env python3
"""Build source-current/<capture-id>/index.json from what is on disk.

The index is assembled by reading the captured units back off disk rather
than by trusting the pass records, so it can only claim coverage that
actually exists. Every frozen checkpoint ends up in exactly one of two
places:

    units               a directory containing page.html, three frames and
                        meta.json really is present
    removed_state_notes it is not, with the reason

Nothing is silently dropped. That includes the checkpoints the frozen
contract itself already marks unavailable or inferred: they appear here with
their reason too, so a reader never has to diff this index against
scope/checkpoints.json to discover an omission.

`capture_divergences` is the third list, and the one worth reading first: a
unit that WAS captured but does not show what the frozen contract expected it
to show. A divergence is not a missing unit and must not be filed as one --
it is evidence that the source, or the vantage point, is not what the scope
pass recorded.

Usage:
    python materials/deleteme/tools/build_index.py --site-dir materials/deleteme
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import capture_common as cc  # noqa: E402
import capture_plan as cp  # noqa: E402

REQUIRED_FILES = ("page.html", "meta.json", "frame-1.viewport.png",
                  "frame-2.viewport.png", "frame-3.viewport.png")


def load_pass_records(out_root: pathlib.Path) -> dict[tuple[str, str], dict]:
    records: dict[tuple[str, str], dict] = {}
    for name in ("_pass-navigable.json", "_pass-interaction.json"):
        path = out_root / name
        if not path.is_file():
            continue
        for record in json.loads(path.read_text()).get("records", []):
            key = (record.get("unit") or "", record.get("viewport") or "")
            records[key] = record
    return records


def build(site: pathlib.Path) -> int:
    out_root = site / "source-current" / cc.CAPTURE_ID
    navigable, interactive, skipped = cp.plan_units(site)
    pass_records = load_pass_records(out_root)

    units: list[dict] = []
    removed: list[dict] = []
    divergences: list[dict] = []

    for planned in navigable + interactive:
        unit_dir = out_root / planned["unit"] / planned["viewport"]
        record = pass_records.get((planned["unit"], planned["viewport"]), {})
        missing = [f for f in REQUIRED_FILES if not (unit_dir / f).is_file()]
        if missing:
            reason = record.get("reason") or record.get("error") or (
                f"unit directory is incomplete (missing {', '.join(missing)})")
            removed.append({
                "checkpoint": planned["checkpoint"],
                "unit": planned["unit"],
                "viewport": planned["viewport"],
                "route_id": planned["route_id"],
                "state": planned["state"],
                "priority": planned["priority"],
                "acceptance_eligible": planned["acceptance_eligible"],
                "category": "planned-but-not-present-in-the-source",
                "reason": reason,
                "control": record.get("control"),
                "control_detail": record.get("control_detail") or {},
            })
            continue
        meta = json.loads((unit_dir / "meta.json").read_text())
        units.append({
            "checkpoint": planned["checkpoint"],
            "unit": planned["unit"],
            "viewport": planned["viewport"],
            "route_id": planned["route_id"],
            "state": planned["state"],
            "priority": planned["priority"],
            "acceptance_eligible": planned["acceptance_eligible"],
            "evidence_kind": planned["evidence_kind"],
            "capture_pass": meta.get("capture_pass"),
            "path": f"{planned['unit']}/{planned['viewport']}",
            "requested_url": meta.get("requested_url"),
            "final_url": meta.get("final_url"),
            "http_status": meta.get("http_status"),
            "title": meta.get("title"),
            "captured_at": meta.get("captured_at"),
            "frames": meta.get("frames"),
            "frames_identical": meta.get("frames_identical"),
            "has_fields_json": (unit_dir / "fields.json").is_file(),
            "reference_count": meta.get("reference_count"),
            "quirks": meta.get("quirks", []),
        })

    for entry in skipped:
        removed.append({
            "checkpoint": entry["checkpoint"],
            "unit": entry["unit"],
            "viewport": entry["viewport"],
            "route_id": entry["route_id"],
            "state": entry["state"],
            "priority": entry["priority"],
            "acceptance_eligible": entry["acceptance_eligible"],
            "category": "deliberately-not-attempted-on-the-live-source",
            "reason": entry["reason"],
            "contract_evidence_kind": entry.get("contract_evidence_kind"),
            "contract_note": entry.get("contract_note"),
        })

    for note in cp.REMOVED_STATE_NOTES:
        removed.append({
            "category": "surface-deliberately-not-visited",
            "surface": note["surface"],
            "decision": note["decision"],
            "reason": note["reason"],
        })

    # --- divergences: captured, but not what the contract expected ---------
    checkout_units = [u for u in units if u["route_id"] == "checkout"]
    if checkout_units:
        divergences.append({
            "checkpoints": [u["checkpoint"] for u in checkout_units],
            "expected": "scope/derived-task-brief.json records a rendered "
                        "checkout form (First/Last Name, Email, Address, a "
                        "Stripe Payment Element, agreements, a promo panel and "
                        "a 'Purchase & Start Deleting' submit)",
            "observed": "the SPA renders 'Checkout Session Expired' with a "
                        "single 'Start New Checkout' action and no form at "
                        "all. Two causes are visible in the capture and only "
                        "one is ours: (a) the page's own anonymous GET to its "
                        "API answers HTTP 401 'Authentication required', which "
                        "the GET-only guard did not touch, and (b) the guard "
                        "aborted the page's POST to "
                        "/api/checkout/checkout/session. The form was "
                        "therefore not observed on this run, and no field "
                        "inventory for it is claimed.",
            "consequence": "checkout.promo-open is unreachable, and the "
                           "checkout field inventory in the task brief remains "
                           "the only record of the form's shape",
        })
    plans_size = [r for r in removed
                  if r.get("state", "").startswith("size-")]
    if plans_size:
        divergences.append({
            "checkpoints": [r["checkpoint"] for r in plans_size],
            "expected": "scope/routes.json describes two tab strips on the "
                        "plan grid: billing term and plan size (Single / "
                        "Couple / Family), defaulting to 2 Years + Couple",
            "observed": "the plan page ships two filter grids and its own "
                        "script picks one by geography: div.us-price-toggle "
                        "gets display:block and "
                        "div#fs-grid-filter-activation.international-price-"
                        "toggle gets display:none. The size tab strip exists "
                        "only inside the hidden international grid. The grid an "
                        "anonymous US visitor sees has NO size dimension: it "
                        "shows the 1 Person, 2 People and Family cards side by "
                        "side and filters them by term alone. The size tabs "
                        "were found in the DOM, found invisible, and not "
                        "clicked.",
            "consequence": "four p0 checkpoints (plans.size-single/couple/"
                           "family desktop and plans.size-single mobile) have "
                           "no observable source state from this vantage "
                           "point. The hidden grid's markup is present in the "
                           "captured plans/*/page.html for anyone who needs "
                           "its structure.",
        })
    complete = [u for u in units if u["route_id"] == "checkout-complete"]
    if complete:
        divergences.append({
            "checkpoints": [u["checkpoint"] for u in complete],
            "expected": "scope/checkpoints.json marks checkout-complete.mobile "
                        "structural-only, 'the rendered page was never reached "
                        "because submitting is a real purchase'",
            "observed": "app.joindeleteme.com/checkout/complete answers 200 to "
                        "an anonymous GET and renders its full confirmation "
                        "copy ('Payment Successful!', 'Check your email for "
                        "next steps'). No purchase was made and none was "
                        "needed.",
            "consequence": "this checkpoint is now current-direct evidence "
                           "rather than structural-only; the contract's "
                           "evidence_kind is more pessimistic than the source",
        })

    viewport_counts: dict[str, int] = {}
    for unit in units:
        viewport_counts[unit["viewport"]] = \
            viewport_counts.get(unit["viewport"], 0) + 1

    index = {
        "schema_version": "deleteme.source-capture-index.v1",
        "capture_id": cc.CAPTURE_ID,
        "created_at": cc.utc_now(),
        "source_origins": sorted({
            "https://joindeleteme.com",
            "https://app.joindeleteme.com",
            "https://help.joindeleteme.com",
            "https://privacy.joindeleteme.com",
        }),
        "channel": {
            "engine": "local-headless-playwright-chromium",
            "ua": cc.CHROME_UA,
            "locale": cc.LOCALE,
            "timezone": cc.TIMEZONE,
            "device_scale_factor": 1,
            "vantage_point": "anonymous, no cookies carried between units, "
                             "United States egress",
        },
        "safety": {
            "methods_allowed": ["GET", "HEAD"],
            "non_get_enforcement": "a context.route handler aborts every "
                                   "request whose method is not GET or HEAD",
            "fields_filled": 0,
            "forms_submitted": 0,
            "consent_controls_clicked": 0,
            "chat_widgets_opened": 0,
            "accounts_created": 0,
            "password_resets_requested": 0,
            "credentials_persisted": "none: no cookie, token, authorization "
                                     "header or session id is written to disk, "
                                     "and every persisted URL is "
                                     "query-stripped unless its query is an "
                                     "opaque plan/term/qty or search term",
            "search_urls_requested": 1,
            "search_directive": "robots.txt disallows /*?s=; exactly one "
                                "user-equivalent search page view was taken",
        },
        "totals": {
            "checkpoints_frozen": len(navigable) + len(interactive)
            + len(skipped),
            "units_captured": len(units),
            "units_acceptance_eligible": sum(
                1 for u in units if u["acceptance_eligible"]),
            "removed_states": len(removed),
            "divergences": len(divergences),
            "by_viewport": viewport_counts,
        },
        "units": sorted(units, key=lambda u: (u["unit"], u["viewport"])),
        "removed_state_notes": removed,
        "capture_divergences": divergences,
    }
    path = out_root / "index.json"
    path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(index["totals"], indent=2))
    print(f"index -> {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", default="materials/deleteme")
    args = parser.parse_args()
    return build(pathlib.Path(args.site_dir).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
