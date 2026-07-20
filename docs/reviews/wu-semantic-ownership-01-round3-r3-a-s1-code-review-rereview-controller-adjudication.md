# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S1 Code Review Re-Review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-A / S1`
- Gate: code review re-review controller adjudication
- Time: `2026-07-12T14:37:34+0800`
- Branch: `phaseflow/host-issues-control`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-rereview-ds.md`

## Decision

S1 code review re-review passes.

Both independent re-reviewers returned `PASS`. Controller validation also passed the focused S1 matrix, stress, pyright, targeted scans, and `git diff --check`.

## Accepted Finding Status

### Codex-F1

- Status: `fixed`
- Evidence: compact strict path now resolves accepted result payload via shared durable integrity before calling lenient accepted-result projection. Payload corruption raises `HostDurableError` and cannot become missing evidence.

### Codex-F2

- Status: `fixed`
- Evidence: `_runner_call_manifest` owns typed full-manifest parsing and graph validation. Tool Trace consumes typed validated manifest only. Engine continuation metadata refs close against actual manifest metadata.

### Codex-F3

- Status: `fixed`
- Evidence: `_runner_call_manifest` owns typed hot payload parsing. Complete hot payload requires explicit diagnostic and cross-checks status/count/digest. Tool Trace and Engine ingest no longer synthesize complete diagnostic from sibling scalars.

## Residual Risk

- Existing stress timing residual: one earlier `active_cleanup` failure was reproduced as non-deterministic scheduler/active-cancel timing and subsequently passed in single-test and full stress reruns. Owner/destination: later scheduler / active-cancel slice, not S1.
- Fresh-schema behavior intentionally fails closed for old hot rows, metadata-only manifests, or non-closing manifest graphs. Owner/destination: deployment/preflight work if historical data must be handled; no compatibility shim in S1.
- S2-S8 lifecycle/admin/scheduler behavior remains outside this S1 accepted slice.

## Next Gate

Proceed to accepted S1 slice commit, then update `docs/host/issues-implementation-control.md` with the accepted slice commit hash and next entry point.
