# WU-OBS-SIGNALS-01 Plan Gate

## Gate Metadata

- Work unit: `WU-OBS-SIGNALS-01`
- Combined scope: `WU-OBS-P01` + `WU-OBS-P02` + `WU-OBS-P03` + `WU-OBS-P04`
- Gate: plan only
- Artifact path: `docs/host/wu-obs-signals-p01-p04-plan.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control document: `docs/host/issues-implementation-control.md`
- Preflight observed branch: `phaseflow/wu-obs-signals-p01-p04`
- Preflight dirty state: `docs/host/issues-implementation-control.md` already modified by controller; this plan must not modify it.

## Goal

为 `WU-OBS-00` Tool Trace analyzer 补齐四类可直接消费、可聚合、可解释的 Host-owned signal contract：

1. P01: context pressure / budget snapshot signal。
2. P02: tool latency / duration signal。
3. P03: structured failure metadata / repair hint / policy block reason signal。
4. P04: Engine bounded partial tool-call summary 到 Host diagnostic / Tool Trace 的投影。

本 work unit 只产出生产路径中的稳定信号与测试夹具，使后续 analyzer 不需要从日志、文本错误、当前代码或 raw payload 反推事实。

## Motivation

第一性原理判断：动机成立，严重性评估合理。

- Analyzer 的输入应是持久化事实或派生 projection，而不是日志文本、进程内状态、当前 prompt builder 代码或当前 ToolRuntime 行为。
- 现有系统已经有 EventLog、projection signal、Tool Trace hot/cold projection 和 Engine bounded partial summary，因此缺口不是“大系统重建”，而是把已有同源事实整理成稳定、业务可读、结构化的 signal contract。
- 若不补这些信号，`WU-OBS-00` analyzer 会被迫做脆弱文本分类或把缺失信号误判为业务事实，违反 LLM-facing / trace material 自解释约束。

## Success Signal

- Tool Trace hot row 与 cold JSONL 的 `trace_summary` 中出现四类稳定字段，字段名、含义、缺失状态和 bounded/redaction 规则明确。
- `USAGE_REPORTED`、context compaction events、`TOOL_RESULT_ACCEPTED`、provider protocol diagnostic 都有 analyzer 可消费的结构化信号。
- P04 能区分：新 trace 明确无 partial、partial summary present、partial arguments digest present、raw payload present/absent；旧 trace 缺字段时后续 analyzer 可报告 limited signal。
- 受影响 Host tests 通过；pyright 通过；没有新增或扩散类型错误。

## Non-goals / Scope Boundary

- 不实现 `WU-OBS-00` analyzer 本体。
- 不实现 prompt-based diagnostics、operator bundle export、trace 目录 analyzer CLI。
- 不把 Tool Trace、Audit、Outbox、timeline 或 memory snapshot 提升为 Host durable truth。
- 不改变 Run / Attempt / recovery / resume / memory / compaction 状态迁移。
- 不保存 raw provider arguments、raw prompt、完整 messages、完整 tool result 或敏感 payload。
- 不让 Engine 理解 Host context budget policy。
- 不改变 `ToolRuntime` accept / governance / execution 语义；只增加 accepted payload 的诊断 projection 字段。
- 不新增 Engine public contract，除非发现现有 `PartialToolCallSummary` 不足；若不足，触发 stop condition。

## Design Document Alignment

Host alignment:

- `docs/host/design.md:1355-1369` 定义 EventLog canonical fact 才是治理真源，diagnostic / projection_signal 只能用于排错和 projection，不能成为业务事实。
- `docs/host/design.md:1652-1663` 定义 Tool Trace 是 EventLog 派生 projection；hot summary 可保存 tool name、digest、policy decision、error code、duration、attempt refs 等诊断字段。
- `docs/host/design.md:1665-1693` 定义 Tool Trace 对 runner-call / projection signal 的消费边界是 read-only signal，不得读取旧 provider request、EngineRunner 内存或当前 prompt builder 反推历史输入。
- `docs/host/design.md:3118` 定义 Context Governance 不直接写 tool trace，只 append canonical facts 或 projection_signal，由 projection 消费。

Engine alignment:

- `docs/engine/design.md:423-483` 定义 EngineEvent stream 是一次 run 的中性事件边界；调用方需要 recovery、audit、usage、tool trace 或 memory 时，必须在 Engine 外部 ingest 成自己的 durable facts。
- `docs/engine/design.md:487-501` 定义 Engine 不计算 Host budget，不理解 Host context policy，只表达 provider context overflow。
- `docs/engine/design.md:303-325` 与 `dayu/engine/contracts/partial_tool_call.py:11-28` 已有 `PartialToolCallSummary`，且不包含 raw argument payload，满足 P04 bounded/redacted 来源要求。

## Direct Code Evidence

- `dayu/host/tool_trace.py:270-321` 的 `ToolTraceProjectionConsumer` 统一消费 canonical / diagnostic / projection_signal，是四类信号的共同落点。
- `dayu/host/tool_trace.py:461-475` 当前 projection_signal 只走 `_extract_usage_trace`，说明新增 context pressure signal 应在该路径补齐，而不是新增 sink。
- `dayu/host/tool_trace.py:1024-1092` 的 `_trace_summary` 是 hot summary JSON 的统一构造点，适合加入四类业务可读结构化字段。
- `dayu/host/engine_ingest.py:2649-2700` 的 `_append_projection_signal` 已写 `USAGE_REPORTED`，包含 usage observation 与 estimator digest，但缺 soft/hard threshold、budget decision 等 analyzer 等价 context pressure summary。
- `dayu/host/context_budget.py:168-187` 与 `dayu/host/context_budget.py:454-468` 已有 `BudgetEstimate` 与 `decide_context_budget`，是 P01 的 Host 同源预算事实。
- `dayu/contracts/tool_result.py:26-37` 的 `ToolResultMeta` 已有 `started_at` / `finished_at`，是 P02 duration 的最稳定来源。
- `dayu/host/tool_runtime.py:3735-3802` 当前 `TOOL_RESULT_ACCEPTED` payload 写入 tool id、digest、policy、diagnostic refs，但未显式写入 timing / failure metadata。
- `dayu/host/tool_runtime.py:5841-5914` 已能把 outcome meta 投影到 JSON digest 输入，说明 metadata 来源存在，但还不是 Tool Trace 可消费字段。
- `dayu/host/engine_ingest.py:2828-2879` 当前 provider protocol diagnostic 只写 `partial_tool_call_count`，未投影 `PartialToolCallSummary` 详情。
- `dayu/host/durable/tool_trace.py:117-170` 与 `dayu/host/durable/tool_trace.py:350-430` 表明 hot table 已有 `trace_summary_json`，无需为本 WU 新增列。

## Affected Files / Modules

Expected implementation files:

- `dayu/host/engine_ingest.py`
- `dayu/host/tool_trace.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/context_budget.py` only if implementation chooses to move reusable budget-summary serialization to budget owner; otherwise leave unchanged.
- `dayu/host/context_events.py` only if existing compact payload validators must accept a new nested summary; preferred plan does not require this.
- `dayu/host/durable/tool_trace.py` only if typed query helper must expose parsed signals; preferred plan keeps SQLite schema unchanged and reads `trace_summary`.
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_context_compact_events.py`

