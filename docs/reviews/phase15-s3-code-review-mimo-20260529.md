# Phase 15 P15-S3 Code Review Artifact

- **Gate**: Phase 15 S3 code review
- **Reviewer**: AgentMiMo code review specialist
- **Date**: 2026-05-29
- **Approved plan**: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- **Implementation artifact**: `docs/reviews/phase15-s3-implementation-codex-20260529.md`

## Scope Verification

S3 scope per plan: wire `purge_session` public command to durable helper, ensure read-after-purge fail closed.

| Constraint | Status | Evidence |
|---|---|---|
| No new public error code/reader | PASS | Only existing `HostApiErrorCode` used |
| No audit JSONL write | PASS | `audit_record_ref=None`, `audit_record_digest=None` in `_PurgeSessionOperation.__call__:832-833` |
| No Engine/Service/UI/Fins change | PASS | Only `dayu/host/command.py`, `dayu/host/open_host.py`, test files changed |
| No new `OpenHostOptions` field | PASS | `_PublicHostHandle.purge_session` signature unchanged |
| No public API shape change | PASS | `PurgeSessionRequest` / `PurgeSessionResult` fields unchanged |
| S4 audit invariant not blocked | PASS | `None` audit fields are replay-consistent; S4 can later populate without tombstone mutation |

## Findings

### F01 — PASS: Error mapping chain

`command.py:759-785` — `host._raise_if_closed()` precedes all DB access. Exception chain maps:
- `PurgeSessionInvalidStateError` → `INVALID_STATE` (line 766-771)
- `PurgeSessionAlreadyPurgedError` → `CONFLICT` (line 772-777)
- `PurgeSessionNotFoundError` → `NOT_FOUND` (line 778-783)
- `HostDurableError` → `_host_api_error_from_durable_error` (line 784-785), which handles `HostIdempotencyConflictError` → `IDEMPOTENCY_CONFLICT` (line 847-850)

`HostIdempotencyConflictError` inherits `HostDurableError` (`durable/errors.py:77`), caught by the generic handler. Mapping is correct per plan §Error handling.

### F02 — PASS: Semantic digest construction

`command.py:809-820` — `_PurgeSessionOperation.__call__` constructs digest from:
- `session_id` (from path)
- `request.reason`
- `operation_context_digest` (sha256 of `operation_context_refs`)
- `operation_context_refs` (`dict[str, JsonValue]` from `_operation_context_json_value`)
- `request_context` (`dict[str, JsonValue]` from `_call_context_json_value`)

`build_purge_semantic_digest` (`purge.py:566`) accepts `Mapping[str, JsonValue]` — type-compatible with `dict[str, JsonValue]`. Digest input excludes mutable DB state and timestamps — replay-safe per plan §Idempotency Design.

### F03 — PASS: Return type refinement

`command.py:1201,1235` — `_call_context_json_value` and `_operation_context_json_value` return type narrowed from `JsonValue` to `dict[str, JsonValue]`. This is a valid subtype refinement: `dict[str, JsonValue]` satisfies `JsonValue` (JSON object) and `Mapping[str, JsonValue]`. No callers break; pyright confirms 0 errors.

### F04 — PASS: OpenHost wiring

`open_host.py:490-502` — `_PublicHostHandle.purge_session`:
1. `self._raise_if_closed()` — closed-handle gate before any DB access
2. Delegates to `_purge_session(self._command_handle, session_id, request)` — command facade call
3. No new options, no new fields

Pattern matches existing `close_session` wiring at line 476-488.

### F05 — PASS: Idempotent replay after facts deleted

`test_command_handle.py:758-795` — `test_purge_session_closed_empty_session_returns_tombstone_result`:
- Creates session, closes, purges → `first.purged is True`, `first.purge_tombstone_ref is not None`
- Same `(session_id, client_request_id)` replay → `replay == first` (frozen dataclass equality)

`test_public_run_api.py:817-855` — `test_purge_session_deletes_run_truth_and_retry_replay_fail_not_found`:
- Creates session with run, cancels run, closes session, purges → tombstone result
- Same request replay → `replay == first`
- Different `client_request_id` → `CONFLICT`

Tombstone survives EventLog/Session deletion; replay does not read deleted facts.

### F06 — PASS: Read-after-purge fail closed

| Read path | Test file | Assertion |
|---|---|---|
| `get_session` | `test_public_session_api.py:332-354` | `NOT_FOUND`, `retryable=False` |
| `get_session` (open host) | `test_open_host_runtime.py:578-579` | `NOT_FOUND` |
| `get_run` | `test_public_run_api.py:840-841` | `NOT_FOUND`, `retryable=False` |
| `retry_run` | `test_public_run_api.py:842-843` | `NOT_FOUND`, `retryable=False` |
| `replay_run` | `test_public_run_api.py:844-845` | `NOT_FOUND`, `retryable=False` |
| `watch_session_events` | `test_open_host_runtime.py:580-581` | `NOT_FOUND` |

No read path reconstructs from tombstone/projection/audit/outbox/memory.

### F07 — PASS: Closed-handle guard

`test_public_lifecycle_smoke.py:219-223` — After `host.close()`, `purge_session` raises `HostClosedError`. No DB access occurs.

### F08 — PASS: Open session precondition

`test_public_run_api.py:798-805` — `purge_session` on open (non-closed) session raises `INVALID_STATE`, `retryable=False`. Event count and idempotency count unchanged — no side effects.

### F09 — PASS: Already-purged different request conflict

`test_public_run_api.py:846-853` — After purge with `"purge-1"`, purge with `"purge-2"` raises `CONFLICT`, `retryable=False`. No second tombstone created.

### F10 — PASS: Typing and docstrings

- All modified functions have Chinese docstrings with `:param`, `:returns`, `:raises`.
- `_PurgeSessionOperation` is `@dataclass(frozen=True, slots=True)`.
- No `object`, `Any`, or untyped parameters in new code.
- `_call_context_json_value` and `_operation_context_json_value` return type narrowed from `JsonValue` to `dict[str, JsonValue]` — valid subtype.

### F11 — PASS: S4 audit invariant preserved

`_PurgeSessionOperation.__call__:832-833` sets `audit_record_ref=None` and `audit_record_digest=None`. The `PurgeTombstoneRow` fields are `NULL`-safe (`purge.py:327-328` docstring). S4 can populate these without mutating the tombstone row — the plan's fail-before-success audit strategy is not blocked.

Idempotent replay with `None` audit fields: same `client_request_id` + same semantic digest → same result. S4 adding audit ref would change the semantic digest only if the digest includes audit fields, which it does not (digest is constructed before audit append per plan §Tombstone Design). Replay consistency is preserved.

## Scope Violations

None.

## Verdict

**PASS** — 0 findings, 0 scope violations.

P15-S3 implementation correctly wires `purge_session` from public command to S2 durable helper, maps errors to existing `HostApiErrorCode`, preserves closed-handle guard, and proves read-after-purge fail closed across all required paths. S4 audit invariant is not blocked.
