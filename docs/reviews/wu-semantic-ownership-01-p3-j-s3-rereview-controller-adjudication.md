# WU-SEMANTIC-OWNERSHIP-01 P3-J S3 Re-Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `P3-J S3 - Idempotency And Descriptor Kind Weak-Contract Closure`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-j-s3-fix-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-j-s3-fix-rereview-ds.md`

## Decision

Decision: `accepted`

Both reviewers concluded `PASS`.

Accepted findings status:

- `P3-J-S3-F1`: closed. `IdempotencyScope`, `IdempotencyResultRef`, and decoded `IdempotencyRecord` now carry typed idempotency owner enum values; dataclass construction and row decode validate through owner parsers; SQLite persistence / lookup serializes with `.value`; production producers pass typed values; no idempotency DDL `CHECK` was added.
- `P3-J-S3-F2`: closed. `payload_resolution.py` consumes `PayloadDescriptorKind` directly for expected descriptor kinds, and `_validate_descriptor_kind(...)` remains the single expected-kind parse/check boundary.

New material findings: none.

## Controller Validation

Controller reran:

- `source .venv/bin/activate && pytest tests/host/test_idempotency_store.py tests/host/test_durable_schema.py tests/host/test_payload_store.py tests/host/test_purge_session.py tests/host/test_wait_record_state.py -q`
  - Result: `119 passed`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py -q`
  - Result: `245 passed`
- `source .venv/bin/activate && pytest tests/host/test_durable_concurrency_matrix.py -q`
  - Result: `5 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

Additional scans:

- `rg -n 'scope_kind TEXT NOT NULL CHECK|result_kind TEXT NOT NULL CHECK' dayu/host/durable/schema.py`
  - Result: no matches.
- `rg -n 'scope_kind="|result_kind="|scope_kind='\''|result_kind='\''|TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND|TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND' dayu/host tests/host/test_idempotency_store.py tests/host/test_purge_session.py tests/host/test_durable_concurrency_matrix.py`
  - Result: only descriptor constants remain in `dayu/host/durable/schema.py`, where they are derived from `PayloadDescriptorKind`; no `payload_resolution.py` consumer hit.

## Residual Risk

- Direct SQL corruption / historical-row tests can still insert out-of-owner idempotency values. This is intentional and scoped to simulating rows outside current Python owner write paths; production `IdempotencyStore` rejects them.
- Generic payload metadata remains schema-light except for explicit `descriptor_kind`, as required by the S3 plan.

## Next Gate

S3 is ready for accepted slice commit. After commit, update `docs/host/issues-implementation-control.md` and continue to P3-J S4.
