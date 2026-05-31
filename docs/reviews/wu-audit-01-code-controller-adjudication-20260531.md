# WU-AUDIT-01 Code Controller Adjudication

## Context

- Work unit: WU-AUDIT-01 Purge Audit Cross-medium Orphan Reconciliation
- Accepted plan: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`
- Implementation report: `docs/reviews/wu-audit-01-slice1-implementation-codex-20260531.md`
- Code reviews:
  - `docs/reviews/wu-audit-01-code-review-mimo-20260531.md`
  - `docs/reviews/wu-audit-01-code-review-ds-20260531.md`
- Code re-reviews:
  - `docs/reviews/wu-audit-01-code-rereview-mimo-20260531.md`
  - `docs/reviews/wu-audit-01-code-rereview-ds-20260531.md`

## Controller Judgment

Implementation accepted after fix and re-review.

The implementation satisfies the design goal without expanding into a generic audit analysis framework:

- `purge_started` is written before destructive purge and does not mark purge complete.
- SQLite tombstone remains the purge completion truth.
- `purge_completed` is written only after tombstone commit and references the committed tombstone digest.
- SQLite failure paths do not write completed audit lines.
- idempotent replay attempts completed append unconditionally and relies on JSONL source-key idempotency, without scanning JSONL.
- `purge_failed` remains best-effort diagnostic only.
- Durable schema and public result fields remain unchanged.

## Finding Dispositions

| Finding | Source | Disposition | Rationale |
|---|---|---|---|
| `failure_stage` was hardcoded to `sqlite_purge_transaction` for all failure types. | DS F-01 | accepted-fixed | Accurate failure_stage is necessary audit diagnostic and does not introduce overdesign. The fix passes explicit stage constants per exception path. |
| idempotency conflict path wrote `purge_failed` with misleading transaction stage. | DS F-02 | accepted-fixed | Keeping best-effort failed audit is acceptable, but the stage must be `idempotency_conflict`; the fix adds a dedicated catch before generic `HostDurableError`. |

## Residual Risks

| Risk | Disposition | Owner / Destination |
|---|---|---|
| `purge_failed` append itself may fail; command path logs warning and preserves original error. | accepted residual behavior | Current WU-AUDIT-01; covered by design as best-effort failed audit. |
| completed append may fail after tombstone commit; caller must retry same `client_request_id` to補写 completed audit. | accepted residual behavior | Current WU-AUDIT-01 tests cover retry補写 path. |
| Precondition / already-purged / not-found / idempotency-conflict failure_stage values are code-reviewed but not all individually asserted in public command tests. | accepted low test gap | No follow-up required before slice acceptance because `purge_failed` is best-effort diagnostic and mappings are explicit constants. |

## Gate Decision

Code review and re-review passed. This implementation may proceed to accepted slice checkpoint.