Expected non-affected files:

- `dayu/engine/contracts/partial_tool_call.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/host/tool_runtime.py` execution / accept semantics beyond payload projection
- SQLite schema files, unless implementation discovers analyzer requires indexed query fields rather than scan/read of `trace_summary_json`.

## Contract / Schema / State-machine / Public Interface Changes

Public Engine contract:

- No change expected. P04 must consume existing `ProviderProtocolErrorData.partial_tool_calls`.
- Stop if existing bounded partial summary cannot express required analyzer signal without extending Engine public contract.

Host public command/API:

- No change expected. No new command, no new Run / Attempt status, no new lifecycle transition.

EventLog payload contract:

- Add or populate structured diagnostic fields inside existing Host-owned EventLog payloads. These are additive payload contract extensions only:
  - `USAGE_REPORTED` projection signal: add Host-owned `context_pressure` object.
  - `TOOL_RESULT_ACCEPTED` canonical fact: add `tool_timing` and `failure_metadata` objects.
  - `PROVIDER_PROTOCOL_ERROR` diagnostic: add `partial_tool_call_signal` and `failure_metadata` objects.
- These additions do not add, remove, or change existing payload fields; existing consumers must tolerate the new optional objects.
- These additions are not SQLite schema changes, not state-machine changes, and not changes to `ToolRuntime` execution / governance / accept semantics.
- Context compaction canonical payloads already contain failure and budget fields; implementation derives Tool Trace `context_pressure` / `failure_metadata` in projection without changing context event payload schema.
- Consumer impact: recovery, resume, memory, audit, outbox, stream fanout, and lifecycle state indexes must continue to consume only their existing fields and ignore these additive diagnostic objects. Tests must cover at least the touched producer/projection paths and assert no Run / Attempt status side effect for projection_signal / diagnostic rows.

Tool Trace projection contract:

- Add four optional top-level objects under `trace_summary`:
  - `context_pressure`
  - `tool_timing`
  - `failure_metadata`
  - `partial_tool_call_signal`
- These are read-only projection fields. They must not be used by recovery, resume, memory projection, RunInputBuilder, ToolRuntime execution, or status transitions.

SQLite durable schema:

