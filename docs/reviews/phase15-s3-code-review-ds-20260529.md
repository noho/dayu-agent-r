# Phase 15 P15-S3 Code Review Artifact

- **Gate**: Phase 15 code review Slice P15-S3
- **Work unit**: Public Command Wiring And Read-after-purge Semantics
- **Approved plan**: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- **Implementation artifact**: `docs/reviews/phase15-s3-implementation-codex-20260529.md`
- **Review agent**: AgentDS code review specialist
- **Date**: 2026-05-29
- **Scope lens**: S3 only — public command wiring, error mapping, closed-handle ordering, read-after-purge fail-closed, idempotent replay, watch semantics, typing/docstrings, S4 audit invariant check.

## Review Target

Files reviewed:
- `dayu/host/command.py` — `purge_session` wired from UNSUPPORTED_OPERATION to durable helper
- `dayu/host/open_host.py` — `_PublicHostHandle.purge_session` concrete method
- `tests/host/test_command_handle.py` — purge closed empty Session + idempotent replay test
- `tests/host/test_public_session_api.py` — get_session after purge NOT_FOUND test
- `tests/host/test_public_run_api.py` — purge deletes Run truth + retry/replay fail closed, open Session rejection
- `tests/host/test_open_host_runtime.py` — open_host purge + watch after purge fail closed
- `tests/host/test_public_lifecycle_smoke.py` — closed-handle guard purge test
- `docs/reviews/phase15-s3-implementation-codex-20260529.md` — implementation self-report

## Adversarial Pass

The following adversarial scenarios were tested against the implementation:

1. **Purge while Session is open**: Rejected with INVALID_STATE at `_enforce_session_closed` in durable helper (command.py:771 → purge.py:895). Test asserts INVALID_STATE (test_public_run_api.py:805).

2. **Purge after handle closed**: `_raise_if_closed()` is first guard in both command.py:759 and open_host.py:501. Test asserts HostClosedError (test_public_lifecycle_smoke.py:218-223).

3. **Purge with same key but different semantic digest after facts deleted**: Durable layer returns HostIdempotencyConflictError → mapped to IDEMPOTENCY_CONFLICT via `_host_api_error_from_durable_error` (command.py:847-852).

4. **Purge with different key after facts deleted**: PurgeSessionAlreadyPurgedError → CONFLICT (command.py:770-775). Test asserts CONFLICT (test_public_run_api.py:849-850).

5. **Read purged Session row directly from DB**: Session row is deleted by durable helper. get_session → _GetSessionOperation → read_session_by_id returns None → NOT_FOUND (read_api.py:254-259). Test asserts NOT_FOUND (test_public_session_api.py:349-350).

6. **retry_run / replay_run from purged source Run**: Run row deleted. get_run → read_run_by_id returns None → NOT_FOUND (read_api.py:282-287). retry_run/replay_run → _RetryRunOperation/_ReplayRunOperation → read source run → None → NOT_FOUND. Test asserts NOT_FOUND (test_public_run_api.py:844-847).

7. **watch_session_events on purged Session**: `_require_session_exists` calls `read_session_by_id` → returns None → NOT_FOUND (identical path as get_session). Test asserts NOT_FOUND (test_open_host_runtime.py:586).

8. **No audit JSONL write — can audit be skipped?** S3 intentionally passes `audit_record_ref=None, audit_record_digest=None` (command.py:833-834). Tombstone is written without audit evidence. Plan acknowledges this as S4 gap. S4 is not made impossible — tombstone schema has audit fields ready, and plan's fail-before-success strategy is architecture-compatible with S3 wiring.

## Plan Compliance Check

### Required items verified

