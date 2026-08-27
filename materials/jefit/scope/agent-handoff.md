# Clone Agent build brief — jefit

You are the sole candidate writer. Write only under `materials/jefit/clone/`
plus `materials/jefit/tools/` build scripts and `materials/jefit/scope/verify.json`
(driver data). Never edit frozen scope evidence (checkpoints, claims,
calibration, coverage, task brief); report needed corrections instead.

## Evidence map (read, never modify)

- `scope/derived-task-brief.json` — roles, journeys, authority, human traces.
- `scope/checkpoints.json` (frozen) — 103 checkpoints; oracle =
  home.{desktop,tablet,mobile}, thresholds bound; every anonymous state has
  `source-current/2026-08-18.jefit-r1/<cp>/<vp>/` with `frame-*.png`,
  `page.html` (rendered DOM), `links.json`, `resources.json`, `meta.json`
  (+ `frame-1.viewport.png` crops).
- `scope/routes.json`, `journeys.json`, `invariants.json`, `purpose.json` —
  behavior contracts and verbatim copy notes.
- `source-assets/manifest.json` — 643 assets already mirrored byte-exact at
  `clone/static/assets/2026-08-18.jefit-r1/<host>/<path>`; `runtime_path` per
  asset. `unresolved-references.json` lists 43 source-404 references (legacy
  /community icons; reproduce the references, the 404s are a source property).
- `source-auth-scratch/2026-08-18.jefit-auth-r1/` (git-ignored, PII-bearing:
  consult locally, NEVER copy content into the candidate) — 29 member states
  + Stripe checkout CAD/USD DOM + `ea1/` depth evidence. Recreate member UIs
  from these structurally with synthetic fixture data only.
- `materials/jefit/artifacts/exploration/ea2/` — anonymous breadth findings.
- `scope/implement-notes.md` — decisions + source quirks register.

## Architecture (follow the repo's proven shape; see materials/aspca-pet-insurance/clone as a structural reference — never copy its UI, fields, fixtures, thresholds, or site conclusions)

- FastAPI app at `clone/app.py` (uvicorn `app:app`, cwd=clone), Python 3.12;
  deps stay within: fastapi, uvicorn, jinja2, python-multipart, argon2-cffi
  (pins in deploy/generic-offline-clone/deployment.jefit.v2.json).
- Backend ONLY through the vendored seam:
  `from websitebench.site_backend import SiteBackend`;
  `SiteBackend.open("backend/runtime.json")` (contract already at
  `materials/jefit/backend/runtime.json`; site_id jefit, local-sandbox
  scenarios sandbox-approved/declined/retry, mail purposes registration +
  password-reset). `clone/backend/site_backend_integration.py` is the
  generated integration point. Business schema (SQLite) is site-implemented
  through that seam: users, sessions, routines (days, day_exercises with
  set/weight/reps/rest and order), workout_sessions (+ logged sets),
  body_stats, goals, preferences (units, privacy, email prefs), membership
  orders + subscription state, custom-exercise count, community fixture posts.
- Frontend: server-rendered Jinja pages reproducing the captured DOM
  (source pages are a client-rendered SPA; the clone re-serves the RENDERED
  presentation server-side — pixels/copy/layout must match the frozen
  frames). Localize every asset URL to `/static/assets/...` per the manifest
  `runtime_path`; zero runtime remote requests (invariant network-closure).
  Client JS only where interaction demands it (tabs, modals, filters,
  builder edits, log modal) — clone-local, no external libs beyond vendored.
- Health endpoints: `/healthz` returning `{"ok": true, "site_id": "jefit"}`
  shape per deploy README, and `/__websitebench/health` returning exactly
  `{"status":"ok"}` (Harbor ABI). Runtime env: HOST, PORT, DATA_DIR, SEED,
  TZ; foreground; SIGTERM clean exit.

## Non-negotiable behavior semantics (from frozen evidence)

1. Entry: `/` serves the marketing homepage (frozen capture). Cookie banner
   renders until Accepted (persist consent client-side as source does).