- No schema change expected.
- Reason: `host_tool_trace_hot.trace_summary_json` already stores structured JSON; current query helpers can page by run/provider/diagnostic and analyzer can aggregate by scanning trace rows. No new indexed query predicate is required for P01-P04.
- If implementation discovers a required operator query cannot be served without an index, stop and ask for schema decision. Any schema change must be full fresh schema, no compatibility reader.

State machine:

- No state-machine change. Projection signal and diagnostic rows remain non-governing.

## Implementation Decisions

### Shared Projection Shape

All new signal objects use:

- `schema_version`: integer, first value `1`.
- `signal_source`: stable source event type or payload owner.
- explicit `status` when a signal can be unavailable.
- no raw prompt, raw provider arguments, full messages, full tool result, API headers, or sensitive payload.
- bounded text only for fields explicitly listed below; long text must be truncated with a digest and `*_truncated=true`.
- Private bounded text constant: `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512`.
- Bounded text rule: `repair_hint`, `cancel_hint`, and `cancel_message` store at most the first 512 Python string characters. For any non-null original text, store `*_sha256` over the full original UTF-8 text. If original length is `> 512`, set `*_truncated=true`; otherwise set `*_truncated=false`. If original text is `null`, the bounded value and digest are `null`, and `*_truncated=false`.
- Tests must cover exact-boundary, over-boundary, digest-of-original, and null cases for bounded text.
- `policy_ref`, `estimator_digest`, `operation_id`, diagnostic refs, payload refs, event refs, cursors, and digests are diagnostic provenance only. They are not business facts and must not be used as LLM reasoning grounds. Future LLM-facing analyzer output must translate them into business-readable semantics such as "budget policy allowed dispatch" or "tool cancellation reason unavailable", not expose naked refs/digests as conclusions.

### P01 Context Pressure / Budget Snapshot

Stable sources:

- `USAGE_REPORTED` projection signal from `EngineEventIngestor._append_projection_signal`.
- `BudgetEstimate` and `decide_context_budget` from `dayu.host.context_budget`.
- Existing context compaction canonical payloads from `dayu.host.context_events`.

`USAGE_REPORTED` payload contract decision:

- `EngineEventIngestor._append_projection_signal` must extend the Host-owned `USAGE_REPORTED` projection_signal payload with a `context_pressure` object.
- `budget_decision`, `input_budget_tokens`, `soft_threshold_tokens`, `hard_threshold_tokens`, `soft_threshold_exceeded`, `hard_threshold_exceeded`, and overage fields are produced during Engine ingest from Host context budget policy, `BudgetEstimate`, and `decide_context_budget`.
- Tool Trace projection only validates and copies `payload.context_pressure` into `trace_summary.context_pressure`. It must not recompute Host budget math, thresholds, or decisions.
- Estimate-unavailable and usage-invalid states are also represented inside the `context_pressure` object so downstream consumers do not infer absence as "no pressure".

Projection JSON shape under `trace_summary.context_pressure`:

```json
{
  "schema_version": 1,
  "signal_source": "USAGE_REPORTED",
  "status": "observed",
  "policy_ref": "policy-ref",
  "estimator_digest": "sha256:...",
  "estimated_input_tokens": 1200,
  "input_budget_tokens": 100000,
  "soft_threshold_tokens": 80000,
  "hard_threshold_tokens": 95000,
  "soft_threshold_exceeded": false,
  "hard_threshold_exceeded": false,
  "budget_decision": "allow_dispatch",
  "overage_reason": null,
  "prompt_tokens": 1230,
  "completion_tokens": 10,
  "total_tokens": 1240,
  "prompt_token_delta": 30
}
```

For estimate unavailable, keep the same keys with token fields `null`, `status="estimate_unavailable"` or `status="usage_invalid"`, and `budget_decision="unknown"`.

For `CONTEXT_COMPACTION_FAILED`, derive from existing payload fields:

```json
{
  "schema_version": 1,
  "signal_source": "CONTEXT_COMPACTION_FAILED",
  "status": "compaction_failed",
  "policy_ref": "policy-ref-or-null",
  "estimator_digest": "sha256-or-null",
  "operation_id": "operation-id",
  "trigger_source": "reactive",
  "budget_reason": "provider_overflow",
  "budget_after_compact": null,
  "budget_after_attempted_compact": 180,
  "fallback_action": "dispatch",
  "fallback_policy_decision": "recent_window_budget_passed",
  "retry_repair_budget_exhausted": true
}
```

For `CONTEXT_COMPACTION_ATTEMPT_REJECTED`, also derive a minimal `context_pressure` shape from existing payload fields. This is required so analyzer can follow the attempted compact budget chain without parsing raw context event payload:

