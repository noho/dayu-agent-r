# WU-OBS-SIGNALS-01 Plan Re-Review

## Re-Review Metadata

- **Work unit**: `WU-OBS-SIGNALS-01`
- **Current gate**: plan re-review
- **Plan artifact**: `docs/host/wu-obs-signals-p01-p04-plan.md`
- **Original review artifact (DS)**: `docs/reviews/wu-obs-signals-p01-p04-plan-review-ds.md`
- **Other review artifact (MiMo)**: `docs/reviews/wu-obs-signals-p01-p04-plan-review-mimo.md`
- **Controller adjudication**: `docs/reviews/wu-obs-signals-p01-p04-plan-review-controller-adjudication.md`
- **Plan fix artifact (Codex)**: `docs/reviews/wu-obs-signals-p01-p04-plan-fix-codex.md`
- **Re-review artifact**: `docs/reviews/wu-obs-signals-p01-p04-plan-rereview-ds.md`
- **Re-review timestamp**: 2026-06-11T19:27:33
- **Design truth**: `docs/host/design.md`, `docs/engine/design.md`

## Re-Review Scope

本 re-review 仅验证 controller adjudication 中所有 accepted findings 是否已在 plan fix 中修复。不评审 plan 的其它方面，不修改任何文件，不实现，不 commit/push/PR/merge，不进入其它 gate。

## Mandatory Checklist Verification

### 1. P01 USAGE_REPORTED.context_pressure 是否明确由 Engine ingest 使用 Host budget policy / BudgetEstimate / decide_context_budget 产生，Tool Trace 只复制

- **位置**: Plan line 166-171
- **证据**: 
  - Line 168: "`EngineEventIngestor._append_projection_signal` must extend the Host-owned `USAGE_REPORTED` projection_signal payload with a `context_pressure` object."
  - Line 169: "`budget_decision`, `input_budget_tokens`, `soft_threshold_tokens`, `hard_threshold_tokens`, `soft_threshold_exceeded`, `hard_threshold_exceeded`, and overage fields are **produced during Engine ingest from Host context budget policy, `BudgetEstimate`, and `decide_context_budget`**."
  - Line 170: "Tool Trace projection **only validates and copies** `payload.context_pressure` into `trace_summary.context_pressure`. It **must not recompute** Host budget math, thresholds, or decisions."
  - Line 171: "Estimate-unavailable and usage-invalid states are also represented inside the `context_pressure` object."
  - OBS-SIG-01 line 466-467: "Produce usage `context_pressure` fields from Host context budget policy, `BudgetEstimate`, and `decide_context_budget`; do not duplicate budget math."
  - OBS-SIG-01 line 468: "In Tool Trace projection, copy `context_pressure` from usage payload **without recalculating thresholds or decisions**."
- **Verdict**: ✅ 已修复。Engine ingest 负责生产 context_pressure（使用 Host budget policy / BudgetEstimate / decide_context_budget），Tool Trace 只做 validate + copy，不重新计算。

### 2. tool_timing / failure_metadata / partial_tool_call_signal 是否明确为 additive payload contract extensions，不是 schema/state-machine/ToolRuntime semantics change

- **位置**: Plan line 113-121, OBS-SIG-02 line 490, OBS-SIG-03 line 512-513, OBS-SIG-04 line 541
- **证据**:
  - Line 113: "These are **additive payload contract extensions only**."
  - Line 114-117: 列出三个变更点：`USAGE_REPORTED` projection signal 加 `context_pressure`；`TOOL_RESULT_ACCEPTED` canonical fact 加 `tool_timing` 和 `failure_metadata`；`PROVIDER_PROTOCOL_ERROR` diagnostic 加 `partial_tool_call_signal` 和 `failure_metadata`。
  - Line 118: "These additions **do not add, remove, or change existing payload fields**; existing consumers must tolerate the new optional objects."
  - Line 119: "These additions are **not SQLite schema changes, not state-machine changes, and not changes to `ToolRuntime` execution / governance / accept semantics**."
  - Line 120-121: 明确 consumer impact：recovery、resume、memory、audit、outbox、stream fanout、lifecycle state indexes 只消费各自现有字段，忽略 additive diagnostic objects。
  - OBS-SIG-02 line 490: "Add `tool_timing` object to `TOOL_RESULT_ACCEPTED` payload as an **additive EventLog payload contract extension**."
  - OBS-SIG-03 line 512: "Add `failure_metadata` to `TOOL_RESULT_ACCEPTED` payload ... as an **additive EventLog payload contract extension**."
  - OBS-SIG-04 line 541: "serialize every `PartialToolCallSummary` into **additive diagnostic payload field**."
