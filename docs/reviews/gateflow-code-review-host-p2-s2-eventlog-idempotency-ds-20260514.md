# Gateflow Code Review Artifact: Host P2 S2 EventLog / Idempotency

## Review Gate

- **review gate name**: code-review
- **reviewed target**: Phase 2 Slice 2 — EventLog Append / Read / event_sequence / Idempotency Primitive
- **approved plan**: `docs/host/phase2-durable-store-eventlog-plan.md`
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p2-s2-eventlog-idempotency-20260514.md`
- **accepted Slice 1 commit**: `be5dbdc`
- **current branch**: `feat/host-phase2-durable-store-eventlog`
- **reviewer**: DS (deepreview)
- **review date**: 2026-05-14

## Scope Verified

Reviewed files (Slice 2 allowed set):

- `dayu/host/durable/event_log.py` (new)
- `dayu/host/durable/idempotency.py` (new)
- `dayu/host/durable/codec.py` (targeted update: +`is_sha256_digest`, +`_SHA256_DIGEST_PATTERN`)
- `dayu/host/durable/errors.py` (no changes from Slice 1 baseline)
- `tests/host/test_event_log_store.py` (new)
- `tests/host/test_event_log_multiprocess.py` (new)
- `tests/host/test_idempotency_store.py` (new)

Not reviewed: Slice 1 files (`schema.py`, `transaction.py`, `connection.py`, `options.py`) are out of scope except as referenced dependencies.

## Reviewer Conclusion

**PASS with 4 low-severity findings.** Slice 2 implementation is correct and well-aligned with the approved plan. All core behaviors — EventLog append/read/duplicate/conflict, global event_sequence, event_body_digest computation, idempotency record/conflict, typed contracts, Chinese docstrings — are implemented as specified. No plan violations, no Slice 3 behavior leakage, no runtime/Engine/Fins/Service/UI pollution. Validation rerun (14+1+15 tests passed, 0 pyright errors) confirms baseline correctness.

## Findings

### Finding 1: Whitespace-only identifier strings pass non-empty validation (Low)

**Evidence:**

- `event_log.py:551-552` — `_require_non_empty_text` only checks `value == ""`.
- `idempotency.py:298-299` — identical logic.

```python
def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if value == "":
        raise HostDurableError(f"{field_name} must be non-empty")
