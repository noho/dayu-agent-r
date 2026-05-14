# Code Re-Review: Host P2 S2 EventLog / Idempotency Accepted Findings Fix

## Scope

- Mode: current changes (re-review of accepted findings fix)
- Branch: `feat/host-phase2-durable-store-eventlog`
- Base: accepted Slice 1 commit `be5dbdc`
- Output file: `docs/reviews/gateflow-code-re-review-host-p2-s2-eventlog-idempotency-mimo-20260514.md`
- Included scope:
  - `dayu/host/durable/codec.py` (modified: +`is_sha256_digest`, +`_SHA256_DIGEST_PATTERN`)
  - `dayu/host/durable/event_log.py` (new, 612 lines)
  - `dayu/host/durable/idempotency.py` (new, 359 lines)
  - `tests/host/test_event_log_store.py` (new, 569 lines)
  - `tests/host/test_event_log_multiprocess.py` (new, 157 lines)
  - `tests/host/test_idempotency_store.py` (new, 392 lines)
  - `docs/reviews/gateflow-fix-host-p2-s2-eventlog-idempotency-20260514.md` (fix artifact)
  - `docs/reviews/gateflow-implementation-host-p2-s2-eventlog-idempotency-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-ds-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-controller-adjudication-20260514.md`
- Excluded scope: Slice 1 files (`schema.py`, `transaction.py`, `connection.py`, `options.py`, `errors.py`, `__init__.py`) reviewed only as referenced dependencies
- Parallel review coverage: 无

## Re-Review Context

Controller adjudication accepted 4 low-severity findings (DS-F1 to DS-F4) from original DS review. Fix artifact `gateflow-fix-host-p2-s2-eventlog-idempotency-20260514.md` reports all 4 fixed, plus a follow-up fix for DS-F1 actor/source gap. This re-review verifies fix completeness and checks for new defects introduced by the fix.

## DS-F Accepted Findings Verification

### DS-F1: Whitespace-only identifier strings pass non-empty validation — VERIFIED FIXED

**Evidence:**

Both `event_log.py` and `idempotency.py` validation helpers now reject empty and whitespace-only strings:

- `event_log.py:544-554` — `_require_non_empty_text` checks `value == "" or value.isspace()`.
- `event_log.py:557-569` — `_require_optional_non_empty_text` checks `value is not None and (value == "" or value.isspace())`.
- `idempotency.py:289-299` — identical `_require_non_empty_text` logic.
- `idempotency.py:302-314` — identical `_require_optional_non_empty_text` logic.

**Actor / Source follow-up fix verified:**

- `event_log.py:461-462` — `_validate_append_request` now routes `request.actor` and `request.source` through `_require_optional_non_empty_text`.
- `test_event_log_store.py:419-439` — `whitespace_actor` and `whitespace_source` test cases verify both raise `HostDurableError`.

**Values are not trimmed or normalized before storage** — validation only rejects semantically empty text; valid non-empty text is stored exactly as provided. Correct.

**Coverage of DS-F1 in tests:**

- `test_event_log_store.py:401-408` — `whitespace_event_id`: required text `" \t"` raises `HostDurableError`.
- `test_event_log_store.py:410-417` — `whitespace_optional_text`: optional `run_id=" \n"` raises `HostDurableError`.
- `test_event_log_store.py:419-428` — `whitespace_actor`: optional `actor=" \n"` raises `HostDurableError`.
- `test_event_log_store.py:430-439` — `whitespace_source`: optional `source=" \t"` raises `HostDurableError`.
- `test_idempotency_store.py:244-292` — `whitespace_scope` and `whitespace_result`: required scope/result fields with `" \t"` / `" \n"` raise `HostDurableError`.

**Conclusion:** DS-F1 fully fixed. Whitespace-only strings are rejected for all required and optional text fields in both EventLog and Idempotency modules, including the follow-up actor/source fix.

---

### DS-F2: Store class wrapper methods have zero test coverage — VERIFIED FIXED

**Evidence:**

- `test_event_log_store.py:321-351` — `test_event_log_store_wrapper_methods_delegate_to_functions` exercises `EventLogStore.append_event`, `.read_event_by_id`, `.read_events_after` through class instances.
- `test_idempotency_store.py:188-213` — `test_idempotency_store_wrapper_methods_delegate_to_functions` exercises `IdempotencyStore.record_idempotent_result`, `.read_idempotency_record` through class instances.

Both tests verify that class method delegation produces identical results to direct module-level function calls. Store classes were kept because the approved plan names them.

**Conclusion:** DS-F2 fully fixed.

---

### DS-F3: Missing edge case tests for `read_event_by_id` returning None and `read_events_after` returning empty tuple — VERIFIED FIXED

**Evidence:**

- `test_event_log_store.py:353-372` — `test_missing_event_and_cursor_beyond_end_return_empty_results`:
  - `read_event_by_id(transaction, "missing-event") is None` — asserts missing event returns `None`.
  - `read_events_after(transaction, 999, limit=10)` — asserts cursor beyond last row returns empty tuple.

**Conclusion:** DS-F3 fully fixed.

---

### DS-F4: `_request` helper never exercises NULL optional fields in single-process EventLog tests — VERIFIED FIXED

**Evidence:**

- `test_event_log_store.py:193-255` — `test_append_optional_none_fields_preserves_nulls_and_digest_idempotency`:
  - Constructs `EventLogAppendRequest` with all optional fields set to `None` (`run_id`, `attempt_id`, `execution_id`, `actor`, `source`, `client_request_id`, `idempotency_key`, `policy_decision`, `reason`, `payload_ref`, `payload_digest`).
  - Appends twice with same request, verifies `first.inserted is True` and `second.inserted is False`.
  - Reads back and verifies all optional fields are `None` in the fetched row.
  - Verifies `event_body_digest` is a valid sha256 digest and is stable across duplicate appends.

