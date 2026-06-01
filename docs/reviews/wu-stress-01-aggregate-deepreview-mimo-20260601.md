# Code Review

## Scope

- Mode: current changes (aggregate deepreview)
- Branch: `test/host-stress-suite`
- Base: `main`
- Output file: `docs/reviews/wu-stress-01-aggregate-deepreview-mimo-20260601.md`
- Included scope: WU-STRESS-01 全部 5 个 slice 的最终实现代码与文档，包括 `pyproject.toml`、`tests/README.md`、`tests/host/stress_support.py`、`tests/host/test_host_production_stress.py`、`docs/host/wu-stress-01-host-production-stress-suite-plan.md`，以及 `docs/host/host-core-followup-implementation-control.md` 的状态更新。
- Excluded scope: 所有 `docs/reviews/wu-stress-01-*` artifact 文件（已由 slice review 流程产出，不重复审查）；生产代码 `dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/service/**`、`dayu/ui/**`、`dayu/fins/**`、`dayu/config/**`（按 plan 约束 forbidden files，确认未被修改）。
- Parallel review coverage: 无；单 reviewer 完成全量走读。

## Findings

未发现实质性问题。

以下是对 plan 合约、实现正确性、类型/docstring 约束、marker/默认排除、docs/README 同步、分层/架构边界和测试覆盖的逐项审查证据：

### 1. Plan 合约一致性

- **Allowed files 合规**: `git diff main...HEAD --name-only` 输出的非 artifact 文件仅为 `pyproject.toml`、`tests/README.md`、`tests/host/stress_support.py`、`tests/host/test_host_production_stress.py`、`docs/host/host-core-followup-implementation-control.md`，均为 plan 允许修改的文件。
- **Forbidden files 未触碰**: `dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/service/**`、`dayu/ui/**`、`dayu/fins/**`、`dayu/config/**`、`docs/host/design.md` 无任何改动。
- **5 个 slice 全部实现**: Slice 1 (marker/sentinel)、Slice 2 (repeated crash/recovery)、Slice 3 (sustained watch/reconnect)、Slice 4 (scheduler/liveness long-run)、Slice 5 (mixed fault injection) 均有对应测试函数和诊断 dataclass。
- **Stop conditions 未触发**: 无 Host public contract、durable schema、EventLog 语义、recovery 状态机或 scheduler 生产行为修改。

### 2. pyproject.toml marker 与默认排除

- `addopts = "-m 'not stress'"` 正确配置默认排除。
- `markers = ["stress: production hardening stress tests; excluded from default pytest runs"]` 正确注册自定义 marker。
- 验证证据 (controller): `markers pass`、`default package+stress file 10 passed 5 deselected`、`explicit stress 5 passed`、`collect-only default exit 5 no tests collected 5 deselected`、`override collect-only 5 collected`。

### 3. 测试文件 marker 与 timeout

- `test_host_production_stress.py:73` 模块级 `pytestmark = pytest.mark.stress`，所有测试自动获得 stress marker。
- 每个测试函数都有 `@pytest.mark.timeout(...)` 防护：sentinel (5s)、Slice 2 (60s)、Slice 3 (90s)、Slice 4 (90s)、Slice 5 (120s)。
- 所有 async 测试都有 `@pytest.mark.asyncio`。

### 4. 类型安全与 docstring 约束

- `stress_support.py` 全部 1410 行通过 pyright 0 errors 验证。
- 所有模块级函数、class、dataclass 均有完整中文 docstring，包含 `:param`、`:returns`、`:raises`。
- 无 `Any`、`object`、无类型参数或无类型返回值。
- `StressFailureBoundary` 使用 `TypeAlias = Literal[...]` 封闭诊断集合，非裸 `str | None`。
- `HostStressSummary`、`StressTerminalObservation`、`StressHostInstanceDiagnostic`、`HostStressScenario` 均为 `frozen=True, slots=True` dataclass。
- `StressWorkerBehavior` 使用 `StrEnum`，封闭行为集合。
- `StressSummaryJsonValue: TypeAlias = str | int | bool | tuple[int, ...] | None`，JSON payload 值类型封闭。
- 所有 helper docstring 声明"不进入生产代码，不作为 Host durable truth"边界。

### 5. SQL 注入与参数化查询

- `read_session_terminal_sequences`、`terminal_events_for_runs`、`terminal_event_count_for_runs` 使用 `?` 占位符和 tuple 参数化，无 SQL 注入风险。
- `_TERMINAL_EVENT_TYPES` 与 `_ALL_RUN_TERMINAL_EVENT_TYPES` 使用模块级 tuple 常量，`",".join("?" for ...)` 动态生成占位符，参数数量一致。

### 6. 并发安全

- `asyncio.Queue[HostEvent]` 用于 watcher 事件传递，线程安全。
- `asyncio.Event` 用于 worker accepted 信号和 blocking final 释放，无竞态。
- `asyncio.wait_for` 用于所有等待操作，有超时保护。
- finally 块正确清理 task 和 watcher iterator，使用 `suppress(asyncio.CancelledError)` 和 `suppress(Exception)` 避免清理异常。
- `close_host_event_iterator` 使用 `cast(AsyncGenerator, iterator).aclose()` 正确关闭 async generator。

### 7. 异常链与清理

