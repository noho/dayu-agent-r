# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: main
- Output file: docs/reviews/wu-semantic-ownership-01-round3-r3-a-s8-code-review-mimo.md
- Included scope:
  - dayu/runtime/interruptible_process.py
  - dayu/runtime/lane.py
  - tests/runtime/test_interruptible_process.py
  - tests/runtime/test_lane.py
  - tests/runtime/test_lane_multiprocess.py
  - tests/runtime/test_import_boundary.py
  - tests/host/test_dispatch_scheduler.py
  - tests/host/test_open_host_runtime.py
  - tests/README.md
  - docs/reviews/wu-semantic-ownership-01-round3-r3-a-s8-implementation-codex.md
  - docs/reviews/wu-semantic-ownership-01-round3-r3-a-s8-controller-validation.md
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Focus Analysis

### 1. InterruptibleProcessHandle: same-handle start retry remains rejected after pre-spawn and post-spawn start failure

**Evidence**: `dayu/runtime/interruptible_process.py:313-326`

```python
def start(self) -> None:
    if self._closed:
        raise RuntimeError("interruptible process has already been closed")
    if self._started:
        raise RuntimeError("interruptible process has already started")
    self._started = True
    self._process.start()
    self._start_completed = True
```

**Analysis**: `_started` 在 `_process.start()` 前设置为 `True`。若 `start()` 抛异常，`_start_completed` 不会设置，但 `_started` 已为 `True`，第二次调用会抛 "already started"。

**Test Coverage**: `test_start_failure_is_non_retryable_and_close_cleans_partial_resources` 参数化测试覆盖 pre/post-spawn failure，验证第二次 start() 拒绝且 close 能完整清理资源。

### 2. Process close: close-start gate, cleanup completion, and per-checkpoint progress are not conflated

**Evidence**: `dayu/runtime/interruptible_process.py:429-445`

```python
self._closed = True  # close-start gate
async with self._cleanup_lock:
    if self._cleanup_completed:  # completion gate
        return
```

**Analysis**: `_closed` 在锁外设置（close-start gate），`_cleanup_completed` 在 `_run_cleanup_attempt` 成功后设置（completion gate）。`_ProcessCleanupProgress` 记录每个 checkpoint 独立完成状态。

**Test Coverage**: `test_cleanup_checkpoint_failure_is_retryable_without_repeating_success` 验证各 checkpoint 独立记录，失败后重试只补未完成步骤。

### 3. Process close: private cleanup is single-flight under concurrent close; caller cancellation does not cancel cleanup

**Evidence**: `dayu/runtime/interruptible_process.py:430-445`

```python
async with self._cleanup_lock:
    if self._cleanup_completed:
        return
    cleanup_task = self._cleanup_task
    if cleanup_task is None or cleanup_task.done():
        cleanup_task = asyncio.create_task(self._run_cleanup_attempt(...))
        self._cleanup_task = cleanup_task
try:
    await asyncio.shield(cleanup_task)  # caller cancellation does not cancel cleanup
except asyncio.CancelledError:
    cleanup_task.add_done_callback(_observe_cancelled_close_cleanup_task)
    raise
```

**Analysis**: `_cleanup_lock` 保护 task 创建，`asyncio.shield()` 防止 caller cancellation 取消 cleanup。并发 caller 共享同一 task。

**Test Coverage**: `test_caller_cancellation_does_not_cancel_single_cleanup_task` 和 `test_concurrent_close_callers_share_cleanup_and_failure` 验证此行为。

### 4. Process close: checkpoint exceptions preserve first error, continue independent queue cleanup, and retry only unfinished steps

**Evidence**: `dayu/runtime/interruptible_process.py:458-541`

```python
first_error: Exception | None = None
# 每个 checkpoint 独立 try/except
if not self._cleanup_progress.signal_completed:
    try:
        ...
    except Exception as exc:
        first_error = _first_cleanup_error(first_error, exc)
```

**Analysis**: `first_error` 保留首个异常，后续 checkpoint 继续执行。`_cleanup_progress` 记录每个 checkpoint 完成状态，下次 close 只重试未完成步骤。

**Test Coverage**: `test_cleanup_checkpoint_failure_is_retryable_without_repeating_success` 参数化测试覆盖六个 checkpoint，验证首错保留、queue cleanup 继续、重试只补未完成步骤。

### 5. Queue cleanup: cancel_join_thread / join_thread usage does not introduce an unbounded wait or false completion

**Evidence**: `dayu/runtime/interruptible_process.py:518-535`

```python
if not self._cleanup_progress.queue_cancel_join_completed:
    try:
        self._result_queue.cancel_join_thread()  # documented cancel-join gate
        self._cleanup_progress.queue_cancel_join_completed = True
    except Exception as exc:
        first_error = _first_cleanup_error(first_error, exc)

if (self._cleanup_progress.queue_cancel_join_completed
    and not self._cleanup_progress.queue_join_completed):
    try:
        await asyncio.to_thread(self._result_queue.join_thread)
        self._cleanup_progress.queue_join_completed = True
```

**Analysis**: 先调用 `cancel_join_thread()`（documented cancel-join 语义），再调用 `join_thread()`。`cancel_join_thread()` 设置取消标志，避免 `join_thread()` 无限等待。

**Test Coverage**: 测试覆盖 queue close/cancel_join_thread/join_thread 各 checkpoint 的 failure 和 retry。

