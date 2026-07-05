# WU-TOOLS-CANCEL-01 Residual Hardening S2B Re-Review — AgentDS

## Verdict

**PASS** — 所有此前 DS/MiMo findings 已关闭，新增代码未引入 correctness/architecture/test 问题。

## Scope

- **Mode**: current changes (workspace uncommitted diff after AgentCodex fix)
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-rereview-ds.md`
- **Included scope**:
  - `dayu/tools/web/web_playwright_backend.py` — sync bridge、debug cleanup logging
  - `tests/tools/web/test_web_tools_provider.py` — synthetic cleanup tests + event loop bridge test + live browser smoke + helper extraction
  - `tests/README.md` — optional live smoke env var 说明
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-implementation-codex.md` — 更新后的 implementation report
- **Excluded scope**: 已提交的 S1/S2A commits、其他未修改文件
- **Context truth documents**: 上一轮 DS review (`wu-tools-cancel-01-residual-hardening-s2b-code-review-ds.md`)、MiMo review (`wu-tools-cancel-01-residual-hardening-s2b-code-review-mimo.md`)、S2A controller adjudication、residual hardening plan S2B 章节

## Previous Findings Disposition

### DS-01 (MEDIUM): `asyncio.run()` 在 sync 函数中为结构性脆弱点

**Verdict: CLOSED.**

新增 `_interrupt_playwright_process_sync()` bridge（`web_playwright_backend.py:476-518`）：

- **快速路径**（当前线程无 running loop）：直接 `asyncio.run(interrupt_multiprocessing_process(...))` — 与原有行为一致
- **Helper thread 路径**（当前线程有 running loop）：`_thread_has_running_asyncio_loop()` 检测到 running loop → 创建 daemon helper thread → helper thread 内 `asyncio.run(...)` → `Queue(maxsize=1)` 回传结果/异常 → 主线程 `helper_thread.join()` 后读取

关键路径验证：

```
_terminate_playwright_process
  → _interrupt_playwright_process_sync
    → _thread_has_running_asyncio_loop() == False
      → asyncio.run(interrupt_multiprocessing_process(...))  [快速路径]
    → _thread_has_running_asyncio_loop() == True
      → Thread(target=_run_process_interrupt_in_helper_thread, daemon=True)
      → helper_thread.start(); helper_thread.join()
      → Queue.get_nowait() → 返回或 re-raise
```

边界检查：
- **异常传播**: `_run_process_interrupt_in_helper_thread` 用 `except BaseException as exc: result_queue.put(exc)` 捕获所有异常（包括 `KeyboardInterrupt`），调用侧 `isinstance(message, BaseException): raise message` 原样传播 ✓
- **Queue 空处理**: `result_queue.get_nowait()` 抛出 `Empty` → 包装为 `RuntimeError("playwright process cleanup helper returned no result")` — 此路径仅在 helper thread 崩溃且未写入 queue 时触发，合理 ✓
- **Daemon thread**: helper thread 为 daemon，父进程退出时 OS 回收，不会阻止进程退出 ✓
- **`multiprocessing.Process` 方法线程安全**: `process.terminate()` / `process.kill()` 通过 `os.kill(pid, signal)` 实现，线程安全；`process.join()` 在 helper thread 的 `asyncio.to_thread()` 中运行，不冲突 ✓

新增测试 `test_playwright_worker_process_cleanup_supports_running_event_loop` 验证 helper thread 路径：sync 测试函数通过 `asyncio.run(_terminate_process_inside_running_loop(process))` 模拟 running loop 场景 → 验证 nested child 被正确清理 ✓

### DS-02 (MEDIUM): Cleanup 诊断在生产中被静默丢弃

**Verdict: CLOSED.**

新增 `_log_playwright_process_cleanup_stage()`（`web_playwright_backend.py:521-548`）：

