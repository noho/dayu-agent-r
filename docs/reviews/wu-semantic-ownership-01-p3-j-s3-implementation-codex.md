# WU-SEMANTIC-OWNERSHIP-01 P3-J S3 Implementation

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `P3-J S3 - Idempotency And Descriptor Kind Weak-Contract Closure`
- Gate: `implementation`
- Agent: Codex
- Artifact path: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-implementation-codex.md`

## Changed Files

- `dayu/host/durable/idempotency.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/payload.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/run_input.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_operation.py`
- `tests/host/test_idempotency_store.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_payload_store.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_purge_session.py`
- `tests/host/test_durable_concurrency_matrix.py`

`tests/host/test_durable_concurrency_matrix.py` was migrated because it directly exercises the idempotency primitive. Leaving its old arbitrary `durable_matrix` / `event` values would break the owner-level contract.

## Owner Boundary

- Idempotency scope/result owner: `dayu.host.durable.idempotency`.
- Payload descriptor kind owner: `dayu.host.durable.schema`, next to the existing descriptor constants and media-type constants.
- Producer-side descriptor metadata validation: `dayu.host.durable.payload` validates `descriptor_kind` only when metadata explicitly carries that key.
- Consumer-side expected-kind validation: `dayu.host.payload_resolution` parses caller expected kind and checks only the referenced descriptor metadata.

## Initial Stop Scans

Commands run before edits:

- `rg -n 'scope_kind=|result_kind=|_OPERATION_|_IDEMPOTENCY_RESULT_KIND|_WAIT_.*SCOPE_KIND|_WAIT_.*RESULT_KIND|PURGE_IDEMPOTENCY|_TOOL_FACT_ACCEPT_' dayu/host tests/host`
- `rg -n 'descriptor_kind|DESCRIPTOR_KIND|_DIAGNOSTIC_DESCRIPTOR_KIND|metadata=\{' dayu/host tests/host`
- `rg -n 'scope_kind TEXT NOT NULL CHECK|result_kind TEXT NOT NULL CHECK' dayu/host/durable/schema.py`

Initial idempotency scan found the accepted production baseline in admission, session lifecycle, waiting, ToolRuntime, and purge. It also found non-idempotency `operation_*` constants in command/context/trace paths and test-only arbitrary idempotency fixtures.

Initial descriptor scan found the accepted descriptor baseline in ToolRuntime, RunInputBuilder, Engine ingest, and compaction operation. It also found `metadata={"kind": ...}` producers for non descriptor-kind metadata; those are not descriptor-kind semantics and were not moved into the descriptor owner.

Initial DDL scan returned no matches for idempotency `scope_kind` / `result_kind` `CHECK`.

## Idempotency Owner / Validation

Added:

- `IdempotencyScopeKind`
- `IdempotencyResultKind`
- `parse_idempotency_scope_kind(...)`
- `parse_idempotency_result_kind(...)`
- legal-value helpers for tests and owner audit

`IdempotencyScope`, `IdempotencyResultRef`, and decoded `IdempotencyRecord` now validate scope/result kind through the idempotency owner. Unknown values fail before write or during durable row decode.

No DDL `CHECK` was added for idempotency scope/result kind. `tests/host/test_durable_schema.py` now asserts the omission is intentional.

## Descriptor Kind Owner / Producer Validation

Added:

- `PayloadDescriptorKind`
- `parse_payload_descriptor_kind(...)`
- `payload_descriptor_kind_values()`
- `payload_descriptor_metadata(...)`

Production descriptor-kind producers now write metadata through `payload_descriptor_metadata(...)`:

- tool call arguments payload
- tool call semantic query payload
- runner-call input manifest
- runner-call input projection
- selected tool schema snapshot
- compactor input projection
- compaction rejected attempt diagnostic

`PayloadStore` rejects unknown `descriptor_kind` before writing when metadata explicitly contains that key. Generic metadata without `descriptor_kind` remains neutral.

## Payload Resolution Expected-Kind Validation

`payload_resolution` now parses the caller-provided expected descriptor kind through the descriptor owner and fails closed when the descriptor metadata is missing or mismatched for that expected kind.

It does not maintain a separate all-known descriptor kind list and does not validate unrelated descriptors unless a caller asks for a specific expected kind.

## DDL Non-CHECK Assertion

Final DDL scan:

```text
rg -n 'scope_kind TEXT NOT NULL CHECK|result_kind TEXT NOT NULL CHECK' dayu/host/durable/schema.py
```

Result: no matches.

## Tests Run

- `source .venv/bin/activate && pytest tests/host/test_idempotency_store.py tests/host/test_durable_schema.py tests/host/test_payload_store.py tests/host/test_purge_session.py tests/host/test_wait_record_state.py -q`
  - Result: `119 passed`
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py -q`
  - Result: `245 passed`