```json
{
  "schema_version": 1,
  "signal_source": "CONTEXT_COMPACTION_ATTEMPT_REJECTED",
  "status": "compaction_attempt_rejected",
  "operation_id": "operation-id",
  "budget_after_attempted_compact": 180,
  "next_policy_decision": "retry_or_fallback",
  "failure_category": "quality_check_failed",
  "repairable": true
}
```

Analyzer count fields such as compaction count or continuation count must be aggregate results computed by analyzer over rows, not per-row invented counters.

### P02 Tool Latency / Duration

Stable source:

- `ToolResultMeta.started_at` and `ToolResultMeta.finished_at` on completed / failed / cancelled tool outcomes.

Producer payload shape on `TOOL_RESULT_ACCEPTED`:

```json
{
  "tool_timing": {
    "schema_version": 1,
    "status": "available",
    "started_at": "2026-06-11T00:00:00+00:00",
    "finished_at": "2026-06-11T00:00:01.250000+00:00",
    "duration_ms": 1250,
    "duration_source": "tool_result_meta"
  }
}
```

When meta is absent:

```json
{
  "tool_timing": {
    "schema_version": 1,
    "status": "missing_tool_result_meta",
    "started_at": null,
    "finished_at": null,
    "duration_ms": null,
    "duration_source": null
  }
}
```

Projection copies this object to `trace_summary.tool_timing`. Missing meta must not fail tool accept or projection; it is a limited signal for analyzer.

### P03 Structured Failure Metadata

Stable sources:

- `ToolResultFailure.error`, `ToolResultFailure.hint`, `ToolCancelledOutcome.reason`, `ToolCancelledOutcome.hint`.
- `ToolPolicyDecision.kind`, `reason_code`, `message`.
- Context compaction failure / attempt rejected payloads.
- Provider protocol error payload.

`failure_metadata` is a closed discriminated union keyed by `failure_kind`. Every variant contains `schema_version`, `signal_source`, and `failure_kind`; each variant then exposes only fields meaningful for that failure kind. Analyzer consumers must first branch by `failure_kind` and only then read variant-specific fields. A `null` field means "not applicable or unavailable for this variant", not "business proof that the condition did not occur".

Allowed variants:

- `tool_failed`
- `tool_cancelled`
- `policy_blocked`
- `provider_protocol_error`
- `context_compaction_attempt_rejected`
- `context_compaction_failed`

`tool_failed` variant:

```json
{
  "schema_version": 1,
  "signal_source": "TOOL_RESULT_ACCEPTED",
  "failure_kind": "tool_failed",
  "error_code": "tool_error_code",
  "repair_hint": "bounded hint",
  "repair_hint_truncated": false,
  "repair_hint_sha256": "sha256:...",
  "diagnostic_refs": ["diag-ref"]
}
```

`tool_cancelled` variant:

```json
{
  "schema_version": 1,
  "signal_source": "TOOL_RESULT_ACCEPTED",
  "failure_kind": "tool_cancelled",
  "cancel_reason": "cancelled_by_user",
  "cancel_message": "bounded cancellation message",
  "cancel_message_truncated": false,
  "cancel_message_sha256": "sha256:...",
  "cancel_hint": "bounded cancellation hint",
  "cancel_hint_truncated": false,
  "cancel_hint_sha256": "sha256:...",
  "diagnostic_refs": ["diag-ref"]
}
```

`policy_blocked` variant:

```json
{
  "schema_version": 1,
  "signal_source": "TOOL_RESULT_ACCEPTED",
  "failure_kind": "policy_blocked",
  "policy_decision_kind": "deny",
  "policy_block_reason": "reason_code",
  "diagnostic_refs": ["diag-ref"]
}
```

`provider_protocol_error` variant:

```json
{
  "schema_version": 1,
  "signal_source": "PROVIDER_PROTOCOL_ERROR",
  "failure_kind": "provider_protocol_error",
  "provider_error_code": "invalid_tool_arguments",
  "diagnostic_refs": ["diag-ref"]
}
```

`context_compaction_attempt_rejected` variant:

```json
{
  "schema_version": 1,
  "signal_source": "CONTEXT_COMPACTION_ATTEMPT_REJECTED",
  "failure_kind": "context_compaction_attempt_rejected",
  "failure_category": "quality_check_failed",
  "repairable": true,
  "next_policy_decision": "retry_or_fallback",
  "budget_after_attempted_compact": 180,
  "diagnostic_refs": ["diag-ref"]
}
```

`context_compaction_failed` variant:

```json
{
  "schema_version": 1,
  "signal_source": "CONTEXT_COMPACTION_FAILED",
  "failure_kind": "context_compaction_failed",
  "failure_reason": "budget_still_exceeded",
  "policy_decision": "fallback",
  "retryable": false,
  "attempt_count": 2,
  "retry_repair_budget_exhausted": true,
  "fallback_action": "dispatch",
  "fallback_policy_decision": "recent_window_budget_passed",
  "diagnostic_refs": ["diag-ref"]
}
```

