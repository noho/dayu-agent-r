# WU-OBS-SIGNALS-01 Plan Re-Review

## Re-Review Metadata

- Work unit: `WU-OBS-SIGNALS-01`
- Gate: plan re-review
- Plan artifact: `docs/host/wu-obs-signals-p01-p04-plan.md`
- Original review artifact: `docs/reviews/wu-obs-signals-p01-p04-plan-review-mimo.md`
- Other review artifact: `docs/reviews/wu-obs-signals-p01-p04-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-obs-signals-p01-p04-plan-review-controller-adjudication.md`
- Plan fix artifact: `docs/reviews/wu-obs-signals-p01-p04-plan-fix-codex.md`
- Re-review timestamp: `20260611-192736`
- Re-review artifact path: `docs/reviews/wu-obs-signals-p01-p04-plan-rereview-mimo.md`

## Re-Review Scope

只验证 controller adjudication 中 accepted findings 是否已在 plan fix 中正确修复。不修改任何文件，不实现，不 commit/push/PR/merge，不进入其它 gate。

## Accepted Findings Verification

### MIMO-001 — P01 context_pressure 信号源：USAGE_REPORTED 缺少 budget decision 字段

- **验证项**: P01 USAGE_REPORTED.context_pressure 是否明确由 Engine ingest 使用 Host budget policy / BudgetEstimate / decide_context_budget 产生，Tool Trace 只复制。
- **Plan 修复文本**: line 168-170 明确写道：`EngineEventIngestor._append_projection_signal` must extend the Host-owned `USAGE_REPORTED` projection_signal payload with a `context_pressure` object. `budget_decision`, `input_budget_tokens`, `soft_threshold_tokens`, `hard_threshold_tokens`, `soft_threshold_exceeded`, `hard_threshold_exceeded`, and overage fields are produced during Engine ingest from Host context budget policy, `BudgetEstimate`, and `decide_context_budget`. Tool Trace projection only validates and copies `payload.context_pressure` into `trace_summary.context_pressure`. It must not recompute Host budget math, thresholds, or decisions.
- **判定**: **已修复**。明确区分了 production（Engine ingest 从 Host budget policy 产生）和 consumption（Tool Trace projection 只复制），实施 agent 不再需要自行选择路径。

---

### MIMO-002 — P02 tool_timing 改变 TOOL_RESULT_ACCEPTED payload contract

- **验证项**: tool_timing 是否明确为 additive payload contract extension，不是 schema/state-machine/ToolRuntime semantics change。
- **Plan 修复文本**: line 114-119 明确写道：These are additive payload contract extensions only. These additions do not add, remove, or change existing payload fields; existing consumers must tolerate the new optional objects. These additions are not SQLite schema changes, not state-machine changes, and not changes to `ToolRuntime` execution / governance / accept semantics. line 121 要求 consumer impact tests。
- **判定**: **已修复**。tool_timing 被显式标记为 additive EventLog payload field，不是 SQLite schema、不是 state-machine 变更，并要求 consumer impact 测试。

---

### MIMO-003 — P03 failure_metadata 改变 TOOL_RESULT_ACCEPTED payload contract

- **验证项**: failure_metadata 是否明确为 additive payload contract extension。
- **Plan 修复文本**: line 114-119 同 MIMO-002 覆盖了 `TOOL_RESULT_ACCEPTED` canonical fact 增加 `failure_metadata` 对象。line 121 要求 consumer impact tests。
- **判定**: **已修复**。与 MIMO-002 共享同一段 payload contract impact 说明，标记为 additive payload field。

---

### MIMO-004 — P04 partial_tool_call_signal 改变 PROVIDER_PROTOCOL_ERROR diagnostic payload contract

- **验证项**: partial_tool_call_signal 是否明确为 additive diagnostic payload contract extension。
- **Plan 修复文本**: line 114-117 明确列出 `PROVIDER_PROTOCOL_ERROR` diagnostic: add `partial_tool_call_signal` and `failure_metadata` objects。line 119 标注非 schema/state-machine/ToolRuntime 变更。
- **判定**: **已修复**。显式标记为 additive diagnostic payload field produced by Host ingest。

---

### MIMO-005 — EventLog payload contract 变更范围未解释

- **验证项**: 是否有专门的 payload contract impact section。
- **Plan 修复文本**: line 112-121 形成完整的 "EventLog payload contract" section，涵盖 canonical、diagnostic、projection_signal payload additions，明确列出 consumer impact 要求（recovery, resume, memory, audit, outbox, stream fanout, lifecycle state indexes），并说明不触发 schema migration / state transition change。
- **判定**: **已修复**。有独立 section 覆盖三类 payload additions 和 consumer impact。

---

