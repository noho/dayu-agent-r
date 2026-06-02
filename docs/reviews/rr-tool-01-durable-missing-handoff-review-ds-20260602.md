# RR-TOOL-01 Durable-Missing Waiter Handoff — AgentDS Review

**Gate**: RR-TOOL-01 durable-missing waiter handoff fix review / re-review
**Reviewer**: AgentDS
**Date**: 2026-06-02
**Conclusion**: PASS — 无 blocking / high / medium finding

---

## 审查范围

| 文件 | 审查内容 |
|---|---|
| `dayu/host/tool_duplicate_governance.py` | `InMemoryAttemptDuplicateGovernance` 的 `decide_duplicate` / `record_durable_missing` / `record_accepted` 并发状态机 |
| `tests/host/test_toolruntime_duplicate_governance.py` | 四类 durable-missing handoff 测试 + 多 waiter 竞争测试 |
| `dayu/host/tool_runtime.py` | `_durable_missing_reason_for_policy` / `_durable_missing_reason_for_accept_result` 生产接线 |
| `dayu/host/README.md` | 第 231 行 durable-missing handoff 语义描述 |
| `tests/README.md` | 第 131 行 "durable-missing waiter 接棒" 覆盖描述 |
| `docs/host/host-core-followup-implementation-control.md` | 第 196 行 RR-TOOL-01 记录 |

---

## 重点问题逐项审查

### 1. durable-missing 后 waiter 是否真的接棒执行

**结论：PASS**

`InMemoryAttemptDuplicateGovernance.decide_duplicate`（第 383–428 行）的并发状态机：

- 旧 owner 的 `record_durable_missing`（第 451–469 行）把 in_flight record 从 `in_flight_by_key` pop 出去，设 state=`DURABLE_MISSING`，再 `notify_all`
- waiter 被唤醒后，`in_flight.state is DURABLE_MISSING`，执行 `continue`（第 428 行），回到 `while True` 顶部
- 此时 `in_flight_by_key` 中该 key 已不存在（被 pop），且 `entries_by_key` 为空（owner 未 accepted）→ 命中第 403–410 行，创建新 `OWNER_RUNNING` record，返回 ALLOW
- waiter 成为新 owner，真实执行工具

**关键证据**：

- `test_same_attempt_concurrent_rejected_accept_hands_off_to_waiter`（第 1012 行）：owner accept rejected → waiter 接棒，tool.call_count==2，waiter 拿到 {"accepted": "replacement"}
- `test_same_attempt_concurrent_owner_cancellation_hands_off_to_waiter`（第 1226 行）：owner cancelled → waiter 接棒
- `test_same_attempt_concurrent_timed_out_accept_hands_off_to_waiter`（第 1144 行）：owner accept timeout → waiter 接棒，tool.call_count==2
- `test_same_attempt_concurrent_tool_exception_hands_off_to_waiter`（第 1186 行）：owner tool exception → waiter 接棒，tool.call_count==2

四个路径均断言 `waiter_outcome.records[0].outcome.result.hint != "duplicate_prior_accept_missing"`，确认 waiter 不再返回旧版"duplicate_prior_accept_missing"提示。

### 2. 并发多个 waiter 时是否只有一个新 owner 执行

**结论：PASS**

核心机制：
1. `record_durable_missing` 先 pop 旧 record，再 `notify_all`
2. 所有 waiter 被同时唤醒，各自检查 `in_flight.state is DURABLE_MISSING` → 各自 `continue` → 回到循环顶部
3. 第一个 waiter 进入循环：`in_flight_by_key` 为空 → 创建新 `OWNER_RUNNING` → 返回 ALLOW（成为新 owner）
4. 后续 waiter 进入循环：`in_flight_by_key` 中已有新 owner 的 `OWNER_RUNNING` record → 进入 `condition.wait()` → 等待新 owner terminal

**关键证据**：`test_durable_missing_only_one_waiter_replaces_owner_and_others_reuse`（第 1070 行）