Rules:

- For successful tool results, `failure_metadata` may be `null`.
- For governed policy blocks, set `failure_kind="policy_blocked"` and use `policy_block_reason=policy_decision.reason_code`.
- For tool cancellations, set `failure_kind="tool_cancelled"` and use `cancel_reason` from `ToolCancelledOutcome.reason`. Do not mix cancellation into the `tool_failed` variant.
- For provider protocol errors, set `failure_kind="provider_protocol_error"` and `provider_error_code=data.error_code`.
- For context compaction attempt rejection, set `failure_kind="context_compaction_attempt_rejected"`, include `failure_category`, `repairable`, `next_policy_decision`, and `budget_after_attempted_compact`.
- For context compaction failed, set `failure_kind="context_compaction_failed"`, include `failure_reason`, `policy_decision`, `retryable`, `attempt_count`, `retry_repair_budget_exhausted`, fallback fields, and diagnostic refs.
- `repair_hint`, `cancel_hint`, and `cancel_message` must use `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512`, include `*_truncated`, and include `*_sha256` over the full original text when non-null.
- Do not store full tool failure `message` as analyzer fact. Cancellation message is allowed only through bounded `cancel_message`. If a future analyzer needs other user-facing message snippets, that is a separate redaction design decision.

### P04 Partial Tool-call Summary

Stable source:

- `ProviderProtocolErrorData.partial_tool_calls`, whose members are `PartialToolCallSummary`.

Producer payload shape on `PROVIDER_PROTOCOL_ERROR`:

```json
{
  "partial_tool_call_signal": {
    "schema_version": 1,
    "signal_source": "PROVIDER_PROTOCOL_ERROR",
    "partial_tool_call_count": 1,
    "summary_status": "present",
    "raw_payload_present": true,
    "partial_tool_calls": [
      {
        "tool_call_index": 0,
        "tool_call_id": "bounded-id-or-null",
        "name_fragment": "bounded-name-or-null",
        "arguments_byte_size": 42,
        "arguments_sha256": "sha256:...",
        "arguments_present": true
      }
    ]
  }
}
```

Rules:

- `_append_provider_protocol_error` produces `partial_tool_call_signal` as an additive diagnostic payload field from `ProviderProtocolErrorData.partial_tool_calls`.
- Tool Trace projection copies the additive diagnostic payload field; it must not rehydrate provider raw payload or infer details not present in `PartialToolCallSummary`.
- New trace with empty tuple must write `summary_status="none"` and `partial_tool_call_count=0`.
- Old trace without `partial_tool_call_signal` will be analyzer limited signal, not proof of no partial.
- `arguments_sha256` and byte size are allowed; raw arguments are forbidden.
- `tool_call_id` and `name_fragment` must remain bounded by Engine contract; Host must not unbound or rehydrate them.

## Implementation Slices

### OBS-SIG-00 Shared Tool Trace Signal Foundation

- Objective: add shared constants/helpers for the four signal objects and copy them into `trace_summary` / cold JSONL consistently.
- Allowed files/modules: `dayu/host/tool_trace.py`, `tests/host/test_tool_trace_projection.py`, `tests/host/test_tool_trace_queries.py`.
- Exact changes:
  - Add private field constants for `context_pressure`, `tool_timing`, `failure_metadata`, `partial_tool_call_signal`.
  - Add a grouped carrier for these optional objects, either a private `_TraceSummarySignals` dataclass or an extension of existing `_ToolTraceExtract`.
  - Do not add four independent optional parameters to `_trace_summary`; `OBS-SIG-00` must avoid growing the function into a God function.
  - Foundation slice only wires the grouped carrier with empty/default signal values and copies those values into `trace_summary` / cold JSONL when present.
  - P01-P04 slices populate actual signal values in their own source-specific extraction paths; `OBS-SIG-00` must not read payloads or compute signal content.
  - Ensure cold line uses the same `trace_summary`.
- Data flow: EventLog payload -> `_extract_*_trace` -> `_ToolTraceExtract.trace_summary` -> hot row / cold JSONL.
- Error handling / invariants:
  - If a named signal field exists but is not a JSON object or `null`, raise `HostDurableError`.
  - Projection failure remains projection failure only; it must not change EventLog source facts.
- Non-goals: no new SQLite column, no analyzer, no new query API.
- Tests / validation:
  - Add projection test proving all four optional signal keys are copied when present.
  - Add projection test proving empty/default grouped signal carrier does not emit misleading signal objects.
  - Existing runner-call and provider query tests must keep passing.
- Completion signal: new keys appear in hot row and cold JSONL for synthetic payloads.
- Stop condition: if adding optional summary objects requires changing `ToolTraceHotRow` schema instead of `trace_summary_json`, stop for schema decision.