**Conclusion:** DS-F4 fully fixed.

---

## Plan Non-Goals Compliance

Fix did not introduce any plan non-goal scope:

- No payload descriptor writer or artifact helper.
- No host instance liveness operations.
- No Session / Run / Attempt state machine or status updates.
- No EngineEvent ingest, projection, stream fanout, audit, trace, outbox, memory, ToolRuntime, Remote.
- No `dayu/runtime`, `dayu/engine`, `dayu/fins`, `dayu/service`, `dayu/ui` imports.
- No command path semantics.
- No compatibility re-export, wrapper, or facade.

Verified by import scan of all changed production files: imports are limited to `dayu.contracts.json_value`, `dayu.host.durable.*`, and Python stdlib.

**Conclusion:** Plan non-goals fully respected.

---

## Core Correctness Verification

### EventLog append/read

- **Global `event_sequence`**: SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` (schema.py:84). Tests confirm monotonic allocation across event classes (`test_event_log_store.py:138-164`) and unique sequences in multi-process (`test_event_log_multiprocess.py:152-157`).
- **Duplicate `event_id` same digest → existing row, `inserted=False`**: `event_log.py:219-221`; verified by `test_event_log_store.py:167-190`.
- **Duplicate `event_id` different digest → `HostEventIdentityConflictError`**: `event_log.py:222-224`; verified by `test_event_log_store.py:258-285`.
- **No second row**: Code paths are mutually exclusive — early return / raise / insert. Verified by `test_event_log_store.py:167-190` (row count stays at 1).
- **Reader by cursor**: `WHERE event_sequence > ? ORDER BY event_sequence ASC LIMIT ?` (`event_log.py:340-368`). Verified by `test_event_log_store.py:288-318`.
- **Read None / empty**: `test_event_log_store.py:353-372` verifies missing event returns `None`, cursor beyond end returns empty tuple.

### event_body_digest

- **Fields included**: `event_log.py:404-421` includes exactly the 16 plan-specified request-assigned fields.
- **Fields excluded**: `event_id`, `event_sequence`, `appended_at` and all DB-assigned fields are absent from digest input dict. Verified.
- **Canonical JSON**: `canonical_json_dumps` uses `sort_keys=True`, compact separators, `allow_nan=False` (`codec.py:34-40`).
- **`occurred_at`**: Formatted to fixed UTC microsecond `Z` timestamp before digest input (`event_log.py:400`).
- **NULL optional fields**: `test_event_log_store.py:193-255` verifies digest stability when all optional fields are `None`.

### Idempotency conflict

- **Same scope/key + same digest → existing record**: `idempotency.py:141-143`; verified by `test_idempotency_store.py:151-185`.
- **Same scope/key + different digest → `HostIdempotencyConflictError`**: `idempotency.py:144-146`; verified by `test_idempotency_store.py:216-241`.
- **Conflict not retried**: `test_idempotency_store.py:295-332` verifies single call recorded before conflict raises.
- **Explicit `result_kind`**: Stored directly from `IdempotencyResultRef.result_kind` (`idempotency.py:236`); no inference from other fields.
- **FK reference to EventLog**: `test_idempotency_store.py:335-362` verifies `created_event_id` / `created_event_sequence` FK linkage.

### Transaction boundaries

- All mutations accept `HostTransaction` as first parameter and call only `transaction.execute()` / `transaction.fetchone()`. No internal connection management, no implicit transaction creation, no command path.
- `after-commit` callback runs only after successful commit: `test_event_log_store.py:533-569` verifies committed row is visible in callback.

### Multi-process sequence

- `test_event_log_multiprocess.py:110-157`: 4 processes × 12 events = 48 total. Verifies:
  - Final row count equals total successful appends.
  - All `event_sequence` values are unique and strictly increasing.
  - All `event_id` values are unique.
  - No `dayu.runtime` import; concurrency handled by SQLite WAL + `BEGIN IMMEDIATE` + busy retry.

**Conclusion:** All core behaviors verified correct.

---

## Validation Rerun

| Command | Result |
|---|---|
| `pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py -q` | **19 passed in 0.12s** |
| `pytest tests/host/test_event_log_multiprocess.py -q` | **1 passed in 0.28s** |
| `pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py -q` | **15 passed in 0.12s** |
| `python -m pyright dayu/host tests/host` | **0 errors, 0 warnings, 0 informations** |

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

## Residual Risk

- **Valid non-null `payload_ref` append path not testable** (covered by Slice 3): EventLog only validates nullable `payload_ref` FK; actual descriptor write/read is Slice 3 scope.
- **Deliberate long lock retry exhausted multi-process branch not tested** (accepted): Slice 1 covers busy retry unit test; Slice 2 multi-process covers normal concurrent append success.
- **Validation helper duplication** (low risk, non-blocking): `_require_non_empty_text` and `_require_optional_non_empty_text` are duplicated between `event_log.py` and `idempotency.py`. Acceptable at current scale; third consumer in a later slice could extract to `codec.py` or `validation.py`.

---

## Conclusion

**PASS.** All 4 controller-accepted findings (DS-F1 through DS-F4) are fully fixed, including the follow-up actor/source whitespace fix. Fix did not introduce new defects, did not violate plan non-goals, and did not break existing EventLog/Idempotency/transaction/schema behavior. All tests pass, pyright clean.
