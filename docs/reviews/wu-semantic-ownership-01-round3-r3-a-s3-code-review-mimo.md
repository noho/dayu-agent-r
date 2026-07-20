# Code Review

## Scope

- Mode: current changes (uncommitted workspace diff)
- Branch: `phaseflow/host-issues-control`
- Base: `c4c6c9ba` (S2 accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s3-code-review-mimo.md`
- Included scope: S3 production files (`_execution_health.py`, `api.py`, `open_host.py`, `dispatch.py`, `admission.py`, `__init__.py`) and S3 test files (`test_scheduler_health.py`, `test_open_host_runtime.py`, `test_dispatch_scheduler.py`, `test_admission_multiprocess.py`, `test_package_exports.py`, `test_public_contracts.py`)
- Excluded scope: S2 actor (`_durable_actor.py`), Service, CLI, S4/S5 scope files, `dayu/config/`, `dayu/engine/`, `dayu/fins/`
- Parallel review coverage: 无（scope 集中在 health gate、admission lease、dispatch retry/replay，单 reviewer 逐路径走读即可覆盖）

## Findings

未发现实质性问题。

## Review Verification Summary

### 1. HostExecutionHealthGate 是否是唯一 owner

**PASS.** `_execution_health.py` 定义 `STARTING → READY → UNAVAILABLE / CLOSING → CLOSED` 单向状态机，`open_host.py` 只创建 gate（line 1268）、调用 `mark_ready()`（line 1349）和 `begin_closing()`/`mark_closed()`；`dispatch.py` 只消费 shared gate 并调用唯一 `report_fatal()`。`_state` 写入只发生在 `_execution_health.py` 内部方法中（`mark_ready`、`report_fatal`、`begin_closing`、`mark_closed`），无外部直接写入。

public handle 的 `_raise_if_closed()` 已从 `self._closed` bool 迁移到 `self._health_gate.raise_if_public_closed()`（`open_host.py:1079`），close truth 统一由 health gate 拥有。admin handle 保留独立 `_closed` bool（`open_host.py:1105`），不参与 execution health gate，符合 S2 admin/opener 分离边界。

### 2. Admission lease 是否覆盖 actor future + commit after-callback + wake

**PASS.** `_invoke_new_work()`（`open_host.py:1062-1079`）执行：
1. `lease = await gate.acquire_admission()` — 获取 lock 并校验 READY
2. `future = actor.submit(operation)` — 同步提交到 executor
3. `lease.release_when_done(future)` — 绑定 lease 到 actor future 的 `done_callback`
4. `await asyncio.shield(future)` — 等待结果，shield 隔离 caller cancellation

`release_when_done()`（`_execution_health.py:69-91`）通过 `future.add_done_callback` 确保 lease 只在 actor future 真实完成（commit/rollback + after-commit wake）后释放。caller cancellation 只取消 shield wrapper，底层 future 继续执行，lease 不提前释放。

`begin_closing()`（`_execution_health.py:181-195`）先写 `_state = CLOSING`，再 `async with self._admission_lock` 等待 active lease 释放。这确保了 close 等待所有已提交 actor operation 完成后才继续 scheduler → projection → actor handle → executor → scheduler store 的关闭序列。

### 3. Critical task fatal / retry exhaustion / normal close 是否被错误合并

**PASS.** 三条路径完全分离：

- **Critical task fatal**：`_supervise_critical_task()`（`dispatch.py`）捕获 `Exception`（非 `CancelledError`），日志后调用 `gate.report_fatal()`，health gate 进入 UNAVAILABLE。`CancelledError` 直接 re-raise，不触发 fatal。
- **Retry exhaustion**：`_drain_loop` 中 `HostTransactionRetryExhaustedError` 分支（`dispatch.py`）改为 `warning` + `asyncio.sleep(poll_interval)` 继续 reconcile，不 self-close、不 terminalize pending queue、不取消 worker、不报告 fatal。
- **Normal close**：scheduler `close()` 取消 background tasks，supervisor 捕获 `CancelledError` re-raise，不触发 fatal。`begin_closing()` + `mark_closed()` 完成 health gate 终态。

非预期异常在 drain/promotion loop 中 `raise` 后由 supervisor 统一处理，不再 `if not self._closed: sleep` 吞掉。

### 4. Idempotent replay wake 是否从 durable snapshot 派生

**PASS.** `_idempotent_replay_pending_dispatch()`（`admission.py`）从 `RunRow`、`AttemptRow`、`DispatchRecordRow` 三个 durable snapshot 派生 wake decision：
- `run.status == RUNNING` + `attempt.status == STARTING` + `dispatch_record.status == PENDING` + identity 三重匹配（run_id/attempt_id/execution_id）+ 无 cancel/worker_accept → 返回 `PendingDispatchRecord`
- ACCEPTED Run 由 `_wake_start_governance_if_needed()` 派生 promotion wake
- terminal、queued、cancelled、lane/worker 已接手 → 返回 `None`（无 wake）

测试 `test_idempotent_replay_derives_matching_wake_from_durable_snapshot`（`test_admission_multiprocess.py:535`）使用真实 SQLite durable store 验证 ACCEPTED→promotion、PENDING→dispatch identity match、cancelled→no wake 三种路径。

### 5. Deterministic race tests 是否只控制时序

**PASS.** 所有 race oracle 使用 `asyncio.Event`、`threading.Event`、actor FIFO/barrier 或 task completion，不依赖 sleep 作为 correctness oracle：

- `test_public_admission_first_commit_and_wake_precede_fatal`（`test_open_host_runtime.py:1053`）：`threading.Event` barrier 占住 actor → `asyncio.Event` 记录 admission submitted → `asyncio.Event` 记录 fatal started → 释放 barrier → 断言 `order[:2] == ["wake", "fatal"]`
- `test_cancelled_public_admission_keeps_lease_until_actor_wake`（`test_open_host_runtime.py:1178`）：同结构，caller cancel 后仍断言 wake 先于 fatal
- `test_admission_first_future_settles_before_fatal_transition`（`test_scheduler_health.py:69`）：`asyncio.Future.set_result()` 控制 actor future 完成时机
- `test_caller_cancellation_does_not_release_admission_future_lease`（`test_scheduler_health.py:106`）：caller cancel + future settle + fatal ordering

`test_open_host_runtime.py` 中 `_wait_for_run_status` helper 使用 poll+sleep，但只用于等待 async dispatch 完成，不作为 correctness oracle——assertion 在 helper 返回后执行。

### 6. S2 actor / Service / CLI / S4/S5 scope 是否越界

**PASS.**
- `_durable_actor.py` 未修改（S2 boundary preserved）
- `dayu/service/`、`dayu/cli/` 未修改
- `command.py` 未修改：start/submit/retry/replay 已统一消费 `RunAdmissionResult.pending_dispatch`，`not idempotent_replay` 命中属于 `resolve_wait`/callback wait resume（S6 scope），不是 S3 new-work admission
- `dispatch.py` 的 `Queue(maxsize=1)` watchdog 未改为 `asyncio.Event`（S5 scope），只让 closed/unavailable wake typed fail
- `_best_effort_closeout_pending_queue_for_shutdown` 已删除（旧 retry-self-close 专用 helper）

### 7. State machine 单向性与 close truth 一致性

**PASS.** Health gate 状态转换：
- `STARTING → READY`（`mark_ready`）
- `STARTING/READY → UNAVAILABLE`（`report_fatal`，首个 detail 保持真源）
- `STARTING/READY/UNAVAILABLE → CLOSING`（`begin_closing`）
- `CLOSING → CLOSED`（`mark_closed`）

`begin_closing` 中先写 `_state = CLOSING` 再 acquire lock，确保后续 `acquire_admission` 看到 CLOSING 并拒绝。`report_fatal` 在 `async with lock` 内写 UNAVAILABLE，与 admission lease 互斥。`mark_closed` 只允许从 CLOSING 进入 CLOSED。

public handle close 使用 `_close_lock` 防止并发 close，`begin_closing()` → 等待 active lease → scheduler → projection → actor handle → executor → scheduler store → `mark_closed()`，close idempotent（`begin_closing` 检查 CLOSED 直接 return）。

### 8. `raise_if_scheduler_unavailable` force 参数语义

**PASS.** `_raise_if_wake_unavailable()`（`dispatch.py`）：
- `self._closed` 时调用 `gate.raise_if_scheduler_unavailable(force=True)` — scheduler 私有 close gate 后，即使 CLOSING 也拒绝 wake
- 非 closed 时调用 `gate.raise_if_scheduler_unavailable(force=False)` — CLOSING 允许 close gate 前已提交 actor command 完成 matching wake（admission-first race 的正确行为）

`raise_if_scheduler_unavailable`（`_execution_health.py:226-263`）中 `force=False` + CLOSING → return（允许），`force=True` + CLOSING → raise（拒绝）。逻辑正确。

## Open Questions

- 无。

## Residual Risk

1. **S5-owned active-cancel watchdog `Queue(maxsize=1)`**：仍存在 wake drop 风险，S3 只让 closed/unavailable wake typed fail，不提前实施 level-triggered Event。按计划由 S5 关闭。
2. **wait/callback resume replay wake suppression**：`command.py:802/886` 的 `not idempotent_replay` 属于 S6 wait owner scope，S3 未扩张处理。
3. **`_wait_for_run_status` poll helper**：`test_open_host_runtime.py:1713` 使用 poll+sleep 等待 async dispatch 完成，理论上在极端负载下可能超时（100 × 10ms = 1s），但不影响 correctness oracle。
4. **未运行全仓 pytest**：focused S3 tests（212 passed）+ controller affected contract（45 passed）+ pyright（0 errors）已通过，未验证与 S4/S5/S6/S7/S8 scope 的交互回归。
