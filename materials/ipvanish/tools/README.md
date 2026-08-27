# IPVanish capture and candidate tooling

`capture_id = 2026-08-19.ipvanish-r1`

Two families live here. The `capture_*` scripts read the source and wrote the
frozen evidence; the `build_*` / `promote_*` scripts read that frozen evidence
and write the candidate under `../clone/`. The frozen evidence is read-only to
the second family.

## Candidate build order (all offline; nothing contacts the source)

```bash
# 1. rendered DOM -> served documents, plus the shell used by clone-local pages
python3 materials/ipvanish/tools/build_clone_pages.py

# 2. localize the 18 demoted stylesheets and repoint the documents at them
#    (must follow step 1: step 1 rewrites the pages from scratch)
python3 materials/ipvanish/tools/promote_localized_assets.py

# 3. record the route/state walk against the freshly built candidate
python3 materials/ipvanish/tools/build_interaction_ledger.py
```

| Script | What it does |
| --- | --- |
| `build_clone_pages.py` | Reads `source-current/<capture_id>/<state>/<viewport>/page.html`, removes every source `<script>`, rewrites every URL-bearing attribute and CSS `url()` onto a local path, prunes responsive-image candidates whose mirror payload was never captured, carries Astra's configured header breakpoint onto the clone bundle, and writes one served document per route into `clone/frontend/pages/` plus `_shell.html`, `external-links.json` and `build-report.json`. Fails loudly if any remote reference survives. |
| `promote_localized_assets.py` | Writes localized siblings of the 18 evidence-only stylesheets into `clone/static/site/vendor/`, verifies each against `websitebench.offline_clone.assets.inspect_asset`, and repoints the candidate at them. The pristine mirror stays byte-exact. Report in `clone/frontend/promotion-report.json`. |
| `build_interaction_ledger.py` | Walks the live candidate with `TestClient` and writes `interaction-ledger.json`: clone URL, stable selector, one visible-text (or accessible-name) proof, one raw-markup proof, and the form action behind every mutation. A declared proof that does not appear in the served document is a build error. |
| `frontend_samples.json` | Hand-authored Harbor input (`ipvanish.frontend-gate-samples.v1`): one check per key route plus `healthz`, the external boundary, POST checks for the checkout submit, and `session: true` checks for the subscriber surfaces. Each check carries at most one `expect_contains` and one `expect_not_contains` value, because a derived contract step holds at most two assertions and a second value of the same kind is dropped rather than asserted. |
| `opencli-harness/` | Transparent local stand-in for the OpenCLI binary, used by `websitebench-harbor run-opencli --opencli-bin`. It executes the committed `harbor/sites/ipvanish/interactions/adapters/*.js` verbatim, shimming only the two `@jackwener/opencli` imports, and reports itself as `wb-local-adapter-harness` so no artifact implies OpenCLI ran. |

The three POST forms live in `../clone/frontend/fragments/` rather than in
`app.py` string literals: `derive-from-clone` resolves a form-backed submit step
by reading the templates on disk, so a form built only at request time is
invisible to it and its check degrades to an unresolved-selector pending.

`clone/htmlslice.py` holds the tag-stack-aware slicer both the build tools and
`clone/app.py` use, so a fragment is never carved with a non-greedy regex.

## Capture tooling

All three scripts run local headless Playwright Chromium with an ordinary
desktop Chrome UA (`CHROME_UA` in `capture_source.py`). That UA is a
rendering-fidelity requirement, not an access-control bypass: `www` serves
UA-dependent markup and `support.ipvanish.com` answers the Playwright
headless UA with a Cloudflare 403 interstitial. See
`../scope/implement-notes.md` for the preflight table.

## Scripts

