# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: S2 accepted commit `c4c6c9ba` 之后的 S3 implementation workspace changes
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s3-code-review-ds.md`
- Included scope: `dayu/host/_execution_health.py`（新增）、`dayu/host/api.py`（`HostApiErrorCode.UNAVAILABLE`、`HostUnavailableDetail`）、`dayu/host/open_host.py`（admission lease、shared gate assembly、close order、`_invoke_new_work`）、`dayu/host/dispatch.py`（critical task supervisor、retry exhaustion 不自闭、typed wake reject、queue closeout helper 删除、非 retry 异常从 backoff-continue 收窄为 raise）、`dayu/host/admission.py`（idempotent replay matching wake from durable snapshot）、`dayu/host/__init__.py`（`HostUnavailableDetail` 导出）、`tests/host/test_scheduler_health.py`、`tests/host/test_open_host_runtime.py`（admission-first/fatal-first/cancelled admission race）、`tests/host/test_dispatch_scheduler.py`（retry exhaustion、critical task fatal mapping）、`tests/host/test_admission_multiprocess.py`（idempotent replay wake）、`tests/host/test_package_exports.py`、`tests/host/test_public_contracts.py`（controller 窄范围 UNAVAILABLE enum 扩充）、`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`。
- Excluded scope: S2 actor（`_durable_actor.py`）、Service、CLI、S4 recovery batching、S5 watchdog level-triggered/deferred cancel classification、S6-S8。均未在 diff 中出现。
- Parallel review coverage: 无。

## Review Method Summary

沿 S3 六个 review focus，逐项走读 `_execution_health.py` → `open_host.py`（admission/invoke/close）→ `dispatch.py`（critical supervisor/retry/wake reject/非 retry Exception raise）→ `admission.py`（idempotent replay matching wake）完整生产调用链，核对 plan Slice S3 冻结契约与代码实际行为一致。随后走读全部 S3 测试代码，验证 race oracle 为 deterministic barrier（`asyncio.Event`/`threading.Event`/actor FIFO barrier），无 sleep/probabilistic oracle。最后做 scope creep 扫描，确认 S2/S4/S5 无越界修改。

各 review focus 结论：

### 1. HostExecutionHealthGate 作为 execution health/admission ordering 唯一 owner

State machine: `STARTING → READY → UNAVAILABLE → CLOSING → CLOSED`，单向不可逆。`mark_ready()` 仅在 `STARTING` 状态允许（`_execution_health.py:128-132`）；首个 `report_fatal()` 的 component/reason_code 保持真源，后续 `report_fatal()` 返回 `False`（`_execution_health.py:153-179`）；`begin_closing()` 在 `CLOSED` 时幂等返回，在非 `CLOSED` 时进入 `CLOSING` 并等待 active admission lease 收口（`_execution_health.py:181-195`）；`mark_closed()` 仅允许从 `CLOSING` 转入（`_execution_health.py:197-208`）。

与 public handle close truth 的关系：`_PublicHostHandle` 不再持有独立 `_closed: bool`，改为委托 `self._health_gate.raise_if_public_closed()`（`open_host.py:1079`）；`_PublicHostHandle.close()` 通过 `self._health_gate.begin_closing()` 进入 CLOSING 状态后再释放资源（`open_host.py:943`）。不存在 scheduler `_closed` 与 public handle `_closed` 分裂的真源双写。

共享 gate 的线程安全：`HostExecutionHealthGate` 全部方法使用 `asyncio.Lock` 保护 admission/fatal 串行化（`_execution_health.py:106`），符合 opener event loop 单线程模型的线程安全语义。

### 2. Admission lease 覆盖范围

`_invoke_new_work()`（`open_host.py:1047-1070`）的覆盖链：
1. `await self._health_gate.acquire_admission()` — 取得 lock，原子校验 READY（`_execution_health.py:134-151`）
2. `future = self._durable_actor.submit(operation)` — 提交到 actor FIFO
3. `lease.release_when_done(future)` — 绑定 actor future 而不是 caller awaiter（`_execution_health.py:69-77`）
4. `return await asyncio.shield(future)` — shield caller cancellation

Caller cancellation 隔离验证：`_release_after_future` 在 actor future 完成后（即使 caller 已取消）才调用 `lease.release()`（`_execution_health.py:79-91`）；`_invoke_new_work` 使用 `asyncio.shield` 防止 caller cancel 传播到 actor future。`test_caller_cancellation_does_not_release_admission_future_lease`（`test_scheduler_health.py:106-154`）证明 caller 取消后 fatal 仍等待 actor future 完成。

`acquire_admission()` 异常分支完整覆盖：STARTING → `_unavailable_error()`；UNAVAILABLE → `_unavailable_error()`；CLOSING/CLOSED → `HostClosedError()`；只有 READY 返回 lease。

### 3. Critical task fatal / transient / normal close 分类

`_supervise_critical_task()`（`dispatch.py:2644-2698`）的三路分类：
- `CancelledError` → 透传（scheduler 正常 close cancel 路径）
- `Exception` → 记录原始异常文本到日志但仅向 health gate 提交稳定 `(component, reason_code="critical_task_unexpected_exit")` → fatal
- 正常 return 且 `_closed=False` → 同样 report_fatal（unexpected exit）

`HostTransactionRetryExhaustedError` 在 drain loop 内部被独立捕获并退避重试（`dispatch.py:2910-2916`），不向上传播到 supervisor，因此不触发 fatal。这是从旧代码 self-close scheduler 的语义修正——旧代码对 retry exhaustion 调用 `_best_effort_closeout_pending_queue_for_shutdown`、写 `_closed=True`、取消 active workers；新代码仅 sleep backoff 后继续 reconcile。

非 `HostTransactionRetryExhaustedError` 的 `Exception`：旧代码通过 `except Exception: sleep + continue` 静默吞掉所有非 retry 异常并继续循环；新代码改为 `raise`，异常传播到 `_supervise_critical_task` 后 report fatal。该收窄与 plan "只有 invariant/non-retryable critical exit 进入 UNAVAILABLE" 一致——旧 broad backoff 实际上掩盖了真实的 invariant 违反。`HostTransactionRunner.run_write()` 内部已将 transient SQLite busy 完整重试后才抛出 `HostTransactionRetryExhaustedError`，因此非 retry-exhausted 异常在 drain loop 层面已是 non-retryable。

`wake_dispatch`/`wake_queue_promotion`/`wake_active_cancel_watchdog` 在 scheduler closed 或 health unavailable 时通过 `_raise_if_wake_unavailable()`（`dispatch.py:2702-2717`）抛出 `HostApiError(UNAVAILABLE, retryable=True)`，不再静默 return（旧 `wake_queue_promotion` 对 `self._closed` 的 `_LOGGER.debug` + return 已被删除）。

已删除的 helper：`_best_effort_closeout_pending_queue_for_shutdown`（`dispatch.py` diff 中完整删除），以及其内部使用的 `_safe_closeout_worker_startup_timeout` helper 调用已移除。

### 4. Idempotent replay wake from durable snapshot

`_idempotent_run_result()` 现在调用 `_idempotent_replay_pending_dispatch(run, attempt, dispatch_record)`（`admission.py:3984-3987`），从同一 transaction 读取的 Run/Attempt/dispatch snapshot 派生 matching wake。

`_idempotent_replay_pending_dispatch()`（`admission.py:4001-4040`）的条件链：`run.status == RUNNING AND attempt != None AND attempt.status == STARTING AND dispatch_record != None AND dispatch_record.status == PENDING AND run.current_attempt_id == attempt.attempt_id AND dispatch_record.run_id == run.run_id AND dispatch_record.attempt_id == attempt.attempt_id AND dispatch_record.execution_id == attempt.execution_id AND dispatch_record.cancelled_event_id is None AND dispatch_record.worker_accept_event_id is None`。全条件满足才返回 `PendingDispatchRecord`；任一不满足返回 `None`。

ACCEPTED replay 的 pre-start governance wake 由既有 `_wake_start_governance_if_needed()` 独立派生，与 PENDING replay 的 dispatch wake 各自从 durable snapshot 独立决策。

`test_idempotent_replay_derives_matching_wake_from_durable_snapshot`（`test_admission_multiprocess.py:535-621`）覆盖三条路径：ACCEPTED replay → 1 次 promotion wake；PENDING replay → 1 次 dispatch wake（且 run/attempt/dispatch_record identity 完整匹配）；CANCELLED replay → 零 dispatch/promotion/watchdog wake。

代码中 `idempotent_replay` bool 仅作为 admission result 的元数据标记（让 command path 判断是否跳过 after-commit wake）；它不替代 durable snapshot 作为 wake 决策的真源。

### 5. Deterministic race tests

全部 S3 race test 使用确定性 oracle：
- Actor FIFO barrier：`threading.Event` 在 actor thread 阻塞 + `asyncio.Event` 在 opener loop 同步（`test_open_host_runtime.py:1067-1087`）
- Admission submission 记录：monkeypatch `DurableActor.submit` 设 `asyncio.Event`（`test_open_host_runtime.py:1090-1105`）
- Wake completion 观察：monkeypatch `HostDispatchScheduler.wake_queue_promotion` 记录 order list（`test_open_host_runtime.py:1107-1117`）
- Fatal 等待：`report_fatal()` 在 lock 上阻塞直到 admission release（`test_open_host_runtime.py:1119-1132`）
- `_supervise_critical_task` 的 fatal 提交：直接调用 `gate.report_fatal()` owner 方法注入（`test_scheduler_health.py:68-102`），不依赖偶然 task timing

无 `asyncio.sleep(n)` 作为 correctness oracle；poll interval sleep 仅出现在被验证的 backoff 行为断言中（`test_dispatch_scheduler.py:2760-2765` 使用 `asyncio.wait_for(retry_seen.wait(), timeout=0.5)` 而非固定 sleep）。

### 6. Scope creep 扫描

- S2 actor：`dayu/host/_durable_actor.py` 不在 diff 中。未修改。
- Service：`dayu/service/` 下无文件变更。未修改。
- CLI：`dayu/cli/` 下无文件变更。未修改。
- S4 recovery batching：`StartupRecoveryScanner.scan()` 仍在 `open_host.py` 中原样调用（单次全量 scan），无 keyset cursor/batch 逻辑。未越界。
- S5 watchdog level-triggered event：`_active_cancel_watchdog_queue` 仍为 `asyncio.Queue(maxsize=1)`（`dispatch.py` unchanged）。未越界。
- S5 deferred cancel classification：`_is_deferred_cancel_state()` 仍存在于 `command.py`，未被修改。未越界。
- `command.py` 中 `resolve_wait` 的 `not idempotent_replay` guard 是既有 wait/callback resume 路径，S3 未修改，不属于 new-work admission scope。

## Findings

未发现实质性问题。

所有六个 review focus 的代码实际行为与 plan Slice S3 冻结契约一致：
- `HostExecutionHealthGate` 是 execution health/admission ordering 的唯一 owner，状态单向不可逆，不与 public handle close truth 分裂
- Admission lease 真实覆盖 health check → actor future → commit after-callback → matching wake completion，caller cancellation 不会提前释放 lease
- Critical fatal、transient retry exhaustion、normal close 三路正确分类；retry exhaustion 不再 self-close scheduler
- Idempotent replay wake 从 durable Run/Attempt/dispatch snapshot 派生，不是 bool shortcut
- 全部 race tests 使用 `asyncio.Event`/`threading.Event`/actor FIFO 作为 deterministic oracle
- S2 actor、Service/CLI、S4/S5 scope 未被越界修改或语义偷跑

## Open Questions

无。

## Residual Risk

- drain loop 的 `except Exception` 从旧 `backoff-continue` 收窄为 `raise → fatal`（`dispatch.py:2926-2930`）。该变更与 plan "只有 invariant/non-retryable critical exit 进入 UNAVAILABLE" 语义一致：`HostTransactionRunner.run_write()` 内部已将 transient busy 完整重试后才抛出 `HostTransactionRetryExhaustedError`，非 retry-exhausted 异常已是 non-retryable。但实现报告和 plan freeze 的变更描述中仅讨论了 retry exhaustion 路径（不再 self-close），未显式讨论非 retry Exception 路径的收窄。controller 若认为需显式记录此边界变更，可在 adjudication 中确认。
- S5 active-cancel watchdog 仍使用 `asyncio.Queue(maxsize=1)`；S3 只让其在 unavailable/closed wake 上 typed fail，未提前实施 level-triggered Event。计划明确留给 S5。
- `resolve_wait` / callback wait resume 的 idempotent replay wake suppression 仍属于 wait owner（S6），S3 未修改。
- `_raise_if_wake_unavailable` 在 `self._closed=True` 时先调用 `force=True` → 无条件 `raise`，随后第二个 `raise_if_scheduler_unavailable`（无 force）不可达。不影响正确性，属于可后续清理的 dead code。
