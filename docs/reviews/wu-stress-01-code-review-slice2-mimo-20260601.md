# WU-STRESS-01 Slice 2 Code Review

## Gate

- **Gate**: deepreview
- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Slice**: Slice 2 — Repeated startup / recovery / crash E2E stress
- **Review role**: AgentMiMo, code review specialist
- **Date**: 2026-06-01

## Reviewed Target

- Uncommitted diff on branch `test/host-stress-suite` vs HEAD (`11d00cc`).
- Changed files:
  - `tests/host/stress_support.py` (+253 lines)
  - `tests/host/test_host_production_stress.py` (+263 lines)
- Accepted plan: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- Implementation artifact: `docs/reviews/wu-stress-01-implementation-slice2-codex-20260601.md`

## Conclusion

**PASS**

No blocking findings. Implementation correctly covers the Slice 2 plan requirements. All assertions are reliable, recovery_support is properly reused via thin wrappers, no production code boundary violations, and Slice 3-5 scope is not encroached.

## Findings

### 01-未修复-INFO-finally块对已join进程的冗余terminate调用

`test_host_production_stress.py:315-316` — `_run_live_owner_probe` 的 `finally` 块在正常路径下会调用 `terminate_process(owner_process)`，但此时 owner_process 已在第 308 行通过 `join` 完成退出。`terminate_process` 内部有 `is_alive()` 守卫（`recovery_support.py:629`），所以不会抛异常，但会产生一次冗余的 `process.terminate()` 系统调用。

**严重程度**: INFO（不影响正确性或稳定性）

**建议**: 可考虑在 `finally` 前 return 后不进入 finally 的 terminate 路径，或在 `terminate_process` 内跳过已退出进程的 terminate 调用。当前实现在功能上无害，不阻塞 review。

### 02-未修复-INFO-terminal_duplicate_count的run_id去重语义

`stress_support.py:557-567` — `terminal_duplicate_count` 同时检查 `run_id` 和 `event_id` 重复。对于 Slice 2 场景（每个 run 恰好一个 terminal event），同一 `run_id` 出现两次才算 duplicate。但如果未来 Slice 5 场景中同一 run 出现不同 event_id 的 terminal event（例如 RUN_SUCCEEDED 后又 RUN_CANCELLED），该实现会把第二次 terminal 计为 duplicate。这符合"terminal 去重"语义（每个 run 至多一个 terminal），但 `run_id` 和 `event_id` 的 OR 逻辑值得在未来 Slice 5 中验证是否符合预期。

**严重程度**: INFO（当前 Slice 2 语义正确，仅提示未来 slice 需确认）

## Verified Properties

### 3 轮 crash/reopen recovery 覆盖

- `_CRASH_CYCLE_COUNT = 3`（`test_host_production_stress.py:45`）
- 循环 `for cycle_index in range(_CRASH_CYCLE_COUNT)`（第 145 行）正确执行 3 轮
- 每轮: `start_and_crash_owner_for_stress` → crash → `open_host` + recovery worker → terminal → get_run snapshot
- 断言: `recovery_count == _CRASH_CYCLE_COUNT`（第 236 行）、`attempt_lost_count == _CRASH_CYCLE_COUNT`（第 237 行）

### Live owner probe 不误恢复

- `_run_live_owner_probe` 在 crash 循环前执行（第 136-137 行）
- 记录 before/after `ATTEMPT_LOST` 和 `RUN_RECOVERING` 计数（第 293-306 行）
- probe 进程打开同一 DB 后关闭，验证 owner 进程仍存活（第 303 行）
- 断言: `live_attempt_lost_delta == 0`（第 234 行）、`live_recovery_delta == 0`（第 235 行）

### attempt_count / recovery_count / terminal duplicate 断言可靠性

- 每个 crashed run 的 `attempt_count == 2`（第 246-248 行），通过 `recovery_support.attempt_count_for_run` 的 durable SQL 查询验证
- Live owner run 的 `attempt_count == 1`（第 249 行）
- `terminal_duplicate_count == 0` 和 `terminal_dedupe_ok` 通过 `terminal_events_for_runs` + `terminal_duplicate_count` 验证（第 189-190 行，第 250-254 行）
- 每个 terminal 观测的 `terminal_status is HostTerminalStatus.SUCCEEDED`（第 251-254 行）

