# JEFIT offline-clone production run — final report

Run: 2026-08-18 → 2026-08-19. Contract:
`prompts/offline-clone/autonomous-source-to-clone.md` (+ `references/01`–`08`),
capture/repair skill `$trace-guided-offline-clone`. Source:
`https://www.jefit.com` (input `https://jefit.com/`). Site id `jefit`.
Final candidate `3721fb002e0ef87bd71e5cec5c6594c8f41266509d05977a124c51bf413a62eb`.

**No single completion percentage is given** — dimensions are reported
separately, per the entry prompt. Every machine status here is
`diagnostic-only`, qualification `maintainer-judgment-required`. Nothing in this
report conveys copyright, redistribution, or publication authorization.

## 1. Functional coverage by class

| Class | Journeys | Status |
| --- | --- | --- |
| P0 (7) | register → Elite annual → sandbox payment → membership (task 539); sign-in → dashboard; browse exercises + filters + no-results; browse routines + detail; create routine + edit sets; log workout session; Elite plan review | implemented, tested, and completed end-to-end by real clicks in a browser |
| P1 (6) | password-recovery view; goals/units/notification preferences; support + FAQ; no-results / 404 / permission recovery; entry navigation; registration entry | implemented, tested |
| P2 (1) | community Q&A / Popular with clone-local posting | implemented on seeded synthetic fixtures |
| unavailable (2) | `elite-checkout.success`, `my-jefit-settings.elite-active` | source post-payment state never reached (real payment prohibited; user holds no Elite account). Clone implements sandbox behaviour on the frozen Account-tab structure; recorded `unavailable`, never as direct evidence |
| omitted (declared) | ~818 blog posts, `/blog/category|author/*`, legacy `/q&a/*`, `/post/*`, `/user/*`, 4 sitemap-only marketing singletons, native/watch apps, live third-party services | in `scope/purpose.json` out_of_scope + the EA2 scope-delta record; these resolve to the faithful unbranded 404 |

Observation table (`tools/observation-table.json`): **195 rows — 165 matched,
14 inferred-architecture, 14 known-difference, 2 unavailable.**

## 2. Visual coverage and residuals

Frozen checkpoints: **103** (74 anonymous-direct incl. 32 interaction states, 27
member-direct, 2 unavailable). Viewports 1440×900 / 1024×768 / 390×844, three
frames per anonymous checkpoint. Pixel oracle is exactly
`home.{desktop,tablet,mobile}`, metric `pixel-mae-similarity-v1`, threshold
min(0.995, flicker_floor − 0.002), zero ignore regions.

Final measured similarity against the frozen source rasters:

| Checkpoint | Similarity | Threshold | Verdict |
| --- | --- | --- | --- |
| home.desktop | 0.99975 | 0.995 | pass |
| home.tablet | 0.99998 | 0.995 | pass |
| home.mobile | 0.99959 | 0.995 | pass |
| login.desktop | 0.99949 | reference | matches source |
| exercise-detail.desktop | 0.99954 | reference | matches source |
| exercises.desktop | 0.99935 | reference | catalogue count differs (declared) |
| routines / routine-detail / support-faq / signup / elite (desktop) | 0.99975–0.99976 | reference | match source |
| build-routine.desktop | 0.94360 vs frame-1; **0.99966 vs frame-3** | 0.9418 | pass — the source's own frame1↔frame3 delta is 0.943808 (an animated promo GIF advances mid-capture); source-side nondeterminism, candidate deliberately not stabilised against it |

**Measured residual (new, disclosed).** Region analysis shows the difference is
concentrated in the last 20 rows of the viewport: above y=880 the clone matches
the source at **0.99999**, while the bottom 20 rows measure ~0.989 across most
desktop checkpoints. Cause is a few-pixel difference in where the following
page section begins. It is below every frozen threshold and invisible above the
fold, so per the stopping rules it is recorded rather than chased. An
independent reviewer did perceive this band on 5 of 5 pairs where it appeared
but declined to rely on it, judging it below their own resolution.

