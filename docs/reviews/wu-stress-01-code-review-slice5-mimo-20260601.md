# Code Review

## Scope

- Mode: current changes
- Branch: test/host-stress-suite
- Base: main
- Output file: docs/reviews/wu-stress-01-code-review-slice5-mimo-20260601.md
- Included scope: tests/host/stress_support.py (HostStressScenario), tests/host/test_host_production_stress.py (Slice5MixedHostDiagnostics, test_mixed_host_stress_deterministic_fault_injection, _slice5_timeout_summary)
- Excluded scope: 生产代码、public contract、durable schema
- Parallel review coverage: 使用 Explore subagent 追踪 `cancel_run` 对 queued run 的 terminal EventLog 行为，确认 RUN_CANCELLED 确实写入 EventLog

## Findings

未发现实质性问题。

## Analysis Notes

以下为 review 过程中重点验证的非平凡结论，不是 findings：

### `_SLICE5_PRIMARY_TERMINAL_COUNTS = (4, 5, 4)` 正确性验证

初始疑虑：session 2 有 5 个 Run（stream-exception、active-final、queued-cancel、failed、final），如果每个都产生 terminal event，预期应为 5 而非 4。

验证结论：`HostEventKind` 枚举只有 `PROGRESS`、`SUCCEEDED`、`FAILED`、`CANCELLED` 四个成员，没有 `LOST`。stream exception 调用 `ingestor.close_worker_lost()` 产生的 `RUN_LOST` terminal 只写入 durable EventLog，不通过 `watch_session_events` public API 传递。`consume_terminals` 过滤 `HostEventKind.SUCCEEDED/FAILED/CANCELLED`，不会消费 `RUN_LOST`。因此 session 2 的 primary watcher 正确观测到 4 个 terminal（active-final→SUCCEEDED、queued-cancel→CANCELLED、failed→FAILED、final→SUCCEEDED），`(4, 5, 4)` 准确。

同理，session 0 的 owner crash 产生 LOST terminal 但不被 primary watcher 消费，count 4 正确。

验证方式：源码分析 `dayu/host/api.py:2489` HostEventKind 枚举定义；实证测试确认 queued-cancel 确实产生 RUN_CANCELLED EventLog 条目（`tests/host/recovery_support` 的 `run_transition.py:2457`）。

### `terminal_dedupe_ok` 证明链验证

`terminal_events_for_runs()` 只返回 succeeded/failed/cancelled 的 `StressTerminalObservation`（不含 RUN_LOST）。`terminal_event_count_for_runs()` 返回包含 RUN_LOST 的 terminal EventLog 总数。

对于 15 个 Run：
- `len(durable_observations)` = 14（不含 RUN_LOST）
- `all_terminal_event_count` = 15（含 stream exception 的 RUN_LOST）
- `len(public_snapshots)` = 15

`terminal_dedupe_ok` = `duplicate_count == 0` AND `terminal_dedupe_ok(observations)` AND `all_terminal_event_count == len(public_snapshots)` = True。证明链完整。

### `watch_lag_drained` 验证

`read_session_terminal_sequences` 使用 `_TERMINAL_EVENT_TYPES`（只含 succeeded/failed/cancelled），与 `consume_terminals` 的过滤集合一致。因此 lag 计算的"已观测"和"durable 最新"使用相同口径，最终 lag 全部为 0。

### `mixed_statuses_ok` 中 LOST 来源验证

session 0 的 crashed run public snapshot 状态为 LOST（run row 直接记录，不依赖 EventLog）。session 2 的 stream exception 也产生 LOST public snapshot。因此 `RunStatus.LOST in statuses` 成立。

### Timeout 行为验证

- pytest timeout: 120s
- 内部 wait/consume timeout 预算: `_SLICE5_WAIT_TIMEOUT_SECONDS=25` + `_SLICE5_CONSUME_TIMEOUT_SECONDS=40` = 65s
- 内部 `TimeoutError` 被捕获并转换为 `AssertionError`，携带 summary JSON
- `_slice5_timeout_summary` 不读取 durable store，避免失败窗口的 SQLite 争用

## Open Questions

无。

## Residual Risk

- `pytest-timeout` 可以在 event loop 全局阻塞时终止整个测试，即使内部 deadline 已设置；内部较短的显式 deadline 用于正常受控等待，降低了此风险。
- owner crash/recovery 的 terminal 可能在 primary watcher attach 之前的 Host startup recovery 阶段发生。Slice 5 的 watch lag diagnostic 因此对 pre-attach terminal count 做了 baseline，只在 watcher attach 后的 mixed flow 上测量 drain。
- `HostEventKind` 无 `LOST` 成员意味着 `RUN_LOST` terminal 事实只能通过 durable SQL 或 `RunStatus.LOST` public snapshot 验证，不能通过 `watch_session_events` 实时观测。这是 Host public contract 的已知设计边界，不是 Slice 5 defect。
