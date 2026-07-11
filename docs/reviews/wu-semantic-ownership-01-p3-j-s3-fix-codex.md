# WU-SEMANTIC-OWNERSHIP-01 P3-J S3 Fix

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `P3-J S3 - Idempotency And Descriptor Kind Weak-Contract Closure`
- Gate: code review fix
- Agent: AgentCodex
- Artifact path: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-code-review-controller-adjudication.md`

## Scope

Only accepted findings from the controller adjudication were fixed:

- `P3-J-S3-F1`
- `P3-J-S3-F2`

Unrelated dirty / untracked files named by the controller were not modified:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/cli_ci*`
- `docs/reviews/code-review-20260710-135625.md`
- `docs/reviews/code-review-20260710-141049.md`

No commit, push, PR, or other gate action was performed.

## Changed Files

- `dayu/host/durable/idempotency.py`
- `dayu/host/admission.py`
- `dayu/host/durable/session_lifecycle.py`
- `dayu/host/waiting.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/durable/purge.py`
- `dayu/host/payload_resolution.py`
- `tests/host/test_idempotency_store.py`
- `tests/host/test_purge_session.py`
- `tests/host/test_durable_concurrency_matrix.py`

## Fix Summary

### P3-J-S3-F1

Decision: fixed.

Changes:

- `IdempotencyScope.scope_kind` is now typed as `IdempotencyScopeKind`.
- `IdempotencyResultRef.result_kind` is now typed as `IdempotencyResultKind`.
- `IdempotencyRecord.scope_kind` and `IdempotencyRecord.result_kind` are now typed as the same owner enums.
- The three dataclasses normalize kind fields through the idempotency owner parser at construction time.
- Row decode now assigns parsed owner enum values to `IdempotencyRecord` instead of discarding parser results.
- SQLite insert and lookup paths explicitly serialize enum values with `.value`, preserving text persistence.
- Production idempotency producers in admission, session lifecycle, waiting, ToolRuntime, and purge now pass typed owner values.
- Tests were updated to use typed owner values for legal construction and to assert constructor-level rejection for unknown kind values.
- Existing direct SQL out-of-scope purge fixture remains direct SQL because it intentionally simulates non-owner historical / external rows.

No idempotency DDL `CHECK` was added.

### P3-J-S3-F2

Decision: fixed.

Changes:

- `payload_resolution.py` now uses `PayloadDescriptorKind` directly for expected descriptor kinds.
- `_validate_descriptor_kind(...)` remains the expected-kind parse/check boundary and still parses both expected and actual descriptor kind through the owner.
- The old descriptor kind string constants are no longer consumed by `payload_resolution.py`.

## Propagation Audit

- Idempotency owner: `dayu.host.durable.idempotency`.
- Descriptor kind owner: `dayu.host.durable.schema.PayloadDescriptorKind`.
- Durable persistence remains text at SQLite boundary via enum `.value`.
- `record.result_kind` comparisons in touched production paths now compare enum owner values.
- Purge session fact cleanup SQL uses owner enum values when building the durable scope-kind set.
- Payload resolution validates expected descriptor kind from `PayloadDescriptorKind` and actual descriptor metadata through `parse_payload_descriptor_kind(...)`.
- Scans:
  - `rg -n "scope_kind TEXT NOT NULL CHECK|result_kind TEXT NOT NULL CHECK" dayu/host/durable/schema.py`: no matches.
  - `rg -n "TOOL_CALL_ARGUMENTS_DESCRIPTOR_KIND|TOOL_CALL_SEMANTIC_QUERY_DESCRIPTOR_KIND" dayu/host/payload_resolution.py`: no matches.
  - `rg -n "scope_kind=\"|result_kind=\"|scope_kind='|result_kind='" dayu/host tests/host/test_idempotency_store.py tests/host/test_purge_session.py tests/host/test_durable_concurrency_matrix.py`: no matches.

## Validation

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

## README Decision

Read:

- `dayu/host/README.md`
- `tests/README.md`

Decision: no README update. The fix tightens internal owner typing and test coverage for existing durable idempotency and descriptor-kind contracts. It does not add a user-facing workflow, command, public entrypoint, new test category, or stable developer-manual concept beyond the already documented Host durable / payload / idempotency boundaries.

## Residual Risk

- Generic direct SQL tests can still insert out-of-owner idempotency rows when they intentionally simulate historical or external rows. This is scoped to tests and direct SQL corruption fixtures, not the production `IdempotencyStore` write path.
- Payload metadata remains schema-light except for explicit `descriptor_kind`, as required by the S3 plan. Missing descriptor kind still fails at descriptor-consuming resolution boundaries.

## Completion Status

All accepted findings in the controller adjudication are fixed and validated.