Region calibration: 85 rows in `scope/visual-calibration-report.json`
(CLI-generated), `source-limited` on 2 header rows (build-routine 0.9718, coach
0.9827) — recorded source instability, not candidate defects.

## 3. State coverage

Loading / empty / populated / validation / permission / success / error states
are frozen and driven by `scope/verify.json`: **39 route aliases, 65 state
recipes**, one prepare step (consent), `status {"not-found": 404}`, **0
deferred**. All checkpoint-backed recipes walk green against the booted clone.

Source-faithful behaviours deliberately reproduced rather than "fixed":
unbranded server-style 404 with no site chrome; login empty-submit showing no
inline validation; an emptied routine name silently ignored; the
signup-created "New Routine" plan rendering twice in the plans list;
`/exercises` filters as client-side state with no query parameter; and the
absence of ratings sections on exercise and routine detail pages.

## 4. Trajectory inventory

| trace_id | side | env | Established | Explicitly did NOT establish | Disposition |
| --- | --- | --- | --- | --- | --- |
| tr-auth-login-r1 | source | human-local | free account exists; member route set | pixels; signup step order | login performed personally by the user; no credentials seen or stored |
| tr-elite-checkout-r1 | source | capture | plan modal; `/elite/checkout?sub={monthly,yearly}`; Stripe-hosted checkout layout; cancel → `/my-jefit/settings`; Account-tab destination view | post-payment state; entitlement/webhook semantics | payment never submitted |
| tr-member-walk-r1 | source | capture | 29 member states: settings tabs, progress family, workouts + editor, logging modal, community, chrome | pixels at frozen viewports; post-payment | artifacts retained out-of-repo (PII) |
| EA2 (breadth, anonymous) | source | capture | full public route inventory, sort query params, entry-behaviour resolution, dark-mode persistence, sitemap deltas | authenticated behaviour | folded into routes + notes |
| EA1 (depth, authenticated) | — | — | nothing | all 7 mission items | **blocked**: the login-holding Chrome exposed pipe-only CDP under an orphaned MCP server, and process termination was denied by the permission classifier (not worked around). Unreached surfaces dispositioned as 14 `inferred-architecture` items and disclosed |

The formal `websitebench-browser-trajectory` recorder could never attach
(pipe-based CDP, no TCP debug port), so there is **no `actions.jsonl` ledger**
for the human demonstration and consequently **no two-sided source/candidate
trajectory diff**. Recorded as a coverage limitation; structural evidence came
from agent-driven capture walks instead.

## 5. Asset closure and runtime network

`source-assets/manifest.json`: **691 assets, 680 required**, mirrored
byte-exact into `clone/static/assets/2026-08-18.jefit-r1/…`.

Repairs during verification: 30 source-404 HTML shells removed from the
manifest (recorded in `unresolved-references.json`); 233 query-URL mirrors
re-extensioned with all candidate references rewritten; 7 pristine copies whose
own bytes carry external references demoted to evidence-only and replaced in
the candidate by localized vendor copies (`clone/static/site/vendor/`, built by
`tools/promote_localized_assets.py`); 4 SVG icon-font fallbacks demoted (no
intrinsic dimensions exist to declare); **78 exercise-rail originals topped up**
(53 referenced by the candidate — this closed a real blind-review defect).

`verify --section static`: **clean, 0 findings, complete** —
`remote_references 0`, `secrets 0`. Browser walks of the final candidate show
**zero local 404s** on every measured page and **zero offsite requests**.

## 6. Backend runtime and payment profile

Runtime contract is scaffold-generated, not hand-written:
`materials/jefit/backend/runtime.json`
(`websitebench.site-backend-runtime.v1`). `site_id` **jefit**; SQLite
`data/jefit.sqlite3`, site-exclusive and site-bound; `__Host-`-style host-only,
Secure, HttpOnly, SameSite=Lax session cookie; Redis namespace `site/jefit`;
mail sender display name **JEFIT** with purposes `registration` and
`password-reset` (local outbox, no real delivery).

