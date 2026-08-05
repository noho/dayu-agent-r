# PR 190 F11/F12 S5 Registry/Docs Acceptance

## Gate result

**PASS** — S5 registry/docs lifecycle replacement has completed implementation, independent dual review, controller adjudication,
targeted fix, and independent dual re-review.

## Accepted scope

- `cli.interactive.core-execution@1` is preserved as historical truth and marked `superseded` only through lifecycle fields.
- `cli.interactive.core-execution@2` is the current accepted owner for the stable interactive predicates, with only predicates 29/30
  replaced by the user-confirmed F11/F12 v3 contract.
- The three legacy F11/F12 scenarios are preserved and superseded; the three replacement scenarios are registered as
  `unadjudicated`, with immutable S4 evidence, and remain outside formal readiness until Oracle controller adjudication.
- Historical `accepted_oracle_refs` are frozen; current semantics resolve only through stable `oracle_predicate_refs` to exactly one
  current accepted owner.
- Both registries remain `calibration`; no implementation or observation is represented as final Oracle conformance.

## Review closure

- MiMo initial review: PASS, no blocking finding.
- DeepSeek initial review: PASS with two low findings/open maintenance questions.
- Controller accepted only the documentation-count precision ambiguity; the frozen-ref concern was rejected because it restated the
  confirmed lifecycle contract.
- Codex split the mixed count statement into four independently verifiable inventories without changing registry data.
- MiMo re-review: PASS.
- DeepSeek re-review: PASS; both findings and both open questions closed by evidence-backed adjudication.

Artifacts:

- `docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md`
- `docs/reviews/pr-190-f11-f12-s5-registry-mimo-review-20260806.md`
- `docs/reviews/pr-190-f11-f12-s5-registry-ds-review-20260806.md`
- `docs/reviews/pr-190-f11-f12-s5-registry-review-adjudication-20260806.md`
- `docs/reviews/pr-190-f11-f12-s5-registry-fix-20260806.md`
- `docs/reviews/pr-190-f11-f12-s5-registry-mimo-rereview-20260806.md`
- `docs/reviews/pr-190-f11-f12-s5-registry-ds-rereview-20260806.md`

## Accepted validation

- JSON: 2/2 valid.
- Inventory: 4 oracle records; 1059 scenario records; unique identities.
- Supersession: 0 dangling, 0 asymmetric, 0 cycle.
- Stable resolution: 66 owner-defined predicates; 64 referenced predicate ids; 1614 refs; 0 dangling; 0 duplicate owner.
- Historical subset: 611 records / 768 refs / 29 referenced ids.
- Current `command=interactive`: 612 records / 768 refs / 28 referenced ids.
- Old records: only authorized lifecycle fields changed; 2 unrelated oracles and 1053 unrelated scenarios exact equal.
- Frozen baseline: all 1056 historical `accepted_oracle_refs` unchanged; readiness first 130 lines byte-identical.
- Registry SHA-256:
  - `docs/cli_ci_oracles.json`: `3404e241dbd71c6244da24b0dbb080022d4c57b36f040ac3456e7a18dbc97acf`
  - `docs/cli_ci_scenarios.json`: `f4363fc5e7026ad075f4b7f855342cae493a4852d21bd72ef6e53b3f2d588e37`
- Immutable evidence report SHA-256: `bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411`.
- Immutable evidence root digest SHA-256: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`.
- `git diff --check`: PASS.

## Remaining owner

Formal adjudication of `tool-trace-formal@2`, `rolling-correction-replacement@1`, and
`cap-constrained-memory-replacement@1` remains exclusively owned by the Oracle controller. This S5 acceptance does not alter that
pending state.

