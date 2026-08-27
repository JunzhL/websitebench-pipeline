# Payment-scope decision — jefit

Decision: **a hash-bound payment-scope proposal is required and is stored in
`scope/payment-scope.json`.**

Mode: **`manifest-native-audit`.** jefit is a new site with no legacy
`websitebench/site-profiles/jefit/site.json`; it selected the payment overlay
in this initial build through the scaffolded backend runtime contract, and its
`materials/jefit/clone.yaml` is an `offline-clone.manifest.v2` manifest. As
with `aspca-pet-insurance` (the same manifest-native shape), the validator
therefore requires `candidate_blocker_id: null`, no retained blockers, and no
legacy-profile binding.

Why local-sandbox only:

- The source Elite checkout is Stripe-hosted and was never submitted
  (`stripe_test_authorized=false`, `live_payment_authorized=false` in the
  frozen authority block), so the clone models the upgrade purely locally.
- The only accepted client payment input is one opaque configured sandbox
  scenario id (`sandbox-approved`, `sandbox-declined`, `sandbox-retry`).
  Card number, CVC, expiry, bank fields, client amounts and provider tokens
  are rejected and never stored or logged (`payment-input-boundary`
  invariant).
- Amounts are server-derived integer USD minor units from the plan table:
  Elite monthly 1299; Elite Annual first-year 5249 (25%OffFirstYear against
  the 6999 renewal list price).
- An approved attempt upgrades membership only when approval consumption, the
  `jefit_orders` insert, and the `jefit_users` membership-state update commit
  in one site-bound SQLite transaction; declined and retryable attempts create
  nothing and duplicates converge idempotently (`membership-order-transactional`
  invariant).
- `optional_adapter` is `null`: `stripe_test` stays unconfigured and every
  deployment profile pins `payment_adapter: local-sandbox`.

Bound current inputs (path + sha256, verified from disk by the check):
`materials/jefit/clone.yaml`, `materials/jefit/scope/purpose.json`,
`materials/jefit/scope/invariants.json`,
`materials/jefit/backend/runtime.json`, `materials/jefit/backend/model.json`,
and `websitebench/capability-packs/payment/pack.json`.

Machine check: `websitebench-workflow check-payment-scope --proposal
materials/jefit/scope/payment-scope.json` — **passed**
(`scope_subject_sha256`
`fcd902320b394aba1c0216ca6ce123dfc52b1cd4c38a48fcda9ac564c2515701`, computed
via `payment_scope_subject()`). The check is diagnostic scope-binding only; it
does not enable an adapter, authorize live payments, or deploy anything.
