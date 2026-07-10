# WU-SEMANTIC-OWNERSHIP-01 P3-D Plan - Engine provider protocol normalization

## Gate State

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- Title: Engine provider protocol normalization
- Gate: plan
- Artifact owner: AgentCodex
- Status: ready-for-plan-rereview
- Blocking questions: none

This plan is code-generation-ready for the current repository state. It only plans future implementation work; this artifact does not modify production code or tests.

## Goal

Normalize provider wire facts at the Runner adapter boundary before Agent or Host can interpret them. The accepted P3-D risk is real: current code still lets OpenAI-compatible adapter choices, finish reasons, protocol diagnostics, context-overflow detection, and Engine error codes leak across boundaries with mixed semantics.

Success signals:

- Fatal provider protocol errors and non-fatal provider diagnostics are distinct typed Runner/Engine events.
- Host persists non-fatal provider diagnostics as a named diagnostic EventLog event with explicit projection behavior.
- Stream and non-stream responses apply one explicit provider `choices` policy.
- Unknown wire `finish_reason` never silently becomes `FinishReason.STOP`.
- Known Engine run failure codes are typed, while provider/runner-specific codes remain possible only through an explicit typed extension wrapper.
- Context-overflow string matching remains inside the adapter as a diagnostic fallback and is surfaced as diagnostic provenance, not hidden business truth.
- Host persists only typed Engine events and bounded diagnostic payloads; Host/Agent never guess provider wire facts from strings.

## Non-Goals

- Do not add a provider plugin registry or general provider framework.
- Do not move Host context governance, compact policy, retry policy, or provider-aware token sizing into Engine.
- Do not ask Host, Agent, memory, Tool Trace, CLI, or tests to infer provider wire semantics from raw text.
- Do not preserve old interface compatibility if it conflicts with the new typed contract.
- Do not treat unknown `finish_reason` as `STOP`.
- Do not expose provider diagnostic internals to LLM-facing messages.

## Design Alignment

`docs/engine/design.md` says Engine owns Runner protocol normalization, emits typed `RunnerEvent` / `EngineEvent`, and reports provider context overflow as `context_compaction_requested` while Host owns compaction. `docs/host/design.md` says EngineEvent ingest is the Host boundary that validates and converts Engine events to Host events; projections, tool trace, outbox, memory, and audit cannot become truth. `docs/host/issues-implementation-control.md` selects P3-D as the current next gate and records this owner boundary.

The plan stays minimal: it does not introduce provider registration, tokenizer work, new Host policy, or broad diagnostic infrastructure. It changes the existing OpenAI-compatible adapter contract and the existing Agent/Host ingest paths that already consume these facts.

## First-Principles Finding Check

| Source | Current disposition | Direct current evidence |
| --- | --- | --- |
| AgentCodex 4: `PROVIDER_PROTOCOL_ERROR` mixes fatal errors and warnings | accepted-current | `ToolCallAggregator.feed()` appends unknown namespace/key warnings as `RunnerProtocolErrorData` while `SSEParser._finalize_success()` later yields successful `RunnerToolCallsCompletedData` and `RunnerDoneData`; Agent treats every `RunnerProtocolErrorData` as `PROVIDER_PROTOCOL_ERROR` and sets `failure_candidate` in `dayu/engine/agent.py`. |
| AgentCodex 5: SSE multi-choice merge vs non-stream first-choice | accepted-current | `SSEParser._handle_chunk_object()` iterates every valid `choice` and merges content/tool state into one buffer; `parse_non_stream_response()` picks `choices[0]`. Existing parity tests cover single-choice only. |
| AgentDS 2: Engine error codes are bare strings | accepted-current | `RunFailedData.error_code`, `EngineRunOutcomeFailed.error_code`, `ProviderProtocolErrorData.error_code`, and `RunnerProtocolErrorData.error_code` are `str`; Agent has many `_ERROR_*` string constants and directly passes runner protocol strings to `RunFailedData`. |
| AgentDS 4: context overflow falls back to English message markers | accepted-current with scope correction | `detect_context_overflow()` first checks structured `error.code`, then searches `_CONTEXT_OVERFLOW_MESSAGE_MARKERS`; the returned boolean is later converted to `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` without exposing whether the source was structured or marker fallback. |
| AgentDS 21: unknown `finish_reason` falls back to `STOP` | accepted-current | Non-stream `_resolve_finish_reason()` logs `unknown_finish_reason` then returns `FinishReason.STOP`; SSE logs the same warning, leaves `_finish_reason=None`, and `_finalize_success()` uses `self._finish_reason or FinishReason.STOP`. Tests currently assert this fallback. |
| AgentMiMo BI-7: context overflow markers are hardcoded | accepted-current with scope correction | The markers are inside the adapter, which is the correct owner, but they still become a hidden source for a recoverable business fact because the detection provenance is not typed or persisted. |