Payments: **`local-sandbox` only** (sandbox-approved / declined / retry), USD,
`stripe_test: null`, live payments forbidden. Client input is an opaque scenario
id — no card, CVC, expiry, or bank field is ever accepted or stored (asserted by
`test_card_like_fields_rejected_and_never_stored` and
`test_card_like_value_rejected_even_in_neutral_field`). Order and membership
commit in one SQLite transaction.

`websitebench-workflow check-payment-scope` → **passed**, mode
`manifest-native-audit`, `scope_subject_sha256`
`fcd902320b394aba1c0216ca6ce123dfc52b1cd4c38a48fcda9ac564c2515701`, six inputs
bound by sha256.

Deployment profiles: `cloudflare-review` (ephemeral-reset — **must never be
described as durable**), `docker-volume`, `offline-harbor`.

## 7. Harbor

Same-id pair `harbor/sites/jefit/` + `harbor/instances/jefit/` (exactly one
instance), created by the current `init-site` / `init-instance`. Interaction
contract derived from clone artifacts: profiles **checkout** (selected by the
instance) and **login**, three steps each, visible-text assertions only.
Adapters: 4 generated files, `opencli-adapters --check` **in-sync**
(`--install` not run).

Replay (advisory, re-run against the final candidate): both profiles
**passed, 3/3 steps, assertion_failures 0**, evidence at
`interactions/replay-evidence/{login,checkout}.json`. The OpenCLI binary is
absent on this host, so replay runs through a transparent local harness that
executes the committed adapters verbatim and identifies itself as
`wb-local-adapter-harness`, never as OpenCLI; `--promote` does not exist in this
checkout's CLI, so the committed artifacts are the record. Replay is wired into
no score and no merge condition.

`validate --instance harbor/instances/jefit --corpus-root harbor` → **exit 0,
`status: draft`, `scorable: false`**, missing counts exact (T1 20, T2 165 [L1 35
/ L2 50 / L3 80], T3 15; total 200). No capture, materialize, calibration, or
scoring was run on the draft — correct for a new site.

Two contract pendings remain with a recorded reason: `unmapped-journey` on both
profiles. `derive.py` matches only `journeys.json` entries of kind
failure/retry/recovery by family, while the frozen journeys express
declined/retry as `failure_variant`/`recovery_variant` *strings* on the P0
success journey — a shape the matcher cannot read, and `journeys.json` is frozen
scope. The behaviours themselves are implemented, pytest-covered, and
recipe-walked.

## 8. Runtime identity and commands

Python 3.12.13; fastapi 0.141.1, uvicorn 0.52.3, jinja2 3.1.6, argon2-cffi
25.1.0 — all matching the descriptor pins. Boot:
`python -m uvicorn app:app --host <h> --port <p> --log-level warning` from
`materials/jefit/clone`; ACCEPTANCE.md's `python app.py` also starts it
directly (a `__main__` guard was added when that literal command was found to
start nothing — the reference ASPCA site has the same gap). Env honoured: HOST,
PORT, DATA_DIR, SEED, TZ;
foreground; **SIGTERM clean exit verified directly**. `/healthz` →
`{"ok":true,"site_id":"jefit"}`; `/__websitebench/health` → exactly
`{"status":"ok"}`; unknown paths → HTTP 404 with the unbranded
`404 Not Found` shell (all verified directly by the orchestrator).