- **Verdict**: ✅ 已修复。三个字段均明确标注为 additive payload contract extensions，非 schema/state-machine/ToolRuntime semantics change。

### 3. tool_cancelled 是否为独立 failure_metadata variant

- **位置**: Plan line 285-292 (variants list), Plan line 309-325 (variant shape), Plan line 389 (rules)
- **证据**:
  - Line 287: 允许的 variants 列表中显式包含 `tool_cancelled`。
  - Line 309-325: 完整的 `tool_cancelled` variant shape，包含 `failure_kind="tool_cancelled"`、`cancel_reason`、`cancel_message`（bounded）、`cancel_message_truncated`、`cancel_message_sha256`、`cancel_hint`（bounded）、`cancel_hint_truncated`、`cancel_hint_sha256`、`diagnostic_refs`。
  - Line 389: "For tool cancellations, set `failure_kind="tool_cancelled"` and use `cancel_reason` from `ToolCancelledOutcome.reason`. **Do not mix cancellation into the `tool_failed` variant.**"
  - OBS-SIG-03 line 528: "Cancellation test must assert `failure_kind="tool_cancelled"` with `cancel_reason` and must assert cancellation is **not represented as `tool_failed`**."
- **Verdict**: ✅ 已修复。`tool_cancelled` 是独立的 `failure_kind` variant，有完整的 shape、规则和测试要求，且明确禁止混入 `tool_failed`。

### 4. CONTEXT_COMPACTION_ATTEMPT_REJECTED 是否有 P01 minimal context_pressure shape

- **位置**: Plan line 219-232
- **证据**:
  - Line 219: "For `CONTEXT_COMPACTION_ATTEMPT_REJECTED`, also derive a **minimal `context_pressure` shape** from existing payload fields. This is required so analyzer can follow the attempted compact budget chain without parsing raw context event payload."
  - Line 221-231: 完整的 JSON shape，包含 `schema_version`、`signal_source`、`status="compaction_attempt_rejected"`、`operation_id`、`budget_after_attempted_compact`、`next_policy_decision`、`failure_category`、`repairable`。
  - OBS-SIG-01 line 480: "Tool Trace projection tests assert usage, context compaction failed, and **context compaction attempt rejected rows expose `context_pressure`**."
- **Verdict**: ✅ 已修复。`CONTEXT_COMPACTION_ATTEMPT_REJECTED` 有 P01 minimal `context_pressure` shape，字段来自已有 payload fields，shape 精简但覆盖 analyzer 追踪预算链所需的关键字段。

### 5. _trace_summary 是否通过 grouped carrier 避免 God function

- **位置**: Plan OBS-SIG-00 line 443-446
- **证据**:
  - Line 443: "Add a **grouped carrier** for these optional objects, either a private `_TraceSummarySignals` dataclass or an extension of existing `_ToolTraceExtract`."
  - Line 444: "**Do not add four independent optional parameters to `_trace_summary`**; `OBS-SIG-00` must avoid growing the function into a God function."
  - Line 445: "Foundation slice only wires the grouped carrier with empty/default signal values and copies those values into `trace_summary` / cold JSONL when present."
  - Line 446: "P01-P04 slices populate actual signal values in their own source-specific extraction paths; `OBS-SIG-00` must not read payloads or compute signal content."
- **Verdict**: ✅ 已修复。`_trace_summary` 通过 grouped carrier（`_TraceSummarySignals` dataclass 或 `_ToolTraceExtract` 扩展）传递四个信号对象，而非四个独立可选参数，明确避免了 God function。

### 6. failure_metadata 是否为 closed discriminated union