No source finding is rejected as obsolete.

## Owner Boundary

Provider wire facts are first produced by the provider HTTP/SSE/non-stream response. The OpenAI-compatible Runner adapter owns all first normalization and validation:

- `dayu/engine/runners/openai/runner.py`: HTTP status, content type, request id, response body, retry, context-overflow classification.
- `dayu/engine/runners/openai/sse_parser.py`: SSE event framing, choice policy, finish reason normalization, streaming content/reasoning/tool deltas, usage, fatal protocol errors, non-fatal diagnostics.
- `dayu/engine/runners/openai/non_stream_parser.py`: non-stream JSON shape, choice policy, finish reason normalization, content/reasoning/tool calls, usage, fatal protocol errors, non-fatal diagnostics.
- `dayu/engine/runners/openai/tool_call_aggregator.py`: tool-call delta assembly, provider-state validation, fatal tool-call protocol errors, non-fatal provider-state diagnostics.
- `dayu/engine/runners/openai/error_classifier.py`: structured context-overflow detection and adapter-only marker fallback with diagnostic provenance.

Agent owns only RunnerEvent consumption and EngineEvent projection. It may decide run state from typed RunnerEvent data, but must not infer provider semantics from raw strings. It can see:

- typed `FinishReason`;
- typed fatal provider protocol error;
- typed non-fatal provider diagnostic;
- typed HTTP error code plus context-overflow detection provenance.

Host owns persistence and projection after EngineEvent ingest. It can see:

- canonical terminal facts such as `FINAL_ANSWER`, `RUN_FAILED`, `CONTEXT_COMPACTION_REQUESTED`;
- diagnostic events such as provider diagnostics and fatal provider protocol errors;
- bounded payload refs/digests, provider request id, client correlation id, and typed error-code text for durable JSON.

Host/Agent must not see raw provider wire payloads as truth and must not parse provider strings to decide finish reason, context overflow, or failure taxonomy. LLM-facing messages must not contain provider diagnostic internals.

Propagation audit target for implementation:

```text
provider wire response
  -> OpenAI adapter normalization
  -> RunnerEvent
  -> Agent state / EngineEvent
  -> Host EngineEvent ingest
  -> EventLog diagnostic/canonical fact
  -> read model / tool trace / activity / outbox / memory visibility
```

Every business fact in this path must derive from the adapter-normalized typed event. Diagnostic refs may be persisted and projected for debugging, but must not become memory, final answer, or LLM-facing evidence.

Current static propagation analysis for implementation:

| Semantic | Current producer / transition | Current durable or projection consumer | Required P3-D treatment |
| --- | --- | --- | --- |
| Fatal provider protocol error code | OpenAI adapter emits `RunnerProtocolErrorData.error_code: str`; Agent projects `ProviderProtocolErrorData.error_code: str`. | `dayu/host/engine_ingest.py` persists `PROVIDER_PROTOCOL_ERROR` and `_provider_protocol_failure_metadata()` writes `provider_error_code`; `dayu/host/tool_trace.py` validates provider protocol failure metadata; `dayu/host/read_api.py` projects provider diagnostic activity. | Keep fatal protocol error as terminal diagnostic/failure fact, but type the code at Engine boundary and serialize through one helper before Host durable JSON. |
| Non-fatal provider diagnostic | Some tool-call warnings are currently stored as `RunnerProtocolErrorData`; usage malformed and missing content type are currently log-only warnings. | No durable typed path for log-only warnings; tool-call warnings currently look fatal once Agent consumes `RunnerProtocolErrorData`. | Introduce non-fatal Runner diagnostic -> Engine diagnostic -> Host `PROVIDER_DIAGNOSTIC` EventLog path; no run status transition and no failure metadata. |
| Context-overflow classification | `error_classifier.py` currently returns bare `bool`; `runner.py` maps true to `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`; Agent emits `context_compaction_requested`. | Host persists `CONTEXT_COMPACTION_REQUESTED` as canonical business fact and later compaction flow owns the policy. | Preserve canonical compaction request only from typed HTTP code; additionally carry `ContextOverflowDetection` provenance to a non-fatal diagnostic when source is marker fallback. |
| Engine-owned run failure code | Agent constants flow into `RunFailedData.error_code: str` and `EngineRunOutcomeFailed.error_code: str`. | `engine_ingest.py` copies `data.error_code` into terminal payloads and stream failure context; `read_api.py`, `tool_trace.py`, public Host events, and outbox read durable payload fields. | Replace known codes with `EngineRunErrorCode`; Host consumers only see durable serialized text produced by the shared serializer. |
| Provider/runner-specific extension code | Runner protocol strings may be passed through Agent into Engine failure or provider protocol data. | Host may expose `provider_error_code` in diagnostic activity/tool trace metadata. | Use `RunnerSpecificErrorCode` only for non-empty bounded provider/runner text with explicit source; empty explicit provider codes fail closed before wrapper creation. |