### MIMO-006 — repair_hint bounding 缺少阈值

- **验证项**: bounded text threshold、truncation、digest 规则是否具体。
- **Plan 修复文本**: line 153 定义 `Private bounded text constant: _TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512`。line 154 详细说明：`repair_hint`, `cancel_hint`, and `cancel_message` store at most the first 512 Python string characters. For any non-null original text, store `*_sha256` over the full original UTF-8 text. If original length is `> 512`, set `*_truncated=true`; otherwise set `*_truncated=false`. If original text is `null`, the bounded value and digest are `null`, and `*_truncated=false`. line 155 要求 tests cover exact-boundary, over-boundary, digest-of-original, and null cases。
- **判定**: **已修复**。有具体常量值（512）、截断规则、digest 规则、null 处理规则和测试要求。

---

### DS-001 — P03 缺少显式 tool_cancelled variant

- **验证项**: tool_cancelled 是否为独立 failure_metadata variant。
- **Plan 修复文本**: line 288 列出 `tool_cancelled` 为 allowed variant。line 309-325 提供完整 JSON shape，包含 `cancel_reason`、`cancel_message`、`cancel_message_truncated`、`cancel_message_sha256`、`cancel_hint`、`cancel_hint_truncated`、`cancel_hint_sha256`。line 389 明确写道：For tool cancellations, set `failure_kind="tool_cancelled"` and use `cancel_reason` from `ToolCancelledOutcome.reason`. Do not mix cancellation into the `tool_failed` variant. line 528 要求 cancellation test 断言 `failure_kind="tool_cancelled"` 且 cancellation 不被表示为 `tool_failed`。
- **判定**: **已修复**。tool_cancelled 是独立 variant，有完整 shape、明确规则和测试要求。

---

### DS-002 — P01 CONTEXT_COMPACTION_ATTEMPT_REJECTED context pressure 未决定

