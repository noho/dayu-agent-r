# WU-CTX-02 + WU-CTX-03 Slice C Code Review (AgentDS)

## 审查范围

- **Gate**: WU-CTX-02 + WU-CTX-03 implementation Slice C
- **审查文件**:
  - `dayu/host/context_fallback.py`（新增）
  - `dayu/host/run_input.py`（修改）
  - `dayu/host/dispatch.py`（修改）
  - `tests/host/test_run_input_builder.py`（修改）
  - `tests/host/test_dispatch_scheduler.py`（修改）
  - `dayu/host/README.md`（修改）
  - `tests/README.md`（修改）
- **前置 accepted commits**: Slice A `2f2f22c`、Slice B `e6156de`
- **设计真源**: `docs/host/design.md` 第 1 节、第 25 节
- **Approved plan**: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- **Implementation artifact**: `docs/reviews/wu-ctx-02-03-implementation-sliceC-codex-20260601.md`

## 验证命令及结果

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q
# 97 passed in 1.15s

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# 0 errors, 0 warnings, 0 informations
```

## Findings

### No blocking findings

审查未发现需要修复的 blocking issue。以下逐条确认评审重点。

---

#### 1. Deterministic recent-window fallback selection 符合设计

**文件**: `dayu/host/context_fallback.py`

`build_recent_window_fallback_selection()` (line 331-410) 的选择逻辑与设计一致：

- **固定 current input anchor**: `_current_input_block()` (line 516-535) 从 material blocks 中精确查找 `section=CURRENT_INPUT_ANCHOR` 且 `current_input_ref in canonical_source_refs` 的唯一 block，未找到或多于一个时抛 `ValueError`。
- **stable / compact represented context**: `_required_block_ids()` (line 538-557) 必保留集合包含 `section=STABLE_INPUT` 和 `already_represented=True` 的所有 blocks。
- **`recent_raw_turns_floor`**: 来自 `MemoryProjectionPolicy.recent_raw_turns_floor`（dispatch.py line 1791-1793）。
- **reverse chronological raw turn block order**: `_reverse_chronological_raw_blocks()` (line 560-579) 按 `event_sequence DESC, event_sub_index DESC, block_id DESC` 排序。
- **hard budget 门控**: 每个候选 raw turn block 在加入前通过 `estimate_recent_window_fallback_budget()` 预估算，仅在 `hard_budget_passed=True` 时加入；被 block 的下一 block id 记录在 `blocked_next_block_id`。
- **必保留集合超 hard budget 时的行为**: `required_budget.hard_budget_passed` 为 `False` 时，`for block in raw_blocks` 循环不追加新 block，最终 `selected_blocks` 仅含必保留集合。调用方 (`dispatch.py` line 1722-1724) 随后因 `budget.hard_budget_passed=False` 走 `fallback_action=fail_closed`。
- **无 public N 配置**: floor 来自 `MemoryProjectionPolicy`，selection 由预算驱动。
- **无 arbitrary max-N 常量**: 未定义任何魔法上限。

结论：**符合**。

---

#### 2. Fallback digest 与 payload 稳定、无泄漏

**payload 结构**: `RecentWindowFallbackSelection.to_window_payload()` (line 188-207) 包含:
- `selected_block_ids`、`dropped_block_ids`（block id 列表）
- `current_input_ref`、`source_refs`（canonical refs）
- `recent_raw_turns_floor`、`trigger_source`、`policy_ref`
- `input_cursor`、`selected_raw_turn_count`
- `blocked_next_block_id`（仅在存在时）

无 raw prompt、API key、headers 或完整 provider payload。

**digest**: `sha256_digest_json(window_payload)` → 对相同 inputs 确定。

**`fallback_action` 语义**:
- `"dispatch"` — fallback 预算通过，创建 Attempt dispatch
- `"fail_closed"` — fallback 预算失败或 selection 失败，Run `FAILED`
- `"not_applicable"` — 非 fallback 路径（compact 成功、limit reached 等）使用此默认值

**Slice B 兼容性**: `tests/host/_context_compaction_assertions.py` 的 `assert_failed_payload_no_fallback()` 断言 `fallback_policy_decision is None`、`fallback_input_window is None`、`fallback_input_digest is None`、`fallback_budget_result is None`、`fallback_action == "not_applicable"`。Slice C 非 fallback 路径（count limit、corrupted count）继续使用此断言，保持 Slice B 兼容。

结论：**符合**。

---

#### 3. Budget re-estimate 复用现有 conservative estimator

**文件**: `dayu/host/context_fallback.py`, line 413-454

`estimate_recent_window_fallback_budget()`:
- 调用现有 `estimate_context_budget(policy, BudgetEstimateInput(...))`
- `message_fragments` 使用 `BudgetTextFragment(fragment_ref=block.block_id, text=block.text)`
- 结果经 `decide_context_budget()` 判定 over/within budget
- 未引入 provider tokenizer
- 未新增 `ContextBudgetPolicy` public 字段
- 未修改估算算法

结论：**符合**。

---

#### 4. RunInputBuilder fallback provider 默认 no-op，active fallback 行为正确

**文件**: `dayu/host/run_input.py`

- `ContextFallbackProvider` Protocol (line 433-450): 定义 `load_context_fallback()` 接口。
- `NoopContextFallbackProvider` (line 453-468): 始终返回 `None`，作为默认 no-op。
- `EventLogContextFallbackProvider` (context_fallback.py line 235-328): 从 EventLog 读取最近 `CONTEXT_COMPACTION_FAILED` 事件中的 `fallback_action=dispatch` payload，提取 `selected_block_ids` / `current_input_ref` / `fallback_input_digest`，构造 `ActiveRecentWindowFallback`。
- 加载时验证 `current_input_ref` 与当前输入匹配，不匹配返回 `None`。
- `RunInputBuilder.build()` (line 1618-1642): fallback 为 `None` 时正常渲染 memory + compact + continuity；不为 `None` 时调用 `_fallback_context_messages()`。

**`_fallback_context_messages()`** (line 2392-2426):
- 用 `selected_block_ids` 从 ordinary material blocks 中过滤同源 block
- 做唯一性校验（frozenset 重复检测）
- 校验所有 selected block ids 均在 material view 中存在
- 排除 current input anchor block（当前 input 由正常 user message anchor 追加）
- 按原 material order 保持 block 顺序

**`_fallback_message_from_material_block()`** (line 2429-2445):
- RAW_USER_TURN → UserMessage
- RAW_ASSISTANT_TURN → AssistantMessage
- 其他（stable/evidence/summary）→ SystemMessage

**默认 no-op**: `create_no_tool_run_input_builder()` (line 1772-1776) 和 `create_tool_enabled_run_input_builder()` (line 1824-1828) 仅在未显式传入时使用 `NoopContextFallbackProvider()`。

**dispatch 接线**: `HostDispatchScheduler` (dispatch.py line 2654) 在构造 `RunInputBuilder` 时注入 `EventLogContextFallbackProvider(self._transaction_runner)`，实现生产路径 fallback。

结论：**符合**。

---

#### 5. Proactive dispatch/fail-closed 状态机正确

**文件**: `dayu/host/dispatch.py`

`_append_compaction_failed_with_proactive_fallback()` (line 1632-1744):
- 无 policy → 写无 fallback 的 failed event，return None（caller fail closed）
- selection/estimate 异常 → 写 `fallback_policy_decision=deterministic_recent_window_selection_failed` + `fallback_action=fail_closed`，return None
- budget 通过 → 写 `fallback_policy_decision=deterministic_recent_window` + `fallback_action=dispatch`，调用 `_start_governed_in_transaction(transaction, run)` 创建 Attempt，返回 PendingDispatchRecord
- budget 失败 → 写 `fallback_action=fail_closed`，return None

调用方：
- 返回 PendingDispatchRecord → `_GovernanceStageResult(pending_dispatch=..., compact_accepted=None)` → `wake_dispatch()` → normal dispatch
- 返回 None → `_fail_unstarted_in_transaction()` → `RUN_FAILED`

**状态路径验证**:

| 路径 | 事件序列 | RECOVERING | CONTEXT_COMPACTED | Attempt 数 |
|---|---|---|---|---|
| fallback dispatch | FAILED(dispatch) → RUN_STARTED → ATTEMPT_STARTED → dispatch | 否 | 否 | 1 |
| fallback fail closed | FAILED(fail_closed) → RUN_FAILED | 否 | 否 | 0 |
| selection failed | FAILED(fail_closed) → RUN_FAILED | 否 | 否 | 0 |
| count limit (no fallback) | FAILED(not_applicable) → RUN_FAILED | 否 | 否 | 0 |

- 不进入 RECOVERING
- 不写 CONTEXT_COMPACTED
- 不写 compact artifact
- 不物化 memory stable facts（_append_compaction_failed_event 中 attempt_id=None，memory projection 只消费 canonical facts，failed event 不被视为 compact success）
- 预算通过 → 创建 Attempt（`_start_governed_in_transaction` 使用 `start_reason=initial|queue_promotion`）
- 预算失败 → 零 Attempt fail closed

结论：**符合**。

---

#### 6. 测试覆盖核心分支，无兼容逻辑堆积

**新增/更新测试** (test_run_input_builder.py):
- `test_recent_window_fallback_selection_is_stable_and_budget_bounded` — determinism、floor 保留、blocked_next_block_id、selected_raw_turn_count、hard_budget_passed
- `test_recent_window_fallback_estimate_covers_normal_empty_stable_and_over_budget` — normal、无 stable input、over-budget 三类估算
- `test_fallback_provider_renders_only_selected_window_and_current_input` — RunInputBuilder 渲染：selected recent window + current input，无 dropped old raw turn

**新增/更新测试** (test_dispatch_scheduler.py):
- `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` — semantic proposal failure 写 rejected facts 后通过 fallback dispatch，1 Attempt，fallback_action=dispatch
- `test_pre_start_governance_compact_failure_is_attempt_free` — compactor missing + fallback budget pass → 1 Attempt，event ordering: FAILED < RUN_STARTED < ATTEMPT_STARTED，no CONTEXT_COMPACTED
- `test_pre_start_governance_fallback_budget_fail_closes_run` — fallback over-budget → 0 Attempt，Run FAILED，fallback_action=fail_closed
- `test_pre_start_governance_proactive_count_limit_blocks_second_compact` — count limit path 使用 `assert_failed_payload_no_fallback`（无 fallback）
- `test_pre_start_governance_corrupted_compact_count_fails_closed` — corrupted count path 使用 `assert_failed_payload_no_fallback`（无 fallback）

**无兼容逻辑堆积**: 测试使用 `_StaticContextFallbackProvider` 辅助类提供预置 fallback view，未修改任何旧测试结构。所有旧测试继续通过。

结论：**符合**。

---

#### 7. README 更新符合职责

**dayu/host/README.md**:
- 在 Context Governance 段落新增一段（+4 行）简洁描述 proactive deterministic recent-window fallback 的稳定语义：fallback 不写 CONTEXT_COMPACTED、不写 compact artifact、不进入 RECOVERING、不物化 memory stable fact、预算失败 fail closed。
- 不写实现细节、不写未来计划、不写过程状态。

**tests/README.md**:
- 在 `test_run_input_builder.py` 覆盖说明中添加 "fallback selected recent window rendering"。
- 在 `test_dispatch_scheduler.py` 覆盖说明中添加 "proactive compaction failure 后 recent-window fallback dispatch / hard-budget fail closed 不写 CONTEXT_COMPACTED"。
- 属于测试手册职责范围（覆盖矩阵说明），未越界。

结论：**符合**。

---

## 设计/AGENTS 合规性结论

### 架构硬约束

| 约束 | 合规 |
|---|---|
| Host 是 context governance 真源 | ✅ fallback 完全在 Host 内部实现 |
| 分层边界 UI → Service → Host → Engine | ✅ 未新增跨层依赖 |
| `dayu.runtime` 不 import `dayu.host` | ✅ context_fallback.py 无 runtime import |
| 禁止反向依赖 | ✅ 无 Engine/Host/Service 反向 import |
| 不下沉业务规则到 runtime | ✅ fallback 完全在 Host 层 |

### 编码硬约束

| 约束 | 合规 |
|---|---|
| 中文 docstring | ✅ 所有函数/类/模块有完整中文 docstring |
| 禁止 `Any`/`object` | ✅ 无使用 |
| 禁止 hasattr/getattr 逃避类型设计 | ✅ 无使用 |
| 禁止魔法数字/魔法字符串 | ✅ 使用模块级常量 |
| 模块间依赖最小化 | ✅ context_fallback.py 只依赖 Host 内部模块 |
| 禁止兼容性代码 | ✅ 无 re-export/wrapper/facade |
| 禁止 god 对象 | ✅ 职责清晰分离 |

### Plan 对齐

| Plan 约束 | 合规 |
|---|---|
| 不新增 public policy 字段 | ✅ |
| 不引入 provider tokenizer | ✅ |
| 不改变 durable schema | ✅ |
| proactive failure 不进 RECOVERING | ✅ |
| fallback 不写 CONTEXT_COMPACTED | ✅ |
| fallback 不物化 memory projection | ✅ |
| fallback budget re-estimate 复用现有 estimator | ✅ |
| RunInputBuilder 默认 no-op | ✅ |
| EventLog failed payload 诊断字段完整 | ✅ |

## 最终结论

**Accepted**

No blocking findings。Slice C proactive deterministic recent-window fallback 实现完整、正确，与 approved plan 和设计真源一致。97 个测试全部通过，pyright 零错误零警告。后续 Slice D 可在本 Slice 的 fallback selection/budget helper、ContextFallbackProvider 协议和 failed payload 诊断字段基础上继续实现 reactive fallback recovery path。