Current Host consumer notes:

- `engine_ingest.py` currently has generic engine diagnostics via `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC` and fatal provider protocol diagnostics via `_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR`; S2 must add a separate non-fatal provider diagnostic dispatch instead of overloading either terminal failure handling path.
- `tool_trace.py` diagnostic allowlist currently includes `ENGINE_EVENT_DIAGNOSTIC` and `PROVIDER_PROTOCOL_ERROR`; S2 must include the new non-fatal provider diagnostic event only as diagnostic material, not as `failure_kind`.
- `read_api.py` currently maps `PROVIDER_PROTOCOL_ERROR` to `HostActivityKind.PROVIDER_DIAGNOSTIC`; S2 may reuse that activity kind for non-fatal provider diagnostics, but the title/summary must not imply run failure.
- `outbox.py` currently filters terminal canonical facts; S2 should not update outbox for the diagnostic event because `EventClass.DIAGNOSTIC` is intentionally filtered out.
- Memory, final answer, accepted evidence material, compact material, and prompt assembly must not consume provider diagnostic payloads. S2/S3 validation must scan these paths and add tests or assertions where a projection path exists.

## Contract Decisions

1. SSE multi-choice policy: the OpenAI-compatible SSE parser validates choices per chunk in `_handle_chunk_object()`. A usage-only SSE chunk with `choices=[]` and valid usage remains legal. A valid assistant choice is a choice object whose `delta` contains at least one non-null semantic field used by the adapter, such as `role`, `content`, `reasoning_content`, `tool_calls`, or `finish_reason`; an object with empty `delta={}` and no `finish_reason` is not a valid assistant choice but still counts as malformed if it carries a non-zero `index` or invalid shape. A chunk containing more than one valid assistant choice is fatal immediately and must yield provider protocol error plus `RunnerDoneData(ERROR)` without merging deltas. A valid assistant choice with explicit non-zero `index` is fatal even if it is the only choice. A single valid choice without `index` is accepted as the sole choice.
2. Non-stream choice policy: a non-stream response must contain exactly one assistant choice. `choices=[]`, missing `choices`, non-list `choices`, more than one choice, or a single choice with explicit non-zero `index` is fatal. Non-stream has no usage-only chunk exception; usage may be parsed as diagnostic/metadata only after the single-choice response shape is valid.
3. Finish-reason policy: known strings map to `FinishReason`. Unknown non-empty strings, non-string non-null values, empty strings, arrays, objects, and booleans are fatal provider protocol errors with bounded diagnostic payloads and `RunnerDoneData(ERROR)`. `null` and missing `finish_reason` are treated as absent, not as `STOP`; absent is legal only for non-terminal intermediate SSE chunks and for the existing complete-tool-call inference path where tool calls themselves imply `TOOL_CALLS`. Content success without a terminal finish reason is fatal unless S1 documents a specific adapter-owned invariant proving it is an intermediate chunk. Cross-chunk conflicting terminal finish reasons are fatal.
4. Non-fatal provider diagnostics: warnings such as unknown provider-state namespace/key, malformed usage, missing stream/non-stream content type, and context-overflow marker fallback must use a new non-fatal diagnostic event, not `PROVIDER_PROTOCOL_ERROR`.
5. Fatal provider protocol errors: malformed JSON, non-object payload, missing non-stream choices, invalid tool call id/name/arguments, invalid finish reason, and invalid multi-choice policy remain fatal and set Agent failure candidates.
6. Context overflow: structured provider code is the primary business signal. Marker fallback may still classify overflow to preserve current recovery behavior, but `ContextOverflowDetection(source=MESSAGE_MARKER_FALLBACK)` must travel from adapter to Agent to Host diagnostic output. The canonical `context_compaction_requested` remains based only on typed `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`; marker text is diagnostic provenance, not business truth.
7. Error code typing: Engine-owned failure codes become `EngineRunErrorCode` or equivalent `StrEnum`. Provider/runner-specific codes use a deliberate typed wrapper such as `RunnerSpecificErrorCode(value=..., source=...)`. The wrapper validates trimmed non-empty bounded text, for example 1-128 characters, and a closed source enum such as `RUNNER_PROTOCOL`, `HTTP_PROVIDER`, or `ADAPTER`. Explicit empty or whitespace-only provider/runner codes fail closed at the producer; missing provider detail uses an Engine-owned fallback such as `RUNNER_ERROR_DONE_WITHOUT_DETAIL` instead of fabricating a provider-specific value. Serialization to Host durable JSON uses one helper, for example `serialize_engine_error_code(code) -> str`, not ad hoc `.value` or raw strings scattered through consumers.