- 在 `_terminate_playwright_process` 的 terminate 和 kill 阶段各调用一次
- 日志字段：`stage`、`reason`、`direct_signal_sent`、`group_signal_sent`、`exited`、`exitcode`、`elapsed_seconds`
- Docstring 明确声明："日志只包含 cleanup 诊断字段，不包含 URL、内容或 headers"
- 使用 `Log.debug(...)` — 与模块现有日志模式一致

测试 `test_playwright_worker_process_cleanup_kills_synthetic_nested_child_on_posix` 新增 `caplog` fixture 断言：
```python
assert "reason=group_signaled" in caplog.text
assert "group_signal_sent=True" in caplog.text
```
验证 debug 日志在生产代码路径中实际输出 ✓

### DS-03 (LOW): 测试 timing assertion 使用错误的参照 grace 值

**Verdict: CLOSED.**

Timing assertion 从 `ProcessCapsuleInterruptPolicy().terminate_grace_seconds`（0.2s）改为 `web_playwright_backend._PW_PROCESS_TERMINATE_GRACE_SECONDS`（1.0s）：

```python
# Before (错误参照):
assert terminate_result.elapsed_seconds <= ProcessCapsuleInterruptPolicy().terminate_grace_seconds  # 0.2s

# After (正确参照):
assert terminate_result.elapsed_seconds <= web_playwright_backend._PW_PROCESS_TERMINATE_GRACE_SECONDS  # 1.0s
```

`cleanup_elapsed_seconds` 断言同样改为使用 `_PW_PROCESS_TERMINATE_GRACE_SECONDS`。Implementation codex 单独记录了 measured cleanup time (0.002593s) 远低于 S1 policy defaults (0.2s)，满足 plan 的 "validate or adjust defaults" 要求 ✓

### DS-04 (LOW): 缺少 optional live browser cleanup smoke

**Verdict: CLOSED.**

新增 `test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort`（`test_web_tools_provider.py:1685`）：

- **默认跳过**：`DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE != "1"` 时 skip
- **POSIX 要求**：非 POSIX skip
- **Chromium binary 探测**：`_live_playwright_chromium_available()` 启动真实 browser 验证可用性
- **进程树观察**：通过 `ps -axo pid=,ppid=` 构建 PID→PPID 映射 → `_descendant_pids()` BFS 遍历 → 观察 worker 子进程的所有后代
- **Cleanup 验证**：`_terminate_playwright_process(process)` → `_wait_for_pids_absent(descendant_pids, timeout_seconds=3.0)`
- **安全网**：finally 块中 `process.kill()` + `_kill_remaining_pids(descendant_pids)` + `_wait_for_pids_absent`
- **测试 worker**：`_LiveBrowserLongRunningWorker`（`@dataclass(frozen=True, slots=True)`，可 pickle），lazy import `playwright.sync_api`，启动 Chromium headless → 导航到本地 fixture → 写 ready marker → `time.sleep(60)`
- Implementation codex 确认：`DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest ... -q` → `1 passed in 2.12s`

tests/README.md 同步更新，记录了 `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE` 环境变量约定 ✓

---

## Previous MiMo Findings Disposition

### MiMo-01 (MEDIUM): `asyncio.run()` 在 sync cleanup 路径中重复创建事件循环

**Verdict: CLOSED.** 与 DS-01 同一问题，sync bridge 修复覆盖。当前 `_interrupt_playwright_process_sync` 在快速路径中仍使用 `asyncio.run()` 创建事件循环，但 helper thread 路径消除了 "从 running loop 线程调用必定崩溃" 的 latent 风险。事件循环创建开销（每次 cleanup 最多 2 次，仅在进程实际被 terminate/kill 时）在 cleanup 场景中是合理的。

### MiMo-02 (LOW): 测试 timing assertion 使用了与生产不同的常量来源

**Verdict: CLOSED.** 与 DS-03 同一问题，assertion 已改为使用生产常量 `_PW_PROCESS_TERMINATE_GRACE_SECONDS`。

---

## New Code Review: Sync Bridge