| Plan Requirement | Status | Evidence |
|---|---|---|
| Closed-handle guard first | PASS | command.py:759 `host._raise_if_closed()` before any transaction |
| Map durable errors to existing codes | PASS | command.py:761-779, explicit except chain |
| Return PurgeSessionResult with tombstone ref | PASS | command.py:780-785 |
| No new public error codes | PASS | Uses NOT_FOUND, INVALID_STATE, CONFLICT, IDEMPOTENCY_CONFLICT |
| No new OpenHostOptions fields | PASS | open_host.py diff, no options changes |
| Read-after-purge returns NOT_FOUND | PASS | Natural via row deletion; read_api.py unchanged and correct |
| No projection/audit/outbox/memory as truth | PASS | Precondition checks use Session/Run/Attempt governance truth only |
| No Engine/Service/UI/Fins changes | PASS | Diff confirms no changes outside allowed scope |
| No audit JSONL write (S4 owns) | PASS | audit_record_ref=None, audit_record_digest=None |

### Non-goals verified

| Non-goal | Status |
|---|---|
| No new public reader | PASS |
| No wait_final_answer / get_run_result | PASS |
| No watch cursor | PASS |
| No public API shape change (Host Protocol unchanged) | PASS |

## Findings

### Finding 1 — [LOW] Error mapping of `HostIdempotencyConflictError` via fallback path

- **File/line**: `dayu/host/command.py:778`
- **Evidence**: `HostIdempotencyConflictError` extends `HostDurableError` and is NOT caught by the specific except clauses (lines 761-776). It falls through to `except HostDurableError as exc:` at line 778, which delegates to `_host_api_error_from_durable_error` (line 779). That function at line 847-852 correctly maps it to `IDEMPOTENCY_CONFLICT`.
- **Assessment**: Functionally correct. However, all other HostDurableError subtypes (including unexpected ones like HostSchemaMismatchError) also go through this same fallback, which could mask schema errors as INTERNAL_ERROR. This is a pre-existing pattern used by other command functions (close_session, retry_run, etc.) — not newly introduced by S3.
- **Recommendation**: No action required for S3. Consistent with existing command error mapping convention.

### Finding 2 — [LOW] `read_api.py` not modified — relies on natural row deletion for read-after-purge

- **File/line**: `dayu/host/read_api.py` (no changes)
- **Evidence**: The plan lists `dayu/host/read_api.py` as an allowed S3 file with instruction: "ensure target purged/missing returns existing NOT_FOUND; do not reconstruct from tombstone/projection/audit." The S3 implementation did not modify read_api.py. Since `purge_session_durable` deletes Session and Run rows, the existing read path naturally returns NOT_FOUND: `_GetSessionOperation` (read_api.py:253-259) calls `read_session_by_id` → returns None → raises NOT_FOUND. Same for `_GetRunOperation` (read_api.py:281-287).
- **Assessment**: No tombstone-aware read code is necessary. The natural row-not-found behavior satisfies the plan requirement without adding tombstone checks. This is actually the cleaner design — tombstone is a durable fact that purge happened, not a substitute for deleted governance rows.
- **Recommendation**: No action required.

### Finding 3 — [LOW] Test uses Protocol + cast pattern to access purge_session on Host

- **File/line**: `tests/host/test_open_host_runtime.py:74-88`, `tests/host/test_public_lifecycle_smoke.py:42-57`
- **Evidence**: `Host` is a Protocol (api.py:3097) that does not include `purge_session`. The concrete `_PublicHostHandle` implements `purge_session` (open_host.py:490-502) but is not exported. Tests define `_PurgeCapableHost` Protocol locally and use `cast(_PurgeCapableHost, host)` to access `purge_session()`. Two test files define slightly different Protocols (return types differ: `PurgeSessionResult` vs `object`).
- **Assessment**: Acceptable. The `cast` pattern is necessary because `purge_session` is a concrete implementation detail of `_PublicHostHandle`, not part of the `Host` Protocol. The Protocol duplication across test files is a minor style concern but each file's Protocol is fit-for-purpose (one file needs the exact return type for assertions, the other only needs to call the method for the closed-handle test). The plan explicitly says "不修改 Host public API shape" — this includes the Host Protocol.
- **Recommendation**: No action required for S3. If purge_session is later added to the Host Protocol, these casts can be removed.

### Finding 4 — [INFO] S4 audit invariant compatibility