## Implementation Slices

### S1 - Adapter choice and finish-reason policy

Goal: make stream and non-stream provider terminal normalization deterministic and fail closed for unknown finish reasons.

Non-goals:

- Do not introduce new Host behavior.
- Do not type all Engine error codes yet.
- Do not split warning events yet unless required by the fatal policy tests.

Candidate files:

- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_non_stream_response.py`
- `tests/engine/runners/openai/test_event_flow_ordering.py`

Required changes:

- Add one private adapter-owned choice policy helper only if it removes duplication without creating a seam. It must expose separate functions or clearly separate branches for SSE chunk semantics and non-stream response semantics.
- SSE path: validate choices inside `_handle_chunk_object()` before merging content/tool state. Reject immediately when a chunk contains multiple valid assistant choices, any valid explicit non-zero `index`, conflicting valid choices, or invalid choice shape. Keep `choices=[]` legal only for usage-only chunks; an empty-delta choice plus one valid delta choice must still be covered by tests and follow the helper's documented validity rule.
- Non-stream path: validate response-level `choices` before selecting a choice. Reject missing/non-list/empty/multi-choice responses and explicit non-zero `index`; do not silently select `choices[0]`.
- Replace unknown or invalid `finish_reason -> STOP` behavior with fatal protocol error.
- Finish reason rules must be implemented consistently in SSE and non-stream: unknown non-empty strings, empty strings, non-string non-null values, bool, number, array, object, and cross-chunk conflicting terminal finish reasons are fatal; `null`/missing is absent and cannot become `STOP` by default.
- Update tests that currently assert unknown finish reason falls back to `STOP`.
- Add parity tests for stream/non-stream multi-choice rejection, including conflicting content, tool calls, finish reasons, and explicit non-zero index.

Testing matrix:

- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_event_flow_ordering.py -q`
- Required S1 positive/negative cases:
  - non-stream multi-choice response rejects before `choices[0]` selection;
  - SSE multi-choice chunk rejects immediately in `_handle_chunk_object()`;
  - SSE usage-only chunk with `choices=[]` remains valid;
  - SSE empty-delta choice plus valid delta choice follows the explicit valid-choice rule and does not merge multiple assistant facts;
  - conflicting content/tool-call choices in one SSE chunk are fatal;
  - unknown non-empty `finish_reason` is fatal in SSE and non-stream;
  - non-string `finish_reason` values, including int, bool, array, and object, are fatal;
  - empty-string `finish_reason` is fatal;
  - null and missing `finish_reason` are treated as absent and tested separately from unknown strings;
  - conflicting terminal `finish_reason` values across SSE chunks are fatal.
- Coverage gate: collect coverage for `dayu/engine/runners/openai/sse_parser.py` and `dayu/engine/runners/openai/non_stream_parser.py`; each touched file must remain at or above 80%.
- Source scan: `rg -n "unknown_finish_reason|FinishReason\\.STOP|finish_reason or FinishReason\\.STOP" dayu/engine/runners/openai tests/engine/runners/openai`

README/docs trigger:

- `dayu/engine/` and `tests/` are affected, so implementation must inspect `dayu/engine/README.md` and `tests/README.md` Agent update constraints. Update only if current implemented behavior changes developer-facing contract or test layering text.

Residual risk:

- Some provider may return multiple choices despite Dayu not requesting them. This plan intentionally fails closed because merging or arbitrary selection would fabricate a single response.

