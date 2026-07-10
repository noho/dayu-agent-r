# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S2 Implementation

S2 implementation complete.

Artifact path: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-implementation-codex.md`

## Gate Scope

- Gate: S2 implementation gate, Fatal protocol error vs non-fatal provider diagnostic。
- Agent: AgentCodex。
- Branch: `phaseflow/host-issues-control`。
- Non-goal kept: 未进入 S3 typed Engine error-code contract；未 commit/push/PR/merge。
- Unrelated untracked files left untouched: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`。

## Source Findings

Closed:

- Provider warning/diagnostic 的 semantic owner 是 provider adapter/Runner：Adapter 首次识别 provider 返回的非致命异常形态，负责归一化为 typed diagnostic。
- Fatal provider protocol error 的 owner 仍是 Runner protocol validation：结构破坏、invalid/unknown `finish_reason`、无可执行 tool call 后的 fatal 空结果仍走 `RunnerProtocolErrorData` 和 `Done(ERROR)`。
- Agent 只做 Runner event 到 Engine event 的同源投影：`RunnerProviderDiagnosticData` 投影为 `ProviderDiagnosticData`，不创建 `failure_candidate`。
- Host EventLog owner 是 Host ingest：新增 `PROVIDER_DIAGNOSTIC` / `EventClass.DIAGNOSTIC`，持久化 bounded diagnostic descriptor，不更新 Run/Attempt terminal 状态，不写 failure metadata。
- Read API / Tool Trace owner 是 projection：只展示非致命诊断；不把 provider diagnostic 投影为 terminal failure、provider error code 或 outbox terminal item。
- Context overflow marker fallback 改为 typed provenance diagnostic；canonical `context_compaction_requested` 仍只基于 typed `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`。

Open:

- 无 S2 阻塞项。
- S3 typed Engine error-code contract 未实现，按本 gate non-goal 保留。

## Files Changed

Production:

- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/__init__.py`
- `dayu/engine/runners/openai/error_classifier.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/engine/agent.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/read_api.py`
- `dayu/host/tool_trace.py`

Tests:

- `tests/engine/contracts/test_runner_events.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_runner_event_contract.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_context_overflow_classifier.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `tests/engine/runners/openai/test_non_stream_response.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_outbox_projection.py`

Docs:

- `docs/engine/design.md`
- `docs/host/design.md`
- `dayu/engine/README.md`
- `dayu/host/README.md`

## Implementation Summary

- Added closed Runner diagnostic contract: `RunnerDiagnosticSeverity`, `RunnerDiagnosticSource`, `RunnerProviderDiagnosticData`, `RunnerEventType.PROVIDER_DIAGNOSTIC`。
- Added Engine diagnostic contract: `ProviderDiagnosticData`, `EngineEventType.PROVIDER_DIAGNOSTIC`。
- Converted non-fatal provider warnings to typed diagnostics:
  - unknown provider tool-call namespace/key diagnostics from tool-call aggregation；
  - malformed usage diagnostics in SSE and non-stream parsers；
  - missing Content-Type diagnostics for both streaming and non-streaming HTTP 200 responses。
- Preserved fatal protocol handling for true protocol errors and S1 invalid/unknown finish reason fail-closed behavior。
- Refactored context overflow detection to `ContextOverflowDetection` with closed kind: `STRUCTURED_CODE`, `MESSAGE_MARKER_FALLBACK`, `NOT_OVERFLOW`。
- Added Host `PROVIDER_DIAGNOSTIC` diagnostic EventLog event with bounded payload fields: `diagnostic_code`, `severity`, `message`, `provider_request_id`, `diagnostic_source`, `payload_ref`, `payload_digest`, `partial_tool_call_count`。
- Updated Tool Trace and Read API to display diagnostics without failure metadata or terminal semantics。
- Added Outbox regression coverage proving `EventClass.DIAGNOSTIC` provider diagnostics are skipped。

## Validation

Required tests:

- `source .venv/bin/activate && pytest tests/engine/contracts/test_runner_events.py tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase2.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_context_overflow_classifier.py -q`
  - Result: `130 passed in 0.18s`
- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_host_activity_event_projection.py tests/host/test_outbox_projection.py -q`
  - Result: `164 passed in 1.53s`
- Additional direct regressions:
  - `source .venv/bin/activate && pytest tests/engine/runners/openai/test_non_stream_response.py -q`
  - Result: `12 passed in 0.13s`
  - `source .venv/bin/activate && pytest tests/engine/test_package_exports.py tests/engine/test_runner_event_contract.py -q`
  - Result: `6 passed in 0.11s`

Type and whitespace:

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed。

Coverage:

- Command:
  - `source .venv/bin/activate && pytest tests/engine tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_host_activity_event_projection.py tests/host/test_outbox_projection.py tests/host/test_tool_trace_queries.py tests/host/test_command_handle.py tests/host/test_read_api_terminal_policy.py tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_local_proxy_engine_ingest.py --cov=dayu.engine.contracts.runner_events --cov=dayu.engine.contracts.engine_events --cov=dayu.engine.runners.openai.error_classifier --cov=dayu.engine.runners.openai.runner --cov=dayu.engine.runners.openai.sse_parser --cov=dayu.engine.runners.openai.non_stream_parser --cov=dayu.engine.runners.openai.tool_call_aggregator --cov=dayu.engine.agent --cov=dayu.host.engine_ingest --cov=dayu.host.read_api --cov=dayu.host.tool_trace --cov-report=term-missing -q`
  - Result: `715 passed in 6.05s`
  - Per touched production file:
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

Broader suite note:

- While seeking coverage, `tests/engine tests/host` was attempted. After updating the two S2-related Engine contract whitelist tests, remaining failures were in unrelated Host dispatch / resolve_wait text expectation / process-backed tool runtime tests. They were not on the required validation path and were not modified in this gate.

## Source Scans

- `rg -n "warnings: tuple\\[RunnerProtocolErrorData|RunnerProtocolErrorData\\(.*unknown_provider|unknown_gemini|usage_field_malformed|missing_content_type" dayu/engine`
  - Result: no old `warnings: tuple[RunnerProtocolErrorData]` or `RunnerProtocolErrorData(...unknown_provider...)` matches. Hits are new diagnostic constants/log lines for `usage_field_malformed`, `runner.http.missing_content_type`, and `tool_call_unknown_gemini_key`。
- `rg -n "CONTEXT_OVERFLOW_MESSAGE_MARKERS|message_marker_fallback|detect_context_overflow\\(" dayu tests`
  - Result: hits are limited to classifier typed detection, runner call site, Agent diagnostic provenance constant, contract enum, and tests。
- `rg -n "runner\\.http\\.missing_content_type|usage_field_malformed" dayu/engine/runners/openai`
  - Result: hits are adapter/parser diagnostic constants and internal diagnostic log lines。
- `rg -n "PROVIDER_DIAGNOSTIC|PROVIDER_PROTOCOL_ERROR|ENGINE_EVENT_DIAGNOSTIC" dayu/host/engine_ingest.py dayu/host/read_api.py dayu/host/tool_trace.py dayu/host/outbox.py tests/host`
  - Result: `PROVIDER_DIAGNOSTIC` appears in Host ingest, read activity projection, tool trace diagnostic projection, outbox skip test, and host tests. `PROVIDER_PROTOCOL_ERROR` remains on fatal provider error path。

## LLM-Facing Leakage Check

Scan:

- `rg -n "PROVIDER_DIAGNOSTIC|provider_diagnostic|ProviderDiagnosticData|RunnerProviderDiagnosticData|diagnostic_source|runner\\.http\\.missing_content_type|usage_field_malformed|context_overflow_message_marker_fallback|message_marker_fallback" dayu/config dayu/host/compaction_operation.py dayu/host/compact_pipeline.py dayu/host/evidence.py dayu/host/llm_compaction.py dayu/host/compaction.py dayu/host/durable/memory.py dayu/host/compact_artifact.py dayu/host/compact_material.py dayu/host/compact_payload.py dayu/host/memory_repair.py dayu/host/memory.py dayu/host/_terminal_answer.py`
  - Result: no hits。

Additional audit:

- Generic `payload_ref` / `payload_digest` appear in existing memory/evidence/compact code, but not tied to provider diagnostic strings。
- `compact_material.py` post-compact delta query is restricted to `EventClass.CANONICAL_FACT` and event types `USER_INPUT_ACCEPTED`, `RUN_SUCCEEDED`, `TOOL_RESULT_ACCEPTED`; `PROVIDER_DIAGNOSTIC` is `EventClass.DIAGNOSTIC` and cannot enter accepted evidence material or compact material through that path。
- Provider diagnostic payload refs are only exposed to internal Host EventLog / Tool Trace diagnostic projection and are not rendered into prompts, memory, final answer, accepted evidence material, compact material, or LLM-facing prompt messages。

## README And Design Docs

- `docs/engine/design.md`: updated Runner/Engine event taxonomy and context overflow marker fallback provenance。
- `docs/host/design.md`: updated EventLog taxonomy, diagnostic event matrix, and Engine-to-Host mapping for `PROVIDER_DIAGNOSTIC`。
- `dayu/engine/README.md`: read Agent update constraints first; updated only public Engine/Runner event contract and provider diagnostic behavior。
- `dayu/host/README.md`: read Agent update constraints first; updated only Host ingest/EventClass/outbox/tool-trace boundary statements。
- `tests/README.md`: checked; no Agent update constraint section. Not updated because new tests are within existing Engine/Host/outbox/tool-trace testing scope and do not change reader-facing test policy。

## Propagation Audit

- Source: provider adapter identifies non-fatal provider diagnostics, including malformed usage, missing Content-Type on HTTP 200, unknown provider tool-call namespace/key, and context overflow message-marker fallback provenance。
- Runner: emits `RunnerEventType.PROVIDER_DIAGNOSTIC` with `RunnerProviderDiagnosticData` and closed `severity/source` enums。
- Agent: maps Runner diagnostic to `EngineEventType.PROVIDER_DIAGNOSTIC` / `ProviderDiagnosticData`; does not set `failure_candidate`。
- Host ingest: appends `PROVIDER_DIAGNOSTIC` as `EventClass.DIAGNOSTIC`, stores bounded diagnostic payload/descriptor, and leaves Run/Attempt terminal state and failure metadata unchanged。
- Read API: projects provider diagnostics as `HostActivityKind.PROVIDER_DIAGNOSTIC` with non-fatal diagnostic title/summary。
- Tool Trace: includes provider diagnostics only in diagnostic display/provenance refs; never as `failure_kind`, `provider_error_code`, or terminal metadata。
- Outbox: excluded by `EventClass.DIAGNOSTIC` filtering; test covers skipped projection。
- Exclusions verified: provider diagnostics do not enter conversation memory, final answer, accepted evidence material, compact material, or LLM-facing prompt messages。

## Residual Risks

- S3 remains necessary to type all Engine error-code contracts; this S2 gate intentionally only carries provider diagnostic provenance and preserves existing fatal Engine error semantics。
- Full `tests/engine tests/host` contains unrelated Host failures outside this work unit. Required S2 validation and targeted coverage pass; those unrelated failures were not remediated here to avoid scope drift。

## Blocker Status

- Blocker status: none.
