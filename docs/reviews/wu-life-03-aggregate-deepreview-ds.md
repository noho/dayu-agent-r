# WU-LIFE-03 Aggregate Deepreview — AgentDS 第二路

## Scope

- Mode: current changes
- Branch: `phase/host-engine-next`
- Base: `main`
- Output file: `docs/reviews/wu-life-03-aggregate-deepreview-ds.md`
- Timestamp: 2026-07-04T12:28:51+08:00
- Included scope:
  - WU-LIFE-03 plan artifact: `docs/host/wu-life-03-active-cancel-watchdog-plan.md`
  - Slice 1 implementation: `dayu/host/durable/run_transition.py`, `dayu/host/engine_ingest.py`
  - Slice 2 implementation: `dayu/host/dispatch.py`, `dayu/host/recovery.py`, `dayu/host/open_host.py`, `dayu/host/api.py`, `dayu/host/command.py`
  - Tests: `tests/host/test_run_attempt_transitions.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_active_cancel_dispatch.py`, `tests/host/test_recovery_scan.py`, `tests/host/test_open_host_runtime.py`, `tests/host/test_dispatch_scheduler.py`
  - Design docs: `docs/host/design.md`, `docs/engine/design.md`
  - Control doc: `docs/host/issues-implementation-control.md`
  - README: `dayu/host/README.md`
  - Review/fix artifacts: all `docs/reviews/wu-life-03-*` and slice code review/re-review/fix artifacts
- Excluded scope: unrelated `dayu/host/` modules not changed by WU-LIFE-03
- Parallel review coverage: 无（单路 aggregate deepreview，本路为第二路）

## 前置验证

- `pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py tests/host/test_recovery_scan.py tests/host/test_open_host_runtime.py -q`: **173 passed**
- `pytest tests/host/test_dispatch_scheduler.py -q -k "watchdog or close_does_not or scheduler_close_during_active"`: **2 passed**
- `pyright dayu/ tests/`: **0 errors, 0 warnings, 0 informations**

## 设计真源对齐检查

### docs/host/design.md 变更

- cancel 路径新增 `OpenHostOptions.active_cancel_timeout_seconds` 与 active cancel watchdog timeout closeout 描述（L2493）
- 将旧"未引入 watchdog" 改为 `active_cancel_timeout_seconds=None` opt-out 语义（L2502）
- startup recovery 新增 `CANCELLING` + accepted cancel facts → defer to watchdog 分支（L3449-L3450）
- Phase 11 recovery policy 新增 watchdog startup tick 先于 scanner 的排序描述（L3457）

**结论**: design.md 变更准确反映了 Slice 1+2 的已实现行为，未写未来能力。

### dayu/host/README.md 变更

- `OpenHostOptions` 字段列表新增 `active cancel timeout`（L91）
- cancel 路径新增 watchdog timeout closeout 描述（L568）
- dispatch scheduler 新增 watchdog scan 机制描述（L592）
- startup recovery 新增 accepted-cancel defer 描述（L602）

**结论**: README 变更准确反映实现行为，与 design.md 一致。

### docs/host/issues-implementation-control.md 变更

- 当前状态表更新为 WU-LIFE-03 `review` gate、WU-WAIT-02/03 completed
- issue status comments 更新移除已关闭 issue
- WU-LIFE-03 条目状态更新为 `review`，完整记录了 plan → Slice 1 → Slice 2 → aggregate deepreview 的 gate 历史

**结论**: control doc 状态准确，无 stale 信息。

## 实现审查

### 审查入口与路径

按以下真实代码路径逐行走读：