### S2 - Fatal protocol error vs non-fatal provider diagnostic

Goal: stop using provider protocol error events for warnings while preserving diagnostic visibility through typed non-fatal events.

Dependency:

- S2 depends on S1. After S1 and before S2, invalid/unknown `finish_reason` is already fatal but still travels through the existing fatal provider-protocol error path. S2 only splits remaining non-fatal diagnostics from fatal protocol errors; it must not reclassify invalid `finish_reason` back into a warning.

Non-goals:

- Do not change Host run lifecycle decisions except to persist/display the new diagnostic event without state transition.
- Do not make diagnostics LLM-facing.
- Do not introduce a generic observability framework.

Candidate files:

- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/runners/openai/error_classifier.py`
- `dayu/engine/runners/openai/usage.py`
- `dayu/engine/agent.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/tool_trace.py`
- `dayu/host/read_api.py`
- `dayu/host/outbox.py`
- `tests/engine/contracts/test_runner_events.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_context_overflow_classifier.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_host_activity_event_projection.py`

Required changes:

- Add a non-fatal Runner diagnostic data type and Runner event type, with fields such as `diagnostic_code`, `severity`, `message`, `provider_request_id`, `raw_payload`, `partial_tool_calls`, and diagnostic source. Use a closed severity enum.
- Add matching Engine diagnostic event data and event type. Agent must project Runner diagnostics to Engine diagnostics without setting `failure_candidate`.
- Host EventLog contract: add a separate non-fatal provider diagnostic event type, recommended exact string `PROVIDER_DIAGNOSTIC`, with `EventClass.DIAGNOSTIC`. Do not reuse `_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR` because that event is terminal/failure-related. Do not reuse `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC` unless the implementation proves the payload contract can distinguish provider diagnostics without weakening existing generic diagnostic semantics; the default plan is a new `_EVENT_TYPE_PROVIDER_DIAGNOSTIC` in `engine_ingest.py`, `read_api.py`, and `tool_trace.py`.
- Host EngineEvent ingest dispatch must persist `PROVIDER_DIAGNOSTIC` with bounded payload fields such as `diagnostic_code`, `severity`, `message`, `provider_request_id`, `diagnostic_source`, `payload_ref`, and `payload_digest`; it must not update Run/Attempt terminal state and must not write failure metadata.
- Tool Trace must add `PROVIDER_DIAGNOSTIC` to diagnostic event allowlists only for diagnostic display. It must not turn it into `failure_kind`, `provider_error_code`, or terminal failure metadata.
- Read API must project `PROVIDER_DIAGNOSTIC` into activity using `HostActivityKind.PROVIDER_DIAGNOSTIC` or a deliberately added equivalent; title/summary must identify a non-fatal provider diagnostic and must not imply run failure. Raw provider text remains behind bounded payload refs.
- Outbox should not change behavior: because `PROVIDER_DIAGNOSTIC` is `EventClass.DIAGNOSTIC`, the existing terminal canonical-fact outbox filter must exclude it. Add or update a test proving it is not emitted as an outbox terminal item if an outbox projection test already covers diagnostic filtering.
- Split current warning sources into two implementation groups:
  - existing `RunnerProtocolErrorData` warnings from tool-call aggregation, such as unknown provider namespace/key, must become non-fatal Runner diagnostics;
  - current log-only adapter warnings, such as malformed usage in `sse_parser.py`/`non_stream_parser.py` and missing `Content-Type` in `runner.py`, must start emitting typed non-fatal diagnostics.
- Missing `Content-Type` diagnostics must cover both streaming and non-streaming HTTP 200 responses. Streaming may still use the existing SSE fallback; non-streaming must keep the JSON parse path but emit a diagnostic for the missing/empty header.
- Keep fatal cases on `RunnerProtocolErrorData` and ensure every fatal protocol error still ends in `RunnerDoneData(ERROR)`.
- Refactor context-overflow detection to return a typed result, for example `ContextOverflowDetection(kind=STRUCTURED_CODE | MESSAGE_MARKER_FALLBACK | NOT_OVERFLOW, diagnostic=...)`, rather than a bare bool.
- Carry context-overflow provenance across the full boundary: `error_classifier.py` produces `ContextOverflowDetection`; `runner.py` stores it in `_AttemptFailedTerminal` or directly in `RunnerHTTPErrorData.context_overflow_detection`; Agent reads that field when consuming `RunnerHTTPErrorData`; Agent emits `context_compaction_requested` only from typed `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`; if provenance is `MESSAGE_MARKER_FALLBACK`, Agent also emits a non-fatal Engine provider diagnostic before terminal closeout; Host persists that diagnostic as `PROVIDER_DIAGNOSTIC`.
- Tests must verify marker-fallback provenance reaches Host diagnostic output without becoming business truth: the same run must have canonical `CONTEXT_COMPACTION_REQUESTED` from typed HTTP code, a non-fatal `PROVIDER_DIAGNOSTIC` with source `message_marker_fallback`, no raw marker text in memory/final answer/evidence/compact prompt material, and no diagnostic-driven status transition.

Testing matrix:

- `source .venv/bin/activate && pytest tests/engine/contracts/test_runner_events.py tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase2.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_context_overflow_classifier.py -q`
- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_host_activity_event_projection.py -q`
- Coverage gate: touched Engine adapter/contract/Agent files and Host ingest/projection files at or above 80%.
- Source scans:
  - `rg -n "warnings: tuple\\[RunnerProtocolErrorData|RunnerProtocolErrorData\\(.*unknown_provider|unknown_gemini|usage_field_malformed|missing_content_type" dayu/engine`
  - `rg -n "CONTEXT_OVERFLOW_MESSAGE_MARKERS|message_marker_fallback|detect_context_overflow\\(" dayu tests`
  - `rg -n "runner\\.http\\.missing_content_type|usage_field_malformed" dayu/engine/runners/openai`
  - `rg -n "PROVIDER_DIAGNOSTIC|PROVIDER_PROTOCOL_ERROR|ENGINE_EVENT_DIAGNOSTIC" dayu/host/engine_ingest.py dayu/host/read_api.py dayu/host/tool_trace.py dayu/host/outbox.py tests/host`

