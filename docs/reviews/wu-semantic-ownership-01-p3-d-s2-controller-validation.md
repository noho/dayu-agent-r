# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S2 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- Slice: `S2 - Fatal protocol error vs non-fatal provider diagnostic`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-implementation-codex.md`
- Controller decision: implementation gate returned; ready for independent code review.

## Validation

- `source .venv/bin/activate && pytest tests/engine/contracts/test_runner_events.py tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase2.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_context_overflow_classifier.py -q`
  - Result: `130 passed in 0.18s`
- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_host_activity_event_projection.py tests/host/test_outbox_projection.py -q`
  - Result: `164 passed in 1.51s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed.
- Coverage command for touched production files:
  - `715 passed in 5.99s`
  - `dayu/engine/agent.py`: 89%
  - `dayu/engine/contracts/engine_events.py`: 99%
  - `dayu/engine/contracts/runner_events.py`: 100%
  - `dayu/engine/runners/openai/error_classifier.py`: 93%
  - `dayu/engine/runners/openai/non_stream_parser.py`: 93%
  - `dayu/engine/runners/openai/runner.py`: 82%
  - `dayu/engine/runners/openai/sse_parser.py`: 93%
  - `dayu/engine/runners/openai/tool_call_aggregator.py`: 89%
  - `dayu/host/engine_ingest.py`: 91%
  - `dayu/host/read_api.py`: 82%
  - `dayu/host/tool_trace.py`: 87%

## Source Scans

- `warnings: tuple[RunnerProtocolErrorData]` and old `RunnerProtocolErrorData(...unknown_provider...)` paths no longer appear in `dayu/engine`.
- Remaining `usage_field_malformed`, `runner.http.missing_content_type`, and `tool_call_unknown_gemini_key` hits are diagnostic constants/logging/projection paths.
- `message_marker_fallback` hits are limited to typed classifier, runner/Agent propagation, contracts, and tests.
- Host `PROVIDER_DIAGNOSTIC` hits are limited to ingest, Read API, Tool Trace, Outbox skip tests, and host tests.
- LLM-facing leakage scan across config, memory, evidence, compact material, terminal answer, and compaction paths returned no hits.

## Propagation Audit

- Producer owner: OpenAI-compatible Runner / adapter identifies non-fatal provider diagnostics.
- Runner contract: `RunnerEventType.PROVIDER_DIAGNOSTIC` carries closed severity/source, diagnostic code, provider request id, bounded raw payload, and partial tool-call summary.
- Engine projection: Agent maps Runner diagnostics to `EngineEventType.PROVIDER_DIAGNOSTIC` and does not set `failure_candidate`.
- Host persistence: Host ingest appends `PROVIDER_DIAGNOSTIC` as `EventClass.DIAGNOSTIC`; it does not mutate Run/Attempt terminal state or failure metadata.
- Read projection: Read API projects the row as non-fatal provider diagnostic activity.
- Tool Trace projection: Tool Trace exposes it only as diagnostic display data, not as terminal failure metadata.
- Exclusions: Outbox, Conversation Memory, final answer, accepted evidence material, compact material, and LLM-facing prompts do not consume provider diagnostic events.

## Residual Risk

- S3 typed Engine error-code contract remains intentionally out of S2 scope.
- AgentCodex reported broader `tests/engine tests/host` still contains unrelated Host dispatch / resolve_wait / process-backed runtime failures; controller did not expand S2 to those unrelated failures.
