# RR-TOOL-01 Durable-Missing Waiter Handoff — AgentDS Re-Review Delta

**Gate**: RR-TOOL-01 durable-missing waiter handoff re-review delta
**Reviewer**: AgentDS
**Date**: 2026-06-02
**Basis**: controller 采纳 AgentDS LOW F-02，新增 `test_governed_before_accept_hands_off_to_waiter` 测试与 `_request(timeout_seconds=...)` 参数

**Conclusion**: PASS — 无 blocking / high / medium finding。新测试正确覆盖 GOVERNED_BEFORE_ACCEPT handoff；`_request` 参数化不破坏既有调用；之前 PASS 结论仍成立。

---

## Delta 逐项审查

### Delta 1: 新测试 `test_governed_before_accept_hands_off_to_waiter`（第 1144–1203 行）

#### 测试覆盖路径验证

测试通过 `timeout_seconds=0.01` 触发 owner 在工具执行中（已进入但未完成）超时，从而激活 `GOVERNED_BEFORE_ACCEPT` 路径。完整时序：

```
T0: _execute_one 入口 → batch_deadline = monotonic + 0.01
T1: decide_duplicate → ALLOW（owner）, 创建 in_flight(OWNER_RUNNING)
T2: _dispatch_tool_call_with_bounds → 剩余 timeout > 0 → 派发工具
T3: 工具 __call__ → call_count=1, owner_entered.set(), 阻塞于 owner_release.wait()
T4: await_or_cancel_or_timeout 超时 → WaitTimedOut
T5: _runtime_timeout_policy_decision → reason_code="tool_runtime_timeout"（非 cancelled）
T6: _durable_missing_reason_for_policy → GOVERNED_BEFORE_ACCEPT
T7: _AcceptingPort 接受 governed 候选 → _record_duplicate_accepted → False（policy_decision 非 ALLOW）
T8: finally → record_durable_missing(GOVERNED_BEFORE_ACCEPT) → notify_all
T9: waiter 唤醒 → DURABLE_MISSING → continue → 创建新 in_flight(OWNER_RUNNING) → ALLOW
T10: 新 owner 派发工具 → call_count=2, replacement_entered.set()
T11: replacement_release.set() → ToolCompletedOutcome → record_accepted
T12: later 调用 → entries_by_key 命中 → REUSE，prior_refs 指向 acks[1]
```

**验证**：
- `_TOOL_RUNTIME_TIMEOUT_REASON = "tool_runtime_timeout"`（第 201 行）≠ `_TOOL_RUNTIME_CANCELLED_REASON = "tool_runtime_cancelled"`（第 200 行）→ `_durable_missing_reason_for_policy` 返回 `GOVERNED_BEFORE_ACCEPT`，不是 `OWNER_CANCELLED`
- `_AcceptingPort` 接受 governed 候选后，`_record_duplicate_accepted` 因 `policy_decision.kind is GOVERNED_ERROR` 返回 False → `duplicate_terminal_recorded` 为 False → `finally` 正确记录 durable_missing
- replacement `record_accepted` 写入 `entries_by_key`，later 调用命中后走 REUSE 路径

#### 断言完整性

| 断言 | 行号 | 验证内容 |
|---|---|---|
| `tool.call_count == 2` | 1183 | owner + replacement，无额外执行 |
| `owner outcome is ToolFailedOutcome` | 1184 | owner 被 govern |
| `waiter outcome is ToolCompletedOutcome` | 1185 | handoff 成功 |
| `waiter value == {"accepted": "replacement"}` | 1186 | 拿到 replacement 结果 |
| `candidates == [GOVERNED_ERROR, COMPLETED]` | 1189 | owner 被 govern、replacement 正常 accept |
| `later tool.call_count == 2` | 1197 | later 不执行工具（复用） |
| `later outcome is ToolCompletedOutcome` | 1198 | 成功复用 |
| `later value == {"accepted": "replacement"}` | 1199 | 复用 replacement 结果 |
| `later kind is REUSE` | 1200 | 复用语义 |
| `prior_refs == acks[1].accepted_event_refs` | 1201 | 引用 replacement 的 accepted refs |

**acks 索引验证**：
- `acks[0]` = owner candidate（GOVERNED_ERROR，但 `_AcceptingPort` 仍 accepted）
- `acks[1]` = replacement candidate（COMPLETED）
- `acks[2]` = later candidate（REUSE）
- later 的 `prior_refs` 指向 `acks[1]`（replacement），非 `acks[0]`（owner）→ 正确

#### 稳定性评估

**潜在风险**：`timeout_seconds=0.01`（10ms）要求 `_execute_one` 入口到工具派发之间的计算（sha256 digest、dataclass 构造、policy 查询）在 10ms 内完成。

- 若预派发计算超过 10ms → `_dispatch_tool_call_with_bounds` 入口处 `_remaining_batch_timeout_seconds ≤ 0` → 工具永不派发 → `owner_entered` 永不置位 → 测试在 `await owner_entered.wait()` 挂起
- 外层 `asyncio.wait_for(replacement_entered.wait(), timeout=1.0)` 提供 1 秒兜底超时，但不会改变 root cause
- 预派发计算（sha256 of small JSON、dictionary lookup、dataclass init）在典型硬件上 < 2ms；10ms 预算充裕
- 在极端 CPU 过载的 CI 环境存在理论上的 flaky 风险

**裁决**：不要求修复。若 CI 中实际出现 flaky，可将 `timeout_seconds=0.01` 调至 `0.05`（50ms），同时将外层 `asyncio.wait_for` timeout 从 `1.0` 调至 `2.0` 以保持安全余量。

