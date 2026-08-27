# Candidate build brief — site `deleteme`

You are the **sole writer of `materials/deleteme/clone/`**. The frozen scope in
`materials/deleteme/scope/` is the contract: `routes.json`, `journeys.json`,
`invariants.json`, `checkpoints.json`, `coverage.json`, `verify.json`,
`claims.jsonl`. Read `derived-task-brief.json` for the observed facts and
`implement-notes.md` for what the source turned out to be.

The frozen source evidence is `materials/deleteme/source-current/2026-08-20.deleteme-r1/`
(rendered DOM + three rasters + `meta.json` per unit) and the mirrored assets are
`materials/deleteme/source-assets/`. **Pixels and copy may come only from those
captures.** Never from memory, a search result, this brief, or the live site.

## What this site is

Two hosts, one experience. Marketing is WordPress (Astra + yootheme) on
`joindeleteme.com`; the member app is a React-Router SPA on
`app.joindeleteme.com` that ships a ~6 KB shell, so its form markup exists only
after JavaScript. The clone serves **one origin**, so map:

| Source | Clone path |
| --- | --- |
| `app.joindeleteme.com/checkout` | `/checkout` |
| `app.joindeleteme.com/checkout/complete` | `/checkout/complete` |
| `app.joindeleteme.com/login` | `/login` |
| `app.joindeleteme.com/password/forgot` | `/password/forgot` |
| `app.joindeleteme.com/<authenticated>` | `/account/...` |
| `help.joindeleteme.com/hc/en-us` | `/help` |
| `privacy.joindeleteme.com/policies` | `/policies` |

Serve the marketing pages from the **frozen rendered DOM** with source scripts
stripped and every reference localised — do not re-template them. Splice
anything the server must compute (order totals, session state, the sandbox
selector that replaces the card iframe) against sentinel comments written at
build time, never by re-parsing the document at request time.

## The P0 journey, exactly

1. `/` → header **Join Now** → `/privacy-protection-plans/`.
2. The plan grid has **one** filter tab strip: billing term, `1 Year` / `2 Years`,
   implemented as `uk-filter-control` over `data-tag="1-Year"|"2-Year"` groups.
   Every `1-Year` group ships `display:none`, so **2 Years is the visible
   default**.
3. **Plan size is not a control.** Inside the active term group four cards render
   side by side: `1 Person`, `2 People`, `Family`, and `Business`. A size is
   chosen by activating that card's own `Start Protection` link. A size-filter
   container (`#fs-grid-filter-activation`, holding Single/Couple/Family) exists
   in the markup but the page ships it `display:none`, so no visitor can operate
   it — reproduce it hidden, do not wire it up.
4. "Individual (1 person)" is therefore the card whose person line reads
   **`1 Person`**. The word "Individual" never appears on the page.
5. Each priced card's CTA carries the selection in the query:
   `?plan=prod_UJ03ZGKxM0BiGF&term=1|2&qty=1|2|4`. The **Business** card has no
   price and no checkout link.

### Prices — derive them, never hard-code a string

Server-side from a plan catalogue, in integer minor units:

| Card label | qty | 1 Year total | 2 Year total |
| --- | --- | --- | --- |
| `1 Person` | 1 | $129.00 | $209.00 |
| `2 People` | 2 | $229.00 | $349.00 |
| `Family` | 4 | $329.00 | $499.00 |
| `Business` | — | no price, no checkout link | no price, no checkout link |

The displayed figure is always **per month** = total ÷ (years × 12), formatted to
two decimals, with `/mo` as its own element. The struck comparison price is the
*undiscounted* base ÷ months (1-year base 129/258/516, 2-year 209/418/836).
**The 1-Person card has no quantity discount, so its comparison price equals its
real price and the source hides it with an explicit inline
`style="visibility: hidden;"`** — while the 2-People and Family cards carry an
explicit `style="visibility: visible;"`. Keep the element in every case and set
visibility explicitly on both, exactly as the source does. Per-card footer copy is
`Billed at $X annually.` or `Billed at $X every 2 years.`

## Payment boundary — absolute

The source collects card data only inside Stripe-hosted iframes. **The clone
reproduces no card field.** Offer only a named sandbox scenario
(`sandbox-approved` / `sandbox-declined` / `sandbox-retry`) from
`backend/runtime.json`, labelled honestly as a simulation. Reject any request
carrying a card-shaped field name (`number`, `cardnumber`, `cvc`, `exp`, …) with
422, and also reject a card-shaped *value* smuggled into another field. Never
persist a payment key of any kind.

## The PII boundary — this site especially

DeleteMe exists to remove personal data, and its own forms ask for it. Therefore:

- **Checkout collects exactly what the source collects**: first name, last name,
  email, one postal address. **No age, phone, previous names, aliases or
  relatives.** Adding them would misrepresent a privacy vendor's data
  collection; a test forbids it.
- The removal profile that *does* collect those lives **after purchase** on the
  source, behind an account this run could never reach. Implement it as a
  clearly labelled clone-local surface.
- Every seeded identity is synthetic and non-resolvable: `example.invalid`
  emails, fictional names, placeholder addresses. No real person's data anywhere.

## Reproduce these source behaviours; do not "fix" them

