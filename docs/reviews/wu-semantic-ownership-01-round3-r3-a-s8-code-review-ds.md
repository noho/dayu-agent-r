# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S8 Code Review（AgentDS）

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: main（未提交 diff + 本分支已提交 vs main 的 diff）
- Output file: docs/reviews/wu-semantic-ownership-01-round3-r3-a-s8-code-review-ds.md
- Included scope:
  - `dayu/runtime/interruptible_process.py` — S8 变更（`_start_completed`、`_ProcessCleanupProgress`、single-flight cleanup）
  - `dayu/runtime/lane.py` — S8 变更（`_close_lock`/`_close_task`、single-flight close、remaining-token retry）
  - `tests/runtime/test_interruptible_process.py` — 新增 partial start/cleanup/cancel/concurrent 测试
  - `tests/runtime/test_lane.py` — 新增 partial release/close concurrent/cancel/reason 测试
  - `tests/runtime/test_lane_multiprocess.py` — 回归通过（未改）
  - `tests/runtime/test_import_boundary.py` — 回归通过（未改）
  - `tests/host/test_dispatch_scheduler.py` — 回归通过（Host diff 为空）
  - `tests/host/test_open_host_runtime.py` — 回归通过（Host diff 为空）
  - `tests/README.md` — S8 覆盖矩阵说明变更
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s8-implementation-codex.md` — 实现自述
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s8-controller-validation.md` — 控制侧裁决
- Excluded scope: 其他与 S8 无关的 branch vs main 累积 diff（cli、config、engine、fins、contracts、documents 等模块变更均不属于 S8 范围）
- Parallel review coverage: 无；本 review 由主 reviewer 逐文件走读全部已纳入 scope 的 production 与 test 文件。

## Findings

未发现实质性问题。

以下逐 review focus 给出证据与判定：

### 1. same-handle start retry 在 pre-spawn / post-spawn failure 后均被拒绝

- **入口**: `InterruptibleProcessHandle.start()` (`interruptible_process.py:313-326`)
- **证据**: `_started` 在 `_process.start()` 调用前即设为 `True`（line 324），任何 `start()` 异常后 `_started` 保持 `True` 但 `_start_completed` 保持 `False`。第二次 `start()` 在 line 322 命中 `raise RuntimeError("already started")`。
- **cleanup 区分**: `_process_may_have_spawned()` (line 543-558) 通过 `_start_completed` 和 `_process.pid` 区分 pre/post-spawn，pre-spawn 返回 `False`（跳过 kill/join），post-spawn 返回 `True`（执行 kill/join/process.close）。
- **测试覆盖**: `test_start_failure_is_non_retryable_and_close_cleans_partial_resources` (test_interruptible_process.py:1210-1251) 用 `_LifecycleFakeProcess` 覆盖 pre/post 两种场景，断言 call counts、alive 状态、`_cleanup_completed` 和新 handle 可用性。所有断言基于 fake 的确定性状态，无 sleep oracle。

### 2. Process close 的 close-start gate / cleanup completion / per-checkpoint progress 未混淆

- **入口**: `InterruptibleProcessHandle.close()` (line 410-445) 和 `_run_cleanup_attempt()` (line 447-541)
- **证据**: `_closed` 在 `close()` 入口即设（line 429），仅作 start-rejection gate 和幂等 close-started 标记。`_cleanup_completed` 仅在 `_run_cleanup_attempt()` 末尾 `_cleanup_progress.is_completed()` 通过后写入（line 541）。`_ProcessCleanupProgress` 的六个独立 marker 各自记录对应 checkpoint 完成状态。三者语义无交集。
- **测试覆盖**: `test_cleanup_checkpoint_failure_is_retryable_without_repeating_success` 参数化六个 checkpoint，证明 `_cleanup_completed` 只在 all-pass 时提交。

### 3. Private cleanup single-flight + caller cancellation 不取消 cleanup

- **入口**: `InterruptibleProcessHandle.close()` (line 410-445)
- **证据**: `_cleanup_lock` 保护 task 创建（line 430），`asyncio.shield(cleanup_task)` 保护 task 执行（line 442）。lock 在 `async with` 块退出后释放，多个 caller 可同时进入 `asyncio.shield()` 等待同一 task。`CancelledError` 被捕获并添加 observer（line 443-445），不取消 private task。
- **测试覆盖**: `test_caller_cancellation_does_not_cancel_single_cleanup_task` 参数化五个 checkpoint，使用 `call_soon_threadsafe` 触发取消，断言 CancelledError 透传 + cleanup task done + `_cleanup_completed`。
- **测试覆盖**: `test_concurrent_close_callers_share_cleanup_and_failure` 使用 Event barrier，两个 caller 观察同一 exception instance，cleanup 只执行一次。