- **位置**: Plan line 283-392
- **证据**:
  - Line 283: "`failure_metadata` is a **closed discriminated union** keyed by `failure_kind`. Every variant contains `schema_version`, `signal_source`, and `failure_kind`; each variant then exposes only fields meaningful for that failure kind."
  - Line 284: "A `null` field means 'not applicable or unavailable for this variant', not 'business proof that the condition did not occur'."
  - Line 285-292: 列出全部 6 个 closed variants：`tool_failed`、`tool_cancelled`、`policy_blocked`、`provider_protocol_error`、`context_compaction_attempt_rejected`、`context_compaction_failed`。
  - Line 296-383: 每个 variant 有独立的 shape，仅包含该 variant 有意义的字段。
  - Line 385-394: 完整的消费规则：analyzer 必须先 branch by `failure_kind`，再读 variant-specific 字段。
- **Verdict**: ✅ 已修复。`failure_metadata` 是 closed discriminated union，6 个 variants 全部封闭列出且不可扩展；每个 variant 只有其有意义的字段；null 语义明确（表示不适用/不可用，非业务证明）。

### 7. OBS-SIG-00 slice 是否只做 foundation/default signal wiring

- **位置**: Plan OBS-SIG-00 line 439-457
- **证据**:
  - Line 440: Allowed files/modules 限定为 `dayu/host/tool_trace.py` 和测试文件。
  - Line 443: 加 grouped carrier。
  - Line 444: 禁止加四个独立参数。
  - Line 445: "Foundation slice **only wires the grouped carrier with empty/default signal values** and copies those values into `trace_summary` / cold JSONL when present."
  - Line 446: "P01-P04 slices populate actual signal values in their own source-specific extraction paths; **OBS-SIG-00 must not read payloads or compute signal content**."
  - Line 452 (non-goals): "no new SQLite column, no analyzer, no new query API."
- **Verdict**: ✅ 已修复。OBS-SIG-00 只做 foundation：加常量、加 grouped carrier、wire empty/default values、copy 到 trace_summary/cold JSONL。不做 payload 读取，不做 signal content 计算。P01-P04 各自 slice 负责填充实际值。

### 8. bounded text threshold、truncation、digest 规则是否具体

- **位置**: Plan line 153-155
- **证据**:
  - Line 153: "Private bounded text constant: **`_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512`**."
  - Line 154: 完整规则——"`repair_hint`, `cancel_hint`, and `cancel_message` store at most the **first 512 Python string characters**. For any non-null original text, store `*_sha256` over the full original UTF-8 text. If original length is `> 512`, set `*_truncated=true`; otherwise set `*_truncated=false`. If original text is `null`, the bounded value and digest are `null`, and `*_truncated=false`."
  - Line 155: "Tests must cover **exact-boundary, over-boundary, digest-of-original, and null cases** for bounded text."
  - P03 rule line 393: "`repair_hint`, `cancel_hint`, and `cancel_message` must use `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512`, include `*_truncated`, and include `*_sha256` over the full original text when non-null."
- **Verdict**: ✅ 已修复。具体阈值 512 chars，完整 truncation/digest/null 规则，exact-boundary/over-boundary/null 测试覆盖。

### 9. policy_ref / digests / refs 是否标注为 diagnostic provenance only，非 LLM-facing business facts

- **位置**: Plan line 156
- **证据**:
  - Line 156: "`policy_ref`, `estimator_digest`, `operation_id`, diagnostic refs, payload refs, event refs, cursors, and digests are **diagnostic provenance only**. They are **not business facts** and **must not be used as LLM reasoning grounds**. Future LLM-facing analyzer output must translate them into business-readable semantics such as 'budget policy allowed dispatch' or 'tool cancellation reason unavailable', not expose naked refs/digests as conclusions."
- **Verdict**: ✅ 已修复。所有内部治理标识（policy_ref、estimator_digest、operation_id、refs、digests、cursors）明确标注为 diagnostic provenance only，不得作为 LLM-facing business facts，并给出了 LLM-facing 翻译的示例。

---

## Accepted Findings Verification Summary