### OBS-SIG-01 P01 Context Pressure Signal

- Objective: make usage and context compaction rows expose analyzer-consumable context pressure / budget snapshot summaries.
- Allowed files/modules: `dayu/host/engine_ingest.py`, `dayu/host/tool_trace.py`, optionally `dayu/host/context_budget.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_tool_trace_projection.py`, `tests/host/test_context_compact_events.py`.
- Exact changes:
  - In `EngineEventIngestor._append_projection_signal`, include `context_pressure` object in `USAGE_REPORTED` payload.
  - Produce usage `context_pressure` fields from Host context budget policy, `BudgetEstimate`, and `decide_context_budget`; do not duplicate budget math.
  - In Tool Trace projection, copy `context_pressure` from usage payload without recalculating thresholds or decisions.
  - For context compaction canonical events, derive `context_pressure` from existing payload fields instead of changing context event builders unless tests prove a required field is unavailable.
- Data flow:
  - `UsageReportedData` -> Host usage observation diagnostic -> budget estimate / decision -> EventLog `USAGE_REPORTED` projection_signal -> Tool Trace `trace_summary.context_pressure`.
  - Context compaction canonical fact -> Tool Trace derived `trace_summary.context_pressure`.
- Error handling / invariants:
  - Missing budget policy, missing input event, or unreadable input remain non-failing usage projection with `status="estimate_unavailable"`.
  - Invalid usage tokens remain `status="usage_invalid"`.
  - Engine never receives or computes Host budget thresholds.
- Non-goals: no proactive compact implementation, no analyzer aggregate counts, no current Run decision rewrites based on post-call usage.
- Tests / validation:
  - `test_usage_reported_is_projection_signal_without_state_change` asserts threshold fields and budget decision.
  - Existing unavailable/invalid usage tests assert status and null threshold fields.
  - Tool Trace projection tests assert usage, context compaction failed, and context compaction attempt rejected rows expose `context_pressure`.
- Completion signal: analyzer fixture can read budget status without reconstructing policy math.
- Stop condition: if a required P01 field cannot be sourced from `BudgetEstimate`, usage diagnostic, or existing context compaction payloads, stop and ask whether Host design truth should be extended.

### OBS-SIG-02 P02 Tool Duration Signal

- Objective: emit stable per-tool duration from `ToolResultMeta` and project it to Tool Trace.
- Allowed files/modules: `dayu/host/tool_runtime.py`, `dayu/host/tool_trace.py`, `tests/host/test_tool_trace_projection.py`; implementation gate should inspect existing ToolRuntime tests before editing them if a direct producer-path test is added.
- Exact changes:
  - Add private helper in `tool_runtime.py` to extract `ToolResultMeta` from completed / failed / cancelled outcomes.
  - Add `tool_timing` object to `TOOL_RESULT_ACCEPTED` payload as an additive EventLog payload contract extension.
  - Compute `duration_ms` as non-negative integer from `finished_at - started_at`.
  - Copy `tool_timing` to `trace_summary.tool_timing`.
- Data flow: Tool outcome meta -> ToolRuntime accepted payload -> EventLog canonical fact -> Tool Trace hot/cold summary -> analyzer aggregate.
- Error handling / invariants:
  - Missing meta yields `status="missing_tool_result_meta"`, not failure.
  - Negative duration should be impossible because `ToolResultMeta` validates it; if malformed payload is encountered in projection, fail closed with `HostDurableError`.
  - Do not time execution in Tool Trace or Engine; no wall-clock guessing.
- Non-goals: no change to timeout, cancellation, accept retry, duplicate governance, or ToolExecutor scheduling.
- Tests / validation:
  - Producer test must prove `TOOL_RESULT_ACCEPTED` payload includes `tool_timing` for meta present and missing.
  - Consumer impact test must prove existing consumers tolerate the additive `tool_timing` field and no state-machine side effect is introduced.
  - Projection test must prove hot/cold rows expose `tool_timing`.
  - Aggregation itself belongs to WU-OBS-00 analyzer, not this slice.
- Completion signal: trace row has `duration_ms` for meta-present outcomes and explicit limited signal for meta-missing outcomes.
- Stop condition: if production payload cannot include timing without changing ToolRuntime execution semantics, stop.

### OBS-SIG-03 P03 Structured Failure Metadata