- owner + waiter_one + waiter_two 并发
- replacement_entered 后断言 `tool.call_count == 2`（owner + 1 个新 owner）
- replacement_entered 后断言 `not waiter_one.done() or not waiter_two.done()`（至少一个 waiter 仍在等待）
- 最终断言 `candidates == [COMPLETED, COMPLETED, REUSE]`：一个 owner 执行、一个新 owner 执行、一个 waiter 复用
- 复用 waiter 的 `prior_event_refs` 指向新 owner 的 `accepted_event_refs`

**时序分析**（条件锁保证串行化）：

```
T0: owner 创建 in_flight(OWNER_RUNNING) → 执行工具
T1: waiter_one 看到 in_flight(OWNER_RUNNING) → wait()
T2: waiter_two 看到 in_flight(OWNER_RUNNING) → wait()
T3: owner record_durable_missing → pop in_flight → DURABLE_MISSING → notify_all
T4: waiter_one 醒来 → DURABLE_MISSING → continue → 创建新 in_flight(OWNER_RUNNING) → ALLOW
T5: waiter_two 醒来 → DURABLE_MISSING → continue → 看到新 in_flight(OWNER_RUNNING) → wait()
T6: waiter_one 执行工具 → record_accepted → ACCEPTED → notify_all
T7: waiter_two 醒来 → ACCEPTED → REUSE
```

### 3. accepted entry 复用、ALLOW policy、后续 duplicate 行为是否被破坏

**结论：PASS**

- **accepted entry 复用**：新 owner `record_accepted` 后写入 `entries_by_key`（第 444 行），后续调用者命中 `entries_by_key` 走 `_decision_for_accepted_entry`（第 397–402 行），按 policy 返回 REUSE/HINT/HARD_STOP 等决策
- **ALLOW policy**：`_decision_for_accepted_entry` 第 487 行：若决策为 ALLOW，调用 `_allow_decision` 传 `prior_refs`，工具 runtime 中 `duplicate_owner_needs_terminal` 为 False（`prior_event_refs` 非空）→ 不进入 `finally` durable-missing 路径
- **后续 duplicate**：`test_durable_missing_only_one_waiter_replaces_owner_and_others_reuse` 第 1058–1067 行验证：handoff 完成后第三次调用 `later.records[0].outcome.result.value == {"accepted": "replacement"}` 且 `tool.call_count == 2`（无额外执行）
- **governed_error 不覆盖成功 outcome**：`test_governed_duplicate_does_not_overwrite_prior_successful_reuse_source`（第 823 行）验证

### 4. 四类 durable-missing 测试覆盖

**结论：PASS**

| 原因 | 测试 | 覆盖确认 |
|---|---|---|
| `OWNER_CANCELLED` | `test_same_attempt_concurrent_owner_cancellation_hands_off_to_waiter` (L1226) | owner 取消后 waiter 接棒执行成功，later 复用 |
| `TOOL_EXCEPTION` | `test_same_attempt_concurrent_tool_exception_hands_off_to_waiter` (L1186) | owner 异常后 waiter 接棒执行 |
| `HOST_ACCEPT_REJECTED` | `test_same_attempt_concurrent_rejected_accept_hands_off_to_waiter` (L1012) | owner accept rejected 后 waiter 接棒，later 复用 |
| `HOST_ACCEPT_TIMEOUT` | `test_same_attempt_concurrent_timed_out_accept_hands_off_to_waiter` (L1144) | owner timeout 后 waiter 接棒 |

每类测试均验证：
- owner 得到 `ToolFailedOutcome`
- waiter 得到正确的 outcome（成功路径复用 replacement 结果，全 timeout 路径各自失败）
- `waiter_outcome.result.hint != "duplicate_prior_accept_missing"`（确认不是旧版行为）

额外覆盖：
- `GOVERNED_BEFORE_ACCEPT` 通过 policy governed error 路径（HINT/HARD_STOP 等）隐式覆盖；该路径在 `finally` 中正确记录 durable_missing。无并发 waiter 场景的显式测试，但状态机行为确定，低风险。

### 5. 文档准确性

**结论：PASS**

