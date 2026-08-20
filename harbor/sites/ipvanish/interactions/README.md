# wb-ipvanish interaction contract

`opencli-interaction-contract.json` is produced by
`websitebench-harbor derive-from-clone` from the clone's own captured artifacts:

```bash
websitebench-harbor derive-from-clone \
  --clone-manifest materials/ipvanish/clone.yaml \
  --assign-profile ipvanish=checkout \
  --max-steps 9 --force
```

`--max-steps 9` is above the derivation default of 6. It is not a relaxed
threshold — raising it makes the contract *stricter*, because it lets both
profiles keep every check the clone's `tools/frontend_samples.json` declares
instead of silently truncating the tail. Nine steps is well inside the schema's
own limit of 60 per profile.

Two profiles are emitted: `checkout` (p0, 9 steps, anonymous) and `account`
(p1, 8 steps, session established from the seeded synthetic subscriber). The
instance selects `checkout`.

## Residual derivation pendings

Ten of the twelve original pending items were resolved by improving the clone's
inputs. Two remain, and they are not resolvable from any input this run owns.

### `unmapped-journey` for both profiles

`derive.py::_journey_paths` populates a profile's `failure_paths` and
`recovery_paths` by matching `scope/journeys.json` entries whose *family* equals
the profile name (or starts with `<profile>-`) **and** whose `kind` is
`failure`, `retry` or `recovery`.

For this site that cannot match:

* `scope/journeys.json` declares no `family` key on any entry, so family falls
  back to the journey `id`.
* The only entries of a failure/recovery kind are `password-recovery`
  (recovery), `no-results-and-recovery` (failure) and
  `validation-and-permission` (failure). None is named `checkout*` or
  `account*`.
* The checkout journey's declined and retryable paths do exist in frozen
  scope — but as the `failure_variant` and `recovery_variant` fields of
  `compare-plans-select-annual-register`, whose `kind` is `success`.
  `_journey_paths` reads `kind` only and never those two fields, so the
  information is present in the evidence and unreachable by the matcher.

`scope/journeys.json` is frozen evidence this run may not edit. The only
remaining lever is the profile name, which comes from the check-id prefix in
`tools/frontend_samples.json` — and renaming the checkout profile to
`no-results` or `validation` to satisfy the matcher would misdescribe what the
profile actually exercises. Left pending deliberately.

The behaviour itself is **not** unverified. The declined and retryable paths are
asserted three ways: as contract steps `checkout-submit-declined` and
`checkout-submit-card-field-rejected` in this contract (both replayed with zero
assertion failures), as
`clone/tests/test_checkout_payment.py::test_declined_creates_nothing` and
`::test_retryable_succeeds_only_on_a_second_attempt`, and in the browser by
`clone/tests/test_operability.py::test_declined_scenario_keeps_the_form_operable`.
What is empty is the contract's *narrative* list of journey ids, not the
coverage.

## Replay evidence

`replay-evidence/<profile>.json` was produced with `--target candidate` against
the clone on loopback. The real OpenCLI binary is absent on this host, so the
runs used `--opencli-bin materials/ipvanish/tools/opencli-harness/opencli-local`:
a transparent harness that executes the committed adapters in
`adapters/*.js` verbatim and identifies itself as `wb-local-adapter-harness`.
The artifacts record `opencli.version_matches: false` and
`doctor_green: false` rather than implying OpenCLI ran. Replay evidence is
advisory and decides nothing.
