# WU-SEMANTIC-OWNERSHIP-01 P3-J S3 Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `P3-J S3 - Idempotency And Descriptor Kind Weak-Contract Closure`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-j-s3-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-j-s3-code-review-ds.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-controller-validation.md`

## Findings Adjudication

### P3-J-S3-F1 - Idempotency dataclasses do not enforce kind owner at construction

- Source:
  - MiMo `S3-01`
  - DS finding `1`
  - DS finding `3` for `IdempotencyRecord` is treated as the same owner-boundary defect.
- Severity: `中`
- Decision: `accepted`
- Reason: The accepted S3 plan states `Validation: IdempotencyScope and IdempotencyResultRef`, and the implementation artifact claims these records validate through the owner. Current code only validates at store insert/read decode and leaves the public dataclass boundary as bare `str`, so the owner boundary is incomplete.
- Required fix:
  - Make `IdempotencyScope.scope_kind`, `IdempotencyResultRef.result_kind`, and decoded `IdempotencyRecord` kind fields typed as `IdempotencyScopeKind` / `IdempotencyResultKind`.
  - Validate/coerce at dataclass construction and row decode through the owner parser.
  - Preserve SQLite persistence as the enum `.value` / `StrEnum` text representation.
  - Add constructor-level rejection tests for unknown scope and result kind, plus any necessary consumer/test updates.

### P3-J-S3-F2 - payload_resolution consumes descriptor kind through string constants

- Source: DS finding `2`
- Severity: `低`
- Decision: `accepted`
- Reason: This does not break correctness because the constants are derived from `PayloadDescriptorKind` and `_validate_descriptor_kind(...)` parses expected values. However, the S3 goal is to close descriptor-kind weak contracts; using the enum owner directly in the descriptor consumer is clearer and avoids a mixed precedent.
- Required fix:
  - Update `payload_resolution.py` to consume `PayloadDescriptorKind` directly for expected descriptor kinds.
  - Keep `_validate_descriptor_kind(...)` as the single expected-kind parser/check boundary.

## Rejected / Deferred

- None.

## Fix Gate

- Next gate: P3-J S3 fix by AgentCodex.
- Fix must not modify unrelated dirty/untracked files.
- Fix must not add idempotency DDL `CHECK`.
- Required validation:
  - `source .venv/bin/activate && pytest tests/host/test_idempotency_store.py tests/host/test_durable_schema.py tests/host/test_payload_store.py tests/host/test_purge_session.py tests/host/test_wait_record_state.py -q`
  - `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py -q`
  - `source .venv/bin/activate && pytest tests/host/test_durable_concurrency_matrix.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
