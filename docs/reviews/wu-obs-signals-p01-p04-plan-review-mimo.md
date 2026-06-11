# WU-OBS-SIGNALS-01 Plan Review

## Review Metadata

- Review target: `docs/host/wu-obs-signals-p01-p04-plan.md`
- Work unit: `WU-OBS-SIGNALS-01` (P01 + P02 + P03 + P04 combined signal-contract implementation)
- Gate: plan review
- Review timestamp: `20260611-191541`
- Review artifact path: `docs/reviews/wu-obs-signals-p01-p04-plan-review-mimo.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control document: `docs/host/issues-implementation-control.md`

## Review Scope

从第一性原理判断合并实施 P01-P04 是否成立、是否过度设计、是否严格服务 WU-OBS-00 analyzer 前置信号、是否遵守 Host/Engine 分层、信号源是否同源可测试、trace_summary JSON shape 是否业务可读自解释、是否存在隐藏 schema migration / public contract change / state-machine change / extra payload / Any/object/无类型签名 / 兼容 wrapper / magic string / README/test/pyright 缺口、slices 是否足够 code-generation-ready、residual risks 是否都有 owner/destination。

## Assumptions Tested

1. 合并实施 P01-P04 不是过度设计，因为四类信号共享同一 source-to-projection path。
2. 计划严格服务 WU-OBS-00 analyzer 前置信号，不实现 analyzer 本体。
3. Engine 不理解 Host budget；Tool Trace 不是 durable truth；ToolRuntime accept/execution 语义不改变。
4. 四类信号的 stable source 同源且可测试。
5. trace_summary JSON shape 业务可读、自解释、bounded/redacted。
6. 不存在隐藏 schema migration、public contract change、state-machine change。
7. slices 足够 code-generation-ready。
8. residual risks 都有 owner/destination。

## Findings

### 001-未修复-高-P01 context_pressure 信号源不完整：USAGE_REPORTED 缺少 budget decision 字段

- **位置**: OBS-SIG-01 P01 Context Pressure Signal，plan 第 160-182 行
- **问题类型**: 契约缺失
- **当前写法**: plan 声称 `USAGE_REPORTED` projection signal 的 `context_pressure` 对象包含 `budget_decision`、`soft_threshold_exceeded`、`hard_threshold_exceeded` 等字段
- **反例/失败场景**: 实际 `_append_projection_signal` 写入的 `USAGE_REPORTED` payload（`engine_ingest.py:2681-2700`）只包含 `prompt_tokens`、`completion_tokens`、`total_tokens`、`policy_ref`、`estimator_digest`、`estimated_input_tokens`、`usage_observation_status`、`usage_observation_digest`、`prompt_token_delta`。它不包含 `budget_decision`、`soft_threshold_exceeded`、`hard_threshold_exceeded`、`input_budget_tokens`、`soft_threshold_tokens`、`hard_threshold_tokens`。
- **为什么有问题**: plan 声称的 `context_pressure` shape 包含 16 个字段，但当前 `USAGE_REPORTED` payload 只有 12 个字段，缺少 4 个关键字段。实施 agent 必须要么修改 `_append_projection_signal` 增加这些字段（改变 EventLog payload contract），要么从 `BudgetEstimate` / `decide_context_budget` 重新计算（在 Tool Trace projection 层引入 budget 计算逻辑，违反 Engine 不理解 Host budget 的约束）。plan 没有明确说明这个 gap 如何处理。
- **直接证据**: `engine_ingest.py:2681-2700` 的 payload dict 与 plan 第 162-181 行的 JSON shape 对比。
- **影响**: 实施 agent 可能被迫在 Tool Trace projection 层重新计算 budget decision，违反 Host/Engine 分层；或者修改 EventLog payload contract，触发 plan 未预期的 schema change。
- **建议改法和验证点**: plan 应明确：(a) 在 `_append_projection_signal` 中增加 budget decision 字段到 `USAGE_REPORTED` payload（需要修改 EventLog payload contract），或 (b) 在 Tool Trace projection 层从已有字段派生（需要说明派生逻辑），或 (c) 简化 `context_pressure` shape 只包含当前 payload 已有的字段。
- **修复风险（低/中/高）**: 中
- **严重程度（高）**: 实施 agent 可能被迫做 plan 未预期的架构决策。

### 002-未修复-中-P02 tool_timing 信号源：ToolResultMeta 可能为 None

- **位置**: OBS-SIG-02 P02 Tool Duration Signal，plan 第 208-244 行
- **问题类型**: 状态机漏洞
- **当前写法**: plan 声称 `TOOL_RESULT_ACCEPTED` payload 应包含 `tool_timing` 对象，从 `ToolResultMeta.started_at` / `ToolResultMeta.finished_at` 派生
- **反例/失败场景**: `ToolResultMeta` 是可选的（`ToolResultSuccess.meta: ToolResultMeta | None`、`ToolResultFailure.meta: ToolResultMeta | None`、`ToolCancelledOutcome.meta: ToolResultMeta | None`）。当 meta 为 None 时，plan 声称写入 `status="missing_tool_result_meta"`，但这需要在 `_build_tool_result_accepted_payload` 中增加条件分支。
- **为什么有问题**: plan 的 stop condition 说"if production payload cannot include timing without changing ToolRuntime execution semantics, stop"，但没有明确说明如何判断是否改变了 execution semantics。当前 `_build_tool_result_accepted_payload` 不包含 timing 字段，增加它需要修改 payload contract。
- **直接证据**: `tool_runtime.py:3757-3802` 的 payload dict 不包含 `tool_timing` 字段；`ToolResultMeta` 是可选的（`tool_result.py:26-36`）。
- **影响**: 实施 agent 可能不确定是否需要修改 payload contract，或者如何处理 meta=None 的情况。
- **建议改法和验证点**: plan 应明确：(a) `tool_timing` 是新增的 payload 字段（修改 EventLog payload contract），或 (b) 在 Tool Trace projection 层从已有 `ToolResultMeta` 派生（需要说明从哪里获取 meta）。验证点：确认 meta=None 时的行为。
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: 实施 agent 可能需要额外决策，但不阻塞。

### 003-未修复-中-P03 failure_metadata 信号源：需要修改 TOOL_RESULT_ACCEPTED payload

- **位置**: OBS-SIG-03 P03 Structured Failure Metadata，plan 第 246-281 行
- **问题类型**: 契约缺失
- **当前写法**: plan 声称 `TOOL_RESULT_ACCEPTED` payload 应包含 `failure_metadata` 对象，从 `ToolResultFailure.error`、`ToolResultFailure.hint`、`ToolCancelledOutcome.reason`、`ToolCancelledOutcome.hint`、`ToolPolicyDecision.kind`、`reason_code`、`message` 派生
- **反例/失败场景**: 当前 `_build_tool_result_accepted_payload`（`tool_runtime.py:3757-3802`）不包含 `failure_metadata` 字段。增加它需要修改 EventLog payload contract。plan 声称"add `failure_metadata` to `TOOL_RESULT_ACCEPTED` payload"，但没有明确说明这是修改 EventLog payload contract。
- **为什么有问题**: plan 的 non-goal 说"不改变 ToolRuntime accept / governance / execution 语义；只增加 accepted payload 的诊断 projection 字段"，但增加 `failure_metadata` 到 `TOOL_RESULT_ACCEPTED` payload 实际上是修改 EventLog payload contract，这可能影响 recovery、resume、memory、audit 等消费方。
- **直接证据**: `tool_runtime.py:3757-3802` 的 payload dict 不包含 `failure_metadata` 字段。
- **影响**: 实施 agent 可能不确定是否需要修改 EventLog payload contract，或者如何确保不影响现有消费方。
- **建议改法和验证点**: plan 应明确：(a) `failure_metadata` 是新增的 EventLog payload 字段（修改 payload contract），或 (b) 在 Tool Trace projection 层从已有字段派生（需要说明从哪里获取 failure 信息）。验证点：确认不影响 recovery、resume、memory、audit 等消费方。
- **修复风险（低/中/高）**: 中
- **严重程度（中）**: 实施 agent 可能需要额外决策，但不阻塞。

### 004-未修复-中-P04 partial_tool_call_signal：需要修改 PROVIDER_PROTOCOL_ERROR payload

- **位置**: OBS-SIG-04 P04 Provider Protocol Partial Tool-call Projection，plan 第 283-318 行
- **问题类型**: 契约缺失
- **当前写法**: plan 声称 `PROVIDER_PROTOCOL_ERROR` payload 应包含 `partial_tool_call_signal` 对象，从 `ProviderProtocolErrorData.partial_tool_calls` 派生
- **反例/失败场景**: 当前 `_append_provider_protocol_error`（`engine_ingest.py:2848-2862`）只写入 `partial_tool_call_count`，不包含 `partial_tool_call_signal` 对象。增加它需要修改 EventLog payload contract。
- **为什么有问题**: plan 声称"add `partial_tool_call_signal` to `PROVIDER_PROTOCOL_ERROR` payload"，但没有明确说明这是修改 EventLog payload contract。当前 payload 只有 `partial_tool_call_count`，增加完整的 `partial_tool_call_signal` 对象需要修改 payload contract。
- **直接证据**: `engine_ingest.py:2848-2862` 的 payload dict 只包含 `partial_tool_call_count`，不包含 `partial_tool_call_signal` 对象。
- **影响**: 实施 agent 可能不确定是否需要修改 EventLog payload contract。
- **建议改法和验证点**: plan 应明确：(a) `partial_tool_call_signal` 是新增的 EventLog payload 字段（修改 payload contract），或 (b) 在 Tool Trace projection 层从已有 `partial_tool_call_count` 派生（但这会丢失 `PartialToolCallSummary` 详情）。验证点：确认 `PartialToolCallSummary` 的所有字段都能在 payload 中表达。
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: 实施 agent 可能需要额外决策，但不阻塞。

### 005-未修复-低-plan 未明确说明 EventLog payload contract 变更的范围

- **位置**: Contract / Schema / State-machine / Public Interface Changes，plan 第 101-138 行
- **问题类型**: 架构边界
- **当前写法**: plan 声称"Add or populate structured diagnostic fields inside existing Host-owned EventLog payloads"，并列出四个变更点
- **反例/失败场景**: 这四个变更点实际上是修改 EventLog payload contract，可能影响 recovery、resume、memory、audit、outbox 等消费方。plan 没有明确说明这些变更的范围和影响。
- **为什么有问题**: `docs/host/design.md:1355-1369` 定义 EventLog canonical fact 才是治理真源，diagnostic / projection_signal 只能用于排错和 projection，不能成为业务事实。修改 `TOOL_RESULT_ACCEPTED`（canonical fact）和 `PROVIDER_PROTOCOL_ERROR`（diagnostic）的 payload contract 可能影响这些消费方。
- **直接证据**: plan 第 114-118 行列出的四个变更点都是修改 EventLog payload contract。
- **影响**: 实施 agent 可能低估变更的影响范围。
- **建议改法和验证点**: plan 应明确：(a) 这些变更是新增字段（不影响现有消费方），或 (b) 需要修改现有字段（需要评估影响）。验证点：确认所有 EventLog payload 消费方都能正确处理新增字段。
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: plan 已经在 non-goal 中说明不改变 ToolRuntime execution semantics，但没有明确说明 payload contract 变更的影响。

### 006-未修复-低-plan 未明确说明 trace_summary JSON shape 的验证规则

- **位置**: Implementation Decisions，plan 第 139-150 行
- **问题类型**: 契约缺失
- **当前写法**: plan 声称"explicit `status` when a signal can be unavailable"和"bounded text only for `repair_hint`; long text must be truncated with a digest or `truncated=true`"
- **反例/失败场景**: plan 没有明确说明如何验证这些规则。例如，`repair_hint` 的最大长度是多少？如何判断"long text"？如何计算 digest？
- **为什么有问题**: 实施 agent 可能需要自行决定这些规则，导致不一致的实现。
- **直接证据**: plan 第 149 行只说"long text must be truncated"，没有定义"long"的阈值。
- **影响**: 实施 agent 可能需要额外决策，但不阻塞。
- **建议改法和验证点**: plan 应明确：(a) `repair_hint` 的最大长度（例如 512 字符），或 (b) 截断规则（例如超过 1024 字符时截断）。验证点：确认截断逻辑一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 实施 agent 可以自行决定，但可能导致不一致。

## Open Questions

无阻塞性 open questions。plan 的 stop conditions 已覆盖关键决策点。

## Residual Risks

| ID | 风险描述 | Owner / Destination |
|---|---|---|
| R1 | `ToolResultMeta` 可能为 None，导致 P02 信号不可用 | WU-OBS-SIGNALS-01 P02；plan 已覆盖（`status="missing_tool_result_meta"`） |
| R2 | context compaction events 可能不包含所有 threshold 字段 | WU-OBS-SIGNALS-01 P01；plan 已覆盖（使用 available fields） |
| R3 | provider partial arguments 无法证明 JSON malformed | WU-OBS-00 analyzer；plan 已覆盖（classify from error code + bounded byte/digest） |
| R4 | `repair_hint` 可能包含长或敏感文本 | WU-OBS-SIGNALS-01 P03；plan 已覆盖（bound/truncate hint） |
| R5 | `trace_summary_json` 字段未索引，大 trace 聚合可能较慢 | WU-OBS-00 analyzer 或未来 retention/query work；plan 已覆盖（不新增 SQLite schema） |

## Final Plan Review Conclusion

**verdict: pass-with-risks**

plan 整体质量较高，从第一性原理判断合并实施 P01-P04 成立（四类信号共享同一 source-to-projection path），不是过度设计。计划严格服务 WU-OBS-00 analyzer 前置信号，不实现 analyzer 本体。遵守 Host/Engine 分层：Engine 不理解 Host budget；Tool Trace 不是 durable truth；ToolRuntime accept/execution 语义不改变。四类信号的 stable source 同源且可测试。trace_summary JSON shape 业务可读、自解释、bounded/redacted。slices 足够 code-generation-ready。residual risks 都有 owner/destination。

主要风险是：plan 声称的 `context_pressure` shape 包含 16 个字段，但当前 `USAGE_REPORTED` payload 只有 12 个字段，缺少 4 个关键字段（finding 001）。实施 agent 必须要么修改 EventLog payload contract，要么在 Tool Trace projection 层引入 budget 计算逻辑。plan 应明确说明这个 gap 如何处理。

其它 findings（002-006）都是中低严重程度，不阻塞实施，但 plan 应明确说明 EventLog payload contract 变更的范围和影响。

## Completion Report

- Artifact path: `docs/reviews/wu-obs-signals-p01-p04-plan-review-mimo.md`
- Overall verdict: `pass-with-risks`
- Finding count: 6（1 high, 3 medium, 2 low）
- Blocking open questions: 无
- Validation 是否运行: 是（review 基于 plan artifact、design truth、control document 和直接代码证据）