| Script | What it does |
| --- | --- |
| `capture_source.py` | Captures every URL-addressable checkpoint in `scope/source-capture-plan.json` at each planned viewport into `source-current/<capture_id>/<checkpoint>/<viewport>/` (`frame-1..3.png`, `page.html`, `links.json`, `resources.json`, `meta.json`), plus `session-fingerprint.json` and `capture-index.json` (`ipvanish.capture-index.v1`). Waits for network idle (12s cap) then a settle delay (default 6000ms, the SPA subdomains need it), dismisses the Ziff Davis consent banner once per context, and probes WordPress/Astra regions (`#masthead`, `#primary`, `#content`, `#colophon`, plus generic landmarks and a `form` probe). |
| `capture_states.py` | Captures the interaction-dependent states that no URL reaches, in the same artifact layout, indexed by `state-capture-index.json` (`ipvanish.state-capture-index.v1`). |
| `capture_assets.py` | Renders the URL-addressable checkpoints (desktop + mobile) recording every response, closes the remainder (CSS `url()` chains and `resources.json` entries) with GET-only fetches, mirrors payloads into `source-assets/<capture_id>/<host>/<path>` **and** `clone/static/assets/<capture_id>/<host>/<path>`, and writes `source-assets/manifest.json` (`offline-clone.assets.v1`), `unresolved-references.json` and `excluded-requests.json`. |

## Run order

```bash
# 1. URL-addressable checkpoints (needs scope/source-capture-plan.json)
python3 materials/ipvanish/tools/capture_source.py --site-dir materials/ipvanish

# 2. Interaction states (writes into the same source-current/<capture_id> tree)
python3 materials/ipvanish/tools/capture_states.py --site-dir materials/ipvanish

# 3. Asset closure (consumes every resources.json written by steps 1 and 2)
python3 materials/ipvanish/tools/capture_assets.py --site-dir materials/ipvanish
```

Re-runs of a subset: `--only <id>,<id>` on any script (step 1 and 2 merge the
fresh records into the existing index; step 3 with `--only` produces a
partial manifest, so prefer a full run before verification). Add
`--skip-render` to step 3 to close the remainder from existing
`resources.json` files only, `--headed` to steps 1 and 2 to watch a run.

## States implemented by `capture_states.py`

`pricing-2year`, `pricing-yearly`, `pricing-monthly` (billing-period tabs on
`/pricing/`; the labels are bare `<strong>` elements, so the click goes to
the nearest sizeable ancestor via in-page JS and the visible prices must
change before capture), `pricing-features-expanded`, `nav-product`,
`nav-features`, `nav-solutions`, `nav-apps`, `nav-resources` (hover-opened
Astra dropdowns on `/`; the parent link is never clicked),
`mobile-menu-open` (390x844), `sso-signin`, `sso-recovery` (reached by
clicking *Forgot password?*; the route needs its trailing slash),
`checkout-chooser-essential-annual`, `checkout-chooser-essential-monthly`,
`checkout-chooser-advanced-annual`, `checkout-card-form-essential-annual`,
`support-home`, `not-found` (records the HTTP status).

## Safety rules

- **Source capture is GET-only navigation.** No field is filled and nothing is
  submitted anywhere in `capture_source.py`.
- **The state walker aborts every non-GET request at the network layer**
  (`context.route`), so no click in the walk can mutate the source site. If an
  aborted non-GET keeps a surface from rendering (the Angular checkout builds
  its quote that way), the state is recorded as an error rather than relaxing
  the rule.
- **Nothing is ever typed or submitted on `checkout.*`.** `assert_fill_allowed`
  refuses any fill while the page sits on a payment origin
  (`checkout.ipvanish.com`, the Zuora iframe) and `assert_click_allowed` — plus
  an independent check inside the in-page clicker — refuses any control whose
  text matches `/subscribe|pay now|place order|complete/i`. The card-form state
  records iframe URLs (query-stripped: Zuora hosted-page URLs carry signature
  tokens) and the field `name`/`id`/`type` inventory only, never a value.
- **No credentials persist.** No cookie, header, token or field value is
  written to the evidence tree; asset `source_url`s are stripped of query
  *and* fragment, and analytics / consent / ad / identity / live-payment hosts
  are never fetched — only logged with a reason in
  `source-assets/excluded-requests.json`.
- Assets larger than 50MB are skipped.