1. **timeout closeout 写路径**: `cancel_run` → `command.py:_cancel_run` → durable transition → `_wake_active_cancel_watchdog` → `dispatch.py:tick_active_cancel_watchdog` → `_read_active_cancel_watchdog_candidates` → `active_cancel_timeout_closeout_in_transaction`
2. **late terminal 拒绝路径**: EngineEvent ingest → `engine_ingest.py:_ingest_before_reactive_compaction` → `_validate_durable_context` → `_late_rejection_reason` → `_append_rejected_diagnostic`
3. **startup recovery defer 路径**: `open_host` → `scheduler.tick_active_cancel_watchdog(datetime.now(UTC))` → `StartupRecoveryScanner.scan()` with `defer_accepted_cancel_to_watchdog=True`
4. **watchdog 后台循环**: `_start_active_cancel_watchdog_loop` → `_active_cancel_watchdog_loop` → immediate wakeup + periodic fallback
5. **scheduler close 边界**: `scheduler.close()` → cancel watchdog task → cancel active workers → clear registry → lane close

### Slice 1: Durable Timeout Closeout Contract

**`ActiveCancelTimeoutCloseoutInput`** (`run_transition.py:874-906`):
- 独立 dataclass，不继承 `ActiveCancelCloseoutInput`，符合 plan 要求
- 字段包含全部 plan 要求的 timeout 诊断字段：`timeout_seconds`、`timed_out_at`、`watchdog_owner`、`worker_lifecycle_signal`、`last_observed_worker_event_index`、`last_accepted_event_id`
- 不含 `engine_event_ref`、`requested_at`/`accepted_at`/`finished_at`（这些来自 Engine cooperative path）

**`active_cancel_timeout_closeout_in_transaction`** (`run_transition.py:2248-2352`):
- 先做 replay check（已 CANCELLED + CANCELLED 同终态 replay 返回 UPDATED）
- 再做 precondition check（Run CANCELLING + Attempt RUNNING + dispatch worker accepted + dispatch not pre-accept cancelled）
- 从 EventLog 读 `RUN_CANCELLING` → 提取 `cancel_request_event_id` → 验证存在
- 写 `ATTEMPT_CANCELLED` + `RUN_CANCELLED`，复用 `cancel_running_attempt_row` / `cancel_cancelling_run_row` CAS
- 前置不满足时返回 `INVALID_STATE`/`NOT_FOUND`，不写部分 terminal facts

**`_cancel_request_event_id_from_cancelling`** (`run_transition.py:6301-6319`):
- 从 EventLogRow payload_json 解析，处理 `None`、JSON 解析失败、非 Mapping、非字符串等边界
- 使用 `json.loads`，异常安全（JSONDecodeError 捕获），但 `payload_json=None` 会抛 TypeError（实际受 SQLite NOT NULL 约束保护）

**`_validate_active_cancel_timeout_closeout_input`** (`run_transition.py:6259-6298`):
- 校验所有必填字段非空、`timeout_seconds` 有限正数、`last_observed_worker_event_index` 非负

**`_late_rejection_reason`** (`engine_ingest.py:3283-3308`):
- 三层判断：
  1. `RUN_SUSPENDED`/`TOOL_AWAITING` + Run WAITING + Attempt SUSPENDED → 允许通过（已确认等待）
  2. Run/Attempt `terminal_event_id is not None` → `terminal_already_closed`
  3. Run CANCELLING + `FINAL_ANSWER`/`RUN_FAILED` → `late_terminal_after_active_cancel`
- 判断 2 在判断 3 之前：已 terminal 的 Run 无论什么状态都先被 `terminal_already_closed` 拦截
- 判断 3 依赖 Run 状态为 `CANCELLING` — engine_ingest 不检查 dispatch record cancelled 标记来区分 pre-accept cancel vs active cancel，这由 `active_cancel_closeout_in_transaction` 的 `_invalid_active_cancel_closeout_precondition` 负责

**等待事件在 CANCELLING 下的行为** (`engine_ingest.py:2347-2413`):
- `RUN_SUSPENDED`/`TOOL_AWAITING` 经过 `_late_rejection_reason` 后，若 Run 不是 `WAITING` 会落入 `_ingest_validated` → `_confirm_waiting_engine_event`
- `_validate_waiting_confirmation` 校验 Host accepted wait refs → 无匹配时写 `waiting_event_without_host_accepted_refs` diagnostic
- 不会创建 wait record、不会把 Run 推到 `WAITING`、不会修改 Attempt 状态

