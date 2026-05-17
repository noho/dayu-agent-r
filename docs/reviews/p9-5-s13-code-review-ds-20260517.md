# P9.5 S13 Message / Tool Result Size Governance Code Review

**Reviewer**: AgentDS
**Date**: 2026-05-17
**Scope**: S13 Message / Tool Result Size Governance implementation
**Design source**: `docs/host/design.md`, `docs/host/implementation-control.md`
**MiMo review**: `docs/reviews/p9-5-s13-code-review-mimo-20260517.md`

## 结论: PASS

S13 实现在三个关键边界（Engine→Runner、ToolRuntime→LLM inline、EventLog canonical fact）建立了防御性大小治理，超限一律产生明确 error/diagnostic，不静默丢内容，不绕过分层，不实现 P10 proactive compaction。0 blocking findings。

## Blocking Findings

**0 blocking.**

## Non-Blocking Observations

### O1 [MEDIUM] Engine iteration-loop size check 缺少集成测试覆盖

**位置**: `dayu/engine/agent.py:676-681`

`_message_inline_size_failure` 在 `_AsyncAgent.run_messages()` 中有两处调用：初始检查（line 664）和 per-iteration 检查（line 676）。per-iteration 检查是唯一能捕获工具产出注入后消息变大的防线——工具结果 inline 内容由 `_project_tool_outcome_for_llm` 转为 `ToolMessage.content` 后，在下一轮 iteration 才会被重新检查。若这条路径被意外删除或重构破坏，engine message size governance 将仅对初始消息生效。

当前 `tests/engine/test_agent_message_union.py::test_oversized_engine_message_content_requires_context_boundary` 只测了 `_message_inline_size_failure` helper，未测 `_AsyncAgent.run_messages()` 对 oversized tool message 的实际拒绝路径。

**建议**: 在 `tests/engine/` 加一条 end-to-end 测试，模拟 `_AsyncAgent.run_messages()` 在 tool result 注入后消息超限的场景，assert `RUN_FAILED(context_compaction_required)` terminal event。

### O2 [MEDIUM] Engine proactive 与 reactive context_compaction_required 路径 event 序列不对称

**位置**: `dayu/engine/agent.py:1303-1319` (reactive), `dayu/engine/agent.py:664-668` (proactive)

Reactive 路径（provider 报 `CONTEXT_LENGTH_EXCEEDED`）先 emit `CONTEXT_COMPACTION_REQUESTED` EngineEvent，再 emit `RUN_FAILED(context_compaction_required)`。Proactive 路径直接 emit `RUN_FAILED(context_compaction_required)`，无中间诊断事件。

**分析**: 语义上这不构成 bug——proactive 路径没有 Runner 调用，不存在"requested"的 trigger。但 Host 侧的 context compaction recovery 逻辑若依赖 `CONTEXT_COMPACTION_REQUESTED` 事件来触发 message rebuild workflow，则需要同时 handle `RUN_FAILED(context_compaction_required)` 直接到达的情况（Host 应已 handle，因 reactive 路径的 `RUN_FAILED` 也是最终信号）。

**建议**: 不阻塞；确认 Host compaction recovery 对两种到达路径均正确响应。S13 设计的 Engine 防御性检查 message: "Host must provide bounded messages through ref, digest, payload, or compact artifact boundaries" 与 reactive 的 "provider context overflow requires Host compaction" 已可通过 message 文本区分。

### O3 [MEDIUM] Engine 阈值硬编码，与 Host 阈值独立定义

**位置**: `dayu/engine/agent.py:178`, `dayu/host/durable/options.py:20`

Engine: `_MAX_ENGINE_MESSAGE_CONTENT_BYTES = 65536`（模块级常量，不可配置）
Host: `_DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES = 65536`（`options.py`，composition root 可覆盖）

当前两者数值相同，但 Engine 阈值不是 Host composition root 的一部分。如果不同场景需要差异化阈值（如 Engine 容忍 128KB 而 Host event log 限制 64KB），Engine 需代码修改。

**分析**: MiMo F1 将此评为 INFO。DS 评为 MEDIUM 的理由：当前 Engine 阈值是一个防御性安全上限（"不应有大于 64KB 的 inline 内容进入 Runner"），不是 policy tunable。但如果后续 P10 proactive compaction 引入 token-based 阈值，这块应一起重构为可配置。

**建议**: 不阻塞 S13；P10 实现时统一定义位置。

### O4 [LOW] `_message_inline_texts` 不检查 AssistantMessage.tool_calls.arguments

**位置**: `dayu/engine/agent.py:358-374`