### 4. Checkpoint exceptions: first error preserved, independent queue cleanup continues, retry-only-unfinished

- **入口**: `_run_cleanup_attempt()` (line 447-541)
- **证据**:
  - `first_error` 通过 `_first_cleanup_error()` (line 582-595) 保留首个异常。
  - Process checkpoint 依赖链（signal → join → process.close）：每个后续 checkpoint 由前驱成功 marker 守卫（e.g. line 483-486 `if signal_completed and not process_join_completed`），失败时链断裂但不影响 queue checkpoint。
  - Queue checkpoint（close/cancel-join/join）无条件执行（line 511-535），不依赖 process checkpoint 状态。
  - `cancel_join_thread()` 在 `join_thread()` 之前执行（line 518-535），使用 documented cancel-join 语义。
  - 第二次 close 因 `cleanup_task.done()` 为 True（首次异常），创建新 task 调用 `_run_cleanup_attempt()`，已完成 checkpoint 被各自的 `_cleanup_progress.*` marker 跳过。
- **测试覆盖**: 六 checkpoint 参数化测试断言 queue 在 process failure 后仍被完整清理、成功步骤不重复、第二次 close 补齐余量、第三次 close 幂等。

### 5. Queue cleanup: cancel_join_thread / join_thread 无不界等待或虚假完成

- **入口**: `_run_cleanup_attempt()` (line 518-535)
- **证据**: `cancel_join_thread()` 在 `join_thread()` 前调用（line 518-523），遵循 Python multiprocessing 文档推荐的 cancel-join 模式。`join_thread()` 通过 `asyncio.to_thread()` 在线程池执行，但 `cancel_join_thread()` 应使其即时返回。整个 cleanup 在 `asyncio.shield()` 保护下运行，caller cancellation 无法中断。
- **关注点**: `join_thread()` 本身无 timeout 参数，依赖 `cancel_join_thread()` 保证非阻塞。若实现背离 CPython documented behavior，可能占用线程池 worker。但这是 CPython 标准库的契约边界，`cancel_join_thread()` 的文档语义正是为此场景设计。不构成 runtime 缺陷。

### 6. LaneController: `_closed` 拒绝新 acquire，`_close_completed` 仅 marker heartbeat stopped + held tokens empty

- **入口**: `LaneController.acquire()` (line 477-564) 和 `_run_close_attempt()` (line 592-623)
- **证据**: `acquire()` 在 line 501 检查 `self._closed` 并 `raise RuntimeLaneClosedError`；在轮询循环 line 518 再次检查并返回 `LaneAcquireCancelled`。`_close_completed = True` 仅在 `_run_close_attempt()` line 623 写入，前提是 `first_error is None`、`_heartbeat_stopped` 为 True、`_held_tokens` 为空。任何失败路径都会在 line 617-622 提前 raise，不会提交 completed。

### 7. Failed token release 保留在 `_held_tokens`，后续 close 只重试 remaining token

- **入口**: `_run_close_attempt()` (line 610-616)
- **证据**: release 循环迭代 `tuple(self._held_tokens.values())` 快照。成功 release 通过 `_mark_token_released()` (line 914-923) 从 `_held_tokens` pop。失败 release 不 pop，token 保留供下次 `tuple()` 快照捕获。心跳已先停止（line 604-608），`_closed` 已阻止新 acquire，新 token 不会出现在 `_held_tokens` 中。
- **测试覆盖**: `test_close_best_effort_release_continues_after_one_release_failure` (test_lane.py:1382-1435): capacity=2，第一 token 失败、第二 token 成功释放 → `_held_tokens` 仅剩第一 token → `_close_completed=False` → 第二次 close 只重试第一 token → `_close_completed=True`。断言 release attempt count 精确为 2+1。

### 8. Lane concurrent close + caller cancellation share one private task；first close reason stable