- `start_and_crash_owner_for_stress:1186-1192` 使用 `except BaseException` + `raise cleanup_error from original_error` 正确保留异常链。
- `_run_live_owner_probe:2543-2549` 同样保留异常链。
- Slice 5 `test_mixed_host_stress_deterministic_fault_injection:1353-1357` 使用 `raise AssertionError(summary_json) from error` 正确传播 TimeoutError 原因。

### 8. 结构化诊断覆盖

- `HostStressSummary` 包含 plan 要求的全部 12 个字段。
- Slice 2-5 各有独立的 typed diagnostics dataclass (`Slice2StressDiagnostics`、`Slice3WatchDiagnostics`、`Slice4SchedulerLivenessDiagnostics`、`Slice5MixedHostDiagnostics`)，每个都有 `failure_boundary` 属性返回封闭诊断。
- `failure_boundary` 返回值严格限于 `StressFailureBoundary` 封闭集合成员或 `None`。
- `summary_to_json` 输出排序 JSON，用于 assertion message 和 `record_property`。
- `_SUMMARY_JSON_FIELDS` tuple 与 `HostStressSummary` 字段一一对应。

### 9. 生产代码边界

- `stress_support.py` import 路径全部为 `dayu.host` public API、`dayu.engine.contracts`、`dayu.runtime.lane` 和 `tests.host.*` helper。
- 无 import `dayu.host.dispatch`、`dayu.host.recovery`、`dayu.host.durable` 的内部实现（仅 `dayu.host.durable.codec.parse_utc_timestamp` 和 `dayu.host.durable.liveness.HostInstanceStatus`，均为 stable diagnostic 类型）。
- deterministic worker 通过 `LocalEngineWorkerFactory` / `LocalWorkerHandle` 边界产出 `EngineEvent`，不接触生产状态机。
- durable SQL helper 仅用于 fault injection（stale heartbeat）和 diagnostic（event count、terminal sequence），不绕过状态机制造成功路径。
- `verify_lane_released` 通过独立 `LaneController.open` + `acquire` + `release` 验证 capacity，不读取 scheduler internals。

### 10. 测试覆盖与确定性

- 5 个 stress 测试覆盖 plan 定义的全部场景。
- 所有测试使用 deterministic worker factory，无随机 fuzz。
- 所有等待操作有 timeout + summary JSON on failure。
- 循环规模固定小数值 (sessions 3-5, runs 12-25, crash cycles 1-3)。
- 验证证据 (controller): `recovery/watch/dispatch/liveness 75 passed`、`tests/host 1044 passed 1 skipped 5 deselected`。

### 11. docs/README 同步

- `tests/README.md` 正确更新：
  - 新增默认排除说明和显式 stress 运行命令。
  - 新增 production stress 测试描述段落，说明 marker、summary JSON 字段约定。
  - 命令列表中新增 stress 命令行。
- `docs/host/host-core-followup-implementation-control.md` 记录 WU-STRESS-01 状态更新（18 行变更）。
- 根 README 和 Host README 未更新（plan 确认无需更新）。

### 12. 生产代码/公共契约/schema/分层违规

- 未发现。
- 无 Host public contract 变更。
- 无 durable schema 变更。
- 无 EventLog 语义变更。
- 无 recovery 状态机变更。
- 无 scheduler 生产行为变更。
- 无反向依赖或跨层泄漏。

## Open Questions

无。

## Residual Risk

- **Watch lag 诊断精度**: `read_latest_event_sequence` 和 `read_session_terminal_sequences` 使用 fresh short read transaction 获取 point-in-time diagnostic，lag 计算依赖两次读取之间 EventLog 不变的假设。在 stress 高并发写入期间，两次读取之间的 snapshot 可能不一致，导致 lag 估算偏大或偏小。Docstring 已明确声明此限制，且 lag 只用于测试诊断不用于生产判断，风险可控。
- **multiprocessing 子进程清理**: `start_and_crash_owner_for_stress` 和 `_run_live_owner_probe` 使用 `terminate_process` 强制终止子进程。如果子进程在 SQLite 写入中途被终止，可能留下 journal 文件。`tmp_path` 是 pytest 临时目录，测试结束后自动清理，且 recovery scanner 会处理 orphan 状态，风险可控。
- **stress 测试耗时**: Slice 5 timeout 设为 120s，全部 5 个 stress 测试理论最大耗时约 375s。Controller 报告 `tests/host 1044 passed 1 skipped 5 deselected` 中 stress 被正确排除，显式运行时在合理时间范围内完成。但 CI 环境可能需要更大的 timeout budget。
- **`_drain_observed_event_count` 队列清空**: 该 helper 使用 `get_nowait()` 循环清空 `asyncio.Queue`。如果在清空过程中 producer 同时 put 新事件，计数可能不精确。测试中 producer (watcher) 和 consumer (lag 记录) 在同一 event loop 中运行，`get_nowait()` 是原子的，实际不会丢失事件。
- **`RUN_LOST` terminal 去重证明边界**: `terminal_events_for_runs` 不返回 `RUN_LOST` observation（因为 `HostEventKind` / `HostTerminalStatus` 不建模 lost），`terminal_event_count_for_runs` 显式纳入 `RUN_LOST`。Slice 4/5 使用两层证明：可表达 terminal observation 无重复 + 包含 `RUN_LOST` 的 terminal EventLog 总数等于 public terminal snapshot 数。这是当前 public contract 下最完整的去重证明，无遗漏。