2. Auth: /login panel (username-or-email + password, Forgot Password?, Sign
   up link, Google/Apple/Facebook IdP buttons rendered as visual parity —
   clicking them shows an honest clone-local notice, never a fake provider
   flow); protected /my-jefit* redirects anonymous to /login?redirect=<path>;
   authenticated /login redirects to /my-jefit. Sessions via seam (__Host-
   cookie). /login/forgot-password: email field, "Send reset link" (seam
   password-reset purpose, local outbox), "Log in" return link.
3. Signup: /signup runs the 16-step questionnaire (steps frozen in
   source-current signup-step-01..16: gender, main goal, current build, goal
   body type, target zones multi-select, fitness level, height FT/LBS-CM/KG,
   current weight, goal weight, age, workout place, equipment familiarity,
   times per week, workout length, mode Tracker/…, limitations) →
   /signup/results (analysis animation → plan projection + Continue) →
   /signup/register (email entry) → account creation (email+password+username
   per the observed register flow; verification state starts Unverified with
   Resend link in settings). Signup auto-creates the "New Routine" current
   plan (and the plans list renders it twice — reproduce the quirk).
4. Discovery: /exercises (client-side muscle/equipment filters, no query
   param; ?page=N pagination; '0 EXERCISES FOUND' empty grid; search box),
   /exercises/<id>/<slug> (no ratings section), /routines (+8 category
   pages, Sort by Most Downloaded/Most Viewed/Latest), /routines/<id>/<slug>
   (tag pills, Share/Download, Plan Details VIEW ALL, day cards with
   Sets x Reps, Featured plans carousel; no ratings/download counts).
   Catalog fixture: representative synthetic-reduced subset preserving
   filter-facet coverage, list density, and ≥1 pagination boundary; keep the
   REAL exercise names/instructions from captured pages only for pages whose
   DOM was captured; the rest of the catalog is synthetic but plausible.
   Preserve the "1295 EXERCISES FOUND" count only if the fixture backs it —
   otherwise render the fixture's true count (never a false count).
   NOTE: data reduction may reduce entity counts only — never fields,
   density, pagination, or states.