README/docs trigger:

- `dayu/engine/README.md` and `docs/engine/design.md` must be updated because Runner/Engine event contract changes.
- `dayu/host/README.md` must be checked because Host EngineEvent ingest gains a new diagnostic event and projection behavior.
- `tests/README.md` must be checked because Engine/Host test layering changes.
- Section-specific design/doc decisions:
  - update `docs/engine/design.md` RunnerEvent and EngineEvent tables/sections that describe fatal protocol errors and diagnostics;
  - update `docs/host/design.md` EngineEvent ingest and diagnostic/canonical matrix sections to add `PROVIDER_DIAGNOSTIC`, state `EventClass.DIAGNOSTIC`, and state outbox/memory exclusion;
  - update `dayu/engine/README.md` only if its contract overview documents Runner/Engine events or provider adapter behavior;
  - update `dayu/host/README.md` only if its Agent update constraints say diagnostic projection or EventLog mapping belongs there;
  - update `tests/README.md` if new contract tests, Host projection tests, or source-scan validation rules become part of the test organization.

Residual risk:

- Provider diagnostics may increase EventLog diagnostic volume. Keep payload bounded and do not persist token deltas as durable truth.

### S3 - Typed Engine error codes and propagation audit

Goal: make known Engine error code semantics typed while preserving an explicit provider/runner-specific extension path.

Atomicity justification:

- Keep S3 as one atomic slice. The public dataclass field type change touches Engine contracts, Agent constructors, Engine run outcomes, Host ingest, Host read projections, Tool Trace, outbox/public events, tests, docs, and source-scan guard in one semantic contract. The project forbids compatibility facades, old aliases, and old string-only constructors; splitting contract typing from all in-repo callers would require either a compatibility layer or a temporarily broken main branch. Weak-typing guard and propagation audit are validation steps for the same type contract, not separate runtime behavior.

Non-goals:

- Do not force provider-specific protocol codes into a fake global enum.
- Do not make Host branch on provider-specific runner codes.
- Do not add compatibility wrappers for old string-only construction.