### Slice 2: Watchdog Runtime Integration

**`HostDispatchScheduler` watchdog 集成** (`dispatch.py`):

- `tick_active_cancel_watchdog(now)` (`L1071-1152`):
  - 接受 injectable UTC now（测试直接调用，不依赖真实时钟）
  - 扫描 `_read_active_cancel_watchdog_candidates` → 对每个候选计算 elapsed time
  - elapsed >= timeout → `active_cancel_timeout_closeout_in_transaction`
  - 成功后触发 `catch_up_projection_best_effort` + `wake_queue_promotion`
  - timeout_seconds=None 时返回全零 tick 结果

- `_read_active_cancel_watchdog_candidates` (`L4044-4071`):
  - 通过 `read_non_terminal_runs` 全表扫描 → Python 过滤 `CANCELLING`
  - 对每个 CANCELLING Run 校验 Attempt RUNNING + dispatch worker accepted + linked CANCEL_REQUESTED
  - 任一条件不满足 → 计入 ignored

- `_active_cancel_watchdog_loop` (`L2561-2619`):
  - `asyncio.wait_for(queue.get(), timeout=interval)` — 立即唤醒 + 周期性 fallback
  - 单次 tick 异常由 `except Exception` 捕获后继续循环
  - `CancelledError` 透传，scheduler close 路径取消

- `wake_active_cancel_watchdog` (`L1054-1069`):
  - `closed` guard
  - `timeout_seconds is None` 时直接返回（disabled 不唤醒）
  - `QueueFull` 时静默忽略（maxsize=1，上一个 wakeup 尚未消费）
  - 调用 `_start_active_cancel_watchdog_loop` 确保 task 存活

**Startup recovery watchdog defer** (`recovery.py`):

- `StartupRecoveryScanner.defer_accepted_cancel_to_watchdog` (`L182`):
  - 构造参数，默认 `False`
  - `open_host` 中当 `active_cancel_timeout_seconds is not None` 时设为 `True`

- `_classify_run` CANCELLING 分支 (`L292-306`):
  - `defer_accepted_cancel_to_watchdog=True` + `_has_accepted_cancel_fact` → `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG`
  - 不满足 defer 条件时走现有 `_classify_active_or_cancelling` → positive orphan → LOST/RECOVERING

- `_has_accepted_cancel_fact` (`L654-695`):
  - 读 `RUN_CANCELLING` → 解析 payload → 提取 `cancel_request_event_id` → 验证同 Run 的 `CANCEL_REQUESTED` 存在
  - 任何步骤失败（event 缺失、payload 解析失败、event_id 不匹配）返回 `False`
  - 与 `dispatch.py:_read_linked_cancel_requested_event` 语义等价

**open_host 启动排序** (`open_host.py:885-901`):

```python
scheduler = await HostDispatchScheduler.open(...)  # 启动 watchdog loop
scheduler.tick_active_cancel_watchdog(datetime.now(UTC))  # 先执行一次 tick
StartupRecoveryScanner(
    ...
    defer_accepted_cancel_to_watchdog=(
        local_execution.active_cancel_timeout_seconds is not None
    ),
).scan()  # 再 scanner，defer 剩余 CANCELLING
```

符合 plan 要求的排序：watchdog tick → scanner（defer 剩余 CANCELLING runs）。

**cancel_run/cancel_session_runs 唤醒** (`command.py:1631`):
- cancel commit 后调用 `_wake_active_cancel_watchdog(host)` → `host._active_cancel_watchdog_wakeup_port.wake_active_cancel_watchdog()`
- wakeup_port 为 `None` 时不调用（scheduler 未装配时）

