# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S2 Fix Controller Validation

## Scope

- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-fix-codex.md`
- Accepted findings fixed: `P3-D-S2-CR-F01`, `P3-D-S2-CR-F02`
- Rejected finding unchanged: `P3-D-S2-CR-F03`
- Controller decision: fix gate returned; ready for independent re-review.

## Validation

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/host/test_host_activity_event_projection.py -q`
  - Result: `83 passed in 0.50s`
- `source .venv/bin/activate && pytest tests/engine/contracts/test_runner_events.py tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase2.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_context_overflow_classifier.py -q`
  - Result: `131 passed in 0.18s`
- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_host_activity_event_projection.py tests/host/test_outbox_projection.py -q`
  - Result: `164 passed in 1.66s`
- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py -q`
  - Result: `43 passed, 3 warnings in 1.47s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed.
- Broad coverage command including Engine, selected Host projection/ingest/read/outbox tests, and Service entrypoint runtime:
  - Result: `759 passed, 3 warnings in 7.71s`
  - Touched production file coverage:
    - `dayu/engine/agent.py`: 89%
    - `dayu/engine/contracts/engine_events.py`: 99%
    - `dayu/engine/contracts/runner_events.py`: 100%
    - `dayu/engine/runners/openai/error_classifier.py`: 93%
    - `dayu/engine/runners/openai/non_stream_parser.py`: 93%
    - `dayu/engine/runners/openai/runner.py`: 82%
    - `dayu/engine/runners/openai/sse_parser.py`: 93%
    - `dayu/engine/runners/openai/tool_call_aggregator.py`: 89%
    - `dayu/host/api.py`: 86%
    - `dayu/host/engine_ingest.py`: 91%
    - `dayu/host/read_api.py`: 82%
    - `dayu/host/tool_trace.py`: 87%
    - `dayu/service/entrypoint_runtime.py`: 88%

## Propagation Audit Delta

- Fatal provider protocol error now projects through Read API as `HostActivityKind.PROVIDER_PROTOCOL_ERROR` / `FAILED`, and Service entrypoint preserves `EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR`.
- Non-fatal provider diagnostic remains `HostActivityKind.PROVIDER_DIAGNOSTIC`, now with `HostActivityStatus.INFO`, avoiding completed-operation semantics.
- Context overflow `detection=None` path has explicit Agent regression coverage proving no provider diagnostic provenance event is emitted.

## Residual Risk

- S3 typed Engine error-code contract remains out of S2 scope.
- `P3-D-S2-CR-F03` remains rejected-with-reason and was not changed.