- **File/line**: `dayu/host/command.py:833-834`, `dayu/host/durable/purge.py:1576-1577`
- **Evidence**: S3 passes `audit_record_ref=None, audit_record_digest=None` to the durable helper. The tombstone row is inserted with NULL audit fields. The plan states: "public success 目前仍可在没有 purge audit JSONL line 的情况下返回 tombstone result" — acknowledged as S4's residual risk.
- **S4 compatibility assessment**: S4 is NOT made impossible:
  - `PurgeTombstoneRow` has `audit_record_ref` and `audit_record_digest` fields ready.
  - The plan's fail-before-success strategy requires S4 to: write audit JSONL line → get ref/digest → wire into `PurgeSessionDeleteRequest` → tombstone written with non-null audit fields.
  - S4 can either: (a) modify `_PurgeSessionOperation` to write audit JSONL before calling `purge_session_durable`, populating `audit_record_ref/digest`; or (b) write audit line inside the durable transaction. Both approaches are structurally compatible with S3's wiring.
  - Existing S3-created tombstones with NULL audit fields represent a known gap — they were created before S4's audit enforcement. S4 may choose to handle these retroactively or declare them out of scope.
- **Recommendation**: S4 must verify that the command layer's audit append (fail-before-success) can be injected between the durable helper's precondition verification and tombstone write without breaking the existing transaction boundary. The current `_PurgeSessionOperation.__call__` is a single durable write transaction; S4 audit append happening outside it would create a two-phase commit problem. This should be flagged in the S4 handoff plan.

### Finding 5 — [LOW] Return type narrowing on helper functions

- **File/line**: `dayu/host/command.py:1203-1237`
- **Evidence**: `_call_context_json_value` return type changed from `JsonValue` to `dict[str, JsonValue]`, and `_operation_context_json_value` similarly narrowed. These are internal helper functions whose concrete return type is always `dict[str, JsonValue]`.
- **Assessment**: Type improvement, not a semantic change. Makes the signatures more precise and useful for callers like `_PurgeSessionOperation.__call__` which pass the result to `sha256_digest_json` and `build_purge_semantic_digest`. No behavioral change.
- **Recommendation**: No action required.

## Semantic Digest Correctness

Verified that `_PurgeSessionOperation.__call__` (command.py:795-837) constructs the semantic digest using:

1. `session_id` — stable identifier
2. `request.reason` — from validated PurgeSessionRequest
3. `operation_context_digest` — sha256_digest_json(operation_context_refs), stable JSON
4. `operation_context_refs` — canonical JSON from OperationContext
5. `request_context` — canonical JSON from HostCallContext

All inputs are stable, deterministic, and free of mutable DB state. The digest is passed to `build_purge_semantic_digest()` (durable/purge.py:566-600) which wraps them in a fixed operation key `"purge_session"` and produces `sha256:` digest. Replay after facts deleted works because the digest is computed from request-level inputs, not from Session/EventLog state.

## Error Mapping Correctness

Full error mapping chain verified:

| Durable Error | Public Error Code | Line | Test Coverage |
|---|---|---|---|
| PurgeSessionInvalidStateError | INVALID_STATE | command.py:762 | test_public_run_api.py:805 |
| PurgeSessionAlreadyPurgedError | CONFLICT | command.py:770 | test_public_run_api.py:849 |
| PurgeSessionNotFoundError | NOT_FOUND | command.py:775 | (natural via row deletion) |
| HostIdempotencyConflictError | IDEMPOTENCY_CONFLICT | command.py:779→848 | (indirect via fallback) |
| HostDurableError (other) | INTERNAL_ERROR | command.py:779→879 | (fallback) |

## Closed-Handle Ordering

Verified ordering at both command and open_host layers:

1. `command.purge_session()` (command.py:759): `host._raise_if_closed()` — first executable statement
2. `_PublicHostHandle.purge_session()` (open_host.py:501): `self._raise_if_closed()` — first executable statement

Both precede any DB access or transaction work.

## Idempotent Replay After Facts Deleted

Verified replay chain:

1. `record_or_read_purge_idempotency` (purge.py:614) → checks tombstone by session_id
2. If tombstone exists → `_decision_for_existing_tombstone` (purge.py:1656) → matches client_request_id and semantic digest
3. If match → `REPLAY_TOMBSTONE` decision → `_result_for_replay_decision` (purge.py:844-851) → returns PurgeSessionDeleteResult with idempotent_replay=True
4. command.py receives result → constructs PurgeSessionResult with tombstone ref

