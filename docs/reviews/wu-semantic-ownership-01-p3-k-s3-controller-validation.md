# WU-SEMANTIC-OWNERSHIP-01 P3-K S3 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-K - Test harness semantic coupling cleanup`
- Gate: implementation slice S3 controller validation
- Slice: S3 Protocol-Faithful Test Double Consolidation
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-k-s3-implementation-codex.md`
- Previous accepted commit: `0ebea2c1`

## Changed Files

- `tests/host/fake_cancellation.py`
- `tests/engine/runners/openai/_fakes.py`
- `tests/engine/runners/openai/test_cancellation_boundaries.py`
- `tests/engine/runners/openai/test_cancellation_no_done_event.py`
- `tests/engine/runners/openai/test_close_releases_resources.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `tests/engine/runners/openai/test_http_unknown_status_runner.py`
- `tests/engine/runners/openai/test_protocol_surface.py`
- `tests/engine/runners/openai/test_request_identity.py`
- `tests/engine/runners/openai/test_response_cleanup_race.py`
- `tests/engine/runners/openai/test_retry_backoff.py`
- `tests/engine/runners/openai/test_runner_b3_extra.py`
- `tests/engine/runners/openai/test_runner_diagnostics.py`
- `tests/engine/runners/openai/test_stream_idle.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_llm_compaction.py`
- `tests/service/test_fins_direct.py`

No production code under `dayu/` changed.

## First-Principles Check

The S3 motivation remains valid. The defect was not that tests need no cancellation controls; tests legitimately need a controllable token. The defect was that multiple local fakes implemented the same cancellation observation protocol with divergent mutation names and timestamp semantics.

The implementation correctly moves the test mutation owner to one helper:

- `tests/host/fake_cancellation.py::ControllableCancellationToken`
- Implements `dayu.contracts.cancellation.CancellationToken`
- Starts open by construction
- Exposes one external mutation method, `request_cancel(...)`
- Preserves first cancellation reason and first UTC-aware timestamp
- Has no constructor-as-cancelled semantics

The implementation also preserves compaction and memory fixture ownership:

- `tests/host/fake_compaction.py` remains the compaction test double owner.
- `tests/host/memory_snapshot_factories.py` remains the memory snapshot construction owner.
- No new `ConversationMemorySnapshotVNext(...)` business-test construction was added.

## Validation Commands

- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_cancellation_boundaries.py tests/engine/runners/openai/test_cancellation_no_done_event.py tests/engine/runners/openai/test_retry_backoff.py tests/engine/runners/openai/test_response_cleanup_race.py -q`
  - Result: `24 passed`
- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py tests/host/test_engine_ingest_mapping.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q`
  - Result: `174 passed`
- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py -q`
  - Result: `19 passed, 3 warnings`
  - Warning classification: existing third-party `edgar` deprecation warnings, unrelated to S3 cancellation helper semantics.
- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - Result: `109 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: pass

## Source Scans

- `rg -n "\.trigger\(" tests/engine tests/host tests/service`
  - Result: no matches
- `rg -n "FakeCancellationToken|StubCancellationToken|ControllableCancellationToken\(cancelled|datetime\.now\(\)" tests/engine/runners/openai tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/host/fake_cancellation.py tests/service/test_fins_direct.py`
  - Result: no matches
- `rg -n "ConversationMemorySnapshotVNext\(" tests/engine tests/host tests/service`
  - Result: construction appears only in `tests/host/memory_snapshot_factories.py`; the other hit is `tests/host/test_import_boundary.py` scanner fixture text.

## README Decision

`tests/README.md` was read before deciding documentation changes. No update is required. The README already documents the test-only cancellation helper location, compaction fake location, and memory snapshot factory responsibility. S3 changed the concrete helper class name and removed duplicate fakes, but did not introduce a new helper layer or change the documented responsibility boundary.

## Propagation Audit

Cancellation:

- Protocol owner remains `dayu.contracts.cancellation.CancellationToken`.
- Test mutation owner is now `tests/host/fake_cancellation.py::ControllableCancellationToken`.
- OpenAI runner tests, Engine Agent tests, Host compaction / ingest tests, and Service direct tests consume the same helper.
- External `.trigger(...)` mutation has been removed from Engine / Host / Service tests.
- OpenAI runner `_fakes.py` no longer owns a local cancellation fake or naive timestamp semantics.

Compaction:

- `dayu.host.compaction.ContextCompactor` remains the production protocol owner.
- `tests/host/fake_compaction.py` remains the test double owner.
- No production compaction schema or behavior changed.

Memory:

- `dayu.host.memory` remains the production schema / digest owner.
- `tests/host/memory_snapshot_factories.py` remains the test snapshot construction owner.
- No new business-test direct snapshot construction was introduced.

LLM-facing / durable state:

- No production durable state, trace, memory, audit, prompt, tool schema, or user / LLM-facing output changed.

## Residual Risks

- The entire `tests/engine`, `tests/host`, and `tests/service` suites were not run; validation covered the approved focused matrices plus the extra Engine Agent files touched by the no-trigger migration.
- Existing third-party `edgar` deprecation warnings remain in `tests/service/test_fins_direct.py`; they are unrelated to this slice.

## Completion Status

Controller validation accepts S3 implementation for code review. No blocking open question is present. Next gate: S3 code review by AgentMiMo and AgentDS.
