# Phase 15 S1 Code Review Controller Adjudication

## Gate

Phase 15 S1 code review adjudication.

Reviewed artifacts:
- `docs/reviews/phase15-s1-code-review-mimo-20260529.md`
- `docs/reviews/phase15-s1-code-review-ds-20260529.md`

Implementation artifact:
- `docs/reviews/phase15-s1-implementation-codex-20260529.md`

## Controller Conclusion

AgentMiMo reported PASS with 0 findings. AgentDS reported PASS with 2 findings. Both DS findings are accepted before S1 closeout because they improve the durable primitive semantics and regression coverage without expanding scope beyond S1.

## Accepted Findings

### S1-ADJ-001 accepted — durable inconsistency misclassified as idempotency conflict

Source: `docs/reviews/phase15-s1-code-review-ds-20260529.md` F1.

Decision: accepted.

Reason: Based on the Host design goal that tombstone is the durable proof after purge, a same-key/same-digest request with a conflicting idempotency table row means internal durable inconsistency, not caller idempotency conflict. Misclassification would leak an incorrect public error category in later command wiring.

Required fix:
- In `_decision_for_existing_tombstone(...)`, map `HostIdempotencyConflictError` from `record_idempotent_result(...)` to `PurgeReplayDecisionKind.DURABLE_INCONSISTENCY`.
- Preserve the existing replay behavior when the record can be inserted/read normally.
- Add a focused test that constructs tombstone plus conflicting idempotency row and asserts durable inconsistency.

### S1-ADJ-002 accepted — missing rejection-path tests for tombstone validation

Source: `docs/reviews/phase15-s1-code-review-ds-20260529.md` F2.

Decision: accepted.

Reason: S1 introduces durable validation primitives that later slices will rely on. Negative tests for malformed counts/digests/audit refs are cheap and keep the durable contract from regressing.

Required fix:
- Add tests covering negative delete counts, mismatched `deleted_counts_digest`, and unpaired `audit_record_ref` / `audit_record_digest`.
- Keep production code changes limited to what S1-ADJ-001 requires unless tests expose a real validation bug.

## Rejected Findings

None.

## Deferred Findings

None.

## Next Gate

Phase 15 S1 fix. Fix agent may modify only:
- `dayu/host/durable/purge.py`
- `tests/host/test_purge_session.py`
- `docs/reviews/phase15-s1-fix-codex-20260529.md`

No public command implementation, EventLog/Session deletion, audit JSONL writing, commit, push, or PR work is authorized in this fix gate.