| 文档 | 位置 | 内容 | 准确性 |
|---|---|---|---|
| Host README | 第 231 行 | "owner 未产生可复用 accepted fact 时，等待者中只允许一个接棒成为新 owner，其它等待者继续等待新 owner" | 与实现一致 |
| Control Doc | 第 196 行 | "durable-missing 后 waiter 接棒执行已在当前 PR 修复；awaiting fanout 不直接实现" | 与实现一致 |
| Tests README | 第 131 行 | "durable-missing waiter 接棒" | 覆盖描述准确 |

### 6. AGENTS.md 约束检查

**结论：PASS**

- **分层**：`dayu.host.tool_duplicate_governance` 仅依赖 `dayu.contracts`（公共契约）和 `dayu.host.durable.codec`（同层 durable 基础），无反向依赖 ✓
- **类型**：无 `Any`/`object`/无类型签名；dataclass 使用 `slots=True`；`DuplicateGovernancePort` 使用 Protocol ✓
- **docstring**：所有公共函数/类有完整中文 docstring（参数、返回值、异常） ✓
- **测试同步**：tests/README.md 已覆盖 durable-missing waiter 接棒描述 ✓
- **无兼容性代码**：`DuplicateDurableMissingReason` 不 re-export 到 `dayu.host.__init__` 或 `dispatch.py` ✓
- **无魔法值**：`_TOOL_RUNTIME_CANCELLED_REASON` 定义为模块级常量 ✓

---

## Findings（按严重度排序）

### F-01 [LOW — Dead Code Path]

`tool_runtime.py` 第 2271–2275 行的 `DURABLE_MISSING` 分支对当前 `InMemoryAttemptDuplicateGovernance` 实现为死代码——`decide_duplicate` 在 durable-missing 场景走 `continue` 重回循环，永不返回 `DURABLE_MISSING`。

- **不影响正确性**：`DuplicateGovernancePort` 是 Protocol，其他实现可能返回 `DURABLE_MISSING`；该分支是合法的 defensive handling
- **建议**：不要求修复；若未来确认无需该分支，可在 Protocol 契约或 tool_runtime 消费侧明确

### F-02 [LOW — Test Coverage Gap]

`GOVERNED_BEFORE_ACCEPT` durable-missing 原因（第 2244 行默认值）在 policy governed error 场景（HARD_STOP/HINT 等）被正确记录，但没有并发 waiter 场景的显式测试。

- **实际风险低**：状态机行为确定——waiter `continue` 后重新成为 owner，同样被 govern；不会死锁或泄漏
- **建议**：不要求当前 gate 补充；若后续扩展 duplicate governance 测试矩阵时可加入

---

## 实际检查的文件

```
dayu/host/tool_duplicate_governance.py      全量 (1–632)
dayu/host/tool_runtime.py                   第 2220–2370, 4822–4905, 5555–5566
tests/host/test_toolruntime_duplicate_governance.py  全量 (1–1659)
dayu/host/README.md                         全量 (1–329)
tests/README.md                             全量 (1–203)
docs/host/host-core-followup-implementation-control.md  第 196 行
```

未检查但与 handoff 间接相关：
- `dayu/host/dispatch.py` — grep 确认无 `durable_missing`/`DuplicateDurableMissingReason` 泄漏
- `dayu/host/__init__.py` — grep 确认 `DuplicateDurableMissingReason` 未 re-export

---

## 建议验证命令

```bash
source .venv/bin/activate

# 核心测试：duplicate governance 全量
pytest tests/host/test_toolruntime_duplicate_governance.py -q

# 相关回归：accept barrier + diagnostics
pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py -q

# 类型检查（目标文件）
python -m pyright dayu/host/tool_duplicate_governance.py dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py
```

---

## 裁决

**PASS** — 无 blocking / high / medium finding。durable-missing waiter handoff 状态机正确实现了"旧 owner 失败 → 只有一个 waiter 接棒 → 其他 waiter 等待新 owner → 复用新 accepted fact"的语义。四个 durable-missing 原因（cancellation / exception / accept rejected / accept timeout）均有并发测试覆盖。文档与代码一致。两项 LOW finding 不要求修复。
