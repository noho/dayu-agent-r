# P9.5 S13 Message / Tool Result Size Governance Code Review

**Reviewer**: AgentMiMo
**Date**: 2026-05-17
**Scope**: S13 Message / Tool Result Size Governance implementation
**Design source**: `docs/host/design.md`, `docs/host/implementation-control.md`

## Review Summary

**结论: PASS**

S13 实现达成了"大消息/工具结果/payload 不无界 inline"的设计目标，没有违反分层架构，测试覆盖真实路径，README 只写当前事实。

## Findings

### F1 [INFO] Engine 与 Host 阈值独立定义

**位置**: `dayu/engine/agent.py:178`, `dayu/host/durable/options.py:20`

Engine 的 `_MAX_ENGINE_MESSAGE_CONTENT_BYTES = 65536` 和 Host 的 `_DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES = 65536` 是相同数值但独立定义。

**分析**: 这可能是有意设计——Engine 和 Host 作为不同层可以有不同阈值。但当前两者恰好相同，若未来需要调整，需要同步修改两处。

**建议**: 不阻塞当前 PR；若认为需要统一，可在后续 PR 中将 Engine 阈值也从 `options.py` 读取。

### F2 [INFO] fetch_more 大小检查失败时 cursor 未清理

**位置**: `dayu/host/tool_runtime.py:1450-1458`

`fetch_more` 中，大小检查失败时只调用 `_cleanup_expired_cursors` 清理过期 cursor，但不清理当前 cursor。这意味着：
- 如果 single-use cursor 大小检查失败，cursor 仍保留，允许后续重试（可能用更小的 limit）
- 如果非 single-use cursor 大小检查失败，cursor 也保留

**分析**: 这可能是正确行为——允许调用方用更小的 limit 重试。但若 cursor 的 remaining 数据本身就超过阈值，该 cursor 将永远无法成功返回，可能导致 cursor 泄漏。

**建议**: 不阻塞当前 PR；可在后续 PR 中考虑：若 remaining 数据本身超过阈值，清理 cursor 并返回明确错误。

### F3 [PASS] 大消息/工具结果/payload 不无界 inline

**验证**:
- Engine: `_message_inline_size_failure` 在 Runner 调用前检查，超限返回 `context_compaction_required` recoverable failure
- EventLog: `_validate_canonical_inline_payload_size` 在 append 时检查，超限抛出 `HostPayloadReferenceError`
- ToolRuntime: `_govern_inline_tool_result` 在 accept barrier 前检查，超限返回 governed error

**结论**: 三个边界都有大小守卫，不无界 inline。

### F4 [PASS] 没有违反 UI->Service->Host->Engine 分层

**验证**:
- Engine 的检查在 `agent.py` 中，是 Engine 层的防御性检查
- Host 的检查在 `tool_runtime.py` 和 `event_log.py` 中，是 Host 层的治理
- 两层各自负责自己的边界，没有反向依赖

**结论**: 分层正确。

### F5 [PASS] Engine message size check 是防御而非 P10 proactive compaction

**验证**:
- `_message_inline_size_failure` 只检查 inline content 大小
- 超限时返回 `context_compaction_required` recoverable failure
- 要求调用方通过 ref / digest / payload / compact artifact 边界重建有界 messages
- 不计算 token、不做 proactive threshold 判断、不做 compact

**结论**: 这是 P10 proactive compaction 的前置防御，不是 P10 本身的实现。符合 S13 scope。

### F6 [PASS] EventLog 使用默认 payload inline threshold 可接受

**验证**:
- `_MAX_CANONICAL_INLINE_PAYLOAD_BYTES = _DEFAULT_INLINE_PAYLOAD_MAX_BYTES`
- 默认值来自 `dayu.host.durable.options._DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES = 65536`
- Host composition root 可通过 `payload_inline_threshold_bytes` 参数覆盖

**结论**: 使用默认值是可接受的；生产环境可通过 composition root 覆盖。

### F7 [PASS] ToolRuntime oversized result 不泄露 raw result

**验证**:
- `_govern_inline_tool_result` 超限时返回 `_governed_failure_outcome(governed_decision)`
- `policy_decision.message` 是固定文本 "tool result exceeded LLM inline size limit"
- 测试验证: `oversized_value["content"] not in candidate.policy_decision.message`
- 测试验证: `oversized_value["content"] not in record.outcome.result.message`

**结论**: raw result 不泄露。

### F8 [PASS] fetch_more oversized continuation 和 single-use cursor 语义正确

**验证**:
- `fetch_more` 先构造 `fetched_outcome`，再检查大小
- 超限时返回 `_truncation_failure`，不返回 fetched 内容
- single-use cursor 清理在大小检查通过后执行
- 测试 `test_fetch_more_rejects_oversized_inline_continuation` 覆盖该路径

**结论**: 语义正确。

### F9 [PASS] 测试覆盖真实路径

**验证**:
- `test_oversized_engine_message_content_requires_context_boundary`: 测试 Engine message inline size guard
- `test_canonical_fact_rejects_oversized_inline_payload_json`: 测试 EventLog canonical fact inline payload size guard
- `test_oversized_tool_result_returns_governed_diagnostic_outcome`: 测试 ToolRuntime oversized result 治理
- `test_fetch_more_rejects_oversized_inline_continuation`: 测试 fetch_more oversized continuation guard

**结论**: 四个测试都覆盖真实路径，不是只测 helper。

### F10 [PASS] README 只写当前事实

**验证**:
- `dayu/engine/README.md`: 描述 Engine 会在 Runner 调用前执行防御性 inline 内容大小检查
- `dayu/host/README.md`: 描述 ToolRuntime 按 payload inline 阈值做 LLM inline 大小治理
- `tests/README.md`: 描述覆盖 canonical fact inline payload size guard、oversized tool result governed diagnostic outcome、oversized fetch_more continuation guard

**结论**: README 只写当前事实，不写未来设计。

## 验证命令

```bash
# 运行 S13 targeted tests
pytest tests/engine/test_agent_message_union.py::test_oversized_engine_message_content_requires_context_boundary
pytest tests/host/test_event_log_store.py::test_canonical_fact_rejects_oversized_inline_payload_json
pytest tests/host/test_toolruntime_executor.py::test_oversized_tool_result_returns_governed_diagnostic_outcome
pytest tests/host/test_toolruntime_executor.py::test_fetch_more_rejects_oversized_inline_continuation

# 运行全量测试
pytest -q

# 类型检查
python -m pyright dayu tests

# 检查 diff
git diff --check
```

## 总结

S13 Message / Tool Result Size Governance 实现质量良好：
- 达成"大消息/工具结果/payload 不无界 inline"的设计目标
- 没有违反 UI->Service->Host->Engine 分层
- Engine 的检查是防御性检查，不是 P10 proactive compaction
- ToolRuntime oversized result 不泄露 raw result
- fetch_more oversized continuation 语义正确
- 测试覆盖真实路径
- README 只写当前事实

两个 INFO 级别的发现不阻塞当前 PR，可在后续 PR 中考虑优化。