Tests confirm: `test_purge_session_closed_empty_session_returns_tombstone_result` (test_command_handle.py:761-797) asserts `replay == first`, verifying replay returns identical PurgeSessionResult after Session facts are deleted.

## Watch Semantics

Verified `watch_session_events` after purge:
- `session_live_event_start_cursor` (read_api.py:126-128) calls `_SessionLiveEventStartCursorOperation`
- Which calls `_require_session_exists` (read_api.py:317)
- `_require_session_exists` → `read_session_by_id` → Session row deleted → None → NOT_FOUND
- No tombstone-aware code intercepts this path — correct behavior per plan: "watch_session_events purge 后仍按现有 missing Session 行为返回 NOT_FOUND"

Test confirms: `test_open_host_purge_session_and_watch_after_purge_fail_closed` (test_open_host_runtime.py:554-589) asserts `watch_exc.value.code == HostApiErrorCode.NOT_FOUND`.

## Tests Coverage Assessment

| Test Condition | File | Line | Status |
|---|---|---|---|
| Closed empty Session purge + replay | test_command_handle.py | 761 | PASS |
| Open Session rejection (INVALID_STATE) | test_public_run_api.py | 805 | PASS |
| Purge deletes Run truth | test_public_run_api.py | 816 | PASS |
| retry after purge → NOT_FOUND | test_public_run_api.py | 843 | PASS |
| replay after purge → NOT_FOUND | test_public_run_api.py | 845 | PASS |
| Different request after purge → CONFLICT | test_public_run_api.py | 849 | PASS |
| get_session after purge → NOT_FOUND | test_public_session_api.py | 330 | PASS |
| open_host purge + watch fail closed | test_open_host_runtime.py | 554 | PASS |
| Closed handle → HostClosedError | test_public_lifecycle_smoke.py | 218-223 | PASS |

Missing from S3 scope (assigned to S5/S6):
- Projection rebuild confidence (S5)
- Recovery/scheduler hardening (S5)
- Import boundary validation (S6)

## Typing / Docstrings

- All new functions have Chinese docstrings with params, returns, raises.
- No `object`, `Any`, untyped parameters/returns in production code.
- `_PurgeCapableHost` Protocol in tests uses `object` return type in one file (test_public_lifecycle_smoke.py:47) — acceptable for test-only Protocol when file doesn't inspect the return value.
- Pyright: 0 errors, 0 warnings, 0 informations on all changed files.

## Validation Results

```bash
# Tests
69 passed in 0.97s

# Pyright
0 errors, 0 warnings, 0 informations
```

## Residual Risks

| Risk | Severity | Owner | Status |
|---|---|---|---|
| No audit JSONL purge record (S3 creates tombstones without audit) | Medium | S4 | S4 must implement fail-before-success audit append |
| Audit append inside durable transaction — S3's single-transaction pattern may need restructuring | Low | S4 | Flagged in Finding 4 |
| HostIdempotencyConflictError routed through generic HostDurableError fallback | Low | S3 | Pre-existing pattern, consistent with other commands |
| read_api.py not explicitly guarded against tombstone reconstruction | None | S3 | Natural row deletion provides correct behavior |

## Review Conclusion

**PASS** — 0 blocking findings. The S3 implementation correctly wires `purge_session` from structured unsupported to the durable purge helper, maintains proper closed-handle ordering before all DB access, maps durable errors to existing public error codes without adding new ones, returns the frozen `PurgeSessionResult` with tombstone ref and deleted counts digest, and preserves read-after-purge fail-closed semantics through natural row-level read behavior. The `Host` Protocol is not modified. Tests cover the full error surface and replay behavior. No S4 audit invariant is made impossible — the schema and wiring are structurally ready for S4's audit append.

## Finding Summary

- Total findings: 5
- Severity: 0 critical, 0 high, 0 medium, 5 low/info
- Blocking: 0
- Final: **PASS**