| Command | Exit | Result |
| --- | --- | --- |
| `websitebench-offline-clone status --site materials/jefit` | 0 | site_id jefit, stateful |
| `websitebench-offline-clone verify --site materials/jefit --section static` | 0 | **clean**, 0 findings, complete |
| `websitebench-offline-clone verify --site materials/jefit` (full, in Linux container) | 0 | **clean — both sections complete, 0 findings.** live: 103 checkpoints, 103 page loads, 2/2 sessions opened, 29/29 session checkpoints visited, 3 visual contracts satisfied, 0 blocked external references |
| same command on the macOS host | 2 | live section refuses by design: "candidate sandbox requires Linux" (Landlock/seccomp fail-closed guard, not weakened) |
| `python -m pytest materials/jefit/clone/tests -q` | 0 | **91 passed** across 11 modules |
| `ruff check src tests websitebench` | 0 | clean |
| `ruff check materials/jefit/tools materials/jefit/clone` | 0 | clean |
| `python -m pytest tests/test_prompt_freshness.py -q` | 0 | 15 passed |
| `python -m pytest tests/offline_clone tests/harbor tests/project -q` | 1 | 383 passed, 9 failed — all pre-existing macOS platform families (`preexec_fn` sandbox, `/tmp`→`/private/tmp` canonicalisation, one timing assert), in temp dirs unrelated to jefit; `src/`, `tests/`, `websitebench/` untouched |
| `websitebench-workflow check-payment-scope --proposal …` | 0 | passed |
| `websitebench-harbor validate --instance harbor/instances/jefit --corpus-root harbor` | 0 | draft, non-scorable |
| `websitebench-harbor run-opencli` (login, checkout) | 0 | both passed, 0 assertion failures |
| `cd deploy/generic-offline-clone && npm ci && npm test` | 0 | pass 0 fail, 2 skipped |
| `node scripts/prepare.mjs --config deployment.jefit.v2.json --check-only` | 0 | candidate `3721fb002e0ef87b…`, deployment `b36a03e98885445c…`, **0 warnings** |
| `node scripts/deploy.mjs --config deployment.jefit.v2.json --dry-run` | 0 | domain `jefit.website-bench.com`, cloudflare-review, ephemeral-reset, **0 warnings** |

### Live diagnostic section (now run)

The live section is Linux-gated by `runtime_isolation.require_isolation()`
(Landlock + seccomp fail-closed). Rather than weaken that guard it was executed
in a Linux container matching the repo's pinned playwright 1.61.0
(`mcr.microsoft.com/playwright/python:v1.61.0-noble`). Results: **overall
`clean`, exit 0, both sections complete, zero findings.**

Two things learned that apply to any site, not just this one:

- The sandbox preflight passes in **plain Docker with no added privileges**
  (Landlock ABI 6, seccomp user notification, enforcement probe passed).
- A **macOS bind mount cannot host the candidate**: under Landlock the sandboxed
  process is denied directory listing through virtiofs, so Python finds no `app`
  module and uvicorn reports the misleading "Could not import module app". The
  tree must be copied onto the container's native filesystem first.

The live section also caught a defect that no macOS run could have surfaced —
see §9 item 5.

Shared diagnostics from their real inputs (advisory): `compare-visual` on the
three oracles passed; `tools explore` walked the P0 journey 15/15 steps with 0
blocked, 0 failed, 0 offsite requests. `tools test-backend` was **not run** — it
consumes a human-gated semantic-selection spec, and authoring one to make a gate
report "passed" would fabricate human approval.

## 9. Usability verification and the defects it caught

The site tests exercise the backend by POSTing directly, so they cannot see a
control that renders but cannot be operated. Real-click browser walks were
therefore run independently, and they caught **four P0/P1 defects every
automated gate had passed**:

1. **Signup questionnaire could not advance.** `build_signup_steps.py` derived
   the panel-swap region by naive character diff, so the markers split
   `<!--$-->` and landed inside a class attribute; the closing marker never
   became a comment node, `slotBounds()` returned null and `renderStep()`
   silently no-oped. Fixed with element-aware boundary snapping plus offset-free
   splicing that raises instead of silently returning.