### 走读 `_interrupt_playwright_process_sync`（`web_playwright_backend.py:476-518`）

```
入参: process (BaseProcess), signal_kind (ProcessCleanupSignal), grace_seconds (float)
  ↓
条件判断: _thread_has_running_asyncio_loop()
  ├─ False → asyncio.run(interrupt_multiprocessing_process(...))  [直接返回 ProcessInterruptResult]
  └─ True  → Queue(maxsize=1) → Thread(daemon=True).start() → .join()
              → Queue.get_nowait() → isinstance(message, BaseException)? raise : return
```

**线程安全分析**:
- `_thread_has_running_asyncio_loop()`: `asyncio.get_running_loop()` + catch `RuntimeError` — 标准检测模式 ✓
- `process.terminate()` / `process.kill()`: `os.kill(pid, signal)` 实现，线程安全 ✓
- `process.join()`: `multiprocessing.Process.join()` 文档声明线程安全；通过 `asyncio.to_thread()` 在 thread pool 中运行，不与主线程并发 join 同一进程 ✓
- `Queue.put()` / `Queue.get_nowait()`: `queue.Queue` 线程安全 ✓

**异常传播路径**:
1. `interrupt_multiprocessing_process` 内 `_validate_grace_seconds` 抛出 `TypeError`/`ValueError` → helper thread 中 `BaseException` 捕获 → put 到 queue → 主线程 `raise message`
2. `os.killpg` 抛出 `OSError` → `_cleanup_process_group_after_direct_signal` 内部处理，不传播 → 返回带有 `GROUP_SIGNAL_FAILED` reason 的 `ProcessInterruptResult` ✓
3. Helper thread 在 put 结果前崩溃 → `Queue.Empty` → `RuntimeError("playwright process cleanup helper returned no result")` ✓

**无新 correctness 问题。**

### 走读 `_log_playwright_process_cleanup_stage`（`web_playwright_backend.py:521-548`）

```
入参: stage (str), result (ProcessInterruptResult | None)
  ↓
条件判断: result is None → return (early exit)
  ↓
Log.debug(f"...stage={stage} reason={...} direct_signal_sent={...} ...")
```

- `result is None` 仅当 process 在 cleanup 前已退出（`_terminate_playwright_process:561-563`），此时无需日志 ✓
- f-string 字段顺序固定，grep 友好 ✓
- `elapsed_seconds:.6f` — 微秒精度，适合 sub-second cleanup 计时 ✓

**无新 correctness/隐私 问题。**

---

## New Code Review: Tests

### `_start_playwright_worker_process`（测试辅助函数）

将此前在多个测试中内联的 worker process 创建逻辑提取为共享 helper：
```python
ctx = multiprocessing.get_context("spawn")
result_queue = cast(_ResultQueueProtocol, ctx.Queue(maxsize=1))
process = ctx.Process(target=_playwright_process_entry, args=(result_queue, worker_callable, worker_kwargs))
process.daemon = True
process.start()
return process, result_queue
```

- 精确复用生产入口 `_playwright_process_entry` ✓
- `cast(_ResultQueueProtocol, ...)` — 与生产代码 `_run_playwright_worker_process:538` 相同模式 ✓
- 调用方仍需自行管理 finally cleanup — 各测试的 finally 块保持不变 ✓

### `test_playwright_worker_process_cleanup_supports_running_event_loop`

```
sync test → asyncio.run(_terminate_process_inside_running_loop(process))
  → async def _terminate_process_inside_running_loop
    → _terminate_playwright_process(process)  [在 running loop 线程中调用]
      → _interrupt_playwright_process_sync
        → _thread_has_running_asyncio_loop() == True
        → helper thread 路径
```

- 两个 event loop 同时存在（主线程 asyncio.run + helper thread asyncio.run）→ Python 允许每个线程独立的 event loop ✓
- 验证 nested child PID 消失 → 确认 helper thread 路径的 cleanup 功能完整 ✓
- 合适的 skip 条件（非 POSIX、group_signal_sent=False）✓

