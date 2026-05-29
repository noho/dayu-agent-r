# Phase 15 P15-S1 Re-Review

## Gate

- Work unit: Phase 15 retention purge production hardening
- Current gate: Phase 15 S1 re-review
- Controller adjudication: `docs/reviews/phase15-s1-code-review-controller-adjudication-20260529.md`
- Fix artifact: `docs/reviews/phase15-s1-fix-codex-20260529.md`
- Review date: 2026-05-29
- Reviewer: AgentMiMo

## Accepted Finding Verification

### S1-ADJ-001 — durable inconsistency misclassified as idempotency conflict

**Status: 已修复**

**Required**: `HostIdempotencyConflictError` in `_decision_for_existing_tombstone` must map to `DURABLE_INCONSISTENCY`, not `IDEMPOTENCY_CONFLICT`. Focused test required.

**Code evidence**: `purge.py:546-552` — `except HostIdempotencyConflictError` now returns `PurgeReplayDecisionKind.DURABLE_INCONSISTENCY` with `_DECISION_MESSAGE_DURABLE_INCONSISTENCY`. Previous `IDEMPOTENCY_CONFLICT` mapping is gone.

```python
# purge.py:546-552
except HostIdempotencyConflictError:
    return PurgeReplayDecision(
        kind=PurgeReplayDecisionKind.DURABLE_INCONSISTENCY,
        tombstone=tombstone,
        idempotency_record=None,
        message=_DECISION_MESSAGE_DURABLE_INCONSISTENCY,
    )
```

**Test evidence**: `test_purge_session.py:455-475` — `test_tombstone_same_key_same_digest_with_conflicting_idempotency_is_inconsistent` constructs a tombstone + conflicting idempotency row (same scope/key, different digest) via `_SeedTombstoneWithConflictingIdempotencyOperation`, calls `record_or_read_purge_idempotency`, and asserts `decision.kind is PurgeReplayDecisionKind.DURABLE_INCONSISTENCY`. The helper at lines 280-311 inserts a tombstone with digest_A then writes an idempotency row with digest_B for the same scope/key — the exact conflict scenario.

### S1-ADJ-002 — missing rejection-path tests for tombstone validation

**Status: 已修复**

**Required**: Tests for negative `PurgeDeleteCounts`, mismatched `deleted_counts_digest`, and unpaired `audit_record_ref`/`audit_record_digest`.

**Test evidence**:

1. `test_purge_session.py:478-482` — `test_deleted_counts_digest_rejects_negative_counts`: uses `replace(_counts(), event_log_rows=-1)` and asserts `HostDurableError` from `build_deleted_counts_digest`.

2. `test_purge_session.py:485-495` — `test_insert_tombstone_rejects_mismatched_deleted_counts_digest`: uses `replace(_tombstone(), deleted_counts_digest=_DIGEST_A)` to break digest consistency, asserts `HostDurableError` from `insert_purge_tombstone`.

3. `test_purge_session.py:498-513` — `test_insert_tombstone_rejects_unpaired_audit_record_ref`: tests both `audit_record_ref`-only and `audit_record_digest`-only variants via `replace()`, asserts `HostDurableError` for each.

All three tests use `_InsertMalformedTombstoneOperation` (lines 314-334) which delegates to `insert_purge_tombstone`, exercising the full validation path including `_validate_tombstone` and `_validate_delete_counts`.

## Validation

```bash
pytest tests/host/test_durable_schema.py tests/host/test_purge_session.py -q
# 30 passed in 0.39s (was 26 before fix; 4 new tests)

python -m pyright dayu/host/durable/purge.py tests/host/test_purge_session.py
# 0 errors, 0 warnings, 0 informations
```

Test count increased from 26 to 30. Pyright remains clean. No new imports introduced beyond `replace` (stdlib), `pytest`, and `HostDurableError` (existing).

## New Blocker Check

No new blockers. Fix changes are minimal and scoped: one `except` branch remapped in production code, four focused tests added.

## Result

**PASS** — Both accepted findings verified fixed. Validation adequate. No new blockers.