5. Builder: anonymous /build-routine (draft created server-side on load with
   ?code=…; Save → the draft's public /routines/<id>/new-routine page);
   member Create Plan → instant server-side plan → autosaving editor at
   /my-jefit/workouts/edit?id=<id> (defaults 3 sets 10 lbs x 8, 60s rest;
   empty name silently ignored).
6. Logging: /my-jefit/progress/history calendar + day panel; "+ Add session"
   → Workout Log modal; adding an exercise logs a default set (25 lbs x 8);
   Training Summary with timers/Complete/Volume/records. Honor EA1's
   findings on edit-persistence semantics.
7. Membership (P0, task 539): dashboard "Upgrade to Elite" card + settings
   upgrade cards → plan modal (Basic Included / Elite $12.99 / Elite Annual
   $69.99→$52.49) → /elite/checkout?isMyJefit=true&sub={monthly,yearly} →
   clone-local checkout page reproducing the captured Stripe-hosted layout
   (USD baseline; "Subscribe to JEFIT Elite Subscription", coupon
   25%OffFirstYear −25%, total $52.49 yearly / $12.99 monthly) EXCEPT the
   payment input: per the payment mandate the form accepts ONLY a sandbox
   scenario selector (Simulated approval / decline / retry) — never card
   fields that accept input. Label the scenario control honestly as the
   sandbox payment method. Subscribe consumes the scenario via the seam and
   writes order + membership in ONE transaction; declined → error + retry
   path; back/cancel link → /my-jefit/settings. Post-payment: settings
   Account tab shows the Elite membership (structure from the frozen
   Account tab; the Elite-active rendering is disclosed clone-local
   behavior — keep it structurally consistent: Account Type row value +
   plan/renewal line replacing the upgrade cards).
8. Settings: tab buttons (URL unchanged); Account (username/email+
   verification/password rows, Account Type, upgrade cards); Profile
   (birthday, gender, units Imperial/Metric, level, top goal); Privacy
   (visibility selects + Email Preferences switches); Data Controls (export
   csv works from clone data; Delete Data/Delete Account real local
   behavior); Integrations (Strava card, Manage → honest clone-local
   notice).
9. Community: Discover My Circle (empty state for fresh account)/Q&A/
   Popular with seeded synthetic fixture posts; Create Post dialog posts
   clone-locally; Sync Info modal; Get App menu; account menu (Settings/
   Sign out/Light mode toggle — implement light mode as captured).
10. Errors: unknown path → unbranded server-style 404 (title '404 Not
    Found', body 'Not Found / The requested URL was not found on this
    server.'); /community legacy template page (single landing page from
    its captured DOM, horizontal overflow preserved).

## Deterministic seed (scope/derived-task-brief.json deterministic_seed_plan)

Seeded via seam hooks, reset-deterministic: two member accounts (primary +
isolation actor) with synthetic identities (never the real capture account),
populated routines/logs/body stats for the primary, empty second account,
sandbox order fixtures. SEED env selects the deterministic state.

## Tests to write under clone/tests/ (site gate: python -m pytest materials/jefit/clone/tests -q)

test_smoke, test_app_surface (routes, titles, 404 fidelity), test_no_remote_refs
(+ negative test test_detector_flags_injected_remote_ref), test_auth (redirects,
session cookie flags, recovery outbox, no plaintext secrets), test_routines_api
(create/autosave/defaults/empty-name quirk/reorder), test_workout_log_api,
test_membership_payment (approved/declined/retry/idempotent duplicate/opaque
scenario IDs only — card-like fields rejected), test_backend_lifecycle
(deterministic reset incl. negative test_reset_detects_divergent_state,
cross-actor isolation, restart persistence), test_payment_mail (outbox only).
Invariant test refs in scope/invariants.json name these files — keep names.

## Ledger + samples (build.md step 2/6)

While walking the matrix record `materials/jefit/tools/interaction-ledger.json`
(clone URL, selector per activated control, one visible-text + one raw-markup
proof, form action per mutation) and author
`materials/jefit/tools/frontend_samples.json`
(schema_version "jefit.frontend-gate-samples.v1", app_file "clone/app.py",
app_attr "app", module_name "jefit_clone_app", checks[]): one check per key
route incl. healthz and an external-boundary check; url:"/" cannot be a
contract step — include an explicit index route alias; expect_contains short
visible-text strings (≤2 assertions/step); include a session_setup and
session:true checks for member routes plus POST checks (url must GET-render
exactly one <form method=post action=url>) so derive-from-clone can emit
click/submit steps for the P0 journey.

## Update scope/verify.json (driver data, not code)

boot argv (uvicorn app:app, cwd clone), routes map for every checkpoint
route_id → clone path, states recipes for non-default states (e.g.
"exercises.no-results": click steps; "my-jefit-settings.account": login
prepare), status {"not-found": 404}, prepare (cookie-banner accept, login as
seeded member for member checkpoints), deferred for the 2 unavailable
post-payment source states (clone implements them; defer only what anonymous
diagnostics cannot reach if login recipes are unsupported — check
`websitebench-offline-clone verify --help` for the recipe grammar first).

## Gates to run (bounded repair loops; 2 no-progress rounds per finding → known difference)

1. `websitebench-offline-clone validate --site materials/jefit` (check --help)
2. `python -m pytest materials/jefit/clone/tests -q`
3. `websitebench-offline-clone verify --site materials/jefit --section static`
   then full (static+live)
4. Shared diagnostics from real inputs:
   `python tools/offline_clone/run.py tools list` then compare-functional /
   compare-visual / test-backend as applicable
5. `ruff check src tests websitebench` must stay green (don't touch those
   trees); your code style: ruff-clean too.

Never: relax thresholds, expand masks, delete tests, fake success, record
inferred as direct. Report every remaining finding honestly.