| Finding ID | Source | Severity | Description | Status |
|---|---|---|---|---|
| MIMO-001 | AgentMiMo | 高 | P01 context_pressure source incomplete / budget decision fields not explicitly sourced | ✅ 已修复 |
| MIMO-002 | AgentMiMo | 中 | P02 tool_timing changes TOOL_RESULT_ACCEPTED payload contract | ✅ 已修复 |
| MIMO-003 | AgentMiMo | 中 | P03 failure_metadata changes TOOL_RESULT_ACCEPTED payload contract | ✅ 已修复 |
| MIMO-004 | AgentMiMo | 中 | P04 partial_tool_call_signal changes PROVIDER_PROTOCOL_ERROR diagnostic payload contract | ✅ 已修复 |
| MIMO-005 | AgentMiMo | 低 | EventLog payload contract change scope underexplained | ✅ 已修复 |
| MIMO-006 | AgentMiMo | 低 | repair_hint bounding lacks threshold | ✅ 已修复 |
| DS-001 | AgentDS | 高 | P03 missing explicit tool_cancelled variant | ✅ 已修复 |
| DS-002 | AgentDS | 中 | P01 CONTEXT_COMPACTION_ATTEMPT_REJECTED context pressure treatment undecided | ✅ 已修复 |
| DS-003 | AgentDS | 中 | _trace_summary signature expansion risks God function | ✅ 已修复 |
| DS-004 | AgentDS | 中 | Unified failure_metadata shape has coupling risk | ✅ 已修复 |
| DS-005 | AgentDS | 低 | OBS-SIG-00 caller update wording can blur slice boundaries | ✅ 已修复 |
| DS-006 | AgentDS | 低 | repair_hint threshold missing (duplicate of MIMO-006) | ✅ 已修复 |
| DS-007 | AgentDS | 低 | policy_ref / digest LLM-facing constraint missing | ✅ 已修复 |

**所有 13 个 accepted findings 均为 已修复。无部分修复、未修复、证据失效。**

---

## New Blocker Check

在验证 accepted findings 过程中，未发现新增 blocker。Plan 当前的规格已足够 code-generation-ready。

具体检查：
- Plan 未引入新的未定义概念或未指定行为。
- Plan 的 stop conditions 完整且合理——每个 slice 都有明确的 stop 触发条件。
- Plan 的 non-goals 清晰且与 controller adjudication 的 preserved decisions 一致。
- 没有发现 contradiction：所有 fix 之间逻辑一致，无 conflict。
- Plan 的 combined WU 决策未在 fix 中被削弱或逆转。

---

## Residual Risks

以下 risks 在 plan 中已有 owner/destination，plan fix 未引入新的 residual risk：

| Risk | Owner/Destination | Status |
|---|---|---|
| ToolResultMeta optional → historical tools lack duration | P02 (handled: `status="missing_tool_result_meta"`) | 不变 |
| Context compaction events may lack threshold fields | P01 (stop-if-missing) | 不变 |
| Provider partial arguments cannot prove JSON malformed | WU-OBS-00 analyzer | 不变 |
| repair_hint/cancel_hint/cancel_message may contain sensitive text | P03 (512-char truncation + digest) | 阈值已明确 |
| trace_summary_json not indexed → slow aggregation | WU-OBS-00 analyzer / future work | 不变 |
| Additive payload fields may affect existing EventLog consumers | Implementation gate (consumer impact tests required) | 测试要求已在 plan 中明确 |
| Bounded free-form text sensitivity | P03 (truncation + digest rules) | 规则已具体化 |

---

## Overall Verdict

**Re-review verdict: PASS**

所有 13 个 controller-accepted findings 均已修复。Plan 现在满足 code-generation-ready 标准：
- P01 context_pressure 的 source 链路明确（Engine ingest 生产，Tool Trace 复制）。
- 所有 additive payload contract extensions 明确标注，不与 schema/state-machine/ToolRuntime semantics 混淆。
- tool_cancelled 是独立 failure_metadata variant。
- CONTEXT_COMPACTION_ATTEMPT_REJECTED 有 P01 minimal context_pressure shape。
- _trace_summary 通过 grouped carrier 避免 God function。
- failure_metadata 是 closed discriminated union（6 variants）。
- OBS-SIG-00 slice 只做 foundation/default wiring。
- bounded text 阈值（512 chars）、truncation、digest 规则具体可测试。
- policy_ref / digests / refs 标注为 diagnostic provenance only。

无新增 blocker，无新增 residual risk。Plan 可进入 implementation gate。

---

*Re-review completed 2026-06-11T19:27:33. No plan files, control documents, code, or review artifacts were modified.*