```

**Analysis:** Strings consisting only of whitespace (`" "`, `"\t"`, etc.) would pass validation and be stored as `event_id`, `session_id`, `scope_kind`, or `idempotency_key`. While the plan does not explicitly require whitespace trimming, whitespace-only identifiers are a data quality risk for downstream consumers (projection, audit, recovery scan). The plan's test requirement mentions "empty ids" should fail validation, and whitespace-only strings are semantically empty.

**Recommendation:** Add `.strip() == ""` check or equivalent whitespace rejection to `_require_non_empty_text`, or add a plan clarification that whitespace-only identifiers are intentionally permitted.

---

### Finding 2: Store class wrapper methods have zero test coverage (Low)

**Evidence:**

- `event_log.py:150-197` — `EventLogStore.append_event`, `.read_event_by_id`, `.read_events_after` are thin delegation methods.
- `idempotency.py:75-116` — `IdempotencyStore.record_idempotent_result`, `.read_idempotency_record` are thin delegation methods.
- All tests (`test_event_log_store.py`, `test_idempotency_store.py`) call module-level functions directly (`append_event`, `record_idempotent_result`, etc.), never the class methods.

**Analysis:** The class methods are pure delegates that forward to module-level functions. While the underlying functions are well-tested, the class delegation layer itself is untested. If a future refactor changes the class method signature without updating the delegate call, no test would catch it.

**Recommendation:** Either add one smoke test per store class (e.g., `EventLogStore().append_event(transaction, request)`) or remove the store classes in favor of direct module-level function usage if they don't carry state or provide abstraction value.

---

### Finding 3: Missing edge case test for `read_event_by_id` returning None and `read_events_after` returning empty tuple (Low)

**Evidence:**

- `test_event_log_store.py` — `read_event_by_id` is only tested with an existing event_id (`"event-2"` at line 248). No test calls `read_event_by_id` with a non-existent event_id.
- `read_events_after` is only tested with a cursor that has subsequent rows (cursor=1, two rows exist at lines 222-252). No test uses a cursor beyond all existing rows.

**Analysis:** These are simple code paths (event_log.py:319-321 and event_log.py:370) that would work correctly given the SQL query semantics, but they lack explicit test coverage. The single-file coverage target is >= 80%, and these branches are unreached.

**Recommendation:** Add two assertions to existing tests or create a dedicated edge-case test:
- `assert read_event_by_id(transaction, "nonexistent") is None`
- `assert read_events_after(transaction, 999, limit=10) == ()`

---

### Finding 4: Test helper `_request` never exercises NULL optional fields (Low)

**Evidence:**

- `test_event_log_store.py:56-96` — `_request()` defaults set every optional field to a non-None value:
  ```python
  run_id="run-1",
  attempt_id="attempt-1",
  execution_id="execution-1",
  actor="host",
  source="test",
  client_request_id="client-1",
  idempotency_key="idem-1",
  policy_decision={"allowed": True},
  reason={"why": "test"},
  ```
- No test constructs an `EventLogAppendRequest` with `run_id=None`, `policy_decision=None`, etc.

**Analysis:** The digest computation path for NULL optional fields (event_log.py:401-428) is exercised in a limited way through the multi-process test (`_request` in test_event_log_multiprocess.py:49-76 sets several fields to None). However, the single-process tests never verify that `event_body_digest` is stable and correct when optional fields are NULL, or that the round-trip (append → read) preserves NULL optional fields correctly.

**Recommendation:** Add one test case that appends an event with all optional fields set to None and verifies:
- The row is inserted successfully.
- `event_body_digest` is computed and stored.
- Reading back returns the row with `None` for all optional fields.
- Digest is deterministic (append same request twice → same digest, duplicate detection works).

## Non-Findings (Reviewed and Confirmed Correct)

### EventLog append/read correctness

- **global event_sequence**: SQLite `AUTOINCREMENT` allocates monotonic values (schema.py:84). Tests confirm 1,2,3,4 across event classes (test_event_log_store.py:163) and unique sequences in multi-process (test_event_log_multiprocess.py:155).
- **Duplicate event_id same digest → existing row, inserted=False**: event_log.py:218-221; verified by test_event_log_store.py:166-189 (row count stays at 1).
- **Duplicate event_id different digest → HostEventIdentityConflictError**: event_log.py:222-224; verified by test_event_log_store.py:192-219.
- **No second row**: Code paths are mutually exclusive — early return / raise / insert. No path inserts a second row for the same event_id.
- **Reader by cursor**: Uses `WHERE event_sequence > ? ORDER BY event_sequence ASC LIMIT ?` (event_log.py:341-368). Tests verify order (test_event_log_store.py:222-252).

### event_body_digest computation

- **Fields included**: event_log.py:404-421 includes exactly the plan-specified request-assigned fields: event_class, session_id, run_id, attempt_id, execution_id, event_type, occurred_at (formatted), actor, source, client_request_id, idempotency_key, policy_decision_json, reason_json, payload_json, payload_ref, payload_digest.
- **Fields excluded**: event_id, event_sequence, event_body_digest, appended_at — none appear in the digest input dict. Verified.
- **Canonical JSON**: `canonical_json_dumps` uses `sort_keys=True`, compact separators, `allow_nan=False` (codec.py:34-40). Digest computed from canonical JSON UTF-8 bytes via `sha256_digest_json`.
- **occurred_at**: Formatted to fixed UTC microsecond `Z` timestamp before digest input (event_log.py:400). Digest input uses the formatted string, not the raw datetime.

### payload_ref / payload_digest validation

- **Paired validation**: event_log.py:470-490 — both None → OK; one None → `HostPayloadReferenceError`; both provided → validates digest format.
- **Missing FK → HostForeignKeyError**: Non-null payload_ref pointing to missing descriptor triggers SQLite FK constraint → `_classify_sqlite_error` → `HostForeignKeyError`. Verified by test_event_log_store.py:334-362 (single call, no retry).
- **No payload descriptor helper**: EventLog only stores nullable FK columns. No descriptor write/read logic in Slice 2.

### Idempotency primitive

- **Scope/key uniqueness**: `PRIMARY KEY(scope_kind, scope_id, idempotency_key)` in schema (schema.py:127).
- **Same digest → returns existing**: idempotency.py:141-143; verified by test_idempotency_store.py:149-183, including that subsequent writes with different result_ref don't overwrite.
- **Different digest → HostIdempotencyConflictError**: idempotency.py:144-146; verified by test_idempotency_store.py:186-211.
- **Explicit result_kind**: Stored directly from `IdempotencyResultRef.result_kind` — no inference from other fields.
- **Conflict not retried**: Verified by test_idempotency_store.py:214-251 (single call recorded).

### Mutations inside caller-provided HostTransaction

- Both `append_event` and `record_idempotent_result` accept `transaction: HostTransaction` as first parameter and call only `transaction.execute()` / `transaction.fetchone()`. No internal connection management, no implicit transaction creation, no command path.

### Multi-process correctness

- Each subprocess opens independent `HostDurableStore` via `open_host_durable_store` (test_event_log_multiprocess.py:95). SQLite WAL + `BEGIN IMMEDIATE` + busy retry handles concurrency. No import of `dayu.runtime.lane` or `dayu.runtime.filelock` in Slice 2 modules.
- Check-then-act pattern in `append_event` is safe under WAL + `BEGIN IMMEDIATE`: the write lock serializes concurrent transactions, so the read check always sees the latest committed state.

### No Slice 3 behavior

- No artifact helper, no host instance liveness operations, no payload descriptor write logic. Confirmed across all Slice 2 production modules.

### Strict typing and Chinese docstrings

- All public and private function signatures are fully typed. No `Any`, `object`, or untyped parameters/returns.
- All modules, classes, and functions have complete Chinese docstrings with `:param`, `:returns`, `:raises` sections.
- `SQLiteScalar` union type used consistently for row value handling.

### Layer isolation

- Imports in Slice 2 modules are limited to: `dayu.contracts.json_value` (public contract), `dayu.host.durable.codec/errors/schema/transaction` (internal durable foundation), and Python stdlib. No imports from `dayu.runtime`, `dayu.engine`, `dayu.fins`, `dayu.service`, or `dayu.ui`.

## Controller Validation Rerun (Verified)

| Command | Result |
|---|---|
| `pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py -q` | 14 passed |
| `pytest tests/host/test_event_log_multiprocess.py -q` | 1 passed |
| `pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py -q` | 15 passed |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |

## Open Questions / Residual Risk

1. **Residual risk (accepted):** Finding 1 (whitespace-only IDs) — if downstream consumers rely on IDs being visually non-empty, whitespace-only strings could cause subtle issues. Mitigation: add whitespace check to validation helpers in a future slice or accept as caller responsibility.
2. **Residual risk (accepted):** Finding 2 (untested store classes) — store classes are thin wrappers; risk of signature drift is low but real. Mitigation: add smoke test or remove classes.
3. **Residual risk (accepted):** Finding 3 and 4 (edge case test gaps) — uncovered branches are simple and unlikely to break, but coverage metrics may fall below 80% target for event_log.py. Mitigation: add the suggested edge case assertions.
4. **Residual risk (covered by Slice 3):** Valid non-null `payload_ref` append path is not testable without payload descriptor writer. Slice 3 will cover this.
5. **Residual risk (covered by later phase):** No EventLog consumer (projection, audit, outbox, recovery) exists yet. The primitive is correct in isolation but integration risk remains for future consumers.

## Controller Decision

**Status: pending-controller-decision**

All 4 findings are low severity and non-blocking. The implementation is correct, plan-aligned, and passes all validation gates. Controller may:
- Accept as-is and advance to Slice 3.
- Request fixes for one or more findings before acceptance.

## Artifact Path

`docs/reviews/gateflow-code-review-host-p2-s2-eventlog-idempotency-ds-20260514.md`
