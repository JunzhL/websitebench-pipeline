# Payment-scope decision — ipvanish

Decision: **a hash-bound payment-scope proposal is required for this site and is
stored in `scope/payment-scope.json`.** IPVanish's whole reason to exist is a
paid subscription funnel, so the clone implements checkout, subscriptions and
orders, and the payment overlay is therefore in scope.

Mode: **`manifest-native-audit`.** ipvanish is a new site with no legacy
`websitebench/site-profiles/ipvanish/site.json`; it selects the payment overlay
in this initial build through its scaffolded `backend/runtime.json`, and
`materials/ipvanish/clone.yaml` is an `offline-clone.manifest.v2` manifest. The
validator therefore requires `candidate_blocker_id: null`, no retained
blockers, and no legacy-profile binding — the same shape used by `jefit` and
`aspca-pet-insurance`.

Why local-sandbox only:

- The frozen authority block in `scope/derived-task-brief.json` records
  `stripe_test_authorized=false`, `live_payment_authorized=false`,
  `real_email_authorized=false`, and authenticated access as *not requested*:
  the subscriber role cannot be reached on the source without buying a plan,
  and no purchase was authorized. `optional_adapter` is `null`, `stripe_test`
  stays `null` in the runtime, and all three deployment profiles
  (`offline-harbor`, `cloudflare-review`, `docker-volume`) pin
  `payment_adapter: local-sandbox`.
- The only accepted client payment input is one opaque configured scenario id
  (`sandbox-approved`, `sandbox-declined`, `sandbox-retry`). The candidate
  offers no card-capable field at all, and `db.reject_payment_fields()` screens
  every submitted key *and* value so a renamed field cannot smuggle a PAN
  through (`payment-input-boundary`).
- Amounts are derived server-side from the six-row `clone/backend/catalogue.py`
  table (Essential and Advanced x monthly, annual, biennial), resolved from the
  request only through `plan_for_flow(?flow=)`: Essential annual 4668 minor
  units for the first year against a 9999 renewal, Advanced annual 6468 against
  12999, monthly 1499 and 1799 undiscounted, biennial 5976 and 8616. Estimated
  tax is `round(charge_minor * 13 / 100)`, the rate that reconciles the captured
  `$6.07` tax on `$46.68`, giving the 5275 annual Essential total
  (`checkout-flow-binding`).
- `db.purchase()` is the final commit: one
  `site_backend.lifecycle.connection(transaction=True)` carries the
  `create_intent` / `attempt` / `consume_approval` sequence and both the
  `ipvanish_subscriptions` and `ipvanish_orders` inserts. A non-`APPROVED`
  attempt returns before consumption, so declined and retryable scenarios write
  nothing at all — not even the account row, which
  `db.ensure_checkout_account()` only creates after approval. Duplicates
  converge on the first order through `UNIQUE (subject_id, idempotency_key)`
  (`subscription-order-transactional`).
- The owner is the checkout-created account, `subject_id =
  'ipvanish-checkout-' + sha256(account_email)[:24]`, and the fingerprint is
  `db._fingerprint()` = SHA-256 over `ipvanish|<subject_id>|<plan_id>|<kind>`,
  re-verified by the seam alongside owner, amount and USD at intent, attempt
  and consumption.

Bound current inputs (path + sha256, verified from disk by the check):
`materials/ipvanish/clone.yaml`, `materials/ipvanish/scope/purpose.json`,
`materials/ipvanish/scope/invariants.json`,
`materials/ipvanish/backend/runtime.json`,
`materials/ipvanish/backend/model.json`, and
`websitebench/capability-packs/payment/pack.json`.

One divergence worth stating plainly: on the source, `checkout.ipvanish.com`
collects card data through a third-party hosted page — a Zuora payment iframe
carrying `field_creditCardNumber`, `field_creditCardHolderName`,
`field_creditCardExpirationMonth`, `field_creditCardExpirationYear` and
`field_cardSecurityCode`, revealed when the `Credit card` payment-method row is
activated. The candidate deliberately does **not** reproduce it. The backend
mandate forbids the clone from accepting card-like input at all, so the clone
keeps the checkout's captured layout, order summary and recurring-charge copy
but replaces the card iframe with an honestly labelled local-sandbox outcome
selector. Nothing was ever entered into or submitted to the source's iframe,
and the post-payment confirmation state is recorded `unavailable` in
`scope/routes.json` rather than guessed at — the clone's confirmation page is
disclosed as clone-local inference.

Machine check: `websitebench-workflow check-payment-scope --proposal
materials/ipvanish/scope/payment-scope.json` — **passed**
(`scope_subject_sha256`
`30b0ebaca44759345e368186f22854293ce0f76ebaf2de9ebdef79b6b35da4fe`, computed
via `payment_scope_subject_sha256()`). The check is diagnostic scope-binding
only: it does not enable an adapter, authorize live payments, or deploy
anything.
