# WU-SEMANTIC-OWNERSHIP-01 P3-J S1 Controller Validation

## Scope

- Sub-WU: P3-J S1 EventLog Event Type Append / Decoder / Fresh-Schema Closure.
- Base accepted plan state: `4ba17c92 docs: record p3-j accepted plan state`.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-s1-implementation-codex.md`.

## Owner Boundary

- Fact producer: Host append paths produce `EventLogAppendRequest.event_type`.
- Semantic owner: `dayu.host.lifecycle_events` owns the complete Host EventLog legal event type set and category grouping.
- Validation owner: `dayu.host.durable.event_log` validates append requests and decoded durable rows using the owner parser.
- Persistence owner: fresh Host durable schema renders `event_log.event_type` CHECK values from the same owner-owned legal set.
- Projection owners: read API, projection runner, memory, tool trace and runner-input consumers continue reading `EventLogRow.event_type` after durable owner validation.

S1 fixes the weak contract at the owner boundary. It does not move validation into downstream consumers or LLM-facing projections.

## Controller Review

- `lifecycle_events.py` now exposes category-preserving EventLog event type enums and `all_host_event_type_values()`.
- `event_log.py` rejects unknown `event_type` during append and rejects externally mutated unknown values during row decode.
- `schema.py` derives the fresh-schema `event_log.event_type` CHECK from `all_host_event_type_values()` and bumps `HOST_SCHEMA_VERSION` to 22.
- Fixture migration replaced arbitrary EventLog event type literals with legal Host values, keeping illegal values only in explicit rejection tests.
- Engine ingest audit confirms `CONTENT_DELTA` and `TOOL_CALL_DELTA` remain transient and are not persisted as EventLog rows; persisted preview/tool/context/diagnostic values are covered by the legal set.

## Additional Controller Finding

The broader consumer validation initially failed:

```text
tests/host/test_tool_trace_projection.py::test_tool_call_chain_projects_hot_rows_and_cold_lines
expected result_status=completed, got unknown
```

Root cause: the test fixture omitted the accept-barrier-owned typed status fields (`resolution_kind`, `tool_fact_kind`) and only carried `raw_tool_outcome.kind`. `AcceptedResultProjection` intentionally does not infer accepted status from raw outcome, because status ownership belongs to typed accepted-result payload fields. The fix was therefore applied to the test fixture by adding the typed status fields, not to projection production code.

## Propagation Audit

- Produce: admission, run transition, dispatch, waiting, tool runtime, engine ingest, session lifecycle and context compaction paths produce Host event types already present in `all_host_event_type_values()`.
- Persist: fresh SQLite schema enforces `event_type IN (...)` from the owner helper.
- Decode: `EventLogRow` construction fail-closes on mutated unknown values before downstream consumers see them.
- Audit/projection: projection runner, public event stream, read API, Tool Trace, Memory and RunInputBuilder consume the validated row text rather than reconstructing the legal set.
- LLM-facing output: this slice does not change LLM-facing text; it prevents invalid durable facts from reaching LLM-facing memory/tool evidence projections.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_lifecycle_events.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_durable_schema.py -q` -> 97 passed.
- `source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_durable_connection.py tests/host/test_durable_transaction.py tests/host/test_public_event_stream.py -q` -> 91 passed.
- `source .venv/bin/activate && pytest tests/host/test_event_log_multiprocess.py tests/host/test_idempotency_store.py tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_storage_orphan_proof.py -q` -> 48 passed.
- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_read_api_terminal_policy.py tests/host/test_run_input_builder.py -q` -> 242 passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` -> 0 errors, 0 warnings, 0 informations.
- `git diff --check` -> passed.

## README Decision

- Read `dayu/host/README.md` Agent update constraints. No update: S1 hardens an existing Host durable contract and does not add a new developer-facing API, workflow, component, or stable operational procedure beyond already documented EventLog ownership.
- Read `tests/README.md`. No update: tests stay within existing Host durable/projection categories and do not introduce a new test layer or new common command.

## Residual Risk

- S1 intentionally closes the EventLog event type set. Future Host features that add durable event types must add them to `dayu.host.lifecycle_events` before writing rows or creating fresh schemas.
- Existing old SQLite databases are not migrated in this WU by design; current schema policy is fresh-schema only unless a task explicitly asks for compatibility migration.