2. **Register Continue button permanently unclickable** — it shipped the
   captured disabled state (`pointer-events-none`) with nothing to enable it.
   Now enabled on field validity; the enabled fill reuses the primary-button
   colour measured on the observed `/login` submit (a **disclosed inference**,
   since the source's enabled state for that button was never captured).
3. **Gated questionnaire Continue buttons, the step-17 hand-off, and the
   dashboard "Upgrade to Elite" button** were similarly inert; all fixed.
4. **Settings page rendered all five tab panels stacked** — document 4500px
   (5× viewport) with Profile and Data Controls content present while Account
   was active. Two compounding causes: unbalanced byte slices whose ancestor
   closers ejected each panel from its wrapper (so `display:none` hid nothing),
   and `_second_nav_bounds()` selecting the mobile header's `lg:hidden` nav.
   Fixed by returning the balanced panel plus its ancestor closers separately,
   selecting the nav by its own tab labels, and adding the missing initial
   activation. Document is now 900px with exactly one panel and one tab bar.

5. **Writable state resolved into the read-only candidate root.** `app.py`
   read only `DATA_DIR`, but the offline-clone live sandbox passes
   `WEBSITEBENCH_DATA_DIR` (plus the vendored compat `CLAWBENCH_DATA_DIR`). With
   no match the database resolved under the read-only candidate root, so under
   the live sandbox `/login` and `/build-routine` answered **500** at every
   viewport and both named sessions failed, leaving 29 member checkpoints
   unvisited — while read-only pages returned 200 and a plain uvicorn run in the
   same container was fine. Fixed by honouring all three variable names and
   declaring `boot.env = {"DATA_DIR": "{data_dir}"}` in `verify.json`; the live
   section then returned clean. This defect was invisible to every macOS gate.

Post-fix, the full task-539 journey completes by **real clicks**: entry →
questionnaire (all panels) → `/signup/results` → `/signup/register` (two-step)
→ dashboard → Upgrade to Elite → Elite Annual → checkout → approved sandbox
scenario → Subscribe → `/my-jefit/settings` showing **"Account Type: Elite —
JEFIT Elite Annual · renews on 2027-08-18"**, with zero offsite requests. A
separate real-click audit of the member area (six pages, four settings tabs,
Create Plan → editor, Add Day, `+ Add session` → log modal, login,
forgot-password) found no blocked controls.

Regression cover added so this defect class is no longer invisible to the
gates: `test_signup_usability.py` (9 tests) and `test_settings_panels.py`
(6 tests), both including negative controls verified to fail against the
pre-fix shapes (4 of the 6 settings tests fail on the old template with the
exact symptoms). One honest note: an earlier version of my own audit
false-positived on defect 4 by asserting that a tab's text appears after
clicking — the text was always present. The new tests assert DOM structure,
not text presence.

## 10. Independent blind review

Two rounds, both with a reviewer given only anonymized A/B screenshot pairs, no
implementation history, and randomized per-pair ordering.

- **Round 1** (12 pairs): 8/12 indistinguishable, clone identified in 4. Two of
  those findings proved not to be candidate defects — the login finding was my
  own harness screenshotting before a 3840×2560 background painted, and
  build-routine was source-side GIF/carousel nondeterminism. The rail-thumbnail
  finding was real (fixed by the asset top-up) and the exercise-count finding is
  the declared catalogue reduction. Round 1 is recorded as partially invalidated
  by that harness defect.
- **Round 2** (12 pairs, final candidate, corrected render timing): **10/12
  indistinguishable.** The reviewer reached a defensible call on 2 pairs and was
  correct on both: `exercises.desktop` (53 vs 1295 catalogue count) and
  `build-routine.desktop` (the promo GIF caught at a different animation phase).
  Verdict in their words: "across this set I could not reliably distinguish the
  reimplementation." Least distinguishable were home tablet/mobile — nothing
  found, reproducing even a distinctive award-badge text-wrap quirk and the
  asymmetric "Male"/"Female" label baselines.

Both surviving tells are **data/asset**, not presentation. The reviewer also
perceived the bottom-edge band quantified in §2 but declined to rely on it.

## 11. Changed paths

New: `materials/jefit/**` (scope, tools, clone, backend, source-current,
source-assets, plus git-ignored source-auth-scratch and artifacts),
`harbor/sites/jefit/**`, `harbor/instances/jefit/**`,
`deploy/generic-offline-clone/deployment.jefit.v2.json`,
`.github/workflows/deploy-jefit-public.yml`,
`.github/workflows/tests-jefit.yml`. No file outside these paths was modified —
`src/`, `tests/`, `websitebench/`, and other sites are untouched. Recon
screenshots that the browser tooling had left in the repo root were moved into
the site's git-ignored `artifacts/exploration/recon-screenshots/`. Nothing is
committed, pushed, or PR'd (not authorized).

## 12. Known differences, blockers, unavailable evidence

1. **Post-payment Elite states unavailable** — real payment prohibited; clone
   behaviour is sandbox-local and disclosed as inference (2 checkpoints).
2. **No recorder ledger, hence no two-sided trajectory diff** — pipe-only CDP.
3. **EA1 depth exploration blocked** → 14 `inferred-architecture` items
   (autosave/log API shapes, monthly checkout variant, member filter apply,
   custom-exercise dialog, per-stat body-stat pages, member light theme, signup
   credential step, login error copy, uncaptured detail fields, sort orderings,
   category membership, populated insights).
4. **Live verify section: RUN and clean** (Linux container, exit 0, 0 findings).
   It cannot run on the macOS host by design, and cannot run over a macOS bind
   mount even on Linux — copy the tree to a native filesystem first.
5. **`tools test-backend` unrun** — human-gated spec.
6. **Catalogue reduced to 53 exercises**, rendering its true count (source
   shows 1295). Entity counts only: fields, density, pagination boundary,
   filter facets and all states preserved. This is the most reliable remaining
   tell, confirmed by both blind reviews.
7. **Animated-GIF phase differences** (exercise-detail, build-routine promo
   carousel) — source-side nondeterminism; not acceptance oracles.
8. **Bottom-20-row residual** (~0.989 vs 0.99999 above y=880), measured and
   disclosed in §2.
9. **Uncaptured legacy assets 404 locally** — ~15 icons plus uncaptured
   `_next/image` optimizer widths and legacy `/forum/attachment.php` refs; all
   local-only, no remote requests. Captured real-user avatars replaced with a
   neutral placeholder so no third-party content ships.
10. **Two Harbor contract pendings** (`unmapped-journey`) with recorded reason.
11. **`/signup?step=N` addressability** is a clone-local addition; the default
    flow matches source.
12. **Enabled-state colour for the register Continue button** is borrowed from
    the observed `/login` primary button — disclosed inference.
13. **Trace-text vs source divergences**, disclosed rather than invented: ht-05
    mentions community ratings (source detail pages have none) and ht-22 expects
    a branded not-found (source serves an unbranded server 404). The clone
    reproduces the source.
14. **2 source-limited calibration rows** (build-routine, coach headers).
15. **Blind-review round 1 partially invalidated** by the harness defect in §10.

## 13. Maintainer judgment

**Deliver as an offline clone; do not publish.** P0 is usable end to end and now
verified the way a human would use it: task 539 completes by real clicks from a
cold start to an Elite membership visible in its destination view, with zero
offsite requests. Static closure is clean with zero remote references and zero
secrets, the pixel oracle passes with margin, 91 site tests and every repo gate
pass (the 9 repo failures are pre-existing macOS platform artifacts), the Harbor
pair is a correct non-scorable draft, and the deployment package passes
check-only and dry-run with zero warnings. An independent blind reviewer could
not distinguish the clone on 10 of 12 surfaces, and the two tells they found are
data/asset differences already declared here.

What is **not** established: no recorder-based two-sided trajectory evidence, no post-payment source evidence,
and 14 inferred-architecture items from the blocked depth exploration. The
catalogue-count difference means a determined reviewer can still identify the
clone from data volume even where presentation is indistinguishable.

The run's most important lesson is recorded rather than buried: passing tests,
a clean static diagnostic, and a passing pixel oracle together still missed five
defects — four that made P0 unusable for a real user, and one that broke every
write route under the live sandbox — because those gates tested the backend, the
pixels, or a platform that skipped the sandbox entirely, and none tested
operability. The added browser-level
regression tests close that hole for this site; the same gap likely exists for
any site built the same way.

Publication remains **unauthorized**: `PUBLIC_DEPLOYMENT_AUTHORIZED=false`,
`PUSH_AUTHORIZED=false`, `PR_AUTHORIZED=false`,
`RIGHTS_OR_REDISTRIBUTION_STATUS=unknown`. A clean diagnostic is not a
copyright, redistribution, or deployment decision.