Candidate files:

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/__init__.py`
- `dayu/engine/agent.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/read_api.py`
- `dayu/host/tool_trace.py`
- `dayu/host/outbox.py`
- `tests/engine/contracts/test_runner_events.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_agent_phase2.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_host_event.py`
- `tests/host/test_read_api_terminal_policy.py`
- `tests/host/test_tool_trace_projection.py`
- `dayu/engine/README.md`
- `docs/engine/design.md`
- `tests/README.md`

Required changes:

- Define a typed Engine-owned error-code enum for Agent/Engine generated failures, including existing known codes such as `max_iterations_exceeded`, `runner_exception`, `runner_abnormal_stop`, `runner_error_done_without_detail`, `context_compaction_required`, `tool_call_not_enabled`, `missing_terminal`, `runner_tool_calls_missing`, `runner_tool_calls_finish_reason_mismatch`, `runner_empty_final_content`, `duplicate_tool_call_id`, `tool_executor_exception`, `tool_execution_timeout`, `tool_batch_outcome_mismatch`, `force_answer_empty`, `consecutive_failed_tool_batches`, and `continuation_tool_call_not_allowed`.
- Define a typed wrapper for provider/runner-specific codes, for example `RunnerSpecificErrorCode(value: str, source: RunnerSpecificErrorSource)`. It must trim and validate non-empty bounded text; reject whitespace-only and overly long values; use a closed source enum; and serialize only through the shared helper. Explicit empty provider/runner codes fail closed at the producer. Missing provider detail must use an Engine-owned fallback enum value, not an empty wrapper and not a fabricated provider code.
- Change Engine dataclasses to use the typed union. Add one helper to serialize error codes to durable strings for Host and public read models.
- Convert Agent constants and construction sites to enum members or wrapper constructors. Direct runner protocol pass-through must go through the wrapper.
- Update Host ingest/read/tool trace/outbox consumers to call the serialization helper at the boundary, not inspect raw strings or wrapper fields ad hoc.
- Add a concrete weak-typing guard. Minimum acceptable mechanism: a checked-in pytest or validation script invoked by tests/CI that scans Engine contract and Agent/Host construction sites. It must fail if any of these patterns remain outside explicitly allowed durable-serialization helpers:
  - `error_code: str` in `dayu/engine/contracts/`;
  - `RunFailedData(`, `EngineRunOutcomeFailed(`, `ProviderProtocolErrorData(`, or `RunnerProtocolErrorData(` with literal string `error_code="..."`;
  - Host consumers reading typed Engine error-code objects without calling the serializer at ingest/public projection boundary.
- Complete propagation audit in the implementation artifact: provider protocol code, Agent failure candidate, Engine `run_failed`, Host `RUN_FAILED`, Tool Trace failure metadata, public HostEvent failure, outbox terminal item, and memory exclusion must be consistent.

Current error-code propagation matrix to preserve while typing:

| Current site | Current shape | S3 action |
| --- | --- | --- |
| `dayu/engine/contracts/runner_events.py` `RunnerProtocolErrorData.error_code` | `str` fatal provider protocol code | Change to typed error-code union or provider-protocol-specific typed code; all constructors use enum/wrapper. |
| `dayu/engine/contracts/engine_events.py` `ProviderProtocolErrorData.error_code` | `str` fatal provider protocol code projected by Agent | Change to same typed representation and serialize at Host ingest. |
| `dayu/engine/contracts/engine_events.py` `RunFailedData.error_code` | `str` Engine-owned failure code | Change to `EngineRunErrorCode | RunnerSpecificErrorCode` or equivalent union. |
| `dayu/engine/contracts/agent_run.py` `EngineRunOutcomeFailed.error_code` | `str` outcome summary | Change to same typed union and update package exports. |
| `dayu/engine/agent.py` `_ERROR_*` constants and `RunFailedData(...)` constructors | string constants and pass-through strings | Replace with enum members or wrapper construction; `_fallback_error_message()` accepts typed code or serialized text by explicit design. |
| `dayu/host/engine_ingest.py` `data.error_code`, stream failure contexts, terminal payloads, `_provider_protocol_failure_metadata()` | copies strings into durable JSON and `provider_error_code` | Call shared serializer once at Host boundary; keep durable JSON as text after serialization. |
| `dayu/host/read_api.py` `error_code` / `provider_error_code` payload reads | reads durable text fields | Keep reading durable text; do not inspect Engine wrapper internals. |
| `dayu/host/tool_trace.py` failure metadata validators | expects durable text fields and provider failure metadata | Keep validating durable serialized text; ensure non-fatal diagnostics do not satisfy provider protocol failure metadata. |
| `dayu/host/outbox.py` and public Host events | terminal canonical payload text | Keep outbox based on Host durable serialized text only. |
| Memory / compact / evidence material | should not ingest diagnostics | Add validation that typed error codes and provider diagnostics do not enter LLM-facing material except through approved user-visible terminal summaries. |

Testing matrix:

- `source .venv/bin/activate && pytest tests/engine/contracts tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py -q`
- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_public_host_event.py tests/host/test_read_api_terminal_policy.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_projection.py -q`
- `source .venv/bin/activate && pytest tests/engine -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- Required wrapper tests: valid provider-specific value serializes once; empty string and whitespace-only values are rejected; missing provider detail uses an Engine enum fallback; overly long values are rejected; Host durable JSON contains the serializer output, not a dataclass repr.
- Coverage gate: all touched production files at or above 80% single-file coverage.
- Source scans:
  - `rg -n "error_code: str|error_code=\"|error_code=data\\.error_code" dayu/engine dayu/host tests/engine tests/host`
  - `rg -n "RunFailedData\\(|EngineRunOutcomeFailed\\(|ProviderProtocolErrorData\\(|RunnerProtocolErrorData\\(" dayu/engine tests/engine`
  - `rg -n "error_code|provider_error_code|failure_metadata" dayu/host/engine_ingest.py dayu/host/read_api.py dayu/host/tool_trace.py dayu/host/outbox.py tests/host`
  - `rg -n "_ERROR_|runner_error_done_without_detail|context_compaction_required|provider_error_code" dayu/engine dayu/host tests`

README/docs trigger:

- Update `dayu/engine/README.md` and `docs/engine/design.md` because public Engine contract changes.
- Check `dayu/host/README.md` for Host diagnostic/terminal payload wording.
- Update `tests/README.md` if new contract/weak-typing/source-scan coverage is added.
- Section-specific design/doc decisions:
  - update `docs/engine/design.md` EngineEvent/Agent run outcome sections that name `RunFailedData`, `ProviderProtocolErrorData`, or runner protocol error data;
  - update `docs/host/design.md` EngineEvent ingest and Host terminal payload sections only if they describe `error_code` / `provider_error_code` source semantics;
  - update `dayu/engine/README.md` if it documents public contract exports or Engine failure code semantics;
  - update `dayu/host/README.md` if it documents Host diagnostic/terminal payload behavior;
  - update `tests/README.md` if the weak-typing guard is added as a test/scenario class.

Residual risk:

- This changes a public dataclass type surface. Because the project forbids compatibility facades, update all in-repo callers/tests in the same slice and fail fast for old string construction.

## Validation Summary

Every implementation slice must finish with:

- focused tests listed in the slice;
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`;
- `git diff --check`;
- per-file coverage evidence for touched files, with each touched production file at or above 80%;
- source scans listed above;
- README trigger decision with direct reference to the target README update constraints;
- propagation audit confirming adapter-normalized facts are the single source of truth;
- no-LLM-facing diagnostic leakage validation. At minimum, implementation must add a focused test or source scan proving `PROVIDER_DIAGNOSTIC`, provider raw diagnostic text, `message_marker_fallback`, and provider diagnostic payload refs do not enter memory, final answer, accepted evidence material, compact material, or LLM-facing prompt messages. Suggested scan set:
  - `rg -n "PROVIDER_DIAGNOSTIC|message_marker_fallback|provider diagnostic|provider_diagnostic" dayu/config dayu/host dayu/engine tests`
  - `rg -n "memory|compact|evidence|prompt|FINAL_ANSWER|final_answer" dayu/host dayu/engine tests`
  The implementation artifact must explain any hits as internal diagnostics only or fix them.

Suggested aggregate validation after all slices:

```bash
source .venv/bin/activate
pytest tests/engine tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_public_host_event.py tests/host/test_read_api_terminal_policy.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

## Explicit Prohibitions

- Do not push provider wire exceptions downstream for Host to guess.
- Do not patch Host/Agent downstream with provider-string special cases.
- Do not add compatibility wrappers, old aliases, or old string-only constructors.
- Do not treat unknown wire `finish_reason` as `STOP`.
- Do not let context-overflow strings become hidden business truth.
- Do not put provider diagnostics into memory, final answer, evidence material, or LLM-facing prompt text.
- Do not use `extra payload` for explicit error-code, finish-reason, diagnostic, or context-overflow fields.

## Completion Report Format

Each implementation slice artifact must report:

- source findings closed or still open;
- exact files changed;
- tests, pyright, coverage, source scans, and README decisions;
- propagation audit result;
- residual risks classified as fixed, covered by later approved slice, assigned to later work unit, tracked by existing issue, or requiring user decision.

Final P3-D closeout cannot happen until all accepted P3-D findings are fixed, reviewed, re-reviewed, and no residual risk remains unclassified.