### Delta 2: `_request` helper 新增 `timeout_seconds` 参数（第 1511–1537 行）

#### 兼容性分析

**变更前**（硬编码）：
```python
BatchToolExecutionContext(
    ...,
    timeout_seconds=10.0,
    ...,
)
```

**变更后**（参数化）：
```python
def _request(
    *calls: ToolCallRequest,
    run_id: str = _RUN_ID,
    timeout_seconds: float | None = 10.0,
    cancellation_token: ... = None,
) -> BatchToolExecutionRequest:
```

- 默认值 `10.0` 与旧硬编码相同
- 类型 `float | None` 与 `BatchToolExecutionContext.timeout_seconds` 字段类型一致（`dayu/contracts/tool_call.py` 第 123 行：`timeout_seconds: float | None`）
- 全量既有调用（26 处）不传 `timeout_seconds=` → 均取默认 `10.0` → 行为不变
- 仅新测试传入 `timeout_seconds=0.01`

**结论**：向后兼容，无破坏性变更。

---

## 既有 durable-missing handoff 语义影响评估

新测试 **仅新增覆盖**，不改变生产代码的 durable-missing 状态机。对既有四类测试无影响：

| 测试 | 行号 | 影响 |
|---|---|---|
| `test_same_attempt_concurrent_rejected_accept_hands_off_to_waiter` | 1012 | 无影响 — 仍测试 HOST_ACCEPT_REJECTED |
| `test_durable_missing_only_one_waiter_replaces_owner_and_others_reuse` | 1070 | 无影响 — 仍测试多 waiter 竞争（HOST_ACCEPT_REJECTED 触发） |
| `test_same_attempt_concurrent_timed_out_accept_hands_off_to_waiter` | 1206 | 无影响 — 仍测试 HOST_ACCEPT_TIMEOUT（accept 层 timeout） |
| `test_same_attempt_concurrent_tool_exception_hands_off_to_waiter` | 1248 | 无影响 — 仍测试 TOOL_EXCEPTION |
| `test_same_attempt_concurrent_owner_cancellation_hands_off_to_waiter` | 1288 | 无影响 — 仍测试 OWNER_CANCELLED |

新测试覆盖了**第五类** durable-missing 原因：`GOVERNED_BEFORE_ACCEPT`（工具派发层 timeout）。五类原因全部有并发 handoff 测试覆盖。

---

## Findings（按严重度排序）

### F-01 [LOW — 测试稳定性]

`test_governed_before_accept_hands_off_to_waiter` 使用 `timeout_seconds=0.01`（10ms）触发预 accept 治理超时。在极端 CPU 过载的 CI 环境，预派发检查可能在 10ms 窗口内来不及完成，导致工具永不派发、`owner_entered` 永不置位、测试在 `await owner_entered.wait()` 挂起。

- **实际风险低**：10ms 在典型硬件上充裕；外层 `asyncio.wait_for(..., timeout=1.0)` 在 1 秒后暴露 TimeoutError 而非静默 hang
- **建议**：若 CI 中实际出现 flaky，将 `timeout_seconds` 调至 `0.05` 并同步调整外层 timeout

### F-02 [INFO — 确认项]

`owner_release` 在测试中永不 set；owner 工具任务由 `await_or_cancel_or_timeout` 在超时后 cancel。`_SequencedBlockingCountingTool` 的 `__call__` 在 `await self._release_events[0].wait()` 处收到 `CancelledError` 后传播，由 `await_or_cancel_or_timeout` 捕获并转为 `WaitTimedOut`。资源清理正确，无 task 泄漏。

---

## 之前 PASS 结论再确认

| 原审查点 | 状态 |
|---|---|
| waiter 接棒执行 | 仍 PASS — 新测试未改变 `decide_duplicate` 状态机 |
| 多 waiter 单 owner | 仍 PASS |
| accepted entry 复用 / ALLOW policy | 仍 PASS |
| 四类 → 五类 durable-missing 测试覆盖 | 仍 PASS — 补全了 GOVERNED_BEFORE_ACCEPT |
| 文档准确性 | 仍 PASS — 未触及文档 |
| AGENTS.md 约束 | 仍 PASS — `_request` docstring 已更新、类型签名正确 |

---

## 实际检查的文件

```
tests/host/test_toolruntime_duplicate_governance.py  第 1144–1203（新测试）, 第 1511–1537（_request delta）
dayu/host/tool_runtime.py                            第 200–201（_TOOL_RUNTIME_TIMEOUT_REASON / _CANCELLED_REASON）,
                                                      第 2422–2461（_dispatch_tool_call_with_bounds）,
                                                      第 5528–5580（timeout helper）
dayu/contracts/tool_call.py                           第 99–127（BatchToolExecutionContext.timeout_seconds 类型）
```

---

## 建议验证命令

```bash
source .venv/bin/activate

# 全量 duplicate governance 测试（含新测试）
pytest tests/host/test_toolruntime_duplicate_governance.py -q

# 相关回归
pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py -q

# 类型检查
python -m pyright tests/host/test_toolruntime_duplicate_governance.py dayu/host/tool_runtime.py
```

---

## 裁决

**PASS** — 新测试正确覆盖 `GOVERNED_BEFORE_ACCEPT` durable-missing handoff 路径。`_request(timeout_seconds=...)` 参数化向后兼容，不影响既有调用。五类 durable-missing 原因全部有并发 handoff 测试。一项 LOW 稳定性观察不要求当前 gate 修复。
