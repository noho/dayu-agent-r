# WU-CTX-02 + WU-CTX-03 Slice E Code Review — AgentMiMo

## 审查范围

- **审查对象**：当前未提交的 Slice E diff（`tests/host/test_dispatch_scheduler.py` + `tests/README.md`）。
- **Approved plan**：`docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md` Slice E。
- **设计真源**：`docs/host/design.md` 第 25 节 Context Governance。
- **Accepted Slice D commit**：13500ae。
- **Implementation artifact**：`docs/reviews/wu-ctx-02-03-implementation-sliceE-codex-20260601.md`。

### Diff 摘要

| 文件 | 变更 |
|---|---|
| `tests/host/test_dispatch_scheduler.py` | 新增 `_RepeatedReactiveOverflowHandle`、`_RepeatedReactiveOverflowWorker`、`_RepeatedReactiveOverflowWorkerFactory` 三个测试辅助类；新增 `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 测试；扩展 `_soft_compact_policy` 增加 `max_reactive_compactions_per_run` 参数；新增常量 `_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS = 2.0`。 |
| `tests/README.md` | 更新 P12.6 memory semantic smoke 中 `test_dispatch_scheduler.py` 覆盖描述，追加"连续 reactive overflow dispatch-loop 达到上限后 fail closed 且不写 `RUN_LOST`"。 |

**生产代码变更**：无。`git diff --stat HEAD -- dayu/` 输出为空。

---

## 验证命令与结果

| 命令 | 结果 |
|---|---|
| `pytest tests/host/test_dispatch_scheduler.py::test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit -xvs` | 1 passed in 0.27s |
| `pytest tests/host/test_dispatch_scheduler.py -q` | 57 passed in 1.02s |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

---

## Findings

### Severity: None (Informational)

#### F-01: 冗余断言 `actual_attempt_count <= expected_attempt_count`

- **文件**：`tests/host/test_dispatch_scheduler.py:4008-4009`
- **描述**：测试先断言 `actual_attempt_count == expected_attempt_count`，紧随其后断言 `actual_attempt_count <= expected_attempt_count`。后者在前者为真的前提下恒真，属于冗余逻辑。
- **影响**：不影响正确性，不影响测试通过/失败判定。
- **建议**：保留 `==` 断言即可，`<=` 可移除。但这不是 blocker，因为设计 plan 中同时列出了两个断言（`== expected_attempt_count` 和 `<= expected_attempt_count`），实现者按 plan 逐条还原是合理的。
- **严重性**：Informational。

---

## 逐项审查结论

### 1. E2E 是否真实覆盖 scheduler / worker dispatch-loop

**通过。** 新增测试使用真实 `HostDispatchScheduler`、`LocalEngineWorkerFactory` / `LocalWorkerHandle` 边界、真实 `drain_once()` 和 `wake_dispatch()`。Worker accept 后通过 `events()` 产出 `CONTEXT_COMPACTION_REQUESTED` EngineEvent，scheduler 完成 ingest 后触发 reactive compact，compactor 成功后创建 recovery Attempt 再次 wake dispatch。这是完整的 dispatch-loop E2E，不是 ingest unit test 的重复。

### 2. 同步机制是否确定性

**通过。** 使用 `asyncio.Condition` + `wait_for` 等待 accept count 和 close count 达标，超时 `_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS = 2.0`。没有裸 sleep。close 发生在 scheduler ingest 收口和资源释放路径之后，作为 deterministic 完成信号。

### 3. Attempt 数是否严格不超过 1 + max_reactive_compactions_per_run

**通过。**
- `expected_attempt_count = 1 + policy.max_reactive_compactions_per_run = 1 + 2 = 3`。
- 测试断言 `factory.created == 3`、`len(factory.accepted_snapshots) == 3`、`_attempt_count_for_run(...) == 3`。
- 设计语义：初始 Attempt（1）+ 每次 reactive overflow compact 成功后创建 recovery Attempt（2 次）= 3。第三次 overflow 触达上限，不再创建新 Attempt。

### 4. 事件计数是否符合设计上限策略

**通过。**

| 事件类型 | 期望 | 实际逻辑 |
|---|---|---|
| `CONTEXT_COMPACTION_REQUESTED` | `max_reactive_compactions_per_run` = 2 | 前两次 overflow 各写一条 |
| `CONTEXT_COMPACTED` | `max_reactive_compactions_per_run` = 2 | 前两次 compact 成功各写一条 |
| `CONTEXT_COMPACTION_FAILED` | 1 | 第三次 overflow 达上限写一条 |
| `RUN_LOST` | 0 | fail closed 不走 LOST |
| `RUN_FAILED` | 1 | fail closed 写一条 |

### 5. Failed payload 验证

**通过。**
- `failure_reason == "reactive_compact_limit_reached"` — 正确。
- `assert_failed_payload_no_fallback` 验证：`operation_id` 非空、`attempt_count == 0`（上限触发时没有外部 LLM attempt）、`retry_repair_budget_exhausted == False`、`fallback_action == "not_applicable"`、`fallback_policy_decision == None` 等全部 no-fallback 形态字段。
- `run_failed_payload["error_code"] == "reactive_compact_limit_reached"` — 正确。
- `run_failed_payload["context_compaction_failed_event_id"] == failed.event_id` — RUN_FAILED 关联到最后的 CONTEXT_COMPACTION_FAILED event。

### 6. 生产代码变更 / 测试 helper 耦合

**通过。** 无生产代码变更。`_soft_compact_policy` 扩展仅增加可选 keyword 参数 `max_reactive_compactions_per_run`，默认值与 `ContextBudgetPolicy` 默认一致，不引入耦合。新增测试辅助类仅在测试文件内使用，未新增生产测试 seam。

### 7. README 更新决策

**通过。**
- `tests/README.md`：触发规则命中（`tests/` 修改），更新内容为追加连续 reactive overflow dispatch-loop 覆盖描述，符合 tests README 职责。
- `dayu/host/README.md` 未更新：合理。现有文档已描述 reactive path 上限后 fail closed 行为。
- `dayu/config/README.md` 未更新：合理。本 Slice 无配置入口变化。

### 8. AGENTS 测试/编码约束

**通过。**
- 中文 docstring：所有新增类和方法均有完整中文 docstring（参数、返回值、异常）。
- 类型签名：无 `Any`、无 `object`、无无类型参数。
- 无魔法数字：`_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS` 为命名常量；`max_reactive_compactions_per_run=2` 为显式参数。
- 无 overfitted fragile test：测试通过确定性 fake factory 和 Condition 同步，不依赖时序竞态。

---

## 最终结论

**Accepted. No blocking findings.**

Slice E diff 实现了 plan 要求的连续 reactive overflow dispatch-loop E2E，验证手段确定性且可靠，断言覆盖 Attempt 数、事件计数、terminal payload 和 RUN_LOST 为零。无生产代码变更，README 同步决策合理。唯一 Informational finding 是冗余 `<=` 断言，不影响正确性。