`_message_inline_texts` 对 `AssistantMessage` 只提取 `content` 和 `reasoning_content`，不提取 `tool_calls[].arguments`。虽然 tool call arguments 通常受 schema 约束且极小，但若 arguments 字段异常膨胀（如超大 JSON args），会绕过 Engine inline size guard 直接进入 Runner。

**建议**: 不阻塞；在下一次 Engine message schema 审视时考虑是否加入 arguments 检查。

### O5 [LOW] fetch_more oversized continuation 不清理当前 cursor

**位置**: `dayu/host/tool_runtime.py:1450-1458`

`fetch_more` 检测到 continuation 超限后，只调用 `_cleanup_expired_cursors()` 清理过期 cursor，不 pop 当前超限 cursor。对于 single-use cursor，这意味着可以重试（用更小 limit），但也意味着如果 remaining 数据本身超限，cursor 将持续存在直到 TTL 过期，期间每次 fetch 都返回同样错误。

**建议**: 不阻塞 S13；属 corner case（fetch_more continuation ≥64KB 的概率低）。MiMo F2 已覆盖此发现。

### O6 [LOW] ToolRuntime 双重大小检查

`TruncationManager.apply_truncation()` 内部已检查截断后结果大小（line 1390-1401），`_govern_inline_tool_result` 又对同一结果再次检查（line 2513）。虽然语义不同——前者只覆盖 truncation 路径，后者覆盖所有工具结果——但刚好相同的阈值和相同的检查逻辑造成双重点。非错误，但维护者可能困惑"为什么有两处检查"。

**建议**: 不阻塞；当前可通过注释或模块内文档说明分工。

## 确认通过的设计要求

基于 `docs/host/implementation-control.md` S13 gate 定义（line 1039-1042）：

| 要求 | 状态 | 证据 |
|------|------|------|
| 大消息不塞入无界 Engine messages | PASS | `_message_inline_size_failure` → `RunFailedData(context_compaction_required, recoverable=True)` |
| 大工具结果不塞入 Engine messages | PASS | `_govern_inline_tool_result` → `ToolFailedOutcome(error="tool_call_governed")`, raw value 不进入 message |
| 大 payload 不塞入 EventLog canonical fact | PASS | `_validate_canonical_inline_payload_size` → `HostPayloadReferenceError` |
| 超限产生结构化诊断或明确 public error | PASS | `HostPayloadReferenceError` / `RunFailedData` / governed error with `ToolTraceDiagnosticRef` |
| 不静默丢内容 | PASS | 三个边界均 raise/return error，无 silent drop 路径 |
| 不实现 P10 proactive compaction | PASS | Engine 只做 go/no-go 防御检查，不做 token 计算、不做 compact、不做 proactive trimming |
| truncation 不绕过治理 | PASS | `apply_truncation` 内部检查截断后大小；超限返回 truncation failure |
| fetch_more 不绕过治理 | PASS | `fetch_more` 内部检查 continuation 大小；超限返回 truncation failure |
| 分层正确 | PASS | Engine 只防守自己的消息边界，Host 治理自己的 tool result / EventLog 边界；无反向依赖 |
| 无 public error taxonomy 新增 | PASS | 复用 `HostPayloadReferenceError`、`_ERROR_CONTEXT_COMPACTION_REQUIRED`；新增 `_TOOL_RUNTIME_RESULT_TOO_LARGE_REASON` 是内部常量 |

## 测试覆盖

| 测试 | 覆盖路径 |
|------|---------|
| `test_oversized_engine_message_content_requires_context_boundary` | Engine `_message_inline_size_failure` helper（隔离） |
| `test_canonical_fact_rejects_oversized_inline_payload_json` | EventLog append 拒绝超大 inline payload_json |
| `test_oversized_tool_result_returns_governed_diagnostic_outcome` | ToolRuntime oversized tool result → governed error + diagnostic ref + raw result 不泄露 |
| `test_fetch_more_rejects_oversized_inline_continuation` | fetch_more oversized continuation → truncation failure |

**测试缺口**: Engine iteration-loop 集成测试（见 O1）。

## Residual Risks

1. **Engine iteration-loop guard 回归风险**: O1 所述——若 per-iteration guard 被意外删除，只在下一个 oversized tool result 的集成场景才能发现。
2. **阈值漂移**: Engine 与 Host 独立定义 65536，若未来只改一处，会产生不一致的治理边界。
3. **fetch_more cursor 持久化语义**: 当前 fetch_more cursor 是内存态，`_TOOL_RUNTIME_RESULT_TOO_LARGE_REASON` 错误不可恢复——调用方无法通过减小 limit 重新 fetch（因为 cursor 仍在，但 remaining 数据本身可能超限）。这段行为未在测试中显式验证"no retry recovery"语义。
