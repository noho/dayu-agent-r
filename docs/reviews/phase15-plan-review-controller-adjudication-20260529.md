# Phase 15 Plan Review Controller Adjudication

## Gate

Phase 15 plan review adjudication.

Reviewed artifacts:
- `docs/reviews/phase15-plan-review-mimo-20260529.md`
- `docs/reviews/phase15-plan-review-ds-20260529.md`

Plan artifact:
- `docs/host/phase15-retention-purge-production-hardening-plan.md`

## Controller Conclusion

The plan is directionally sound, but accepted findings must be fixed before accepted plan commit. The reviewers marked the plan as PASS with non-blocking findings, but several findings affect code-generation readiness: FK-safe deletion, idempotency replay after deleted facts, audit failure semantics, and test scope must be explicit in the plan so the implementation agent does not redesign Phase 15 during implementation.

## Accepted Findings

### ADJ-001 accepted — idempotency_records FK handling

Source: `F15-PLAN-DS-001`.

Decision: accepted.

Reason: Based on the design goal that purge must reliably delete recoverable Session facts under Host governance, `idempotency_records` rows with FK references to target EventLog rows must be in the delete matrix; otherwise EventLog deletion can fail under SQLite foreign-key enforcement.

Required plan fix:
- Add `idempotency_records` to the purge delete matrix.
- Specify deletion before EventLog rows for target Session command idempotency rows that reference target EventLog rows.
- Preserve the new `purge_session` idempotency/tombstone replay path with `created_event_id` / `created_event_sequence` set to `NULL`.
- Add tests for purge after existing command idempotency records.

### ADJ-002 accepted — Run source_run_id child ordering

Source: `F15-PLAN-DS-002`.

Decision: accepted.

Reason: Purge must work for retry/replay chains, and `host_runs.source_run_id` is a self-reference; the plan must specify child-before-parent deletion or a recursive dependency order.

Required plan fix:
- Add explicit Run deletion order for `source_run_id` chains.
- Add a test where a closed Session containing retry/replay-linked Runs can be purged.

### ADJ-003 accepted — FK dependency graph and assertion

Source: `AgentMiMo finding 1`, overlaps `F15-PLAN-DS-001/002`.

Decision: accepted.

Reason: Phase 15 delete logic touches many Host durable tables; requiring implementation agents to rediscover FK topology invites mistakes and violates the handoff-ready plan bar.

Required plan fix:
- Add a concise FK dependency summary before the S2 delete order.
- Add a validation assertion that purge completes with `PRAGMA foreign_keys=ON`.

### ADJ-004 accepted — tombstone-only replay

Source: `AgentMiMo finding 2`.

Decision: accepted.

Reason: After destructive cleanup, tombstone is the durable proof of purge. If the idempotency row is missing but tombstone exists, the safest and most direct behavior is tombstone-based replay or conflict classification rather than recreating facts.

Required plan fix:
- Specify tombstone-present/idempotency-missing behavior.
- Add a test for tombstone-only replay.

### ADJ-005 accepted — audit append failure strategy

Source: `AgentMiMo finding 3`, related to `AgentDS OBS-001`.

Decision: accepted.

Reason: `docs/host/design.md` says purge must write a purge tombstone audit record. A plan that leaves both fail-fast and audit-pending paths open forces implementation-time architecture choice.

Required plan fix:
- Choose one strategy explicitly. Controller decision: the plan must require public `purge_session` to fail before reporting success if the purge audit line cannot be appended.
- Remove the ambiguous audit-pending alternative from release-blocking implementation guidance.
- Add a test asserting audit append failure does not return successful `PurgeSessionResult`.

### ADJ-006 accepted — precondition_digest input list

Source: `AgentMiMo finding 4`.

Decision: accepted.

Reason: The digest is part of tombstone auditability; leaving inputs as "etc." weakens reproducibility.

Required plan fix:
- Replace open-ended wording with an explicit field list or helper contract.

### ADJ-007 accepted — multiprocess test scope

Source: `AgentMiMo finding 5`.

Decision: accepted.

Reason: Phase 15 explicitly excludes remote work but includes local multiprocess confidence; the test must say whether it is same-process multi-handle or actual multiprocess.

Required plan fix:
- Specify actual local multiprocess test scope and the interprocess assertion.

### ADJ-008 accepted — projection checkpoint reset operation

Source: `F15-PLAN-DS-003`, related to `AgentMiMo residual risk 4`.

Decision: accepted as low-risk plan clarity fix.

Reason: Projection checkpoint reset must remain a rebuildable projection operation, not an implementation choice.

Required plan fix:
- Specify reset as deleting affected checkpoint/failure rows or another exact SQL-level operation.
- Define the allowed consumer set or rebuildability criterion.

## Rejected Findings

None.

## Deferred Findings

None.

## Next Gate

Plan fix. Assign planning/fix specialist to update only:
- `docs/host/phase15-retention-purge-production-hardening-plan.md`
- a plan fix artifact under `docs/reviews/`

No source, test, runtime, README, commit, push, or PR work is authorized in this fix gate.