### `test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort`

Skip 层级（按优先级）：
1. `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE != "1"` → skip（默认）
2. `os.name != "posix"` → skip
3. `_live_playwright_chromium_available() == False` → skip
4. `_process_table_from_ps() is None` → skip
5. `descendant_pids` 为空 → skip（无可见后代）

每层 skip 都有明确 reason string ✓

**进程树快照竞态**: `_descendant_pids(process.pid)` 在 ready marker 出现后调用，此时浏览器已启动并创建子进程。在 snapshot 和 `_terminate_playwright_process` 之间，可能有新的子进程产生或旧进程退出。但测试只验证 "observed descendants disappear" — 新产生的 PID 不在 observed set 中，不参与验证。这是 process tree snapshot 的固有 tradeoff，accept as best-effort ✓

**`_LiveBrowserLongRunningWorker` picklability**: `@dataclass(frozen=True, slots=True)` 无字段 → `__slots__ = ()` → 模块级定义 → pickle by reference (`__module__` + `__qualname__`) ✓

**`_live_playwright_chromium_available()` 探测**: 启动 Chromium → 立即关闭 — 正确探测而不泄漏资源 ✓

### 其他测试质量确认

- **Spawn picklability**: `_SyntheticNestedPlaywrightWorker` 和 `_LiveBrowserLongRunningWorker` 均为 `@dataclass(frozen=True, slots=True)` 无字段，模块级定义 ✓
- **PID file sync**: `_read_pid_file` poll 0.02s / timeout 3.0s — 足够慷慨 ✓
- **Skip/fallback logic**: 所有 9 个 `ProcessGroupCleanupReason` 枚举值均在 skip set 中覆盖 ✓
- **Queue cleanup**: 所有测试 finally 块执行 `result_queue.close(); result_queue.join_thread()` ✓

---

## Architecture Boundary Re-Check

- `dayu.tools.web → dayu.runtime.interruptible_process`：tools → runtime 方向正确 ✓
- 新增 import：`from queue import Queue`、`from threading import Thread` — 标准库，无层级问题 ✓
- 无 `dayu.tools.web → dayu.host` 新增依赖 ✓
- `_ProcessInterruptBridgeMessage` TypeAlias 仅在模块内部使用 ✓

---

## Open Questions

无。

## Residual Risk

1. **真实 Chromium process tree cleanup 仍为环境依赖**: live browser smoke 已添加且通过（`DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`），但仅在当前开发环境验证。Chromium 进程树形状在不同 OS/版本间可能变化，`ps` 可见性不保证完整性。分类：S2B 已满足 plan 要求（optional/manual smoke exists），更强证据需后续 work unit。

2. **Sync bridge helper thread 的 `BaseException` 捕获**: `_run_process_interrupt_in_helper_thread` 使用 `except BaseException` 捕获所有异常。若 `KeyboardInterrupt` 在 helper thread join 前到达主线程，`helper_thread.join()` 被中断 → message 可能未写入 queue → 抛出 `RuntimeError("...returned no result")`。这是 cleanup 路径中 `KeyboardInterrupt` 处理的已知 edge case，不属于 regression。

3. **PID/PGID reuse race**: S2A 已记录的 POSIX 限制，S2B 不扩大。

4. **Live smoke 依赖 `ps` 输出格式**: `_process_table_from_ps` 解析 `ps -axo pid=,ppid=` 输出。格式在不同 POSIX 系统上可能略有差异（已在 `len(parts) != 2` 时跳过该行，非致命）。

## Validation

- `pytest tests/tools/web/test_web_tools_provider.py -q`: **33 passed, 1 skipped** (skipped = live browser smoke) ✓
- `pyright dayu/tools/web/web_playwright_backend.py tests/tools/web/test_web_tools_provider.py`: **0 errors, 0 warnings, 0 informations** ✓
- `git diff --check`: passed ✓