### 6. LaneController: _closed rejects new acquire but _close_completed only means heartbeat stopped and held tokens empty

**Evidence**: `dayu/runtime/lane.py:575-623`

```python
self._closed = True  # rejects new acquire
if reason is not None and self._close_reason is None:
    self._close_reason = reason
self._wake_waiters()
# ...
# _close_completed=True 只在以下条件满足时设置：
if first_error is not None:
    raise first_error
if not self._heartbeat_stopped:
    raise RuntimeLaneError("runtime lane heartbeat 尚未完成 close cleanup")
if self._held_tokens:
    raise RuntimeLaneError("runtime lane close 后仍存在 held token")
self._close_completed = True
```

**Analysis**: `_closed` 在锁外设置，立即拒绝新 acquire。`_close_completed` 只在 heartbeat stopped 且 held tokens 为空时设置。

**Test Coverage**: `test_close_best_effort_release_continues_after_one_release_failure` 验证 failed token 保留，`_close_completed=False`。

### 7. LaneController: failed token release remains in _held_tokens and later close retries only remaining token

**Evidence**: `dayu/runtime/lane.py:610-616`

```python
for lane_token in tuple(self._held_tokens.values()):
    try:
        await lane_token.release()
    except Exception as exc:
        if first_error is None:
            first_error = exc
```

**Analysis**: 遍历 `_held_tokens` 快照进行 release。release 成功时，token 从 `_held_tokens` 中移除（通过既有 release owner）。release 失败时，token 保留在 `_held_tokens` 中，下次 close 只重试剩余 failed token。

**Test Coverage**: `test_close_best_effort_release_continues_after_one_release_failure` 验证 failed token 保留，第二次 close 只重试 failed token。

### 8. LaneController: concurrent close and caller cancellation share one private task; first close reason remains stable

**Evidence**: `dayu/runtime/lane.py:576-590`

```python
if reason is not None and self._close_reason is None:
    self._close_reason = reason  # first close reason remains stable
# ...
async with self._close_lock:
    if self._close_completed:
        return
    close_task = self._close_task
    if close_task is None or close_task.done():
        close_task = asyncio.create_task(self._run_close_attempt())
        self._close_task = close_task
try:
    await asyncio.shield(close_task)
```

**Analysis**: `reason` 只在 `_close_reason is None` 时设置，保证首次 close reason 稳定。`_close_lock` 保护 task 创建，`asyncio.shield()` 防止 caller cancellation 取消 cleanup。并发 caller 共享同一 task。

**Test Coverage**: `test_concurrent_close_and_caller_cancel_share_single_cleanup_task` 和 `test_concurrent_close_callers_share_failure_then_retry_remaining_token` 验证此行为。

### 9. Boundary: dayu.runtime does not import dayu.engine/dayu.host/dayu.service/dayu.ui/dayu.fins; Host production is not changed

**Evidence**:

```bash
rg -n "dayu\.(engine|host|service|ui|fins)" dayu/runtime
# 只命中 dayu/runtime/__init__.py 的架构说明 docstring
```

**Analysis**: runtime 模块没有反向依赖。Host production 未修改。AST import boundary 测试通过。

**Test Coverage**: `tests/runtime/test_import_boundary.py` 通过 AST 扫描验证边界。

### 10. Tests: assertions prove owner-level contract, not private incidental behavior only; no flaky sleep-based race oracle

**Evidence**: 测试使用 `threading.Event` 和 `asyncio.create_task` 而不是 sleep。测试验证的是 contract-level 行为（如 `_cleanup_completed`、`_held_tokens`）。

**Analysis**: 测试使用 barrier 机制而不是随机 sleep，避免 flaky。断言针对 owner-level contract，而不是私有实现细节。

**Test Coverage**: 所有新增测试使用 `threading.Event`、callback 或 task barrier。

## Validation

### Required pytest

```text
source .venv/bin/activate
pytest tests/runtime/test_interruptible_process.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py tests/runtime/test_import_boundary.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py -q

210 passed in 6.31s
```

### Required pyright

```text
source .venv/bin/activate
python -m pyright dayu/runtime/ tests/runtime/ tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py

0 errors, 0 warnings, 0 informations
```

### Source scans

```bash
rg -n "_started|_closed|cleanup|join_thread|cancel_join_thread" dayu/runtime/interruptible_process.py
```

分类：
- `_started` 只作为 start-attempt gate；`_start_completed` 才允许 wait/interrupt 操作。
- `_closed` 只作为 close-started/start-rejection gate；幂等 return 读取 `_cleanup_completed`。
- private lock/task 提供 single-flight；六个 cleanup checkpoint 均有独立 success marker。
- `cancel_join_thread()` 明确先于 `join_thread()`，使用 documented cancel-join 语义。

```bash
rg -n "_close_completed = True|_held_tokens|close_task|close_lock" dayu/runtime/lane.py
```

分类：
- `_close_lock` / `_close_task` 只拥有 concurrent close single-flight。
- 成功 release 的唯一 `_held_tokens.pop(...)` 仍在 token release/lost owner。
- `_close_completed=True` 唯一位于 `_heartbeat_stopped` 校验和 `_held_tokens` 空校验之后。

```bash
rg -n "dayu\.(engine|host|service|ui|fins)" dayu/runtime
```

结果只命中 `dayu/runtime/__init__.py` 的架构说明 docstring；无 Python import 命中。

```bash
git diff --check
```

结果：无输出。

## Open Questions

无。

## Residual Risk

无。
