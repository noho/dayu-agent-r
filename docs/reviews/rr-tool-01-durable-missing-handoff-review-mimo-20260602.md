# RR-TOOL-01 Durable-Missing Waiter Handoff Review

## Review Metadata

- Reviewer: AgentMiMo
- Date: 2026-06-02
- Gate: RR-TOOL-01 durable-missing waiter handoff fix review
- Scope: `dayu/host/tool_duplicate_governance.py`, `tests/host/test_toolruntime_duplicate_governance.py`, `dayu/host/README.md`, `tests/README.md`, `docs/host/host-core-followup-implementation-control.md` RR-TOOL-01 row

## Review Result

**PASS**

无 blocking finding。所有审查重点均已验证通过。

## Findings

无。

## 逐项审查

### 1. durable-missing 后 waiter 是否真的接棒执行

**PASS**

`decide_duplicate` 的 `DURABLE_MISSING` 分支（`tool_duplicate_governance.py:428`）执行 `continue`，使 waiter 回到 `while True` 循环顶部重新竞争 owner。关键机制：

- `record_durable_missing`（line 464-469）从 `in_flight_by_key` pop 出 in-flight 记录并设置状态为 `DURABLE_MISSING`，随后 `notify_all()` 唤醒所有等待者。
- waiter 被唤醒后重新检查 `entries_by_key`（无 accepted 条目）和 `in_flight_by_key`（已被 pop，故为 `None`），进入 `in_flight is None` 分支，创建新的 `OWNER_RUNNING` in-flight 记录并返回 `ALLOW` 决策，成为新 owner。
- 新 owner 真实执行工具后通过 `record_accepted` 写入 accepted 条目，后续调用者或等待者命中 accepted 条目后复用结果。

等待者不再返回 `duplicate_prior_accept_missing`，而是重新竞争并真实执行。行为正确。

### 2. 并发多个 waiter 是否只有一个新 owner 执行

**PASS**

`asyncio.Condition` 保证同一时刻只有一个协程持有锁：

- `notify_all()` 唤醒所有等待者，但它们在 `await self._state.condition.wait()` 返回后必须重新获取锁，因此串行执行。
- 第一个获取锁的 waiter 发现 `in_flight_by_key` 为空，创建 `OWNER_RUNNING` 记录并返回 ALLOW，成为新 owner。
- 后续 waiter 获取锁后发现已存在 `OWNER_RUNNING` 记录，回到等待循环，直到新 owner 完成后复用 accepted 结果。

测试 `test_durable_missing_only_one_waiter_replaces_owner_and_others_reuse`（line 1071-1141）直接验证了该行为：

- owner accept 被拒绝，触发 durable-missing。
- 两个 waiter 中只有一个接棒（`tool.call_count == 2`，候选事实为 `[COMPLETED, COMPLETED, REUSE]`）。
- 另一个 waiter 复用新 owner 的 accepted 结果（`_candidate_reuse_prior_event_refs` 匹配 `accept_port.acks[0].accepted_event_refs`）。

不存在 thundering herd 风险。

### 3. accepted entry 复用、ALLOW policy、后续 duplicate 行为是否被破坏

**PASS**

- `record_accepted`（line 430-449）在新 owner 完成后正确写入 `entries_by_key` 并唤醒等待者。测试 line 1058-1067 验证 durable-missing handoff 后的后续调用命中 accepted 条目并正确复用。
- `test_allow_policy_concurrent_waits_for_owner_before_second_execution`（line 1284-1314）验证 ALLOW policy 下并发 duplicate 仍必须等待 owner terminal 后才二次执行。
- `test_allow_policy_post_owner_completion_executes_again`（line 1317-1333）验证 ALLOW policy owner 完成后的重复调用会再次真实执行。
- `test_governed_duplicate_does_not_overwrite_prior_successful_reuse_source`（line 822-853）验证 governed_error accepted 不覆盖 duplicate index 中的成功 outcome。

现有 accepted entry 复用和 ALLOW policy 路径未被 durable-missing handoff 逻辑破坏。

### 4. 四类 durable-missing 测试覆盖

**PASS**

| 原因 | 测试 | 行为验证 |
|---|---|---|
| owner cancellation | `test_same_attempt_concurrent_owner_cancellation_hands_off_to_waiter` (line 1227) | waiter 接棒执行，后续调用复用 |
| tool exception | `test_same_attempt_concurrent_tool_exception_hands_off_to_waiter` (line 1187) | waiter 接棒执行，后续调用真实执行 |
| accept rejected | `test_same_attempt_concurrent_rejected_accept_hands_off_to_waiter` (line 1013) | waiter 接棒执行，后续调用复用 |
| accept timeout | `test_same_attempt_concurrent_timed_out_accept_hands_off_to_waiter` (line 1144) | waiter 接棒执行，后续调用真实执行 |

四类场景均覆盖 waiter 接棒成为新 owner 并真实执行的行为。测试还验证了 durable-missing 后的后续调用不再返回 `duplicate_prior_accept_missing`（line 1176, 1215 通过 `!= "duplicate_prior_accept_missing"` 断言）。

### 5. 文档是否准确表达

**PASS**

- `dayu/host/README.md` ToolRuntime 章节（line 231）准确描述："owner 未产生可复用 accepted fact 时，等待者中只允许一个接棒成为新 owner，其它等待者继续等待新 owner"。
- `docs/host/host-core-followup-implementation-control.md` RR-TOOL-01 行（line 196）准确记录："durable-missing 后 waiter 接棒执行已在当前 PR 修复；awaiting fanout 不直接实现，后续 issue 中设计 single wait owner / follower / resume shared fact / cancel 与 late result 收口规则"，状态为 `transferred-to-issue`（GitHub Issue #111）。
- `tests/README.md` 测试分层描述（line 131）包含 "durable-missing waiter 接棒" 的事实记录。

### 6. 分层、类型、docstring、测试/README 同步约束

**PASS**

- 分层：`tool_duplicate_governance.py` 只 import `dayu.contracts` 和 `dayu.host.durable.codec`，无反向依赖。
- 类型：所有 dataclass 使用严格类型标注，无 `object` / `Any` / 无类型参数。`DuplicateGovernancePort` Protocol 有完整类型签名。
- docstring：所有公共类、方法和模块级私有函数均提供完整中文 docstring，包含参数、返回值、异常说明。
- `__all__`：`DuplicateDurableMissingReason` 已在 `__all__` 中导出。
- 测试/README 同步：Host README 和 tests README 均已反映 durable-missing handoff 行为。

## 已检查文件

| 文件 | 检查内容 |
|---|---|
| `dayu/host/tool_duplicate_governance.py` | `decide_duplicate` DURABLE_MISSING 分支、`record_durable_missing`、`record_accepted`、`_InFlightDuplicateState` 状态机、`__all__` |
| `tests/host/test_toolruntime_duplicate_governance.py` | 四类 durable-missing handoff 测试、并发 waiter 测试、ALLOW policy 测试、accepted entry 复用测试 |
| `dayu/host/README.md` | ToolRuntime 章节 duplicate governance 描述 |
| `tests/README.md` | duplicate governance 测试分层描述 |
| `docs/host/host-core-followup-implementation-control.md` | RR-TOOL-01 行 |

## 建议验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_toolruntime_duplicate_governance.py -v
python -m pyright dayu/host/tool_duplicate_governance.py
```
