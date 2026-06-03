# RR-TOOL-01 Durable-Missing Waiter Handoff Final Re-Review (Delta)

## Review Metadata

- Reviewer: AgentMiMo
- Date: 2026-06-02
- Gate: RR-TOOL-01 durable-missing waiter handoff final re-review delta
- Delta 来源：controller 采纳 AgentDS 测试稳定性 LOW 观察

## Review Result

**PASS**

无 blocking finding。

## Delta 内容

1. 新增模块级常量 `_GOVERNED_BEFORE_ACCEPT_TIMEOUT_SECONDS = 0.1` 和 `_GOVERNED_BEFORE_ACCEPT_WAIT_SECONDS = 1.0`。
2. `test_governed_before_accept_hands_off_to_waiter` 中 `timeout_seconds=0.01` 改为 `_GOVERNED_BEFORE_ACCEPT_TIMEOUT_SECONDS`（0.1），`asyncio.wait_for` 的 `timeout=1.0` 改为 `_GOVERNED_BEFORE_ACCEPT_WAIT_SECONDS`（1.0）。
3. waiter 创建后新增并发断言：`tool.call_count == 1` 且 `not waiter.done()`。

## 逐项审查

### 1. timeout 从 0.01 提升到 0.1

**PASS**

0.01（10ms）在 CI 负载高时可能因事件循环调度延迟导致 owner 未在预期窗口内触发超时，退化为非预期路径。0.1（100ms）在 asyncio 确定性调度下足够触发 batch 超时，同时保留 10x 余量（`_GOVERNED_BEFORE_ACCEPT_WAIT_SECONDS = 1.0`）。常量命名清晰，消除魔法数字。

### 2. 新增并发断言 `tool.call_count == 1` 且 `not waiter.done()`

**PASS**

这两个断言验证测试的关键时序前提：waiter 创建时 owner 工具仍在执行中（`call_count == 1`），且 waiter 尚未完成（`not waiter.done()`）。若测试退化为 owner 已结束后的 fresh request，这两个断言会失败，防止静默退化。

### 3. 对既有 PASS 结论的影响

**PASS**

该 delta 仅修改 `test_governed_before_accept_hands_off_to_waiter` 的常量和新增并发断言，不改变任何生产代码或其它测试。之前所有 PASS 结论不受影响。

## 已检查文件

| 文件 | 检查内容 |
|---|---|
| `tests/host/test_toolruntime_duplicate_governance.py` | 模块级常量、`test_governed_before_accept_hands_off_to_waiter` timeout 和并发断言变更 |

## 建议验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_toolruntime_duplicate_governance.py::test_governed_before_accept_hands_off_to_waiter -v
```