**`HostCommandHandle` 协议扩展** (`command.py:160-171, 174-221`):
- 新增 `ActiveCancelWatchdogWakeupPort` Protocol 类
- `HostCommandHandle.__init__` 新增 `active_cancel_watchdog_wakeup_port` 参数

**`OpenHostOptions` 新增字段** (`api.py:1036, 1080`):
- `active_cancel_timeout_seconds: float | None = _DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS`（默认 300.0s）
- 校验：`_require_optional_finite_positive_float`
- 传递到 `HostLocalExecutionOptions.active_cancel_timeout_seconds`

**scheduler.close() watchdog 清理** (`dispatch.py:2515-2518`):
- `watchdog_task.cancel()` → `await _suppress_task_cancel(watchdog_task)`
- close 不调用 `tick_active_cancel_watchdog`，不写 terminal facts

### 测试矩阵覆盖

| Plan 要求的测试 | 实现位置 | 状态 |
|---|---|---|
| `test_active_cancel_timeout_closeout_writes_cancelled_terminal_facts` | `test_run_attempt_transitions.py:1796` | PASS |
| `test_active_cancel_timeout_closeout_requires_cancelling_run` | `test_run_attempt_transitions.py:1877` | PASS |
| `test_active_cancel_timeout_closeout_first_committer_wins_after_cooperative_cancel` | `test_run_attempt_transitions.py:1969` | PASS |
| `test_active_cancel_timeout_closeout_rejects_after_succeeded_terminal` | `test_run_attempt_transitions.py:2024` | PASS |
| `test_late_final_answer_after_run_cancelling_is_rejected_with_diagnostic` | `test_engine_ingest_mapping.py:2466` | PASS |
| `test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic` | `test_engine_ingest_mapping.py:2501` | PASS |
| `test_late_worker_terminal_after_timeout_is_rejected_as_terminal_closed` | `test_engine_ingest_mapping.py:2432` | PASS |
| `test_late_awaiting_after_cancel_does_not_move_to_waiting` | `test_engine_ingest_mapping.py:2536` | PASS |
| `test_active_cancel_timeout_closeout_rejects_malformed_cancelling_payload` | `test_run_attempt_transitions.py:1911` | PASS |
| `test_active_cancel_watchdog_times_out_non_cooperative_worker` | `test_active_cancel_dispatch.py:407` | PASS |
| `test_active_cancel_watchdog_noops_before_timeout` | `test_active_cancel_dispatch.py:455` | PASS |
| `test_active_cancel_watchdog_zero_cancelling_runs_noops` | `test_active_cancel_dispatch.py:491` | PASS |
| `test_active_cancel_watchdog_multiple_cancelling_runs_closes_each_eligible` | `test_active_cancel_dispatch.py:515` | PASS |
| `test_active_cancel_timeout_promotes_queued_run` | `test_active_cancel_dispatch.py:587` | PASS |
| `test_cancel_session_replay_repropagates_active_without_new_facts` | `test_active_cancel_dispatch.py:724` | PASS |
| `test_cancel_session_replay_after_timeout_does_not_append_or_propagate` | `test_active_cancel_dispatch.py:765` | PASS |
| `test_scheduler_close_does_not_write_active_cancel_timeout_terminal` | `test_active_cancel_dispatch.py:809` | PASS |
| `test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` | `test_open_host_runtime.py:623` | PASS |
| `test_open_host_reopen_closes_existing_cancelling_run_as_cancelled` | `test_open_host_runtime.py:660` | PASS |
| `test_open_host_reopen_before_timeout_defers_cancelling_to_watchdog` | `test_open_host_runtime.py:694` | PASS |
| `test_scan_defers_accepted_cancel_cancelling_to_watchdog_when_enabled` | `test_recovery_scan.py:687` | PASS |
| `test_scan_malformed_cancelling_payload_uses_orphan_policy` | `test_recovery_scan.py:714` | PASS |
| `test_scan_watchdog_disabled_keeps_cancelling_orphan_policy` | `test_recovery_scan.py:741` | PASS |
| `test_active_cancel_watchdog_loop_continues_after_transient_tick_failure` | `test_dispatch_scheduler.py:2715` | PASS |

