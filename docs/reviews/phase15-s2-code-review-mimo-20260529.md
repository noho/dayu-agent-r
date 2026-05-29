# Phase 15 S2 Code Review — Delete Matrix Transaction Helper

## Gate / Scope

- Gate: Phase 15 S2 code review.
- Review target: `dayu/host/durable/purge.py`, `tests/host/test_purge_session.py`, `docs/reviews/phase15-s2-implementation-codex-20260529.md`.
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`.
- Scope lens: S2 only — internal transaction-scoped delete matrix helper and tests. Must not wire public command, write audit JSONL, delete cold JSONL, or change public API.

## Reviewer

AgentMiMo (mimo-v2.5-pro).

## Verdict

**PASS with findings.** 7 findings: 0 BLOCK, 2 LOW, 5 INFO. No blocking correctness issues. Implementation correctly delivers the S2 contract.

## Scope Boundary Compliance

| Constraint | Status |
|---|---|
| No public command wiring | PASS — `purge_session_durable` is internal; no `command.py`/`open_host.py` changes |
| No audit JSONL append | PASS — `audit_record_ref`/`audit_record_digest` accepted as `None` in S2 |
| No cold JSONL deletion | PASS — only SQLite payload rows and descriptors deleted; file IO deferred to cleanup refs |
| No public API shape change | PASS — no `api.py` changes; `PurgeSessionDeleteRequest`/`Result` are internal |
| FK-safe delete order | PASS — see detailed analysis below |
| Tombstone/idempotency preservation | PASS — tombstone and purge idempotency row written after matrix deletion; NULL EventLog refs preserved |
| Payload ref-count cleanup | PASS — `_delete_unreferenced_payload_descriptors` checks all 8 reference columns before deletion |
| Projection checkpoint reset | PASS — exact `DELETE ... WHERE checkpoint_event_id IN target_event_ids` |
| Other Session preservation | PASS — test asserts other Session row and shared payload descriptor survive |

## FK-Safe Delete Order Analysis

Implementation order in `_delete_session_matrix` (purge.py:1318-1445):

1. `host_audit_sink_markers` by event_ids
2. `host_outbox_drain_idempotency` by session_id
3. `host_outbox_terminal_items` by session_id
4. `host_tool_trace_hot` by session_id
5. `host_memory_diagnostics` by session_id
6. `host_memory_items` by session_id
7. `host_memory_snapshots` by session_id
8. `host_run_results` by session_id
9. `host_session_timeline_items` by session_id
10. `host_projection_checkpoints` by event_ids
11. `host_projection_failures` by event_ids
12. `idempotency_records` (old command rows)
13. `host_wait_records` by session_id
14. `host_attempt_dispatch_records` by run_ids
15. `host_attempts` by run_ids
16. `host_runs` child-before-parent via `_delete_runs_child_before_parent`
17. `host_session_slots` by session_id
18. `host_sessions` by PK
19. `event_log` by session_id
20. Unreferenced `payload_descriptors`
21. Unreferenced `host_sqlite_payloads`

**Assessment:** Correct. All FK-dependent tables are deleted before their FK targets. Memory items before snapshots (cascade-safe). Runs use iterative child-before-parent deletion. Payload descriptors deleted after all referencing EventLog/projection rows. SQLite payloads deleted after descriptors. No FK violation risk under `PRAGMA foreign_keys=ON`.

## Findings

### FINDING-1: Redundant `_read_target_run_ids` calls in precondition digest builder

- **File:** `dayu/host/durable/purge.py:1247-1254`
- **Severity:** LOW
- **Category:** Correctness risk / maintainability

`_build_purge_precondition_digest` calls `_read_target_run_ids(transaction, session_id)` three times:

1. Line 1248: `_read_target_run_ids(transaction, session_id)` — result discarded
2. Line 1252: `_read_target_run_ids(transaction, session_id)` — passed to `_in_clause`
3. Line 1254: `_read_target_run_ids(transaction, session_id)` — conditional check

Within a single SQLite transaction the snapshot is consistent, so no data inconsistency occurs. However, this is wasteful (3 identical queries) and fragile — if the function signature or query changes, the three call sites may diverge.

**Recommendation:** Cache the result in a local variable at the top of the function and reuse it.

### FINDING-2: Missing PEP 8 blank lines between adjacent definitions

- **File:** `dayu/host/durable/purge.py:1631-1632`, `tests/host/test_purge_session.py:2115-2116`
- **Severity:** INFO
- **Category:** Style

Two locations have no blank line between adjacent top-level function/class definitions:

- `purge.py`: `_counts_with_payload_cleanup` ends at line 1631, `_decision_for_existing_tombstone` starts at line 1632.
- `test_purge_session.py`: `_insert_other_session_with_shared_payload` ends at line 2115, `test_insert_tombstone_rejects_unpaired_audit_record_ref` starts at line 2116.

**Recommendation:** Add blank lines per PEP 8.

### FINDING-3: Non-terminal run test uses minimal single-run fixture, not full matrix

- **File:** `tests/host/test_purge_session.py:2241-2253`
- **Severity:** LOW
- **Category:** Test adequacy

The parametrized `test_purge_session_durable_rejects_non_terminal_runs` uses `_SeedClosedSessionMatrixOperation(run_status=non_terminal)`. When `run_status != "succeeded"`, the seed operation inserts only a single parent run (line 437-449) and returns early — no child run, no attempts, no projections, no dispatch records.

This means the test never validates the scenario where a closed Session has a terminal parent run AND a non-terminal child run. While `_enforce_no_non_terminal_runs` iterates all runs (so single-run coverage proves the check works), the test does not exercise the full matrix state that would occur in production.

**Recommendation:** Consider adding a targeted test with a terminal parent + non-terminal child run to prove the full matrix is checked.

### FINDING-4: No test for closed Session with zero runs

- **File:** `tests/host/test_purge_session.py`
- **Severity:** INFO
- **Category:** Test adequacy

The plan's precondition section requires "All Run rows must be terminal." A closed Session with zero Run rows is an edge case — the implementation would raise `HostDurableError("purge target Session has no EventLog facts")` since a closed Session must have at least created/closed events. This path is not explicitly tested.

**Recommendation:** Low priority. The "no EventLog facts" guard is unreachable for a valid closed Session (which always has ≥2 events). Consider adding if completeness is desired.

### FINDING-5: Non-terminal run rejection test does not assert tombstone absence

- **File:** `tests/host/test_purge_session.py:2241-2253`
- **Severity:** INFO
- **Category:** Test adequacy

The test asserts `PurgeSessionInvalidStateError` is raised but does not verify that no tombstone was written as a side effect. By contrast, `test_purge_session_durable_rejects_open_session` (line 2226-2238) explicitly reads the tombstone after the error and asserts it is `None`.

The implementation correctly rolls back the transaction on error, so no tombstone is written. But the test does not prove this invariant for the non-terminal run case.

**Recommendation:** Add tombstone absence assertion consistent with the open-session test pattern.

### FINDING-6: `_delete_old_idempotency_records` scope broader than plan literal

- **File:** `dayu/host/durable/purge.py:1690-1718`
- **Severity:** INFO
- **Category:** Design alignment

The plan says: "delete old command idempotency rows whose `created_event_id`/`created_event_sequence` points to target EventLog rows, plus target Session command idempotency rows scoped to deleted Session facts."

The implementation deletes ALL idempotency records matching `(scope_id = session_id AND scope_kind IN _SESSION_FACT_SCOPE_KINDS)`, regardless of whether the record's `created_event_id`/`created_event_sequence` points to a target EventLog row. This is broader than the plan literal but narrower than a blind session_id delete (it filters by `_SESSION_FACT_SCOPE_KINDS`).

The current behavior is correct: all scope kinds in `_SESSION_FACT_SCOPE_KINDS` are Session/Run command scopes whose records should be purged with the Session. No non-command idempotency records are affected.

**Recommendation:** No change needed. The `_SESSION_FACT_SCOPE_KINDS` filter provides the necessary guard.

### FINDING-7: Test does not verify idempotency records outside `_SESSION_FACT_SCOPE_KINDS` are preserved

- **File:** `tests/host/test_purge_session.py:2134-2224`
- **Severity:** INFO
- **Category:** Test adequacy

The main purge test (`test_purge_session_durable_deletes_matrix_and_preserves_replay`) seeds two old idempotency rows: `close_session` and `cancel_run`. Both are in `_SESSION_FACT_SCOPE_KINDS` and both are deleted (count=2). The test does not seed an idempotency record with a scope kind outside `_SESSION_FACT_SCOPE_KINDS` to prove it is preserved.

**Recommendation:** Low priority. The `_SESSION_FACT_SCOPE_KINDS` filter is an internal implementation detail. Adding a preservation test would increase confidence but is not release-blocking.

## Detailed Code Correctness Checks

### Precondition enforcement (purge.py:709-714)

```python
session_row = _read_session_row(transaction, request.session_id)
if session_row is None:
    raise PurgeSessionNotFoundError("purge target Session not found")
