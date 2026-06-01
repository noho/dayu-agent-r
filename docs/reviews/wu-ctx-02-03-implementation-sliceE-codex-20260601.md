# WU-CTX-02 + WU-CTX-03 Implementation Slice E - AgentCodex

## 结论

Slice E 已完成。当前实现未修改生产代码，只补齐真实 `HostDispatchScheduler` / `LocalEngineWorkerFactory` / `LocalWorkerHandle` / EngineEvent ingest / recovery dispatch-loop 组合路径的连续 reactive overflow E2E。

## 变更文件

- `tests/host/test_dispatch_scheduler.py`
  - 新增 `_RepeatedReactiveOverflowWorkerFactory`、`_RepeatedReactiveOverflowWorker`、`_RepeatedReactiveOverflowHandle`。
  - 新增 `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit`。
  - 扩展 `_soft_compact_policy`，允许测试显式设置 `max_reactive_compactions_per_run`。
- `tests/README.md`
  - 同步 `test_dispatch_scheduler.py` 已覆盖连续 reactive overflow dispatch-loop 达到上限后 fail closed 且不写 `RUN_LOST`。

## 实现行为

新增 E2E 使用真实 scheduler dispatch 路径：

1. 先创建已处于 `RUNNING` 且带初始 Attempt / pending dispatch 的 Run。
2. 使用 deterministic fake worker factory；每次 worker accept 后，handle 的 `events()` 立即产出一个 `EngineEventType.CONTEXT_COMPACTION_REQUESTED`。
3. 前两次 overflow 由 `FakeContextCompactor` compact 成功，Host 写入 `CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED` 并创建 recovery Attempt。
4. 第三次 overflow 触发 `max_reactive_compactions_per_run=2` 上限，Host 不再创建新的 compact request / recovery Attempt，写入 `CONTEXT_COMPACTION_FAILED` 并将 Run fail closed。

测试同步使用 `asyncio.Condition` 等待 accept count 与 handle close count；没有用裸 sleep 观察最终状态。handle close 发生在 scheduler ingest 收口和资源释放路径之后，用作 deterministic 完成信号。

## 精确断言

新增测试断言：

- `expected_attempt_count = 1 + policy.max_reactive_compactions_per_run`。
- `run.status == RunStatus.FAILED`。
- `factory.created == expected_attempt_count`。
- `len(factory.accepted_snapshots) == expected_attempt_count`。
- `_attempt_count_for_run(...) == expected_attempt_count`。
- `_attempt_count_for_run(...) <= expected_attempt_count`。
- `CONTEXT_COMPACTION_REQUESTED` count 等于 `policy.max_reactive_compactions_per_run`。
- `CONTEXT_COMPACTED` count 等于 `policy.max_reactive_compactions_per_run`。
- `CONTEXT_COMPACTION_FAILED` count 为 1。
- `RUN_LOST` count 为 0。
- `RUN_FAILED` count 为 1。
- 最后一条 `CONTEXT_COMPACTION_FAILED` payload：
  - `failure_reason == "reactive_compact_limit_reached"`。
  - `attempt_count == 0`。
  - `retry_repair_budget_exhausted is False`。
  - fallback 字段为 no-fallback 形态，`fallback_action == "not_applicable"`。
- 最后一条 `RUN_FAILED` payload：
  - `error_code == "reactive_compact_limit_reached"`。
  - `context_compaction_failed_event_id` 指向最后的 `CONTEXT_COMPACTION_FAILED` event id。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -q`
  - 结果：`57 passed in 1.10s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`

## README 决策

- 已更新 `tests/README.md`，因为本 Slice 修改了 `tests/host/test_dispatch_scheduler.py` 的稳定覆盖范围。
- 未更新 `dayu/host/README.md`：现有文档已经说明 reactive path 在 `max_reactive_compactions_per_run` 范围内继续 compact，超过上限后 fail closed，并说明不写 `RUN_LOST`。
- 未更新 `dayu/config/README.md`：本 Slice 没有配置入口、默认配置或 profile 行为变化。

## RR-CTX-PLAN-03 覆盖情况

本 Slice 覆盖连续 reactive overflow 不无限 compact / dispatch 的 dispatch-loop 风险：通过真实 scheduler + worker accept + ingest + recovery Attempt 路径证明达到 reactive 上限后 fail closed，Attempt 数、compact 事件数和 terminal 状态均可观察。

## 残余风险

- 本 Slice 使用 fake compactor 和 fake worker，不覆盖真实 provider context overflow 文案分类；该能力属于 runner/provider 层既有测试边界。
- 本 Slice 不覆盖多进程 recovery / positive orphan proof；设计中该语义属于 Phase 11，不应由 WU-CTX-03 dispatch-loop E2E 承担。
- 本 Slice 不重复 ingest-level reactive compact count 损坏读取测试；这里只验证真实 dispatch-loop 组合路径。

## Stop Status

未触发 blocker。未发现需要修改生产代码的 correctness bug。未 commit，变更留在 working tree 供 controller review gate。