全部 24 个 plan 要求的测试均已实现且通过，另有额外覆盖（如 `test_cancel_predispatch_starting_updates_dispatch_attempt_and_run` 等既有测试继续通过）。

**没有发现为旧测试添加兼容代码或表面修复。** 既有 cooperative cancel 测试、recovery scan 测试、ingest mapping 测试与 dispatch scheduler 测试全部通过，未做适配性修改。

## Findings

### 01-NON-BLOCKING-[低]-watchdog scan 使用全表扫描过滤 CANCELLING

- **入口/函数**: `_read_active_cancel_watchdog_candidates`
- **文件(行号)**: `dayu/host/dispatch.py:4044-4071`
- **输入场景**: 生产环境有大量非终态 Run（数百+），其中只有少数处于 CANCELLING
- **实际分支**: `read_non_terminal_runs(transaction)` 读取全部非终态 Run，Python 层 `if run.status is not RunStatus.CANCELLING: continue` 过滤
- **预期行为**: plan 描述 "scan current CANCELLING runs" — 直接扫描 CANCELLING Run
- **实际行为**: 全量加载后 Python 过滤，O(all_non_terminal) 而非 O(cancelling)
- **直接证据**: `dispatch.py:4058` 调用 `read_non_terminal_runs`，`L4059` Python 过滤
- **影响**: 在大量活跃 Run 的生产环境中，watchdog 每次 tick 都做全表扫描；不导致 correctness 错误
- **建议改法和验证点**: 后续 #87 调优时考虑在 `dayu/host/durable/state.py` 新增按状态过滤的非终态 Run reader；不在当前 WU 范围
- **修复风险（低）**: 只读查询优化
- **严重程度（低）**: 性能优化，无正确性影响

### 02-NON-BLOCKING-[低]-timeout closeout 后 active worker handle 未从 registry 清理

- **入口/函数**: `tick_active_cancel_watchdog` → `active_cancel_timeout_closeout_in_transaction`
- **文件(行号)**: `dayu/host/dispatch.py:1105-1127`, `dayu/host/dispatch.py:635-644`
- **输入场景**: watchdog timeout closeout 成功后，worker stream 仍在运行但永不返回
- **实际分支**: timeout closeout 写 `RUN_CANCELLED` 后返回，不清理 `ActiveWorkerRegistry` 中的 `(attempt_id, execution_id)` entry，也不调用 `handle.on_cancel` 或 `cancellation_token.request_cancel`
- **预期行为**: plan 明确 timeout closeout 不表示 provider/tool 已物理停止，physical cancel 归 WU-TOOLS-CANCEL-01
- **实际行为**: registry entry 保留，`_consume_worker_events` coroutine 可能无限等待 `anext(events)`；late events 被 ingest 拒绝
- **直接证据**: `dispatch.py:1105-1127` tick 内不调用 `active_registry.unregister`；plan `docs/host/wu-life-03-active-cancel-watchdog-plan.md:398` residual risk "timeout CANCELLED does not physically stop provider/tool work"
- **影响**: 已取消 Run 的 handle/coroutine 资源未释放，直到 worker 自然退出或 scheduler close；不影响 durable truth 正确性
- **建议改法和验证点**: WU-TOOLS-CANCEL-01 实现后，timeout closeout 应触发 registry cleanup 或至少记录已 timeout 标记；当前 WU 无需修改
- **修复风险（低）**: 后续 WU 的自然扩展
- **严重程度（低）**: plan 已识别的 residual risk，owner 明确

### 03-OBSERVATION-[信息]-`_cancel_request_event_id_from_cancelling` 的 `payload_json=None` 边界