_enforce_session_closed(session_row)
_enforce_no_non_terminal_runs(transaction, request.session_id)
_enforce_no_active_waits(transaction, request.session_id)
```

**PASS.** Uses Session/Run/wait governance truth only. No projection/audit/outbox/memory used as precondition.

### Tombstone/idempotency after deletion (purge.py:761-770)

Tombstone and idempotency row are inserted AFTER matrix deletion, within the same transaction. The purge idempotency row uses `created_event_id=None`, `created_event_sequence=None`, so it does not FK to deleted EventLog rows.

**PASS.** Survives Session/EventLog deletion.

### Payload ref-count correctness (purge.py:1448-1510)

`_delete_unreferenced_payload_descriptors` checks all 8 reference columns (EventLog, timeline, run results result_ref/summary_ref, memory items, tool trace hot, outbox result_ref/terminal_summary_ref) before deleting a descriptor. `_delete_unreferenced_sqlite_payloads` checks remaining descriptors before deleting SQLite payload rows.

**PASS.** No path-prefix guessing. Pure ref-count based.

### Run source dependency deletion (purge.py:1792-1823)

`_delete_runs_child_before_parent` uses iterative leaf deletion: delete runs whose `run_id` is not referenced as `source_run_id` by any other run in the same session, repeat until no runs remain. Raises `HostDurableError` if progress stalls.

**PASS.** Correctly handles retry/replay chains. Test covers parent-child chain (lines 2134-2224).

### Projection checkpoint/failure reset (purge.py:1385-1396)

```python
projection_checkpoints = _delete_by_event_ids(
    transaction, TABLE_HOST_PROJECTION_CHECKPOINTS, "checkpoint_event_id", event_ids,
)
projection_failures = _delete_by_event_ids(
    transaction, TABLE_HOST_PROJECTION_FAILURES, "failed_event_id", event_ids,
)
```

**PASS.** Exact reset by target EventLog IDs, not global consumer checkpoint wipe.

### Idempotency replay after purge (purge.py:699-707)

`purge_session_durable` calls `record_or_read_purge_idempotency` first. If tombstone exists with matching key/digest, returns replay result without reading deleted Session facts.

**PASS.** Test at line 2134-2224 proves second call returns `idempotent_replay=True` with same tombstone.

### Typing and docstrings

All new public functions and dataclasses have complete Chinese docstrings with `:param`, `:returns`, `:raises` sections. No `object`, `Any`, or untyped parameters/signatures found. `PurgeSessionDeleteRequest`, `PurgeSessionDeleteResult`, `PurgeCommitCleanupRefs` all use strict typing.

**PASS.**

## Test Adequacy Summary

| Test case | Status |
|---|---|
| Insert/read tombstone round trip | PASS |
| Tombstone replay with NULL EventLog refs | PASS |
| Same key + different digest conflicts | PASS |
| Different key after purge conflicts | PASS |
| No tombstone + same key different digest conflicts | PASS |
| Tombstone + conflicting idempotency = inconsistency | PASS |
| Negative counts rejected | PASS |
| Mismatched counts digest rejected | PASS |
| Unpaired audit_record_ref rejected | PASS |
| Full delete matrix + idempotent replay | PASS |
| Open session rejected | PASS (with tombstone absence assertion) |
| Non-terminal runs rejected | PASS (parametrized 6 statuses; no tombstone assertion) |
| Active wait rejected | PASS |
| Missing session without tombstone = not found | PASS |
| Other session + shared payload preserved | PASS |
| Retry/replay child-before-parent run chain | PASS |
| Old command idempotency deleted, purge idempotency preserved | PASS |
| Projection checkpoint/failure reset by event IDs | PASS |

**Coverage gap:** No test for closed Session with zero runs; non-terminal run test doesn't assert tombstone absence.

## Implementation Artifact Verification

The implementation artifact (`docs/reviews/phase15-s2-implementation-codex-20260529.md`) accurately describes the changes. Validation commands and results match. Residual risk classification is correct.

## Conclusion

S2 correctly implements the transaction-scoped delete matrix helper within the approved plan scope. FK-safe delete order is verified. Tombstone/idempotency survives fact deletion. Payload cleanup is ref-counted. No scope boundary violations. 7 non-blocking findings (2 LOW, 5 INFO) — all are maintainability/test-adequacy improvements, not correctness defects.
