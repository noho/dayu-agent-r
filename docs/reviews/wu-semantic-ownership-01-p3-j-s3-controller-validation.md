# WU-SEMANTIC-OWNERSHIP-01 P3-J S3 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `P3-J S3 - Idempotency And Descriptor Kind Weak-Contract Closure`
- Gate: controller validation after AgentCodex implementation
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s3-implementation-codex.md`
- Selected base for later code review: `6a208bec`

## Owner Boundary

- Idempotency scope/result kind owner: `dayu.host.durable.idempotency`.
- Idempotency producers: admission, session lifecycle, waiting, ToolRuntime, purge.
- Idempotency validation / persistence boundary: `record_idempotent_result(...)`, `read_idempotency_record(...)`, and row decode for `idempotency_records`.
- Descriptor kind owner: `dayu.host.durable.schema`, colocated with existing payload descriptor constants and media-type constants.
- Descriptor producers: ToolRuntime, RunInputBuilder, Engine ingest, compaction operation.
- Descriptor validation / persistence boundary: `PayloadStore` validates explicit `descriptor_kind` metadata before write; `payload_resolution` validates caller expected kind and actual descriptor metadata at descriptor-backed read time.

## Controller Checks

Direct diff inspection confirmed:

- `IdempotencyScopeKind` and `IdempotencyResultKind` define the accepted S3 baseline values.
- Idempotency store insert and durable row decode parse scope/result kinds through the owner.
- The schema intentionally does not add idempotency `scope_kind` / `result_kind` DDL `CHECK`.
- `PayloadDescriptorKind` and `payload_descriptor_metadata(...)` define the descriptor-kind legal set and producer helper.
- Production descriptor-kind writes for tool-call arguments, semantic query, runner input manifest/projection, selected tool schema snapshot, compactor input projection, and compaction rejected diagnostic now use `payload_descriptor_metadata(...)`.
- Remaining `metadata={"kind": ...}` writes are not descriptor-kind semantics.
- `tests/host/test_purge_session.py` now uses direct SQL for the historical/out-of-scope `external_ack` fixture. This is accepted because the test is simulating a row outside the current idempotency owner path; production creation through `IdempotencyStore` rejects that value.

Review focus to pass to code review:

- `IdempotencyScope` and `IdempotencyResultRef` still expose `str` fields. Current fail-closed behavior is at store insert/read boundaries, not dataclass construction. Reviewers should verify whether this satisfies the accepted S3 owner-boundary requirement or whether construction-time validation is required.

## Propagation Audit

- Production command paths still construct idempotency scopes/results at their existing owner-adjacent command modules, then pass them through the durable idempotency owner before persistence.
- Persisted idempotency rows with manually mutated unknown result kinds now fail closed at row decode.
- Payload descriptor producers no longer hand-format `descriptor_kind`; the descriptor-kind value is derived from one owner helper.
- Descriptor-backed readers validate missing, unknown, and mismatched descriptor kinds before returning LLM-facing tool-call request atoms.
- No Engine, Service, UI, runtime, or Fins reverse dependency was introduced.

## README Decision

Read:

- `dayu/host/README.md`
- `tests/README.md`

Decision: no README update for this slice. The Host README already documents durable truth, EventLog/state ownership, ToolRuntime, RunInputBuilder, and payload descriptor responsibilities at the stable developer-manual level. The tests README already covers the affected Host durable, idempotency, payload, ToolRuntime, RunInputBuilder, Engine ingest, compaction, and concurrency test areas. S3 tightens internal owner validation and does not add a new public workflow, command, package entrypoint, or test category.

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
- `rg --count-matches 'scope_kind=|result_kind=|_OPERATION_|_IDEMPOTENCY_RESULT_KIND|_WAIT_.*SCOPE_KIND|_WAIT_.*RESULT_KIND|PURGE_IDEMPOTENCY|_TOOL_FACT_ACCEPT_' dayu/host tests/host`
  - Result: expected production/test owner hits only; no unreviewed idempotency producer category found.
- `rg --count-matches 'descriptor_kind|DESCRIPTOR_KIND|_DIAGNOSTIC_DESCRIPTOR_KIND|metadata=\{' dayu/host tests/host`
  - Result: expected descriptor owner/helper hits plus non-descriptor generic metadata hits.
- `rg -n 'scope_kind TEXT NOT NULL CHECK|result_kind TEXT NOT NULL CHECK' dayu/host/durable/schema.py`
  - Result: no matches.

## Residual Risk

- Local idempotency command constants remain in producers such as admission, waiting, session lifecycle, ToolRuntime, and purge. This is accepted for S3 because the durable owner now validates persistence and decode, while some local operation constants also drive command payload semantics.
- Generic payload metadata remains schema-light by design. S3 only closes `descriptor_kind`; generic metadata is not promoted to a global schema.
- Construction-time validation of `IdempotencyScope` / `IdempotencyResultRef` remains a review focus before S3 acceptance.
