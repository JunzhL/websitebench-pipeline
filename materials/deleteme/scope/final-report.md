# DeleteMe offline-clone continuation — final report

Run resumed 2026-08-20 and acceptance pass completed 2026-08-21 under
`prompts/offline-clone/autonomous-source-to-clone.md`. Source:
`https://joindeleteme.com/`; site id `deleteme`.

Every machine result below is diagnostic-only and requires maintainer judgment.
This report conveys no copyright, redistribution, deployment, or publication
authorization.

## Maintainer judgment

**Acceptable for delivery as the declared offline clone.** The P0 journey is
usable end to end with a local-sandbox payment: public entry, plan comparison,
1-person selection, checkout validation, declined/retry recovery, approval,
confirmation, and persisted order/subscription history. Public auth, recovery,
support, search-empty, and branded not-found paths work; the seeded subscriber
can edit the removal profile, inspect reports and billing, change plan, pause,
cancel, and reactivate.

This is not a claim of strict source indistinguishability. Authenticated and
post-payment source pages were unavailable without making a prohibited live
purchase, so those coherent clone-local states remain visibly labelled
inference. A formally independent blind reviewer was not available in this
continuation; the objective diagnostic and same-environment raster comparison
were completed instead.

The source contradicts two requested trace assumptions and the clone preserves
the observed behavior: checkout collects name, email, and one address—not the
separate removal-profile PII—and a no-match search shows a silent empty region,
not an invented no-results message.

## Acceptance evidence

- 83/83 declared checkpoints loaded in the Linux browser walk; all 8 seeded
  signed-in checkpoints were visited through one synthetic session.
- Static and live diagnostic sections are complete with zero findings, zero
  remote references, zero blocked external requests, and zero deferred routes
  or checkpoints.
- Same-environment home similarity exceeds every frozen threshold: desktop
  `0.996240 >= 0.993912`, tablet `0.996367 >= 0.995`, mobile
  `1.000000 >= 0.995`.
- The independent Linux rendering also passes desktop (`0.9948`) and mobile
  (`0.9967`). Tablet is `0.9942`, 0.0008 below its source-runtime threshold;
  the same-environment comparison passes, and visual inspection attributes the
  residual to cross-platform rendering rather than a layout/asset mismatch.
- Responsive source runtime state is reproduced explicitly: the measured 675px
  hero, the tablet 1600w image selection, the desktop 1920w selection, the
  mobile stacked-button gap, correct press-logo ordering, and absent initial
  sticky CTA. Regression coverage locks these states.
- 594 assets are declared; 585 runtime-required assets verify; 9 are retained
  as evidence-only. Candidate browser walks make no offsite request.
- The complete clone suite passes **95 tests**. It covers browser operability,
  responsive overflow, reference/network closure, source-plan arithmetic,
  checkout recovery and idempotency, payment-data rejection, synthetic seed
  identity, deterministic reset, actor isolation, restart persistence,
  backup/restore integrity, and concurrent unique checkout writes.

## Backend and payment boundary

Runtime: `backend/runtime.json`, schema
`websitebench.site-backend-runtime.v1`, unique site id `deleteme`, site-local
SQLite `deleteme.sqlite3`, host-only session identity, and site-specific
database/volume namespaces. Mail purposes are `registration` and
`password-reset`; local/offline profiles retain messages in the local outbox.
Payments are USD `local-sandbox` only (approved, declined, retryable), with
`stripe_test: null`. The server rejects card fields, card-shaped values, and
removal-profile PII submitted at checkout. Deployment profiles are
`offline-harbor`, `cloudflare-review` (ephemeral reset), and `docker-volume`
(persistent, unique volume).

## Validation ledger

| Check | Result |
| --- | --- |
| `pytest -q materials/deleteme/clone/tests` | **95 passed**, 1 dependency deprecation warning |
| Linux full `verify` | **clean**, static/live complete, 83/83 loads, zero findings |
| same-environment visual comparison | all 3 contracts above threshold |
| project backend/workflow tests | **11 passed, 5 skipped** |
| generic deployment package | **23 passed, 2 skipped** |
| deployment descriptor check + dry run | complete; no deployment performed |
| Harbor contract/adapters | 2 profiles, 5 steps each; adapters in sync |
| advisory local adapter replay | checkout **5/5**, subscription management **5/5** |
| Harbor instance/corpus validation | instance draft/non-scorable; corpus valid |
| broader Harbor tests on macOS | 243 passed, 7 skipped, 7 known platform failures unrelated to DeleteMe |

The Harbor instance intentionally has zero scored cases and remains
draft/non-scorable. OpenCLI is absent on this host; the transparent local
adapter harness executed the generated adapters verbatim. Replay is advisory.

## Remaining limits

1. Authenticated and post-payment source states were not observable; their
   local implementations cannot claim direct visual fidelity.
2. The Linux tablet raster observation is fractionally below a threshold
   calibrated from source frames captured in a different runtime; the
   same-runtime comparison and structural regression both pass.
3. Formal independent blind review remains an external review step, so this
   report does not use the stronger `verified` conclusion.
4. The Harbor derivation retains two honest pending notes: one raw-markup
   assertion checks a saved input value, and the success-kind subscription
   journey has no separately typed failure/recovery journey.
5. Rights status remains unknown. Nothing was committed, pushed, deployed, or
   published.

No unrelated dirty JEFIT work was modified by this continuation.