- Objective: emit structured failure metadata for tool failures, tool cancellations, policy blocks, provider protocol errors, context compaction attempt rejections, and context compaction failures.
- Allowed files/modules: `dayu/host/tool_runtime.py`, `dayu/host/engine_ingest.py`, `dayu/host/tool_trace.py`, `tests/host/test_tool_trace_projection.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_context_compact_events.py`.
- Exact changes:
  - Add `failure_metadata` to `TOOL_RESULT_ACCEPTED` payload for failed, cancelled, and governed-policy outcomes as an additive EventLog payload contract extension.
  - Add provider protocol `failure_metadata` in `_append_provider_protocol_error` as an additive diagnostic payload contract extension.
  - Derive context compaction attempt rejection / failure metadata in Tool Trace projection from existing context event payload fields.
  - Bound `repair_hint`, `cancel_hint`, and `cancel_message` length and include truncation flag plus digest. Do not store raw failure message body as a classification dependency.
- Data flow:
  - Tool outcome / policy decision -> ToolRuntime payload -> Tool Trace summary.
  - Provider protocol error -> Engine ingest diagnostic -> Tool Trace summary.
  - Context compaction canonical facts -> Tool Trace summary.
- Error handling / invariants:
  - Successful outcomes have `failure_metadata=null`.
  - Policy block reason must come from `ToolPolicyDecision.reason_code`, not from parsing message text.
  - Provider error code must come from Engine event data, not raw provider payload.
  - Context repairability must come from context compaction payload fields.
- Non-goals: no new failure taxonomy for analyzer, no prompt-based remediation, no provider payload preservation.
- Tests / validation:
  - Tool failure / cancellation / policy block projection tests.
  - Cancellation test must assert `failure_kind="tool_cancelled"` with `cancel_reason` and must assert cancellation is not represented as `tool_failed`.
  - Bounded text tests must cover `repair_hint`, `cancel_hint`, and `cancel_message` at null, exact 512-character, and over-512-character boundaries, including digest of the original text.
  - Consumer impact test must prove existing consumers tolerate additive `failure_metadata`.
  - Provider protocol error mapping test for `provider_error_code`.
  - Context compaction failed / attempt rejected projection tests.
- Completion signal: analyzer fixture can classify failure kind from structured fields without text parsing.
- Stop condition: if repair hint or policy block reason would require parsing raw payload or free-form message, stop and classify as unavailable/limited signal instead.

### OBS-SIG-04 P04 Provider Protocol Partial Tool-call Projection

- Objective: project Engine bounded partial tool-call summaries into Host diagnostic payload and Tool Trace summary.
- Allowed files/modules: `dayu/host/engine_ingest.py`, `dayu/host/tool_trace.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_tool_trace_projection.py`, `tests/host/test_tool_trace_queries.py`.
- Exact changes:
  - In `_append_provider_protocol_error`, serialize every `PartialToolCallSummary` into additive diagnostic payload field `partial_tool_call_signal.partial_tool_calls`.
  - Keep `partial_tool_call_count` for existing coarse diagnostic compatibility inside the same payload.
  - Add `summary_status`: `none` for new empty tuple, `present` for non-empty tuple.
  - Include `raw_payload_present` from descriptor presence, not payload contents.
  - Copy `partial_tool_call_signal` to Tool Trace `trace_summary`.
- Data flow: Engine `ProviderProtocolErrorData.partial_tool_calls` -> Host diagnostic EventLog -> Tool Trace hot/cold summary -> analyzer fixture.
- Error handling / invariants:
  - Do not persist raw arguments.
  - Do not infer malformed JSON from `arguments_sha256`; expose bytes/digest and let analyzer classify limited/failure with error code context.
  - Empty tuple is a positive new signal of no partials; absent field is historical limited signal.
- Non-goals: no Engine parser changes, no provider stream replay, no raw payload export.
- Tests / validation:
  - Engine ingest mapping test covers empty partial, partial present, arguments digest present, raw payload absent/present.
  - Consumer impact test must prove existing diagnostic consumers tolerate additive `partial_tool_call_signal`.
  - Tool Trace projection/query test confirms provider-request query returns partial signal.
- Completion signal: P04 fixture can distinguish absent field, none, and present bounded summaries.
- Stop condition: if `PartialToolCallSummary` lacks a required field for analyzer and adding it would change Engine public contract, stop.

### OBS-SIG-05 Integration, Docs Decision, Validation

- Objective: close the signal contract loop without entering analyzer implementation.
- Allowed files/modules: tests listed above; relevant README files only after reading their Agent update constraints.
- Exact changes:
  - Add compact fixture/assertion helpers inside existing test files; do not create analyzer module.
  - Ensure all new helper functions/classes have Chinese docstrings and strict typed signatures.
  - Check README triggers and update only if the target README says this signal-contract change is in scope.
- Data flow: production payload tests + projection tests + query helper tests.
- Error handling / invariants:
  - Tests must assert no state transition side effects for usage/provider diagnostic paths.
  - Tests must assert cold JSONL matches hot `trace_summary`.
- Non-goals: no commit, push, PR, review, deepreview, or analyzer report artifact.
- Tests / validation:
  - Run affected pytest and pyright commands listed below.