- The desktop header `Join Now` target is the dead anchor `#pricing`, with no
  such element on the page. Keep it dead.
- A no-match search answers **200** with heading `Search`, an H2 echoing the term
  in **curly quotes**, and an **empty results region with no message at all**.
  Do not invent "no results found". The home page has **no** search form; it
  lives on blog/archive pages.
- An unknown **marketing** path answers **404** with full chrome, headings
  `Oops!` and “That page can’t be found.”, body `It looks like nothing was found
  at this location.`, and `Back` plus `Go to the homepage`.
- An unknown **`/account/...`** path answers **200** with `Page not found` and
  “The page you're looking for doesn't exist or has been moved.” The two hosts
  genuinely disagree; keep both.
- Extensionless unknown marketing paths **301 to the trailing-slash form** first.
- Sign-in has **no remember-me control** and exactly one identity provider,
  `Continue with Google`. Recovery link text is `Forgot Password?`; registration
  link text is `Create Account` and it goes to `/checkout`.
- There is **no free registration**: `/signup` and `/register` do not exist on
  the app host, and no password is collected at checkout.

## Runtime contract

`backend/runtime.json` is the sole authority for site id, database identity,
session cookie, mail purposes and payment adapter. Use the seam:
`from websitebench.site_backend import SiteBackend`, `SiteBackend.open("backend/runtime.json")`.

- Resolve the writable directory as `DATA_DIR` → `WEBSITEBENCH_DATA_DIR` →
  `CLAWBENCH_DATA_DIR`. **All three.** The offline-clone live sandbox passes the
  second, and reading only the first put a jefit database inside a read-only
  candidate root and failed two sessions.
- `app.py` must run under **`python app.py`** as well as uvicorn: add a
  `__main__` guard honouring `HOST`, `PORT`, `DATA_DIR`, `SEED`, `TZ`, staying in
  the foreground and exiting cleanly on SIGTERM.
- `/healthz` → `{"ok": true, "site_id": "deleteme"}`;
  `/__websitebench/health` → exactly `{"status": "ok"}`.
- Mail goes to the local outbox only. Nothing is ever sent.

## Five defect classes that passed every gate on the two previous sites

Treat these as build requirements, not review items.

1. **Advertised srcset widths that are not mirrored.** At device pixel ratio 1 a
   browser picks a width that exists; at 2 or 3 it picks a missing one and the
   image breaks — invisible to static closure, the live diagnostic, the pixel
   oracle and a blind review, all of which ran at ratio 1. Prune any candidate
   the mirror lacks, and if that empties a `srcset`, make sure the plain `src`
   still resolves.
2. **Lazy-loaded references that 404 locally.** This source lazy-loads images
   below the fold via `data-src`/`data-srcset`, and those payloads were never
   requested during capture. The external-only closure check cannot see them and
   the viewport-crop oracle cannot either. Every local reference must resolve or
   be declared with a reason in `source-assets/excluded-requests.json`.
3. **Root-relative `url()` inside pristine mirrored stylesheets.** They pass
   `inspect_asset` because they are not external, then 404 at the clone origin.
   Any stylesheet entering the mirror must go through the localisation pass — and
   re-run it after adding one, or the pages start fetching fonts offsite again.
4. **"Renders but is unusable."** Three separate controls shipped broken on an
   earlier site while API tests, static closure and pixel comparison all passed:
   a submit button left `pointer-events-none` from a captured disabled state, a
   stepper whose slot markers were split mid-comment, and five tab panels
   rendered stacked because the panel splitter ignored the tag stack. Assert DOM
   structure and real clicks, not text presence, and give every such test a
   negative control that fails on the reintroduced defect.
5. **A data URI split on its own comma.** `srcset="data:image/gif;base64,R0lGO…"`
   is one candidate, not two. Splitting it produced a bogus relative path that
   then won a fallback and overwrote the element's real `data-src`, so 50 images
   could never render. Skip `data:` values in any srcset handling.

## Tests you must write (with negative controls)

Under `clone/tests/`, matching the `positive_test_refs` and
`negative_test_refs` named in `invariants.json`:
`test_payment_boundary.py`, `test_checkout.py`, `test_plans.py`,
`test_operability.py`, `test_reference_closure.py`, `test_no_remote_refs.py`,
`test_not_found.py`, `test_search.py`, `test_disclosure.py`,
`test_isolation.py`, `test_seed_identity.py`, `test_no_secrets.py`,
plus a smoke test and a reset-determinism test.

Every negative control must be verified to **fail** when the defect is
reintroduced — on an earlier site a regression test was blind on its first
version, and only the negative control caught it.

## Disclosure

Every surface whose behaviour was never observable — the whole `/account/*`
tree, the removal profile, reports, billing history, plan change, pause, cancel,
reactivate, the password-reset success state and the password-set page — must
carry a **visible clone-local notice** naming why. Recording inferred or
unavailable evidence as observed is an unconditional rejection.

## Stopping rules

If two consecutive repair rounds on the same finding produce no measurable
improvement, record it as a known difference and move on. If three source frames
for a checkpoint fall below the stability floor, that page is moving on the
source: downgrade it to reference evidence and do **not** stabilise the
candidate against it. When something cannot be done, write "not done" and
deliver the rest.