- **入口**: `LaneController.close()` (line 566-590)
- **证据**: `_close_lock` 保护 task 创建（line 579），`_close_task` 已存在且未完成时复用。caller cancellation 通过 `asyncio.shield(close_task)` 保护（line 586）。first reason 检查在 lock 外执行（line 576），asyncio 单线程模型中无竞态。
- **测试覆盖**: `test_concurrent_close_and_caller_cancel_share_single_cleanup_task` (test_lane.py:1438-1507): barrier 测试证明 heartbeat stop 一次、release 一次、first reason 稳定、caller cancel 后另一 caller 正常完成、`_close_completed=True`。
- **测试覆盖**: `test_concurrent_close_callers_share_failure_then_retry_remaining_token` (test_lane.py:1509-1568): 两个 caller 观察同一 exception instance，后续 close 只重试 failed token。

### 9. Boundary: 无反向依赖，Host production 未改

- **证据**:
  - `rg -n "dayu\.(engine|host|service|ui|fins)" dayu/runtime/interruptible_process.py dayu/runtime/lane.py` → 无命中
  - `test_runtime_does_not_import_business_layers` (test_import_boundary.py:77-87) AST 扫描覆盖全 runtime 模块
  - `git diff -- tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py` → 无输出（Host 文件未改）
  - Host production 调用方无补偿 close/cleanup 逻辑
  - `dayu/runtime/__init__.py` 未扩大 public export

### 10. Tests: owner-level contract 断言，无 flaky sleep oracle

- **证据**:
  - 所有新增并发测试使用 `threading.Event` barrier 或 callback + `call_soon_threadsafe` 实现确定性同步，无 `time.sleep(N)` 作为 race correctness oracle
  - 断言聚焦于 owner-level contract：`_start_completed` gate、`_cleanup_completed` 提交条件、`_held_tokens` 残留、`_close_completed` 提交条件、first reason 稳定性、retry-only-incomplete-step 调用计数
  - 参数化测试覆盖六 checkpoint failure、五 cancel point、pre/post-spawn failure、两 token partial release、concurrent close/cancel 组合
  - 测试不经由 Host/Engine/Service/UI 层调用，直接操作 runtime primitive，证明 contract 行为不依赖上层装配
  - 210 tests passed，pyright 0 errors/0 warnings

## Open Questions

无。

## Residual Risk

- `cancel_join_thread()` 依赖 CPython documented behavior（调用后 `join_thread()` 即时返回）。若该契约在非 CPython 运行时或未来版本中失效，close 可能在线程池 worker 上产生无界等待。当前实现是 Python multiprocessing 官方推荐的 close-time cleanup 模式，不是 S8 引入的新风险。
- `_run_cleanup_attempt()` 若 `_process_may_have_spawned()` 持续以异常失败（极罕见场景：`_process.pid` 反复 raise），private task 将永不能到达 `_cleanup_completed`。每次 retry 都重新抛出同一 `_process_may_have_spawned` 错误。这反映了底层状态不可恢复的事实，行为正确但调用方应知道重试有界（例如在事件循环关闭前给有限次尝试）。
- Lane `_stop_heartbeat_once()` 若 heartbeat task 以非 CancelledError 异常完成，后续 retry 会反复 re-raise 同一 task exception，controller 不能到达 `_close_completed`。与上述 process 场景同理，反映真实不可恢复错误。
- 若承载 private cleanup task 的 event loop 被外力销毁，Python async task 无法继续——S8 保证的是 cooperative cancellation / concurrent close 下的 completion，不扩展为进程级 event-loop crash recovery。该边界由 runtime 调用方的 loop lifecycle 拥有，不是当前 S8 slice 的缺陷。

## 验证结果

```text
source .venv/bin/activate
pytest tests/runtime/test_interruptible_process.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py tests/runtime/test_import_boundary.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py -q

210 passed in 6.33s

python -m pyright dayu/runtime/ tests/runtime/ tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py

0 errors, 0 warnings, 0 informations
```

---

## Completion Report

- **status**: pass
- **artifact path**: docs/reviews/wu-semantic-ownership-01-round3-r3-a-s8-code-review-ds.md
- **number of findings**: 0（未发现实质性问题）
- **validation ran**: 全量 S8 scope 测试（210 passed）+ pyright（0 errors/0 warnings）+ 独立 `rg` boundary scan（无反向 import）+ Host diff 确认（空）
