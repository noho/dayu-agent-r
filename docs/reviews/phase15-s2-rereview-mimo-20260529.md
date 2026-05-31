# Phase 15 S2 Re-Review — Delete Matrix Transaction Helper (Fix Verification)

## Gate / Scope

- Gate: Phase 15 S2 re-review.
- Fix artifact: `docs/reviews/phase15-s2-fix-codex-20260529.md`.
- Controller adjudication: `docs/reviews/phase15-s2-code-review-controller-adjudication-20260529.md`.
- Original reviews: `docs/reviews/phase15-s2-code-review-mimo-20260529.md`, `docs/reviews/phase15-s2-code-review-ds-20260529.md`.
- Task: Verify accepted findings S2-ADJ-001 through S2-ADJ-005 only. Do not revisit rejected findings.

## Reviewer

AgentMiMo (mimo-v2.5-pro).

## Verdict

**PASS.** All 5 accepted findings verified as 已修复. 21 tests pass, pyright 0 errors, no new blockers.

## Per-Finding Final Status

### S2-ADJ-001 — 已修复

**Requirement:** Add explicit allowed consumer set for projection checkpoint/failure reset. Reject non-allowed consumers that reference target EventLog.

**Evidence:**

1. Allow-list defined at `purge.py:131-136`:
   ```python
   _PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS = (
       "host.minimal-read-model",
       "host.memory.session.v1",
       "host.audit-log-jsonl",
       "host.tool-trace",
       "host.outbox-terminal",
   )
   ```

2. Guard function `_raise_for_unsupported_projection_reset_refs` at `purge.py:1744-1778` queries for checkpoint/failure rows where `event_id IN target_ids AND consumer_id NOT IN allow_list`. Raises `HostDurableError` if any found.

3. Delete function `_delete_allowed_projection_reset_refs` at `purge.py:1781-1807` deletes only rows where `consumer_id IN allow_list`.

4. Delete matrix at `purge.py:1395-1418` calls guard BEFORE delete, ensuring rollback on unsupported consumer:
   ```python
   _raise_for_unsupported_projection_reset_refs(transaction, TABLE_HOST_PROJECTION_CHECKPOINTS, ...)
   _raise_for_unsupported_projection_reset_refs(transaction, TABLE_HOST_PROJECTION_FAILURES, ...)
   projection_checkpoints = _delete_allowed_projection_reset_refs(transaction, TABLE_HOST_PROJECTION_CHECKPOINTS, ...)
   projection_failures = _delete_allowed_projection_reset_refs(transaction, TABLE_HOST_PROJECTION_FAILURES, ...)
   ```

5. Two new tests:
   - `test_purge_session_durable_rejects_unsupported_projection_checkpoint_and_rolls_back` (line 2409): Seeds unsupported consumer checkpoint (`host.recovery-governance`), asserts `HostDurableError`, verifies tombstone is `None`, target EventLog rows preserved (count=12), unsupported checkpoint preserved (count=1).
   - `test_purge_session_durable_rejects_unsupported_projection_failure_and_rolls_back` (line 2447): Same pattern for projection failure.

**Assessment:** Correctly implements the plan's rebuildable-consumer criterion. Guard-then-delete ordering ensures atomicity. Tests prove both checkpoint and failure rejection paths with full rollback verification.

---

### S2-ADJ-002 — 已修复

**Requirement:** Cache `_read_target_run_ids(...)` result in `_build_purge_precondition_digest(...)`.

**Evidence:**

At `purge.py:1145`:
```python
run_ids = _read_target_run_ids(transaction, session_id)
```

The cached `run_ids` tuple is reused at:
- Line 1258: `WHERE {_in_clause("run_id", run_ids)}`
- Line 1261: `run_ids,` (parameter)
- Line 1263: `if run_ids` (conditional)

No remaining calls to `_read_target_run_ids` within this function.

**Assessment:** Single read, full reuse. Clean fix.

---

### S2-ADJ-003 — 已修复

**Requirement:** Add missing top-level blank lines.

**Evidence:**

