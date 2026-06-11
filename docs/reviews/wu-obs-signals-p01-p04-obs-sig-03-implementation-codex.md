# WU-OBS-SIGNALS-01 OBS-SIG-03 Implementation

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-03 / P03 Structured Failure Metadata`
- Agent: AgentCodex
- Gate: implementation only; no commit, no push, no PR, no code review.

Implemented additive `failure_metadata` signal production and Tool Trace projection for:

- `TOOL_RESULT_ACCEPTED`: `tool_failed`, `tool_cancelled`, `policy_blocked`
- `PROVIDER_PROTOCOL_ERROR`: `provider_protocol_error`
- Tool Trace derived context events: `context_compaction_attempt_rejected`, `context_compaction_failed`

## First-principles Motivation

The motivation is valid. Tool Trace analyzer input must be durable facts or read-only projections, not text logs or free-form error messages. Before this slice, relevant source facts existed, but failure classification still required consumers to infer from outcome text, policy messages, provider raw payloads, or context payload details. That would make analyzer behavior brittle and could turn diagnostic text into false business facts.

The accepted plan is the right path for this slice because it adds bounded, host-owned, read-only signals without changing ToolRuntime governance, Engine public contract, SQLite schema, scheduling, memory, recovery, or analyzer taxonomy.

## Direct Evidence

- `dayu/host/tool_runtime.py` already receives typed `ToolFailedOutcome`, `ToolCancelledOutcome`, `ToolPolicyDecision`, and diagnostic refs before writing `TOOL_RESULT_ACCEPTED`.
- `ToolResultFailure.error` / `hint` and `ToolCancelledOutcome.reason` / `message` / `hint` provide same-source failure fields. Full failure `message` is intentionally not used for `tool_failed`.
- `ToolPolicyDecision.reason_code` is available and is used directly as `policy_block_reason`; no policy message parsing is used.
- `dayu/host/engine_ingest.py` receives `ProviderProtocolErrorData.error_code`; `provider_error_code` is sourced from that field, not raw provider payload.
- Existing context compaction payloads already contain failure category, repairability, policy decision, retryability, attempt count, budget, fallback and diagnostic refs, so Tool Trace can derive context failure metadata without changing context event schema.
- `dayu/host/tool_trace.py` is the common projection consumer for canonical, diagnostic and projection signal events.

## Changes

- Added `failure_metadata` to `ToolAcceptResult` and `TOOL_RESULT_ACCEPTED` payloads.
- Added closed discriminated-union producer helpers for `tool_failed`, `tool_cancelled`, and `policy_blocked`.
- Added 512 Python-string-character bounded text handling for `repair_hint`, `cancel_hint`, and `cancel_message`, including full original UTF-8 sha256 digest and `*_truncated`.
- Added provider protocol `failure_metadata` in `_append_provider_protocol_error`.
- Added Tool Trace closed-union validation and fail-closed behavior via `HostDurableError`.
- Added Tool Trace derivation for context compaction attempt rejected / failed metadata from existing payload fields.
- Updated Host and tests README only where their Agent update constraints said current implemented host/test boundaries are in scope.
- Updated control document status to implementation completed and waiting controller.

## Tests

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_engine_ingest_mapping.py tests/host/test_context_compact_events.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py
```

Result: 185 passed.

Passed:

```bash
source .venv/bin/activate && pyright
```

Result: 0 errors.

Coverage added:

- Tool failure producer and projection.
- Tool cancellation producer and projection, including `failure_kind="tool_cancelled"` and not `tool_failed`.
- Policy block producer and projection using `reason_code`.
- Bounded text null / exact 512 / over 512 and full original digest for `repair_hint`, `cancel_hint`, `cancel_message`.
- Provider protocol mapping using Engine event `error_code`; test raw payload uses a different code to prove it is not parsed.
- Context compaction failed / attempt rejected projection metadata.
- Malformed `failure_metadata` closed-union fields fail closed.
- Successful tool result payload keeps `failure_metadata=null`.

## README Decision

- `dayu/host/README.md`: updated one current-boundary sentence because Host tool trace now implements structured read-only signals.
- `tests/README.md`: updated the Host testing layer description because tests now cover failure metadata Tool Trace signals.

## Risks / Not Covered

- No analyzer taxonomy, prompt remediation, P04 partial tool-call signal, Engine public contract, SQLite schema, ToolExecutor scheduling, or ToolRuntime governance changes were made.
- `cancel_message` is non-null in current typed `ToolCancelledOutcome`; null handling is still accepted and tested at Tool Trace projection boundary for malformed/historical signal tolerance.
- This slice does not add indexed queries for `failure_metadata`; analyzer can scan existing Tool Trace rows as planned.
