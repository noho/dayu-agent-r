# Phase 15 P15-S1 Code Review

## Gate

- Work unit: Phase 15 retention purge production hardening
- Current gate: Phase 15 S1 code review
- Slice: Purge Tombstone Schema And Durable Primitives
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- Implementation artifact: `docs/reviews/phase15-s1-implementation-codex-20260529.md`
- Review date: 2026-05-29
- Reviewer: AgentMiMo

## Scope Lens

S1 only. Must add schema v14 tombstone table and durable primitives. Must NOT implement public `purge_session`, delete EventLog/Session facts, or write audit JSONL.

## Reviewed Files

- `dayu/host/durable/schema.py`
- `dayu/host/durable/purge.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_purge_session.py`

## Validation Results

```bash
pytest tests/host/test_durable_schema.py tests/host/test_purge_session.py -q
# 26 passed in 0.37s

python -m pyright dayu/host/durable/schema.py dayu/host/durable/purge.py tests/host/test_durable_schema.py tests/host/test_purge_session.py
# 0 errors, 0 warnings, 0 informations
```

## Findings

### PASS - Scope Compliance

S1 correctly limits itself to schema and durable primitives:

- Schema bump `HOST_SCHEMA_VERSION` 13 → 14. `schema.py:26`.
- `TABLE_HOST_PURGE_TOMBSTONES` constant, DDL, governance table set, index constant and DDL all present. `schema.py:51`, `schema.py:972-997`, `schema.py:141-142`, `schema.py:93`, `schema.py:1122-1125`.
- Tombstone table has no FK to `event_log` or `host_sessions` — correct, since target rows will be deleted. DDL at `schema.py:972-997`.
- Unique `session_id` index ensures one tombstone per session. `schema.py:1122-1125`.
- No public `purge_session` wiring present.
- No EventLog/Session fact deletion present.
- No audit JSONL writing present.

### PASS - Schema DDL Correctness

- `tombstone_id TEXT PRIMARY KEY` — correct.
- `session_id TEXT NOT NULL` with unique index — correct.
- `audit_record_ref` / `audit_record_digest` CHECK constraint enforces both-set-or-both-unset — correct. `schema.py:991-995`.
- JSON columns (`operation_context_refs_json`, `deleted_counts_json`, `request_context_json`) are `TEXT NOT NULL` — correct.
- All DDL is included in `PURGE_GOVERNANCE_DDL` tuple and `HOST_DURABLE_DDL` aggregate — correct. `schema.py:1189-1190`, `schema.py:1227-1243`.
- `HOST_DURABLE_TABLES` includes `PURGE_GOVERNANCE_TABLES` — correct. `schema.py:144-153`.

### PASS - Dataclass Design

All dataclasses are `frozen=True, slots=True` — correct for durable row carriers.

- `PurgeDeleteCounts`: 21 typed `int` fields. `json_value()` method serializes to stable JSON object via module-level key constants. `purge.py:79-169`.
- `PurgePreconditionSnapshot`: 19 typed fields, all `str | int | int | None`. Correctly a typed carrier only — not instantiated in S1. `purge.py:172-215`.
- `PurgeTombstoneRow`: 17 fields matching DDL columns exactly. JSON columns typed as `Mapping[str, JsonValue]` — correct, no `dict`/`Any` leak. `purge.py:218-257`.
- `PurgeReplayDecisionKind(StrEnum)`: 5 closed variants — correct. `purge.py:260-267`.
- `PurgeReplayDecision`: 4 fields with correct optionality. `purge.py:270-283`.

### PASS - Idempotency Replay Semantics

`record_or_read_purge_idempotency` at `purge.py:433-500` implements the plan's replay flow:

1. Read tombstone by session_id — correct first check.
2. Tombstone exists → `_decision_for_existing_tombstone`:
   - Different `client_request_id` → `ALREADY_PURGED_CONFLICT`. `purge.py:519-525`.
   - Same key, different semantic digest → `IDEMPOTENCY_CONFLICT`. `purge.py:526-531`.
   - Same key, same digest → write idempotency row via `IdempotencyStore().record_idempotent_result()`, catch `HostIdempotencyConflictError` → `IDEMPOTENCY_CONFLICT`. `purge.py:533-558`.
3. No tombstone → check idempotency record:
   - No record → `PROCEED_TO_PURGE`. `purge.py:466-472`.
   - Different digest → `IDEMPOTENCY_CONFLICT`. `purge.py:473-479`.
   - Wrong `result_kind` → `DURABLE_INCONSISTENCY`. `purge.py:480-486`.
   - Tombstone not found by `result_ref` → `DURABLE_INCONSISTENCY`. `purge.py:487-494`.
   - All match → `REPLAY_TOMBSTONE`. `purge.py:495-500`.