- **验证项**: CONTEXT_COMPACTION_ATTEMPT_REJECTED 是否有 P01 minimal context_pressure shape。
- **Plan 修复文本**: line 219-232 提供完整的 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` context_pressure shape，包含 `schema_version`、`signal_source`、`status`、`operation_id`、`budget_after_attempted_compact`、`next_policy_decision`、`failure_category`、`repairable`。line 480 在 OBS-SIG-01 tests 中要求 Tool Trace projection tests assert context compaction attempt rejected rows expose `context_pressure`。
- **判定**: **已修复**。有独立的 minimal context_pressure shape，从现有 payload fields 派生。

---

### DS-003 — _trace_summary 签名扩展导致 God function

- **验证项**: _trace_summary 是否通过 grouped carrier 避免 God function。
- **Plan 修复文本**: line 443 写道：Add a grouped carrier for these optional objects, either a private `_TraceSummarySignals` dataclass or an extension of existing `_ToolTraceExtract`. line 444 明确写道：Do not add four independent optional parameters to `_trace_summary`; `OBS-SIG-00` must avoid growing the function into a God function.
- **判定**: **已修复**。要求使用 grouped carrier 而非独立参数，明确禁止 God function。

---

### DS-004 — failure_metadata 统一 shape 有耦合风险

- **验证项**: failure_metadata 是否为 closed discriminated union。
- **Plan 修复文本**: line 283 明确写道：`failure_metadata` is a closed discriminated union keyed by `failure_kind`. Every variant contains `schema_version`, `signal_source`, and `failure_kind`; each variant then exposes only fields meaningful for that failure kind. Analyzer consumers must first branch by `failure_kind` and only then read variant-specific fields. A `null` field means "not applicable or unavailable for this variant", not "business proof that the condition did not occur". line 285-292 列出 6 个 allowed variants。每个 variant 有独立 JSON shape 示例。
- **判定**: **已修复**。closed discriminated union 设计，有明确的 variant 枚举、variant-specific fields、null 语义和消费规则。

---

### DS-005 — OBS-SIG-00 caller 更新措辞模糊 slice 边界

- **验证项**: OBS-SIG-00 slice 是否只做 foundation/default signal wiring。
- **Plan 修复文本**: line 445 写道：Foundation slice only wires the grouped carrier with empty/default signal values and copies those values into `trace_summary` / cold JSONL when present. line 446 写道：P01-P04 slices populate actual signal values in their own source-specific extraction paths; `OBS-SIG-00` must not read payloads or compute signal content.
- **判定**: **已修复**。OBS-SIG-00 职责边界明确：只做 grouped carrier + empty/default，P01-P04 填充值。

---

### DS-006 — repair_hint threshold 缺失（与 MIMO-006 同）

- **判定**: **已修复**。由 MIMO-006 修复覆盖。

---

### DS-007 — policy_ref / digest LLM-facing 约束缺失

- **验证项**: policy_ref / digests / refs 是否标注为 diagnostic provenance only，非 LLM-facing business facts。
- **Plan 修复文本**: line 156 明确写道：`policy_ref`, `estimator_digest`, `operation_id`, diagnostic refs, payload refs, event refs, cursors, and digests are diagnostic provenance only. They are not business facts and must not be used as LLM reasoning grounds. Future LLM-facing analyzer output must translate them into business-readable semantics such as "budget policy allowed dispatch" or "tool cancellation reason unavailable", not expose naked refs/digests as conclusions.
- **判定**: **已修复**。明确标注为 diagnostic provenance only，禁止作为 LLM reasoning grounds，并要求 analyzer 输出翻译为业务可读语义。

---

## 必须检查项逐项验证

| # | 检查项 | 判定 | 证据位置 |
|---|---|---|---|
| 1 | P01 USAGE_REPORTED.context_pressure 明确由 Engine ingest 使用 Host budget policy / BudgetEstimate / decide_context_budget 产生，Tool Trace 只复制 | ✅ 已修复 | Plan line 168-170 |
| 2 | tool_timing / failure_metadata / partial_tool_call_signal 明确为 additive payload contract extensions，不是 schema/state-machine/ToolRuntime semantics change | ✅ 已修复 | Plan line 114-119 |
| 3 | tool_cancelled 为独立 failure_metadata variant | ✅ 已修复 | Plan line 288, 309-325, 389 |
| 4 | CONTEXT_COMPACTION_ATTEMPT_REJECTED 有 P01 minimal context_pressure shape | ✅ 已修复 | Plan line 219-232 |
| 5 | _trace_summary 通过 grouped carrier 避免 God function | ✅ 已修复 | Plan line 443-444 |
| 6 | failure_metadata 为 closed discriminated union | ✅ 已修复 | Plan line 283-292 |
| 7 | OBS-SIG-00 slice 只做 foundation/default signal wiring | ✅ 已修复 | Plan line 445-446 |
| 8 | bounded text threshold、truncation、digest 规则具体 | ✅ 已修复 | Plan line 153-155 |
| 9 | policy_ref / digests / refs 标注为 diagnostic provenance only，非 LLM-facing business facts | ✅ 已修复 | Plan line 156 |

## Finding 修复汇总

| Source | Finding | 判定 |
|---|---|---|
| MIMO-001 | P01 context_pressure 信号源不完整 | 已修复 |
| MIMO-002 | P02 tool_timing 改变 payload contract | 已修复 |
| MIMO-003 | P03 failure_metadata 改变 payload contract | 已修复 |
| MIMO-004 | P04 partial_tool_call_signal 改变 diagnostic payload contract | 已修复 |
| MIMO-005 | EventLog payload contract 变更范围未解释 | 已修复 |
| MIMO-006 | repair_hint bounding 缺少阈值 | 已修复 |
| DS-001 | P03 缺少显式 tool_cancelled variant | 已修复 |
| DS-002 | P01 CONTEXT_COMPACTION_ATTEMPT_REJECTED context pressure 未决定 | 已修复 |
| DS-003 | _trace_summary 签名扩展导致 God function | 已修复 |
| DS-004 | failure_metadata 统一 shape 有耦合风险 | 已修复 |
| DS-005 | OBS-SIG-00 caller 更新措辞模糊 slice 边界 | 已修复 |
| DS-006 | repair_hint threshold 缺失 | 已修复 |
| DS-007 | policy_ref / digest LLM-facing 约束缺失 | 已修复 |

## 新增 Blocker

无。plan fix 正确覆盖了所有 controller-accepted findings，未引入新的架构风险或设计矛盾。

## Residual Risk

| Risk | Owner / Destination | Notes |
|---|---|---|
| Additive payload fields 不影响现有 EventLog consumers | 实施阶段 OBS-SIG-00 ~ OBS-SIG-05 测试验证 | plan 已要求 consumer impact tests |
| P01 context compaction projection 需确认 source fields 可用 | 实施阶段 OBS-SIG-01；stop condition 已覆盖 | plan line 482 stop condition |
| Large-scale aggregation over unindexed trace_summary_json | WU-OBS-00 analyzer 或未来 retention/query work | plan line 134-136 正确延迟 |
| Bounded free-form text 敏感性风险 | WU-OBS-SIGNALS-01 P03 | plan 已有 truncation + digest rules |

## Overall Verdict

**pass**

所有 13 个 accepted findings 均已在 plan fix 中正确修复。plan 修复质量高，每个 finding 的修复都有明确的 plan 文本支撑，可直接对应到 plan 行号。修复未引入新的 blocker、架构矛盾或设计漂移。plan 可以进入 implementation gate。