- Extra affected fixture validation: `source .venv/bin/activate && pytest tests/host/test_durable_concurrency_matrix.py -q`
  - Result: `5 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## README Decision

Read:

- `dayu/host/README.md`
- `tests/README.md`

Decision: no README update. The Host README already documents the durable truth, payload descriptor, ToolRuntime, RunInputBuilder, Tool Trace, and idempotency boundaries at the stable developer-manual level. The tests README already lists the affected idempotency, payload, durable schema, ToolRuntime, RunInputBuilder, Engine ingest, compaction, and durable concurrency test areas. This slice tightens internal owner validation and does not add a new user-facing workflow, command, public package entrypoint, or test category.

## Final Source Scans

Commands run after edits:

- `rg -n 'scope_kind=|result_kind=|_OPERATION_|_IDEMPOTENCY_RESULT_KIND|_WAIT_.*SCOPE_KIND|_WAIT_.*RESULT_KIND|PURGE_IDEMPOTENCY|_TOOL_FACT_ACCEPT_' dayu/host tests/host`
- `rg -n 'descriptor_kind|DESCRIPTOR_KIND|_DIAGNOSTIC_DESCRIPTOR_KIND|metadata=\{' dayu/host tests/host`
- `rg -n 'scope_kind TEXT NOT NULL CHECK|result_kind TEXT NOT NULL CHECK' dayu/host/durable/schema.py`

Final idempotency scan status:

- Production values remain within the accepted S3 baseline.
- Test-only illegal values remain only in negative tests or direct SQL corruption fixtures.
- `external_ack` is no longer produced through `IdempotencyStore`; purge uses direct SQL only to simulate out-of-scope historical/external rows retained by the purge matrix.

Final descriptor scan status:

- Production `descriptor_kind` writes use `payload_descriptor_metadata(...)`.
- Remaining `metadata={"kind": ...}` writes are not descriptor-kind semantics.
- Test direct `descriptor_kind` writes are negative/corruption tests or legal fixture assertions.

Final DDL scan status: no idempotency `CHECK` matches.

## Propagation Audit

- Admission/session lifecycle/waiting/tool runtime/purge continue to pass idempotency values through `IdempotencyScope` and `IdempotencyResultRef`; the durable owner validates the closed Python set.
- Row decoding now rejects unknown persisted idempotency result kind; write tests and mutated-row tests cover the owner boundary.
- Descriptor producers no longer hand-write `descriptor_kind` in local metadata dicts.
- Payload resolution validates expected descriptor kind for tool-call arguments and semantic query descriptors without becoming the global descriptor owner.
- No Engine, Service, UI, runtime, or Fins reverse dependency was introduced.

## Residual Risks

- Residual risk: existing production modules still keep local command operation constants such as `_OPERATION_START_RUN`; they are also used in command payload semantics, not solely idempotency. This slice relies on owner validation at `IdempotencyScope` / `IdempotencyResultRef` rather than moving all operation constants. Classification: accepted current-scope non-blocking.
- Residual risk: generic payload metadata remains schema-light by design. Only `descriptor_kind` receives owner validation. Classification: accepted non-goal per S3.

## Blocker Status

No blocker.
