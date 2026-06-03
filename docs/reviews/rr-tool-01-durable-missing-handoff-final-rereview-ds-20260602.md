# RR-TOOL-01 Durable-Missing Waiter Handoff — AgentDS Final Re-Review Delta

**Gate**: RR-TOOL-01 durable-missing waiter handoff final delta
**Reviewer**: AgentDS
**Date**: 2026-06-02
**Basis**: controller 采纳 AgentDS 前轮 LOW 稳定性观察，提升 timeout 并新增并发状态断言

**Conclusion**: PASS — 无 finding。两项变更均正确且改善测试质量。

---

## Delta 逐项审查

### 变更 1: 模块级常量替代魔法数字（第 71–72 行）

```python
_GOVERNED_BEFORE_ACCEPT_TIMEOUT_SECONDS = 0.1
_GOVERNED_BEFORE_ACCEPT_WAIT_SECONDS = 1.0
```

| 维度 | 评估 |
|---|---|
| 命名 | `_` 前缀模块私有，与同文件 `_SESSION_ID` / `_RUN_ID` 等常量风格一致 |
| 取值 | `0.1`（100ms）相比原来 `0.01`（10ms）提升 10 倍余量，在重负载 CI 下预派发计算有充足时间窗口 |
| AGENTS.md | 符合"禁止魔法数字"约束 |
| 作用域 | 仅该测试使用，模块级定义合理 |

### 变更 2: timeout 从 `0.01` → `_GOVERNED_BEFORE_ACCEPT_TIMEOUT_SECONDS`（第 1172 行）

`timeout_seconds=0.1`（100ms）在典型硬件上预派发计算（sha256 + dataclass 构造 + policy 查询）通常 < 5ms，留 95ms 余量。同时 100ms 远小于人工感知阈值，测试总耗时不受影响。

### 变更 3: 新增并发状态断言（第 1180–1182 行）

```python
await asyncio.sleep(0)
assert tool.call_count == 1
assert not waiter.done()
```

**设计意图**：防止测试退化为"owner 已结束 → waiter 以 fresh request 身份执行"的伪并发场景。

**时序验证**：

```
T0: owner_entered 已置位 → owner 阻塞于 owner_release.wait()
T1: waiter = asyncio.create_task(...) → waiter 进入 decide_duplicate
T2: await asyncio.sleep(0) → 让出事件循环，waiter 推进
T3: [断言点] tool.call_count == 1（仅 owner 进入工具）
             waiter.done() == False（waiter 阻塞于 condition.wait()）
```

**反例检测能力**：

若 owner timeout 在 waiter 进入 `decide_duplicate` 前已触发 → `record_durable_missing` 已 pop 掉 in_flight → waiter 看到空位、直接成为新 owner → 工具派发 → `tool.call_count` 变成 2 → 断言 `tool.call_count == 1` 失败。

若 waiter 因任何原因已执行完毕 → `waiter.done()` 为 True → 断言失败。

两项断言构成 concurrent handoff 的必要条件证明：
- `tool.call_count == 1`：waiter 尚未进入工具执行
- `not waiter.done()`：waiter 仍在等待（condition.wait() 或工具执行中）

### 变更 4: `asyncio.wait_for` timeout 使用常量（第 1184–1187 行）

`timeout=1.0` → `timeout=_GOVERNED_BEFORE_ACCEPT_WAIT_SECONDS`（1.0），语义不变，消除魔法数字。

---

## 对之前 PASS 结论的影响

无影响。两项变更均为测试质量改善，不触碰生产代码的 durable-missing 状态机。

---

## 实际检查的文件

```
tests/host/test_toolruntime_duplicate_governance.py  第 71–72（新常量）, 第 1146–1211（final 测试）
```

---

## 裁决

**PASS** — 无 finding。`timeout_seconds=0.1` 消除稳定性风险；新增 `tool.call_count == 1` + `not waiter.done()` 断言有效防止测试退化为伪并发；模块级常量消除魔法数字。