### Durable SQL helper 类型安全

- `terminal_events_for_runs`（`stress_support.py:791-853`）使用参数化查询（第 820-828 行），无 SQL 注入风险
- 每个 row 字段都有 `isinstance` 类型检查（第 836-843 行）
- docstring 明确声明 point-in-time diagnostic 语义（第 796-800 行）
- `count_event_type` 和 `attempt_count_for_run` 有空值校验并委托给 `recovery_support` 的同名函数

### 复用 recovery_support 而非复制

- `run_blocking_stress_owner_process`（第 640-675 行）是 `recovery_support.run_blocking_owner_process` 的薄封装
- `run_open_probe_for_stress`（第 678-691 行）是 `recovery_support.run_open_probe_process` 的薄封装
- `start_and_crash_owner_for_stress`（第 694-750 行）组合复用 `wait_for_accepted_marker`、`terminate_process`、`wait_for_runtime_lane_claim_ttl_to_expire`、`force_owner_pid_missing_and_heartbeat_stale`、`recovery_attempt_count_for_run`
- `count_event_type`（第 753-769 行）委托 `recovery_event_type_count`
- `attempt_count_for_run`（第 772-788 行）委托 `recovery_attempt_count_for_run`

### 无 production code 越界

- `stress_support.py` 只新增测试 helper，未修改 `dayu/host/`、`dayu/engine/`、`dayu/runtime/` 等 production 代码
- `test_host_production_stress.py` 只通过 `open_host`、`get_run`、`watch_session_events` 等 public API 操作 Host
- Durable SQL 只用于 diagnostic 读取和 fault injection（与现有 `recovery_support` 一致）

### Slice 3-5 未实现

- diff 中只包含 Slice 2 的 `test_repeated_startup_recovery_crash_stress` 和配套 helper
- 未出现 `test_sustained_watch_slow_consumer_reconnect_stress`（Slice 3）、`test_scheduler_liveness_long_run_mixed_flow_stress`（Slice 4）、`test_mixed_host_stress_deterministic_fault_injection`（Slice 5）

### Docstring / 强类型 / 禁止 Any-object-裸 dict

- 所有新增函数和类均有完整中文 docstring（参数、返回值、异常）
- 函数签名全部有类型注解，无 `Any`、`object`、裸 `dict`/`list`
- `StressFailureBoundary` 使用 `Literal` 封闭类型（第 55-67 行）
- `HostStressSummary` 和 `StressTerminalObservation` 使用 frozen dataclass（第 98-149 行）
- JSON 序列化使用 `Mapping[str, StressSummaryJsonValue]` 强类型（第 514 行）

### 验证结果可信度

- Slice 2 stress test: `1 passed, 1 deselected`（3.28s，远低于 60s timeout）
- Recovery multiprocess tests: `3 passed`（无回归）
- Pyright: `0 errors, 0 warnings, 0 informations`

## Open Questions / Residual Risk

1. **3 轮 crash 足够性**: 计划允许 3-6 轮，实现取最小值 3。在 CI 环境中稳定性优先，合理选择。若未来需要更高覆盖率，可增加到 6 轮，但需同步调整 timeout。

2. **Terminal dedupe 语义在 Slice 5 中的适用性**: `terminal_duplicate_count` 的 OR 语义在混合 fault injection 场景下是否仍然符合预期，需在 Slice 5 实现时确认。

3. **Live owner probe 时序窗口**: probe 在 owner accepted 后立即运行，如果 Host startup recovery scanner 的执行窗口极短，理论上存在 probe 未在 stale window 内运行的风险。当前实现通过 `_PROCESS_START_TIMEOUT_SECONDS` 和 `count_event_type` 的 before/after 差值验证，实际运行稳定（3.28s），风险极低。

## Controller Decision Status

N/A（code review artifact，不涉及 controller 裁决）

## Artifact Path

`docs/reviews/wu-stress-01-code-review-slice2-mimo-20260601.md`