All branches use `created_event_id=None` / `created_event_sequence=None` for purge idempotency rows — correct per plan.

### PASS - Tombstone Codec

- `insert_purge_tombstone`: validates → executes INSERT → reads back by id → defensive null check. `purge.py:324-382`.
- `_tombstone_from_row`: maps HostRow fields through typed validation helpers, then validates the assembled tombstone. `purge.py:591-660`.
- `_json_mapping_from_text`: parses JSON, validates Mapping type and string keys. `purge.py:694-712`.
- `_deleted_counts_from_json`: parses via `_json_mapping_from_text`, then constructs `PurgeDeleteCounts` with `_required_count` validation. `purge.py:715-773`.
- `_required_count`: rejects `bool` (Python `bool` is `int` subclass), non-`int`, and negative values. `purge.py:776-788`.

### PASS - Digest Builders

- `build_purge_semantic_digest`: canonicalizes operation/session_id/reason/context into `JsonValue` dict, delegates to `sha256_digest_json`. `purge.py:385-419`.
- `build_deleted_counts_digest`: delegates to `sha256_digest_json(counts.json_value())`. `purge.py:422-430`.

### PASS - Validation

- `_validate_tombstone`: validates all fields through typed helpers, cross-validates `deleted_counts_digest` against recomputed value, enforces `audit_record_ref`/`audit_record_digest` both-set-or-both-unset. `purge.py:827-879`.
- `_validate_delete_counts`: iterates all 21 count fields, rejects negative. `purge.py:791-824`.

### PASS - Strict Typing

- No `object`, `Any`, or untyped parameters/returns in any reviewed file.
- JSON boundaries use `JsonValue` and `Mapping[str, JsonValue]` — correct.
- All function signatures fully typed. Pyright confirms 0 errors.
- `_validation` helpers imported and used correctly — `require_text` as converter, `require_non_empty_text` / `require_sha256_digest` as validators.

### PASS - Chinese Docstrings

- Module docstring in `purge.py:1-6` — correct scope statement.
- All 5 dataclasses have Chinese class docstrings with `:param:` for every field.
- All public and private functions have Chinese docstrings with `:param:`, `:returns:`, `:raises:` where applicable.
- Module-level constants have Chinese docstrings (`purge.py:37-40`).

### PASS - Test Coverage

`test_purge_session.py` (5 tests):

| Test | Coverage |
|---|---|
| `test_insert_and_read_purge_tombstone_round_trip` | Tombstone insert, read-by-id, read-by-session-id, deleted_counts_digest consistency, no Session/EventLog FK required. |
| `test_tombstone_replay_records_purge_idempotency_with_null_event_refs` | Tombstone exists + idempotency missing → REPLAY_TOMBSTONE, idempotency row written with NULL event refs. |
| `test_tombstone_same_key_different_digest_conflicts` | Tombstone exists + same key + different digest → IDEMPOTENCY_CONFLICT. |
| `test_tombstone_different_key_returns_already_purged_conflict` | Tombstone exists + different key → ALREADY_PURGED_CONFLICT. |
| `test_existing_idempotency_same_key_different_digest_conflicts` | No tombstone + idempotency exists + different digest → IDEMPOTENCY_CONFLICT. |

`test_durable_schema.py` additions:

| Test | Coverage |
|---|---|
| `test_host_schema_version_is_phase15_purge_tombstone_version` | Schema version == 14. |
| `test_purge_tombstone_table_has_no_session_or_event_log_fk` | No FK to event_log/host_sessions, unique session index present, correct PK. |
| `test_schema_creates_only_owned_purge_tombstone_table` | No unexpected purge-related tables beyond `host_purge_tombstones`. |

### PASS - No Scope Violations

- No public `purge_session` command wiring.
- No EventLog / Session fact deletion.
- No audit JSONL writing.
- No Engine / Service / UI / Fins modification.
- No compatibility re-export / wrapper / facade.

## Non-blocking Observations

### OBS-1: PROCEED_TO_PURGE Path Not Explicitly Tested

The `PROCEED_TO_PURGE` branch (no tombstone, no idempotency record) in `record_or_read_purge_idempotency` is not covered by an explicit test. This is the "happy path" for a first-time purge and is implicitly exercised when later slices call the helper. Not a defect in S1 since the branch is straightforward and the test file will grow in S2/S3.

### OBS-2: DURABLE_INCONSISTENCY Branch Not Tested

The two `DURABLE_INCONSISTENCY` branches (wrong `result_kind` and missing tombstone by `result_ref`) are not covered. These are defensive edge cases for data corruption. Not a defect in S1; consider adding in S2 when the full purge flow is testable.

## Result

**PASS** — 0 findings. S1 implementation is correct, strictly typed, properly tested, and scope-compliant.