1. `purge.py:1653-1656`: Two blank lines between `_counts_with_payload_cleanup` (ends line 1653) and `_decision_for_existing_tombstone` (starts line 1656).

2. `test_purge_session.py:2228-2231`: Two blank lines between `_insert_other_session_with_shared_payload` (ends line 2228) and `_event_sequence_for_id` (starts line 2231).

3. `test_purge_session.py:2250-2253`: Two blank lines between `_event_sequence_for_id` (ends line 2250) and `test_insert_tombstone_rejects_unpaired_audit_record_ref` (starts line 2253).

**Assessment:** PEP 8 compliant. Note: a new helper `_event_sequence_for_id` was added between the original two definitions, which is fine — the blank line requirement is satisfied.

---

### S2-ADJ-004 — 已修复

**Requirement:** Non-terminal Run rejection test should assert no tombstone is written.

**Evidence:**

At `test_purge_session.py:2389-2406`:
```python
@pytest.mark.parametrize("run_status", _NON_TERMINAL_RUN_STATUSES)
def test_purge_session_durable_rejects_non_terminal_runs(
    tmp_path: Path, run_status: str
) -> None:
    """purge helper 拒绝 active/queued/running/waiting/cancelling/recovering Run。"""

    tombstone: PurgeTombstoneRow | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        store.transaction_runner.run_write(
            _SeedClosedSessionMatrixOperation(run_status=run_status)
        )
        with pytest.raises(PurgeSessionInvalidStateError):
            store.transaction_runner.run_write(_PurgeMatrixOperation())
        tombstone = store.transaction_runner.run_read(
            _ReadTombstoneBySessionOperation()
        )

    assert tombstone is None
```

**Assessment:** Now consistent with `test_purge_session_durable_rejects_open_session` pattern. Proves atomic rejection — no tombstone left behind.

---

### S2-ADJ-005 — 已修复

**Requirement:** Seed idempotency record outside `_SESSION_FACT_SCOPE_KINDS` and assert purge preserves it.

**Evidence:**

1. Constants at `test_purge_session.py:89-90`:
   ```python
   _OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND = "external_projection_ack"
   _OUT_OF_SCOPE_IDEMPOTENCY_KEY = "external-ack-key"
   ```

2. Seed in `_SeedClosedSessionMatrixOperation` at `test_purge_session.py:2169-2183`:
   ```python
   IdempotencyStore().record_idempotent_result(
       transaction,
       IdempotencyScope(
           scope_kind=_OUT_OF_SCOPE_IDEMPOTENCY_SCOPE_KIND,
           scope_id=_SESSION_ID,
           idempotency_key=_OUT_OF_SCOPE_IDEMPOTENCY_KEY,
       ),
       _DIGEST_C,
       IdempotencyResultRef(
           result_kind="external_ack",
           result_ref="external-ack-1",
           created_event_id=None,
           created_event_sequence=None,
       ),
   )
   ```

3. Read helper `_ReadOutOfScopeIdempotencyOperation` at `test_purge_session.py:594-616` checks row existence.

4. Assertion in main purge test at `test_purge_session.py:2287-2289` and `2340`:
   ```python
   out_of_scope_idempotency_exists = store.transaction_runner.run_read(
       _ReadOutOfScopeIdempotencyOperation()
   )
   ...
   assert out_of_scope_idempotency_exists is True
   ```

**Assessment:** Scope kind `external_projection_ack` is not in `_SESSION_FACT_SCOPE_KINDS`. The test proves purge preserves this row while deleting `close_session` and `cancel_run` rows (idempotency_records count=2, not 3).

---

## Validation

- `pytest tests/host/test_purge_session.py -q`: **21 passed in 0.34s** (was 19 before fix; +2 unsupported projection tests).
- `python -m pyright dayu/host/durable/purge.py tests/host/test_purge_session.py`: **0 errors, 0 warnings, 0 informations**.

## New Blockers

None. The fix did not introduce any new correctness, typing, or scope boundary issues.

## Conclusion

All 5 accepted findings are verified as 已修复 with direct code and test evidence. Fix artifact claims are accurate. S2 is ready for closeout.
