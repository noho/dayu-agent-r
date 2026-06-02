# RR-TOOL-01 Durable-Missing Waiter Handoff Re-Review (Delta)

## Review Metadata

- Reviewer: AgentMiMo
- Date: 2026-06-02
- Gate: RR-TOOL-01 durable-missing waiter handoff re-review delta
- Delta 来源：controller 采纳 AgentDS LOW F-02，新增 `test_governed_before_accept_hands_off_to_waiter`，`_request` helper 支持可选 `timeout_seconds`

## Review Result

**PASS**

无 blocking finding。delta 不破坏既有 durable-missing handoff 语义。

## Findings

无。

## 逐项审查

### 1. 新测试 `test_governed_before_accept_hands_off_to_waiter` 稳定性与覆盖

**PASS**

测试结构：

- owner 使用 `timeout_seconds=0.01`（10ms），工具进入阻塞后 batch 超时触发 `GOVERNED_BEFORE_ACCEPT` 路径。
- waiter 在 owner 已进入后创建，等待 durable-missing 信号后接棒执行。
- replacement 工具被 `_SequencedBlockingCountingTool` 独立事件控制，`await asyncio.wait_for(replacement_entered.wait(), timeout=1.0)` 提供 100x 安全余量。
- 后续 `tool-call-3` 验证复用 replacement 的 accepted refs（`accept_port.acks[1].accepted_event_refs`）。

稳定性分析：

- 10ms 超时在 asyncio 中是确定性的：工具阻塞在 `asyncio.Event.wait()`，不依赖真实时钟漂移。
- `_SequencedBlockingCountingTool` 使用独立事件对，owner 和 replacement 的进入/释放互不干扰。
- `asyncio.wait_for(replacement_entered.wait(), timeout=1.0)` 替代裸 `await`，避免测试无限挂起。

覆盖分析：

- 该测试覆盖 `DuplicateDurableMissingReason.HOST_ACCEPT_TIMEOUT` 对应的 `GOVERNED_BEFORE_ACCEPT` 场景，与之前的 `test_same_attempt_concurrent_timed_out_accept_hands_off_to_waiter`（使用 `_TimedOutPort` 触发 `HOST_ACCEPT_TIMEOUT`）形成互补：前者通过 accept port 直接返回 timeout，后者通过 batch 级超时触发。
- 断言验证了 owner 的 `ToolFactKind.GOVERNED_ERROR`（不是 `COMPLETED`），确认 owner 在 accept 前被治理。

### 2. `_request(timeout_seconds=...)` 对其它测试的影响

**PASS**

变更：`_request` helper 的 `timeout_seconds` 参数从硬编码 `10.0` 改为 `timeout_seconds: float | None = 10.0`。

- 默认值 `10.0` 与原硬编码值完全一致，其它所有测试不传此参数，行为无变化。
- 新测试传入 `timeout_seconds=0.01`，仅影响该测试的 batch 超时。
- 类型 `float | None` 与 `BatchToolExecutionContext.timeout_seconds` 的类型定义一致。

无回归风险。

### 3. 之前 PASS 结论是否仍成立

**PASS**

Delta 对既有测试的变更：

- `test_same_attempt_concurrent_rejected_accept_hands_off_to_waiter`：从 `_RejectingPort` + `_BlockingCountingTool` 改为 `_RejectOnceThenAcceptingPort` + `_SequencedBlockingCountingTool`，断言从 "waiter 也 failed + `duplicate_prior_accept_missing`" 改为 "waiter completed + 复用 replacement refs"。行为正确对齐 handoff 语义。
- `test_same_attempt_concurrent_timed_out_accept_hands_off_to_waiter`：断言从 `hint == "duplicate_prior_accept_missing"` 改为 `hint != "duplicate_prior_accept_missing"`，`tool.call_count` 从 1 改为 2。行为正确。
- `test_same_attempt_concurrent_tool_exception_hands_off_to_waiter`：同上模式，`tool.call_count` 从 1 改为 2。行为正确。
- `test_same_attempt_concurrent_owner_cancellation_hands_off_to_waiter`：从 `_BlockingCountingTool` 改为 `_SequencedBlockingCountingTool`，waiter 结果从 `ToolFailedOutcome` + `duplicate_prior_accept_missing` 改为 `ToolCompletedOutcome` + replacement value。行为正确。

新增测试：

- `test_durable_missing_only_one_waiter_replaces_owner_and_others_reuse`：覆盖多 waiter thundering herd 防护，验证只有一个 waiter 接棒、其它复用。
- `test_governed_before_accept_hands_off_to_waiter`：覆盖 `GOVERNED_BEFORE_ACCEPT` handoff。

新增 helper 类：

- `_SequencedBlockingCountingTool`：按调用序号使用独立事件阻塞，支持 owner + replacement 独立控制。
- `_RejectOnceThenAcceptingPort`：第一次 rejected、后续 accepted，用于触发 durable-missing 后让 replacement 成功。

所有变更方向一致：将旧 "waiter 得到 `duplicate_prior_accept_missing`" 断言改为 "waiter 接棒执行并产生新 accepted fact"。既有 PASS 结论的所有审查点（durable-missing handoff、thundering herd 防护、accepted entry 复用、ALLOW policy、四类 durable-missing 原因、文档准确性、分层/类型/docstring 约束）均不受影响。

## 已检查文件

| 文件 | 检查内容 |
|---|---|
| `tests/host/test_toolruntime_duplicate_governance.py` | delta diff：新增测试、修改测试、新增 helper 类、`_request` helper 变更 |

## 建议验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_toolruntime_duplicate_governance.py -v
python -m pyright dayu/host/tool_duplicate_governance.py tests/host/test_toolruntime_duplicate_governance.py
```
