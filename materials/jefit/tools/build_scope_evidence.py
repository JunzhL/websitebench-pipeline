#!/usr/bin/env python3
"""Freeze the jefit scope against the 2026-08-18.jefit-r1 capture evidence.

Modeled on materials/aspca-pet-insurance/tools/build_scope_evidence.py with
the same frozen evidence topology: the pixel-locked visual_contract oracle is
exactly home.{desktop,tablet,mobile}; every other captured (checkpoint,
viewport) is retained as a frozen source raster via source_artifact_path and
witnessed by browser evidence. Thresholds derive ONLY from source-side
3-frame calibration: threshold = min(0.995, flicker_floor - 0.002).

jefit-specific extension: authenticated member states were captured inside
the user-provided session and their raw artifacts carry account PII, so per
the entry prompt's data-retention rule they live ONLY in the git-ignored
source-auth-scratch/ directory. Their checkpoint rows are recorded as
evidence_kind 'direct' with artifact_retention 'source-auth-scratch' and no
committed raster; they are never acceptance-eligible pixel contracts.
Post-payment states remain 'unavailable' (payment never performed on source).

Deterministic; reads capture-index.json + state-capture-index.json, writes
scope/checkpoints.json, scope/visual-calibration-spec.json,
scope/visual-calibration-report.json, scope/claims.jsonl, scope/coverage.json
and source-current/<id>/capture-metadata.json.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

from PIL import Image, ImageChops, ImageStat

SITE = pathlib.Path(__file__).resolve().parents[1]
SITE_ID = "jefit"
CAPTURE_ID = "2026-08-18.jefit-r1"
AUTH_CAPTURE_ID = "2026-08-18.jefit-auth-r1"
CAP_ROOT = SITE / "source-current" / CAPTURE_ID
METRIC = "pixel-mae-similarity-v1"
BASE_THRESHOLD = 0.995
SAFETY_MARGIN = 0.002
STABILITY_FLOOR = 0.98

VIEWPORTS = {
    "desktop": (1440, 900),
    "tablet": (1024, 768),
    "mobile": (390, 844),
}

ORACLE_IDS = {"home.desktop", "home.tablet", "home.mobile"}

# checkpoint id -> (route_id, state) for anonymous URL captures.
ROUTE_OF = {
    "home": ("home", "loaded"),
    "elite": ("elite", "loaded"),
    "exercises": ("exercises", "loaded"),
    "exercise-detail": ("exercise-detail", "loaded"),
    "routines": ("routines", "loaded"),
    "routine-detail": ("routine-detail", "loaded"),
    "routines-beginner": ("routines-category", "loaded"),
    "exercises-page2": ("exercises", "page-2"),
    "build-routine": ("build-routine", "loaded"),
    "login": ("login", "loaded"),
    "signup": ("signup", "loaded"),
    "forgot-password": ("forgot-password", "loaded"),
    "support": ("support", "loaded"),
    "support-faq": ("support-faq", "loaded"),
    "not-found": ("not-found", "loaded"),
    "about-us": ("about-us", "loaded"),
    "ai-workout-tracker": ("ai-workout-tracker", "loaded"),
    "adaptive-plan": ("adaptive-plan", "loaded"),
    "use-case": ("use-case", "loaded"),
    "watch": ("watch", "loaded"),
    "coach": ("coach", "loaded"),
    "our-story": ("our-story", "loaded"),
    "community": ("community", "loaded"),
    "blog": ("blog", "loaded"),
    "terms-of-use": ("terms-of-use", "loaded"),
    "privacy-policy": ("privacy-policy", "loaded"),
    "ip-notice-process": ("ip-notice-process", "loaded"),
    "press-media": ("press-media", "loaded"),
    # interaction states (capture_states.py)
    "exercises-filter-abs": ("exercises", "filtered"),
    "exercises-no-results": ("exercises", "no-results"),
    "nav-products-dropdown": ("home", "nav-products"),
    "nav-workouts-dropdown": ("home", "nav-workouts"),
    "nav-more-dropdown": ("home", "nav-more"),
    "mobile-menu-open": ("home", "mobile-menu"),
    "home-dark-mode": ("home", "dark-mode"),
    "login-validation-empty": ("login", "validation-error"),
    "forgot-password-validation-empty": ("forgot-password", "validation-error"),
    "build-routine-validation-empty": ("build-routine", "validation-error"),
    "signup-results": ("signup", "results"),
    "signup-account-create": ("signup", "account-create"),
}
# signup-step-NN handled by prefix.

# Member states captured in the authenticated session; raw artifacts retained
# ONLY under git-ignored source-auth-scratch/ (account PII). state id ->
# (route_id, state, scratch basename).
MEMBER_STATES = {
    "my-jefit.discover-empty.desktop": ("my-jefit", "discover-empty", "dashboard-discover-mycircle"),
    "my-jefit.create-post-dialog.desktop": ("my-jefit", "create-post-dialog", "create-post-dialog"),
    "my-jefit.sync-info-modal.desktop": ("my-jefit", "sync-info-modal", "sync-info"),
    "my-jefit.getapp-menu.desktop": ("my-jefit", "getapp-menu", "getapp-menu"),
    "my-jefit.account-menu.desktop": ("my-jefit", "account-menu", "account-menu"),
    "my-jefit.plan-upgrade-modal.desktop": ("my-jefit", "plan-upgrade-modal", "elite-plan-modal"),
    "my-jefit-qa.loaded.desktop": ("my-jefit-qa", "loaded", "qa-feed"),
    "my-jefit-popular.loaded.desktop": ("my-jefit-popular", "loaded", "popular-feed"),
    "my-jefit-settings.account.desktop": ("my-jefit-settings", "account", "settings-account-free"),
    "my-jefit-settings.profile.desktop": ("my-jefit-settings", "profile", "settings-profile"),
    "my-jefit-settings.privacy.desktop": ("my-jefit-settings", "privacy", "settings-privacy"),
    "my-jefit-settings.data-controls.desktop": ("my-jefit-settings", "data-controls", "settings-datacontrols"),
    "my-jefit-settings.integrations.desktop": ("my-jefit-settings", "integrations", "settings-integrations"),
    "my-jefit-progress.empty.desktop": ("my-jefit-progress", "empty", "progress-empty"),
    "my-jefit-progress.log-modal.desktop": ("my-jefit-progress", "log-modal", "workout-log-active"),
    "my-jefit-progress.populated.desktop": ("my-jefit-progress", "populated", "workout-log-done"),
    "my-jefit-progress-photos.empty.desktop": ("my-jefit-progress-photos", "empty", "progress-photos-empty"),
    "my-jefit-progress-insights.empty.desktop": ("my-jefit-progress-insights", "empty", "progress-insights-empty"),
    "my-jefit-body-stats.empty.desktop": ("my-jefit-body-stats", "empty", "progress-bodystats-empty"),
    "my-jefit-workouts.initial.desktop": ("my-jefit-workouts", "initial", "workouts-empty"),
    "my-jefit-workouts.populated.desktop": ("my-jefit-workouts", "populated", "workouts-routine-saved"),
    "my-jefit-workouts.plan-menu.desktop": ("my-jefit-workouts", "plan-menu", "workouts-plan-menu"),
    "my-jefit-workouts-edit.editor.desktop": ("my-jefit-workouts-edit", "editor", "workouts-routine-editor"),
    "my-jefit-exercises.custom-empty.desktop": ("my-jefit-exercises", "custom-empty", "member-exercises-custom-empty"),
    "my-jefit-exercises.database.desktop": ("my-jefit-exercises", "database", "member-exercises"),
    "my-jefit-exercises.detail.desktop": ("my-jefit-exercises", "detail", "member-exercise-detail"),
    "elite-checkout.yearly.desktop": ("elite-checkout", "yearly", "elite-checkout-yearly-usd"),
}

UNAVAILABLE_ROWS = [
    {
        "id": "elite-checkout.success.desktop", "route_id": "elite-checkout",
        "state": "success", "role": "member", "viewport": "desktop",
        "priority": "p0", "evidence_kind": "unavailable",
        "acceptance_eligible": False,
        "note": ("Post-payment confirmation was never reached on source: the "
                 "authorization boundary forbids real payment and the user "
                 "holds no Elite account. The clone's success state is "
                 "clone-local sandbox behavior built on the frozen settings "
                 "Account-tab structure, disclosed as inference."),
    },
    {
        "id": "my-jefit-settings.elite-active.desktop",
        "route_id": "my-jefit-settings", "state": "elite-active",
        "role": "member", "viewport": "desktop", "priority": "p0",
        "evidence_kind": "unavailable", "acceptance_eligible": False,
        "note": ("Elite-active Account Type rendering unavailable for the "
                 "same reason; clone-local behavior, disclosed."),
    },
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
    if cp.startswith("signup-step-"):
        return ("signup", cp.replace("signup-", "questionnaire-"))
    raise SystemExit(f"capture {cp} has no route mapping")


def build() -> int:
    captures = load_captures()
    rows: list[dict] = []
    calibration_rows: list[dict] = []
    report_rows: list[dict] = []
    claims: list[dict] = []
    direct_items: list[str] = []
    oracle_floors: dict[str, float] = {}

    for cap in captures:
        cp, vp = cap["checkpoint"], cap["viewport"]
        cid = f"{cp}.{vp}"
        width, height = VIEWPORTS[vp]
        dest = CAP_ROOT / cp / vp
        frames = [normalize(Image.open(dest / f"frame-{n}.png"), width, height)
                  for n in (1, 2, 3)]
        site_rel = f"source-current/{CAPTURE_ID}/{cp}/{vp}"
        repo_rel = f"materials/{SITE_ID}/{site_rel}"
        frames[0].save(dest / "frame-1.viewport.png", format="PNG")

        regions = {"full": {"x": 0, "y": 0, "width": width, "height": height}}
        for name, enum_name in (("header", "header"), ("main", "main"),
                                ("footer", "footer"), ("form", "action")):
            clipped = clip_region((cap.get("regions") or {}).get(name),
                                  width, height)
            if clipped and enum_name not in regions:
                regions[enum_name] = clipped

        region_contracts = []
        for rname, reg in regions.items():
            box = (reg["x"], reg["y"], reg["x"] + reg["width"],
                   reg["y"] + reg["height"])
            sims = [round(similarity(frames[i], frames[j], box), 6)
                    for i, j in ((0, 1), (0, 2), (1, 2))]
            floor = min(sims)
            threshold = round(min(BASE_THRESHOLD, floor - SAFETY_MARGIN), 4)
            report_rows.append({
                "id": f"{cid}.{rname}", "checkpoint_id": cid,
                "region": rname, "region_box": reg,
                "pairwise_similarity": sims, "flicker_floor": floor,
                "derived_threshold": threshold,
            })
            if rname != "full":
                calibration_rows.append({
                    "id": f"{cid}.{rname}", "region": rname,
                    "source_samples": [{"path": f"{repo_rel}/frame-{n}.png"}
                                       for n in (1, 2, 3)],
                    "ignore_regions": [],
                })
            region_contracts.append({"region": rname, "box": reg,
                                     "threshold": threshold,
                                     "flicker_floor": floor})

        route_id, state = route_state(cp)
        full = next(r for r in region_contracts if r["region"] == "full")
        row = {
            "id": cid, "route_id": route_id, "state": state,
            "role": "visitor", "viewport": vp,
            "priority": cap.get("priority", "P1").lower(),
            "evidence_kind": "direct", "capture_id": CAPTURE_ID,
            "requested_url": cap.get("requested_url"),
            "final_url": cap["final_url"], "title": cap["title"],
        }
        if cid in ORACLE_IDS:
            oracle_floors[cid] = full["flicker_floor"]
            eligible = full["flicker_floor"] >= STABILITY_FLOOR
            row["acceptance_eligible"] = eligible
            if not eligible:
                row["acceptance_exclusion_reason"] = (
                    f"full-region source flicker floor {full['flicker_floor']}"
                    f" is below the {STABILITY_FLOOR} stability minimum "
                    "(continuous source-side animation); frames retained as "
                    "reference evidence, no pixel acceptance claimed")
            row["pixel_oracle_candidate"] = True
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
        rows.append(row)
        direct_items.append(cid)
        claims.append({
            "id": f"claim.capture.{cp}.{vp}", "kind": "directly-observed",
            "statement": (
                f"Checkpoint {cp} ({state}) at {vp} {width}x{height} was "
                f"captured from {cap['final_url']} with 3 full-page frames, "
                f"DOM html, link census, and region geometry; title "
                f"{cap['title']!r}, body length {cap.get('body_text_len')}."),
            "evidence_refs": [
                f"{site_rel}/frame-1.png", f"{site_rel}/frame-2.png",
                f"{site_rel}/frame-3.png", f"{site_rel}/meta.json",
                f"{site_rel}/page.html", f"{site_rel}/links.json",
            ],
        })

    # Member states: direct evidence, artifacts retained out-of-repo (PII).
    for cid, (route_id, state, basename) in sorted(MEMBER_STATES.items()):
        rows.append({
            "id": cid, "route_id": route_id, "state": state, "role": "member",
            "viewport": "desktop",
            "priority": "p0" if route_id in (
                "my-jefit", "my-jefit-settings", "my-jefit-workouts",
                "my-jefit-workouts-edit", "my-jefit-progress",
                "elite-checkout") else "p1",
            "evidence_kind": "direct", "capture_id": AUTH_CAPTURE_ID,
            "acceptance_eligible": False,
            "artifact_retention": "source-auth-scratch",
            "note": ("Captured inside the user-provided authenticated "
                     "session; raw screenshot+DOM carry account PII and are "
                     "retained only in the git-ignored source-auth-scratch/ "
                     f"directory ({AUTH_CAPTURE_ID}/{basename}.*) per the "
                     "entry prompt's data-retention rule. Never a committed "
                     "raster or pixel contract."),
        })
        claims.append({
            "id": f"claim.capture-auth.{cid}", "kind": "directly-observed",
            "statement": (
                f"Member state {cid} was captured on 2026-08-18 in the "
                "user-provided authenticated session (full-page screenshot + "
                "DOM). Artifacts are policy-retained outside git in "
                f"source-auth-scratch/{AUTH_CAPTURE_ID}/{basename}.* because "
                "they contain the throwaway account's PII; committed clone "
                "fixtures use synthetic data only."),
            "evidence_refs": [],
        })

    rows.extend(UNAVAILABLE_ROWS)
    for u in UNAVAILABLE_ROWS:
        claims.append({
            "id": f"claim.unavailable.{u['id']}", "kind": "unavailable",
            "statement": u["note"], "evidence_refs": [],
        })

    structural = [
        {
            "id": "claim.structural.entry-behavior",
            "kind": "directly-observed",
            "statement": (
                "Entry behavior at / was observed twice as a client redirect "
                "to /signup rendering a Log In panel (first visits, two "
                "browser channels, 13:28 UTC) and three times as a directly "
                "served marketing homepage (signed-in, fresh incognito, and "
                "?noredirect, ~14:00 UTC). The formal capture run's home "
                "checkpoint records which behavior froze; both observations "
                "are retained."),
            "evidence_refs": [
                f"source-current/{CAPTURE_ID}/home/desktop/meta.json"],
        },
        {
            "id": "claim.structural.login-contract",
            "kind": "directly-observed",
            "statement": (
                "/login renders H1 'Log In' with input[name=username] "
                "('Username or email'), input[name=password], 'Forgot "
                "Password?' -> /login/forgot-password, button 'Log In', "
                "'New to JEFIT? Sign up' -> /signup, and 'Or continue with' "
                "Google (GSI iframe), 'Sign in with Apple', 'Sign in with "
                "Facebook'. Authenticated visits client-redirect to "
                "/my-jefit; protected routes redirect to "
                "/login?redirect=<path>."),
            "evidence_refs": [
                f"source-current/{CAPTURE_ID}/login/desktop/page.html"],
        },
        {
            "id": "claim.structural.elite-pricing",
            "kind": "directly-observed",
            "statement": (
                "/elite offers Basic (Free, 'Included'), Elite $12.99/month "
                "('Buy plan'), Elite Annual $69.99 struck to $52.49 'for one "
                "year, then $69.99/year' ('Buy plan', '60% discount when "
                "paid annually' — copy reproduced verbatim despite the "
                "arithmetic inconsistency). The authenticated plan modal "
                "links Buy plan to /elite/checkout?isMyJefit=true&"
                "sub={monthly,yearly}."),
            "evidence_refs": [
                f"source-current/{CAPTURE_ID}/elite/desktop/page.html"],
        },
        {
            "id": "claim.structural.checkout-stripe-hosted",
            "kind": "directly-observed",
            "statement": (
                "/elite/checkout?isMyJefit=true&sub=yearly redirects to a "
                "Stripe-hosted checkout (checkout.stripe.com, merchant "
                "'Jefit, Inc.'): 'Subscribe to JEFIT Elite Subscription', "
                "coupon 25%OffFirstYear ('25% off for a year'), CAD/USD "
                "currency toggle with exchange-rate note, Apple Pay, email "
                "prefill, card/name/country/postal fields, Subscribe. The "
                "back/cancel link returns to /my-jefit/settings. No payment "
                "data was entered and Subscribe was never activated; raw "
                "captures are policy-retained in source-auth-scratch/."),
            "evidence_refs": [],
        },
        {
            "id": "claim.structural.membership-destination-view",
            "kind": "directly-observed",
            "statement": (
                "/my-jefit/settings Account tab (client-side tab buttons) is "
                "the membership destination view: Username/Change Username, "
                "Email with 'Unverified' + 'Resend Verification Link', "
                "Password/Change Password, 'Account Type: Free', and "
                "'Upgrade your account' cards Monthly ELITE $12.99/month and "
                "Yearly ELITE $69.99/year ('Everything in Elite with a 55% "
                "discount')."),
            "evidence_refs": [],
        },
        {
            "id": "claim.structural.workouts-builder",
            "kind": "directly-observed",
            "statement": (
                "'Create Plan' on /my-jefit/workouts creates a plan "
                "server-side immediately and opens the autosaving Routine "
                "Builder at /my-jefit/workouts/edit?id=<id> (name textbox, "
                "collapsed More settings with Focus/Level/Day tag/"
                "description, Add Day, per-exercise Set/Weight(lbs)/Reps/"
                "Rest columns defaulting to 3 sets of 10 lbs x 8 with 60s "
                "rest, exercise library rail). 'Save' is an anchor back to "
                "the plans list; an emptied routine name is silently ignored "
                "(no validation error). Signup auto-creates a 'New Routine' "
                "current plan which the list renders twice (source quirk)."),
            "evidence_refs": [],
        },
        {
            "id": "claim.structural.web-workout-logging",
            "kind": "directly-observed",
            "statement": (
                "Web workout logging lives on /my-jefit/progress/history: "
                "'+ Add session' opens the 'Workout Log' modal (Start/End "
                "time, exercise library); adding an exercise logs a default "
                "set and the persisted day panel shows a Training Summary "
                "(timers, Complete count, Volume lbs, record badges, per-set "
                "rows). There is no web 'Start Workout' player; the Sync "
                "Info modal states app sync is manual."),
            "evidence_refs": [],
        },
        {
            "id": "claim.structural.not-found",
            "kind": "directly-observed",
            "statement": (
                "Unknown paths (e.g. /zzzz-no-match-websitebench, "
                "/index.html) return an unbranded server-level HTTP 404 "
                "(title '404 Not Found', body 'Not Found / The requested "
                "URL was not found on this server.') with no site chrome; "
                "they do not fall through to the SPA."),
            "evidence_refs": [
                f"source-current/{CAPTURE_ID}/not-found/desktop/page.html"],
        },
        {
            "id": "claim.structural.exercises-filters-client-side",
            "kind": "directly-observed",
            "statement": (
                "/exercises filters (11 muscle groups, 12 equipment) are "
                "client-side state with no URL/query change; pagination uses "
                "?page=N (72 pages, 1295 exercises). An impossible combo "
                "renders '0 EXERCISES FOUND' with an empty grid. Exercise "
                "and routine detail pages expose no ratings sections and no "
                "download counts."),
            "evidence_refs": [
                f"source-current/{CAPTURE_ID}/exercises/desktop/page.html"],
        },
        {
            "id": "claim.structural.recorder-unavailable",
            "kind": "structural-only",
            "statement": (
                "The formal websitebench-browser-trajectory recorder could "
                "not attach to the human demonstration: the session Chrome "
                "exposes pipe-based CDP only. Structural trajectory evidence "
                "comes from agent-driven capture walks; this is a recorded "
                "coverage limitation, not a substitute claim."),
            "evidence_refs": [],
        },
    ]
    claims = structural + claims

    now = dt.datetime.now(dt.timezone.utc)
    doc = {
        "schema_version": "offline-clone.checkpoints.v1",
        "site_id": SITE_ID,
        "capture_id": CAPTURE_ID,
        "status": "frozen",
        "metric": METRIC,
        "calibration_spec": "scope/visual-calibration-spec.json",
        "viewports": {k: {"width": w, "height": h}
                      for k, (w, h) in VIEWPORTS.items()},
        "topology_note": (
            "Frozen evidence topology (petfinder/edx/tripit/aspca pattern): "
            "the pixel-locked visual_contract oracle is exactly "
            "home.{desktop,tablet,mobile} (threshold = min(0.995, "
            "flicker_floor - 0.002), full region, zero ignore regions); "
            "every other captured anonymous state is a frozen source raster "
            "via source_artifact_path witnessed by browser evidence. "
            "Authenticated member states are direct evidence whose raw "
            "artifacts are policy-retained outside git (account PII) in "
            "source-auth-scratch/; post-payment states are unavailable."),
        "freeze_decision": {
            "named_supervisor": "claude-fable-5-offline-clone-run",
            "decided_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rationale": (
                "Anonymous marketing, discovery, auth-entry, support and "
                f"error contracts freeze against the {CAPTURE_ID} "
                "three-frame local-Playwright capture before any candidate "
                "render exists; thresholds derive only from source-side "
                "flicker floors. Member-area contracts freeze against the "
                f"{AUTH_CAPTURE_ID} authenticated walk (retained "
                "out-of-repo per the data-retention rule). Post-payment "
                "states stay unavailable by authorization policy."),
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
        "rows": report_rows,
    }

    metadata = {
        "schema_version": f"{SITE_ID}.capture-metadata.v1",
        "status": "captured",
        "capture_id": CAPTURE_ID,
        "captured_at_utc": "2026-08-18",
        "source_origins": ["https://www.jefit.com/"],
        "engine": {
            "primary": "local-playwright",
            "browser": "Chromium 149 headless via Python Playwright",
            "notes": (
                "jefit.com serves local Playwright directly (no WAF); one "
                "browser context spans the whole matrix so consent and "
                "experiment state stay constant. Interaction states ran "
                "with non-GET requests aborted at the network layer. "
                "Authenticated member states were captured separately in "
                "the user-provided local Chrome session (chrome-devtools "
                "MCP) and retained only under git-ignored "
                "source-auth-scratch/."),
        },
        "baseline": {"locale": "en-US", "timezone": "Etc/UTC",
                     "consent": "banner-accept-once-per-context"},
        "viewports": [{"name": k, "width": w, "height": h}
                      for k, (w, h) in VIEWPORTS.items()],
        "roles_captured": ["anonymous", "member (out-of-repo retention)"],
        "roles_unavailable": {
            "elite-member": ("post-payment states unavailable: real payment "
                             "prohibited and the user holds no Elite "
                             "account"),
        },
        "frames_per_checkpoint": 3,
        "captures": [
            {k: c.get(k) for k in ("checkpoint", "viewport", "requested_url",
                                   "final_url", "title", "frames",
                                   "frame_sha256", "frames_identical",
                                   "engine")}
            for c in captures
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
                "rationale": (
                    "Every anonymous state captured directly from the source "
                    f"in {CAPTURE_ID}; each carries a frozen three-frame "
                    "raster. The pixel oracle subset is "
                    "home.{desktop,tablet,mobile}."),
            },
            {
                "id": "member-direct-states",
                "label": "Authenticated member route states",
                "unit": "route-state",
                "category": "functional-fidelity",
                "required_evidence_kinds": ["browser"],
                "required_items": sorted(MEMBER_STATES),
                "satisfied_items": [],
                "rationale": (
                    "Authenticated member states observed in the "
                    f"{AUTH_CAPTURE_ID} session; raw evidence retained "
                    "out-of-repo (PII), clone behavior verified functionally "
                    "and by local diagnostic comparison."),
            },
            {
                "id": "source-unavailable-states",
                "label": "Recorded unavailable surfaces",
                "unit": "route-state",
                "category": "honest-gaps",
                "required_evidence_kinds": ["independent-audit"],
                "required_items": sorted(u["id"] for u in UNAVAILABLE_ROWS),
                "satisfied_items": [],
                "rationale": ("Post-payment surfaces unavailable by "
                              "authorization policy; disclosed, never "
                              "inferred as direct evidence."),
            },
            {
                "id": "p0-network-invariants",
                "label": "Runtime network closure",
                "unit": "invariant",
                "category": "network-closure",
                "required_evidence_kinds": ["network"],
                "required_items": ["no-runtime-remote-requests"],
                "satisfied_items": [],
                "rationale": ("The candidate must make zero runtime requests "
                              "to non-local origins on every checkpoint."),
            },
            {
                "id": "deterministic-database-state",
                "label": "Deterministic backend business state",
                "unit": "behavior",
                "category": "backend-semantics",
                "required_evidence_kinds": ["full-suite"],
                "required_items": ["seed-reset-deterministic",
                                   "membership-order-transactional",
                                   "cross-actor-isolation"],
                "satisfied_items": [],
                "rationale": ("Seeded SQLite resets deterministically; the "
                              "Elite order commits atomically with payment "
                              "consumption; actors cannot read each other's "
                              "data."),
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
    with (SITE / "scope" / "claims.jsonl").open("w") as fh:
        for claim in claims:
            fh.write(json.dumps(claim) + "\n")
    (CAP_ROOT / "capture-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n")

    floors = sorted((row["flicker_floor"], row["id"])
                    for row in report_rows if row["region"] == "full")
    print(f"checkpoints: {len(rows)}  anonymous-direct: {len(direct_items)}  "
          f"member-direct: {len(MEMBER_STATES)}  calibration rows: "
          f"{len(calibration_rows)}  claims: {len(claims)}")
    print("oracle full-region floors:",
          {k: round(v, 6) for k, v in sorted(oracle_floors.items())})
    print("lowest full-region flicker floors:")
    for floor, rid in floors[:8]:
        print(f"  {floor:.6f}  {rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