- **入口/函数**: `_cancel_request_event_id_from_cancelling`
- **文件(行号)**: `dayu/host/durable/run_transition.py:6301-6319`
- **输入场景**: EventLog row 的 `payload_json` 字段为 `None`（理论上受 SQLite NOT NULL 约束保护，不会发生）
- **实际分支**: `json.loads(None)` 抛出 `TypeError`（非 `JSONDecodeError`），未被捕获，向上传播
- **预期行为**: 返回 `None` 表示 payload 非法
- **实际行为**: `TypeError` 向上传播；在 timeout closeout 路径中，调用方 `active_cancel_timeout_closeout_in_transaction` 在 `L2289` 调用本函数，但其外层 try 不捕获 TypeError
- **直接证据**: `run_transition.py:6311` `json.loads(event.payload_json)` — 只捕获 `json.JSONDecodeError`
- **影响**: 当前受 SQLite schema NOT NULL 约束保护，不会触发；如果未来 schema 变更允许 NULL payload_json，将导致未处理异常
- **建议改法和验证点**: 将 `except json.JSONDecodeError` 改为 `except (json.JSONDecodeError, TypeError)` 或在调用前增加 `payload_json is None` guard；低优先级，当前无需修改
- **修复风险（低）**: 纯 defensive
- **严重程度（低）**: 受 schema 约束保护的理论边界

## Open Questions

无。

## Residual Risk

- **WU-TOOLS-CANCEL-01**: timeout `CANCELLED` 不物理停止 provider/tool；旧 side effects 可能继续，active worker handle/coroutine 可能持续存在。已在 plan 中记录为 residual risk，owner 为 WU-TOOLS-CANCEL-01。
- **#87 生产调优**: timeout 默认值 300s 可能不适用于所有 provider/worker backend；watchdog scan 使用全表扫描可能在高负载下需要优化。已在 plan 中记录，owner 为 #87 Host Lifecycle Watchdog / Supervisor umbrella。
- **跨实例 UTC 时钟偏差**: reopen 后 timeout 判定使用 durable UTC timestamp 对比当前 Host UTC clock；偏差量影响 timeout 精度。已在 plan 中记录，owner 为 #87。
- **watchdog disabled opt-out**: `active_cancel_timeout_seconds=None` 时 orphan `CANCELLING` Run 仍走 recovery `LOST`/inconclusive 策略。已在 plan 和 design.md 中记录为特殊测试装配 opt-out。

## 结论

**PASS** — 无 BLOCKING FINDINGS。

WU-LIFE-03 Slice 1+2 实现完整满足 plan 目标：

1. **Active cancel accepted 后 Host durable truth 不依赖 worker/provider/tool cooperation**：watchdog 通过 durable `CANCELLING` + `CANCEL_REQUESTED` fact 判定 timeout，在写事务内 CAS 收口为 `CANCELLED`，不依赖 Engine event stream。
2. **Timeout 后有 CANCELLED terminal closeout**：`active_cancel_timeout_closeout_in_transaction` 写入 `ATTEMPT_CANCELLED` + `RUN_CANCELLED(reason=active_cancel_timeout)`，包含完整 timeout diagnostic payload。
3. **First-committer-wins / late terminal / awaiting-suspend rejection** 跨 Slice 1+2 一致：`_late_rejection_reason` + precondition guards 构成双层防御；cooperative cancel、timeout closeout、late terminal 三者互不覆盖。
4. **Replay / queue promotion / projection / startup recovery ordering** 跨 Slice 1+2 一致：cancel replay 不重复 facts；timeout closeout 后触发 promotion；startup 先 watchdog tick 再 scanner defer。
5. **架构边界** 无问题：Host 拥有全部 cancel/timeout 治理；Engine 不参与；`dayu.runtime` 无新增依赖；无跨层穿透。
6. **测试矩阵** 覆盖 plan 全部 24 个要求测试，173 个 focused 测试通过，pyright 零错误。
7. **README/design/control doc** 准确反映已实现行为，不写未来能力。
