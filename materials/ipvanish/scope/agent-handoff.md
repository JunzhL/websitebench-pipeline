# IPVanish clone — build brief for the sole candidate writer

You write the candidate. Write only under `materials/ipvanish/clone/`,
`materials/ipvanish/tools/` (build scripts, interaction ledger, frontend
samples) and the single file `materials/ipvanish/scope/verify.json`. Frozen
scope evidence (checkpoints, claims, calibration, coverage, routes, journeys,
invariants, task brief) is read-only: if something in it is wrong, report it
instead of editing it.

## Evidence map

- `scope/derived-task-brief.json` — roles, journeys, authority, the 23 verbatim
  human trace texts.
- `scope/routes.json`, `journeys.json`, `invariants.json`, `purpose.json` —
  behaviour contracts, verbatim copy notes, declared omissions.
- `scope/checkpoints.json` (frozen) — every captured state, its source raster,
  and which states carry a pixel contract.
- `scope/implement-notes.md` — the authority state, the browser preflight, the
  directly-observed source shapes, and the autonomous decisions so far. Read it
  fully; it answers most "why is it like this" questions.
- `source-current/2026-08-19.ipvanish-r1/<state>/<viewport>/` — `frame-1..3.png`,
  `frame-1.viewport.png`, `page.html` (rendered DOM), `links.json`,
  `resources.json`, `meta.json` (the checkout card-form's `meta.json`
  `interaction` note carries the registration form's field inventory).
- `source-assets/manifest.json` — 1,035 assets, already reconciled against the
  closure inspector and mirrored byte-exact at
  `clone/static/assets/2026-08-19.ipvanish-r1/<host>/<path>`; `runtime_path` per
  asset. 23 entries are demoted evidence-only (18 CSS carrying external
  references, 5 Font Awesome icon SVGs) — see "Asset promotion" below.
- `source-assets/unresolved-references.json` — source-404 references, including
  two discarded HTML response shells. Reproduce the references; the 404s are a
  source property.

There is **no authenticated evidence at all** for this site and no
`source-auth-scratch/`: IPVanish gates account creation behind a purchase, so
the subscriber role was never reached. Everything subscriber-side you build is
inference and must be labelled as such in your report.

## Architecture

- FastAPI at `clone/app.py`, run as `uvicorn app:app` from `clone/`, Python
  3.12. Dependencies limited to fastapi, uvicorn, jinja2, python-multipart,
  argon2-cffi (pin them in `clone/requirements.txt` and mirror the pins into the
  deployment descriptor later).
- **Resolve the writable state directory from `DATA_DIR`, then
  `WEBSITEBENCH_DATA_DIR`, then `CLAWBENCH_DATA_DIR`.** Harbor's ABI passes the
  first; the offline-clone live sandbox passes the second. On the JEFIT run,
  reading only `DATA_DIR` sent the database into the read-only candidate root
  and every write route answered 500 under the live diagnostic while read-only
  pages passed. Do not repeat that.
- Backend only through the vendored seam: `from websitebench.site_backend import
  SiteBackend`, `SiteBackend.open("backend/runtime.json")`. The runtime contract
  at `materials/ipvanish/backend/runtime.json` is authoritative for site id,
  database identity, session cookie, mail purposes and the payment adapter
  (`local-sandbox`). Do not hand-roll auth, mail or payment.
- Business schema through that seam: accounts, sessions, the plan catalogue,
  subscriptions, orders/billing history, billing contacts, sandbox payment
  records, support articles, and the seeded fixtures.
- Server-rendered Jinja pages that reproduce the captured rendered DOM. The
  source is a WordPress/Astra marketing tree plus two client-rendered SPAs
  (Angular checkout, Next.js SSO); the clone re-serves their *rendered*
  presentation server-side. Client JS only where interaction demands it, all
  clone-local, no external libraries beyond what is vendored.
- Health endpoints: `/healthz` → `{"ok": true, "site_id": "ipvanish"}` and
  `/__websitebench/health` → exactly `{"status":"ok"}`. Honour `HOST`, `PORT`,
  `DATA_DIR`, `SEED`, `TZ`; stay in the foreground; exit cleanly on SIGTERM.
  Include a `if __name__ == "__main__":` guard that runs uvicorn, because
  `ACCEPTANCE.md` step 3 starts the clone with `python app.py`.

### Single origin, source subdomains

The source spreads across `www`, `checkout`, `sso`, `support` and `my`
subdomains. The clone serves one origin. Use these local paths and record the
aliases in `scope/verify.json`:

| Source | Clone path |
| --- | --- |
| `www.ipvanish.com/…` | same path |
| `checkout.ipvanish.com/checkout/address-payment-method?flow=…` | `/checkout/address-payment-method?flow=…` |
| `sso.ipvanish.com/` | `/login` |
| `sso.ipvanish.com/reset-password/` | `/login/reset-password` |
| `support.ipvanish.com/hc/en-us` | `/support` |
| `my.ipvanish.com/…` | `/account/…` |

Cross-subdomain links in captured markup must be rewritten to these local paths
— a link that still points at `checkout.ipvanish.com` is a remote reference and
will fail the closure invariant.

## Non-negotiable behaviour

1. **Pricing (P0).** Three billing-period tabs — `2-Year Plan` (default),
   `Yearly Plan`, `Monthly Plan` — each with `Essential` and `Advanced`
   (`Best Protection` ribbon). Render the captured prices exactly: Monthly
   `$14.99` / `$17.99`; Yearly `$3.89` / `$5.39` per month struck from `$179.88`
   / `$215.88` with "for the first year" copy `$46.68` / `$64.68`; 2-Year
   `$2.49` / `$3.59` struck from `$359.76` / `$431.76` with `$59.76` / `$86.16`.
   Renewal copy per period ("Renews Yearly at $99.99." / "$129.99." /
   "Renews Monthly at …"), the `30 days risk free` sub-label on Yearly and
   2-Year only, and the feature comparison rows including the eSIM allowance
   (`3GB` / `5GB`) and the Advanced-only rows. The `30-day Money-back Guarantee`
   row is absent from the Monthly table on the source — keep it absent.
   Reproduce the verbatim `60% discount when paid annually`-style copy even
   where the arithmetic looks odd.
   The tab controls on the source are bare `<strong>` elements. Make them
   genuinely operable in the clone (a real click must switch the period) and
   make sure **exactly one period's cards are visible at a time** — the JEFIT
   run shipped a settings page where all five tab panels rendered stacked
   because nothing established the initial state and the panels were carved as
   unbalanced HTML fragments. If you carve panels out of captured markup, use a
   tag-stack-aware splitter that keeps each panel self-contained and re-emits
   ancestor closers outside the wrappers.
2. **Checkout (P0, task 687).** `/checkout/address-payment-method?flow={tier}-{period}`.
   Step one is the payment-method chooser: `Credit card`, `PayPal`, `Apple Pay`,
   `Google Pay` rows with chevrons, beside the Order Summary — for
   `essential-annual`: `12 months`, `IPVanish Essential`, `$179.88`,
   `Save 74% - $133.20`, `Estimated tax $6.07`, `Total due $ 52.75`, the 30-day
   money-back badge and the Trustpilot block. Derive every one of those figures
   server-side from the plan catalogue; never accept an amount from the client.
   Activating `Credit card` reveals the registration form. The source form is a
   Zuora iframe carrying `field_email`, `field_creditCardHolderName`,
   `field_creditCardNumber`, `field_creditCardExpirationMonth`,
   `field_creditCardExpirationYear`, `field_cardSecurityCode`,
   `field_creditCardCountry`, `field_creditCardPostalCode`, with `Subscribe now`
   in the main document and the copy "Secure checkout. Your payment information
   is fully protected. By subscribing, you agree to be charged $52.75. Your plan
   will automatically renew annually at $99.99 until canceled…".
   **The candidate must not offer any field capable of carrying card data.**
   Reproduce the layout and copy, keep the account email and billing
   country/postal fields (they are real business inputs), and replace the card
   number / holder / expiry / CVC group with an honestly labelled
   `local-sandbox` scenario selector (approved / declined / retryable). Say so
   on the page — do not imply a real card is being taken. `Subscribe now`
   consumes the scenario through the seam and writes the subscription plus its
   order row in one transaction.
3. **Post-payment.** A confirmation view and then the account dashboard. Both
   are clone-local: the source's confirm/done steps were never reached because
   reaching them charges a card. Keep them structurally consistent with the
   captured funnel and disclose them.
4. **Auth.** `/login` reproducing the SSO view (`RECLAIM YOUR ONLINE PRIVACY
   TODAY`, `Welcome back! Sign in to continue to customer portal`, Email address
   + Password, `Forgot password?`, `Not a member? Sign up now!` → `/pricing/`).
   No third-party identity-provider buttons were observed on the source, so do
   not invent any. `/login/reset-password` reproducing `Reset password`,
   `Enter you account email, you will receive a reset password code` (**source
   typo, verbatim**), Email address (input named `username`), `Back to sign in`,
   `Send code`. Reset mail goes to the seam's local outbox only.
5. **Not-found fidelity.** An unmatched path must answer **HTTP 404 with the
   home page as its body** — that is what the source does (markup
   byte-near-identical to `/`, no "404" string anywhere). Do not build a branded
   404 page. Trace ht-22 expects one; that divergence is recorded, not fixed.
6. **Support.** `/support` reproducing the captured Zendesk-style centre with a
   search box, Support Categories, FAQ entries and the system-status banner.
   Searching `zzzz-no-match-websitebench` yields a no-results state with a route
   back to plans.
7. **Subscriber dashboard (`/account/…`, all inference).** Overview with the
   current plan and renewal date, billing history, plan change, billing-contact
   edit, pause, cancel and reactivate — each performing real local business
   behaviour with sandbox payments where money is involved. Traces ht-08, ht-12
   and ht-14 ask for a shipping address, a delivery skip and shipment status; a
   VPN subscription has none of those, so provide the billing-address, pause and
   billing-history equivalents and record the divergence rather than inventing
   shipping.
8. **Source quirks to reproduce, not tidy.** The WPML banner "This site is
   registered on wpml.org as a development site."; the rendered top-level nav
   carrying only Product, Apps, Resources, Help, Pricing (plus My Account and
   Get Started) even though the served markup contains more; the absence of a
   rendered "View All Features" expander; the absence of any product search on
   the marketing tree.

## Asset promotion

18 pristine CSS files carry external `url()`/`@import` references and are
already demoted to evidence-only in the manifest. Follow
`materials/aspca-pet-insurance/tools/promote_localized_css.py` /
`materials/jefit/tools/promote_localized_assets.py`: write
`tools/promote_localized_assets.py` that emits localized copies under
`clone/static/site/vendor/`, rewrites their internal references to captured
local mirrors, verifies each copy passes
`websitebench.offline_clone.assets.inspect_asset`, and repoints candidate
references at the vendor copies. Pristine bytes stay untouched. Where a
referenced asset was never captured, let it 404 locally and record it — do not
invent a substitute.

## Deterministic seed

Two synthetic accounts (a primary subscriber plus an isolation actor), the
six-entry plan catalogue with the captured prices, one active annual
subscription, one canceled subscription for reactivation, billing history rows
covering an initial charge and a renewal, and the three sandbox scenarios.
`SEED` selects the state; reset must be byte-stable. Synthetic identities only.

## Tests (`materials/ipvanish/clone/tests/`)

Name the files exactly as `scope/invariants.json` references them:
`test_smoke.py`, `test_app_surface.py` (routes, titles, **404-with-home-body
fidelity**), `test_no_remote_refs.py` (+ the negative detector test),
`test_auth.py`, `test_pricing.py` (period switching, no price mixing),
`test_checkout_payment.py` (flow binding, server-derived amounts, approved /
declined / retryable / idempotent duplicate, **card-like input rejected**),
`test_backend_lifecycle.py` (deterministic reset + negative divergence test,
cross-actor isolation, restart persistence), `test_payment_mail.py`,
`test_operability.py`.

`test_operability.py` is required from the start, not after a review finds
something broken. Boot the app and drive a real browser: assert that the three
billing tabs switch periods by real click, that exactly one period's cards are
visible at a time, that the plan CTAs navigate with the right flow, that the
payment-method rows expand, that the registration form submits, that sign-in and
recovery submit, and that no visible control on a frozen journey has
`pointer-events: none` or is `disabled`. Include a negative control proving the
test would fail if such a control were introduced.

## Ledger and Harbor inputs

While walking the route/state matrix, record
`tools/interaction-ledger.json`: clone URL, the stable selector of each
activated control, one visible-text proof and one raw-markup proof per route,
and the form action behind every mutation. Author
`tools/frontend_samples.json` (`schema_version
"ipvanish.frontend-gate-samples.v1"`, `app_file "clone/app.py"`,
`app_attr "app"`, `module_name "ipvanish_clone_app"`) with one check per key
route plus `healthz` and an external-boundary check. Keep `expect_contains`
short visible-text strings, at most two assertions per step, no markup in
visible-text keys. Include a `session_setup` plus `session: true` checks for
subscriber routes and POST checks for the checkout submit, so
`derive-from-clone` can emit real click/submit steps. `url: "/"` cannot become a
contract step — add an explicit index alias.

## `scope/verify.json`

Driver data only, never code: `boot` (uvicorn argv, `cwd: "clone"`, and
**`env: {"DATA_DIR": "{data_dir}"}`**), the `routes` alias map for every
checkpoint route id, `states` recipes for non-default states (billing tabs, nav
dropdowns, the checkout chooser and card form, the no-results search, subscriber
states behind a login `prepare`), `status: {"not-found": 404}`, and `prepare`
for anything needed before assertions. Check `verify --help` for the recipe
grammar before inventing one.

## Gates (bounded repair: two rounds without measurable progress on a finding → record it as a known difference and move on)

1. `websitebench-offline-clone validate --site materials/ipvanish`
2. `python -m pytest materials/ipvanish/clone/tests -q`
3. `websitebench-offline-clone verify --site materials/ipvanish --section static`
   (must stay clean — it is clean now, before any candidate code exists)
4. the full static+live verify, which is Linux-gated: use the containerized
   runner pattern from `materials/jefit/tools/run-live-diagnostic.sh` (copy the
   tree onto the container's native filesystem — a macOS bind mount cannot host
   the candidate because Landlock denies directory listing through virtiofs)
5. `ruff check` clean on everything you write

Never relax a threshold, widen a mask, delete a test, fake a success, or record
inferred or unavailable evidence as directly observed. Report every remaining
finding honestly, and state plainly which parts of the subscriber experience are
inference.
