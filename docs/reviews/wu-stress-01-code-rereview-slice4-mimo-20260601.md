# Code Review

## Scope

- Mode: current changes (re-review after focused fix)
- Branch: test/host-stress-suite
- Base: HEAD (uncommitted Slice 4 diff)
- Output file: docs/reviews/wu-stress-01-code-rereview-slice4-mimo-20260601.md
- Included scope:
  - `tests/host/stress_support.py` (uncommitted diff)
  - `tests/host/test_host_production_stress.py` (uncommitted diff)
- Excluded scope:
  - No production code modified (`dayu/host/**`, `dayu/engine/**`, etc.)
  - No Slice 5 behavior
- Parallel review coverage: 无

## Gate

- **Gate**: Slice 4 re-review after focused fix
- **Work Unit**: WU-STRESS-01 Host Production Stress Suite
- **Slice**: Slice 4 scheduler / liveness long-run stress
- **Controller adjudication source**: `docs/reviews/wu-stress-01-code-controller-adjudication-slice4-20260601.md`
- **Fix artifact source**: `docs/reviews/wu-stress-01-fix-slice4-codex-20260601.md`

## Accepted Findings Validation

### DS-01: `RUN_LOST` terminal dedupe proof

**Status**: closed

`terminal_event_count_for_runs()` (`stress_support.py:1274-1321`) docstring显式说明了两层证明：`terminal_events_for_runs()` 只覆盖 succeeded/failed/cancelled，本 helper 在 count 层纳入 `RUN_LOST`。`Slice4SchedulerLivenessDiagnostics.terminal_dedupe_ok` (`test_host_production_stress.py:658-676`) docstring 明确解释了两层去重证明边界。`_ALL_RUN_TERMINAL_EVENT_TYPES` (`stress_support.py:110`) 常量将 `_EVENT_TYPE_RUN_LOST` 纳入全量 terminal 计数。

### MiMo-01: unused `InspectableStressWorkerFactory.wait_accepted_run`

**Status**: closed

旧的 `wait_accepted_run` 方法已删除。`InspectableStressWorkerFactory` (`stress_support.py:574-616`) 只暴露 `accepted_handle_count`、`total_cancel_count`、`total_close_count` 三个 property。父类 `DeterministicStressWorkerFactory.wait_accepted()` (`stress_support.py:563-571`) 仍然存在并被 Slice 4 测试通过 `_wait_accepted_count` 使用。

### MiMo-02 / DS-03: duplicated constants

**Status**: closed

`_EVENT_TYPE_RUN_LOST` (`stress_support.py:104`)、`_ALL_RUN_TERMINAL_EVENT_TYPES` (`stress_support.py:110`)、`run_lost_event_count()` (`stress_support.py:1324-1336`) 均在 `stress_support.py` 中定义。测试文件通过 import 使用这些符号，不再复制 durable event type 常量。未引入兼容性 re-export。

### DS-04: `verify_lane_released` hard-codes lane DB path

**Status**: closed

`verify_lane_released()` (`stress_support.py:1008-1053`) 签名为 `verify_lane_released(lane_db_path: pathlib.Path, lane_name: str) -> bool`，显式接收 `lane_db_path` 参数。调用点 (`test_host_production_stress.py:923`) 传入 `options.lane_db_path`。docstring 明确说明如果调用方传入的不是同一个 Host lane DB 则证明无效。

### DS-05: stale threshold rationale

**Status**: closed

`_HOST_INSTANCE_STALE_AFTER_SECONDS` (`stress_support.py:115`) 上方有行内注释："该阈值只用于 stress diagnostic 解释已被测试 helper 主动改旧的 heartbeat；Host recovery stale policy 仍以生产 recovery scanner 为准。" `read_host_instances()` docstring (`stress_support.py:954-1005`) 重复说明 stale 阈值只解释测试证据，不替代 Host recovery policy。

### DS-02: `_is_terminal_status` includes `LOST`

**Status**: closed

`_is_terminal_status()` (`test_host_production_stress.py:1830-1845`) docstring 更新为："判断 RunStatus 是否为 Host public Run 终态"，返回值说明明确列出 "succeeded/failed/cancelled/lost"，并补充注释说明此语义不等同于 HostEventKind / HostTerminalStatus 可表达的 terminal observation 集合。`_is_public_run_terminal()` (`stress_support.py:1373-1386`) 同样包含 `RunStatus.LOST`。

## Findings

未发现实质性问题。

## Scope Verification

- **No production code**: diff 只涉及 `tests/host/stress_support.py` 和 `tests/host/test_host_production_stress.py`，未修改 `dayu/host/**` 或其他生产模块。
- **No Slice 5**: diff 中无 `test_mixed_host_stress_deterministic_fault_injection` 或 `HostStressScenario`。Slice 4 test 函数为 `test_scheduler_liveness_long_run_mixed_flow_stress`。

## Open Questions

无。

## Residual Risk

- Slice 4 stress 仍为 deterministic bounded 测试，非 randomized fuzz 或 long-duration soak。
- liveness stale diagnostic 仅测试层使用；production recovery truth 仍以 startup scanner classification + durable EventLog 为准。
- `RUN_LOST` 无 public `HostTerminalStatus` 对应项，因此证明刻意分为 public terminal observation 层和 EventLog count 层。

## Conclusion

**PASS**。controller adjudication 中 accepted 的 6 项 findings 均已关闭，未引入新问题，未修改生产代码，未引入 Slice 5 行为。