- Completion signal: all tests and pyright pass, README decision recorded in implementation report.
- Stop condition: any validation failure that indicates design truth, SQLite schema, Engine public contract, ToolRuntime semantics, or analyzer body is required.

## Required Tests And Validation Commands

Run after implementation, from repository root:

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_engine_ingest_mapping.py tests/host/test_context_compact_events.py
```

If implementation adds or updates dedicated ToolRuntime producer-path tests, include that file in the pytest command after reading the existing test file.

Run pyright:

```bash
source .venv/bin/activate && pyright
```

Expected assertions:

- `USAGE_REPORTED` remains `projection_signal` and does not change Run / Attempt status.
- Provider protocol errors remain `diagnostic` and do not change active Run state.
- `TOOL_RESULT_ACCEPTED` signal fields are projected through Tool Trace; ToolRuntime execution semantics remain unchanged.
- Hot row and cold JSONL contain identical `trace_summary` for the new fields.
- Existing runner-call reconstruction tests still pass.

## Docs Decision

This plan artifact itself only writes `docs/host/wu-obs-signals-p01-p04-plan.md`; it does not trigger README updates.

Expected implementation README checks under AGENTS.md:

- Modifying `dayu/host/` requires checking `dayu/host/README.md` and following its Agent update constraints before deciding whether to update.
- Modifying `tests/` requires checking `tests/README.md` and following its Agent update constraints before deciding whether to update.
- No expected `dayu/engine/` modification; if Engine public contract changes become necessary, stop first instead of updating `dayu/engine/README.md`.
- No expected layer-boundary or assembly change; `dayu/README.md` update is not expected.
- No expected `dayu/config/` or `dayu/fins/` change.

Expected README outcome: likely no README content update if changes stay within Tool Trace signal fields and tests, but implementation gate must verify target README constraints before final closeout.

## Why Combined Implementation Is Not Overdesign

P01-P04 share the same source-to-projection path:

```text
Engine / ToolRuntime / Context canonical fact or diagnostic
-> Host EventLog canonical / diagnostic / projection_signal
-> ToolTraceProjectionConsumer
-> hot trace_summary_json + cold JSONL
-> future analyzer fixture
```

Implementing them separately would duplicate field validation, bounded/redaction rules, and projection tests across the same `ToolTraceProjectionConsumer` boundary. The combined plan still keeps slices small and independently verifiable: shared projection foundation, P01, P02, P03, P04, integration. It does not add a generic observability framework, a new analyzer abstraction, a new storage schema, or new Engine/ToolRuntime semantics.

## Risks / Open Questions / Residual Risks

- Risk: `ToolResultMeta` is optional, so historical or third-party tools may lack duration.
  - Owner/destination: current WU P02 signal contract; represent as `status="missing_tool_result_meta"` and let WU-OBS-00 report limited signal.
- Risk: context compaction events may not include every threshold field needed for exact old analyzer parity.
  - Owner/destination: current WU P01; use available `BudgetEstimate` fields for usage and compact event fields for compact lifecycle. If exact threshold is required for compact events and unavailable, stop for Host design decision.
- Risk: provider partial arguments cannot prove JSON malformed because raw arguments are intentionally not saved.
  - Owner/destination: WU-OBS-00 analyzer; classify from error code plus bounded byte/digest presence, and report limited signal where malformed proof requires raw arguments.
- Risk: `repair_hint`, `cancel_hint`, and `cancel_message` are free-form and may contain long or sensitive text from tools.
  - Owner/destination: current WU P03; bound/truncate these fields, store truncation flags and original-text digests, and avoid storing failure message bodies as analyzer dependency.
- Risk: JSON fields inside `trace_summary_json` are not indexed, so large trace aggregation may be slower.
  - Owner/destination: WU-OBS-00 analyzer or future retention/query work. Current WU does not add SQLite schema because no required indexed predicate has been established.

No blocking open questions at plan gate based on current evidence.

## Completion Report Format

Implementation closeout should report:

- Artifact path for implementation report.
- Slices completed: `OBS-SIG-00` through completed slice id.
- Files changed.
- Signal fields added, grouped by P01/P02/P03/P04.
- Tests run and result.
- Pyright result.
- README decision and files checked/updated.
- Residual risks with owner/destination.
- Explicit statement that no analyzer, no schema migration, no Engine public contract extension, no ToolRuntime execution semantic change, no commit/push/PR occurred unless separately authorized.

## Plan Gate Conclusion

Plan gate passes. The work unit is valid and can proceed to implementation only after explicit approval for the next gate. Current plan does not require Host/Engine design truth edits, SQLite durable schema change, Engine public contract beyond existing bounded partial summary, ToolRuntime execution semantic change, or analyzer implementation.
