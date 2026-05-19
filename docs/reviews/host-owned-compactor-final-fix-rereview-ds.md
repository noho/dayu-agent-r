# Code Review — Host-owned Compactor Final Fix Re-Review

## Scope

- **Mode**: current changes
- **Branch**: feat/host-p10-5-public-contract-freeze
- **Base**: main (uncommitted workspace changes only — 无新增 committed changes 相对已有 git log)
- **Output file**: docs/reviews/host-owned-compactor-final-fix-rereview-ds.md
- **Included scope**:
  - `dayu/host/llm_compaction.py` — 线程桥移除、`_run_agent_request` async 化
  - `dayu/host/compaction.py` — `ContextCompactor.compact` Protocol async 化
  - `dayu/host/compaction_operation.py` — `run_compaction_operation` async 化
  - `dayu/host/dispatch.py` — `_promotion_queue` / `_promotion_drain_loop` 引入、`wake_queue_promotion` / `run_queue_promotion` 分离、`_run_pre_start_governance` / `_execute_proactive_compaction` async 化、`_consume_worker_events` 切换 `ingest_async`
  - `dayu/host/engine_ingest.py` — `ingest` / `ingest_async` 拆分、`_ingest_before_reactive_compaction` / `_finish_ingest` 提取、`_execute_reactive_compaction` async 化
  - `dayu/host/fake_compaction.py` — `FakeContextCompactor.compact` async 化
  - `dayu/host/context_budget.py` — `BudgetEstimate.hard_threshold_tokens` 最小值校验
  - `dayu/host/context_policy.py` — `ContextBudgetPolicy.hard_threshold_tokens` 最小值校验、`MIN_CONTEXT_HARD_THRESHOLD_TOKENS` 导出
  - `dayu/host/README.md` — 文档同步
  - `AGENTS.md` / `CLAUDE.md` — 架构约束措辞收紧
  - `tests/host/test_compaction_operation.py` (新文件) — async retry 测试
  - `tests/host/test_llm_compaction.py` — 线程桥移除断言、`default_timeout_seconds` 参数化
  - `tests/host/test_dispatch_scheduler.py` — promotion task 生命周期、异常、close 测试
  - `tests/host/test_context_budget.py` — hard threshold 最小值拒绝测试
  - `tests/host/test_context_policy.py` — hard threshold 最小值拒绝与自动计算测试
  - `tests/host/test_compact_artifact_store.py` — async compact 调用适配
  - `tests/host/test_compaction_contract.py` — async compact 调用适配
  - `tests/host/test_engine_ingest_mapping.py` — reactive compaction 测试切换 `ingest_async`
  - `tests/host/test_active_cancel_dispatch.py` — `_start_governed_refs` async 化
  - `tests/host/test_phase5_local_execution_integration.py` — `run_queue_promotion` 调用适配
  - `tests/host/test_phase7_waiting_integration.py` — `_run_pre_start_governance` await
  - `tests/README.md` — 测试覆盖文档同步
- **Excluded scope**: docs/reviews/ 下的已有 review artifacts、untracked 非变更文件
- **Parallel review coverage**: 无（单 reviewer 全量走读）

## Findings

### 1-未修复-中-`_drain_loop` catch-all Exception 静默退出且不重建

- **入口/函数**: `HostDispatchScheduler._drain_loop` → `HostDispatchScheduler._promotion_drain_loop`
- **文件(行号)**: `dayu/host/dispatch.py:1570-1576` (drain), `dayu/host/dispatch.py:1578-1621` (promotion)
- **输入场景**: drain loop 内部任意非 `CancelledError` 的 `Exception`（例如 `_dispatch_one` 抛出未被内层捕获的 RuntimeError、数据库连接断开导致 transaction runner 抛出异常等）。
- **实际分支**: `_drain_loop` 外层 `except Exception` 分支（line 1570），仅 `LOGGER.warning` 后退出函数，不 re-raise，也不触发 task 重建。`_promotion_drain_loop` 内层有 per-item 异常捕获，但外层 while 循环中若 `self._promotion_queue.get()` 抛出非 `CancelledError` 异常（理论上可能，虽然 asyncio.Queue 实际不会），同样静默退出。
- **预期行为**: drain loop 是 scheduler 的核心调度心跳，异常退出后应通知上层或触发重建。最坏情况下 scheduler 存活但不再消费 dispatch queue / promotion queue，表现为"调度静默停止"。
- **实际行为**: task 静默完成（不报错到 scheduler owner），没有 task 重建逻辑。`wake_dispatch` / `wake_queue_promotion` 会在下次 wakeup 时检测到 `task.done()` 并重建，但如果不再有新的 wakeup 入队，scheduler 永久停滞。
- **直接证据**:
  - `_drain_loop` (line 1570-1576): `except Exception as exc: _LOGGER.warning(...)` — 无 `raise`、无 task 重建。
  - `_promotion_drain_loop` (line 1616-1621): `except asyncio.CancelledError: ... raise` — 仅处理取消，非 CancelledError 的异常会击穿到 task 层级被 asyncio 静默记录。
- **影响**: 调度静默停滞。当前条件下触发概率低（内层已捕获几乎所有异常），但一次未覆盖的异常即可导致 scheduler 不可恢复地停止工作。
- **建议改法和验证点**: 在 `_drain_loop` 和 `_promotion_drain_loop` 外层增加 `except BaseException` 兜底，写 CRITICAL 日志后由 `wake_dispatch` / `wake_queue_promotion` 的下次调用重建；或在异常退出后通过 `add_done_callback` 触发自动重建。验证：注入故障后确认 scheduler 恢复调度。
- **修复风险**: 低。这是防御性改进，不改变正常路径行为。
- **严重程度**: 中。此问题在 diff 之前的原始 `_drain_loop` 中已存在，本 diff 新增的 `_promotion_drain_loop` 复用了相同模式（存在一致性考虑）。不算本 diff 引入的回归，但作为 re-review 在 compaction async 化后 compaction 走 promotion path 更多，暴露面增大。

### 2-未修复-低-`_promotion_drain_loop` close 竞态窗口可能丢排队的 session_id

- **入口/函数**: `HostDispatchScheduler.wake_queue_promotion` → `HostDispatchScheduler.close` → `HostDispatchScheduler._promotion_drain_loop`
- **文件(行号)**: `dayu/host/dispatch.py:614-628` (wake), `dayu/host/dispatch.py:1514-1529` (close), `dayu/host/dispatch.py:1578-1621` (loop)
- **输入场景**: `wake_queue_promotion` 在 `close()` 设置 `_closed=True` 之前将 session_id 入队，close 设置 `_closed=True` 后 cancel promotion task。task 在 `_promotion_queue.get()` 处被取消，已入队但未处理的 session_id 被丢弃。
- **实际分支**: close 流程: `self._closed = True` → `promotion_task.cancel()` → `await _suppress_task_cancel(promotion_task)`。此时 promotion task 在 `_promotion_queue.get()` 等待中收到 CancelledError，不处理队列中已排队的项。
- **预期行为**: shutdown 期间丢排队的 session 不造成数据损坏（Run 仍留在 QUEUED/ACCEPTED 状态，下次 scheduler 实例 replay 时会被重新处理）。从正确性角度可接受。
- **实际行为**: 被丢弃的 session_id 不触发 promotion，但 session 的 queued Run 不会进入错误终态。下次实例重启时通过 admission replay 重新评估。
- **直接证据**: `_promotion_drain_loop` (line 1587): `session_id = await self._promotion_queue.get()` — 取消时队列项丢失。`close` (line 1514, 1527-1529): 在 `_closed=True` 之后 cancel promotion task。
- **影响**: 低。shutdown 竞态窗口极窄，且 Run 终态不受影响。与 `_drain_loop` / `_queue` 的 shutdown 行为一致。
- **建议改法和验证点**: 若需严格保证，在 close 中先 drain 队列（非阻塞 get_nowait 直到 QueueEmpty），再 cancel task。当前优先级低。
- **修复风险**: 低。
- **严重程度**: 低。行为与已有 `_drain_loop` close 模式一致，属 shutdown 边界可接受 tradeoff。

### 3-无缺陷-线程桥移除完整且验证到位

对审查问题 #1 的逐项确认：

- `dayu/host/llm_compaction.py`: 已删除 `import threading`、`import asyncio`、`_ThreadRunState`、`_run_agent_request_sync`、`_run_agent_request_in_thread`。`LLMContextCompactor.compact` 直接 `await _run_agent_request(...)`，`_run_agent_request` 直接 `await run_agent_and_wait(request)`。
- `dayu/host/` 全目录：`asyncio.run`、`run_until_complete` 零匹配。`threading` 仅用于 `RLock`（`dispatch.py:18`、`tool_runtime.py:23`），与线程桥无关。
- `dayu/host/compaction.py:877`: `ContextCompactor.compact` Protocol 声明为 `async def compact(...)`。
- 测试 `test_llm_context_compactor_does_not_use_thread_bridge` (test_llm_compaction.py:30-35) 通过 `inspect.getsource` 断言模块源码不含 `threading`、`thread.join(`、`asyncio.run`，提供回归防护。

结论：线程桥已彻底移除，无隐形 sync-async bridge 残留。

### 4-无缺陷-`ingest` / `ingest_async` 拆分语义正确

对审查问题 #2 的逐项确认：

- `EngineEventIngestor.ingest()` (engine_ingest.py:486) 保留为 sync 方法，仅限不需要 reactive compaction 的事件。若内部逻辑返回 `_ReactiveCompactPending`，抛出 `RuntimeError("reactive context compaction requires ingest_async")`。
- `EngineEventIngestor.ingest_async()` (engine_ingest.py:507) 为新 async 方法，处理需要 reactive compaction 的事件路径。
- 提取的 `_ingest_before_reactive_compaction()` (engine_ingest.py:529) 是纯 sync durable transaction，两个方法共享，无重复逻辑。
- 提取的 `_finish_ingest()` (engine_ingest.py:578) 收口 promotion 与日志，两个方法共享。
- `dispatch.py:2499`: `_consume_worker_events` 循环已切换为 `await ingestor.ingest_async(...)`。
- 无剩余 `ingestor.ingest(` 调用在 `dayu/host/` 生产代码中。
- 测试中保留的 `.ingest()` 调用（test_engine_ingest_mapping.py:256 等约 30 处）均为非 reactive compaction 事件（FINAL_ANSWER、TOOL_RESULT_ACCEPTED 等），不会触发 RuntimeError。所有 CONTEXT_COMPACTION_REQUESTED 相关测试已切换为 `ingest_async`。

结论：API 拆分语义清晰，sync `ingest()` 的行为变更是对调用方的明确契约（docstring 已更新），无生产代码遗漏。

### 5-无缺陷-Promotion drain task 生命周期管理完整

对审查问题 #3 的逐项确认：

- **创建与追踪**: `wake_queue_promotion()` (dispatch.py:614-628) 在 `_promotion_drain_task is None or done()` 时通过 `asyncio.create_task` 创建，赋值给 `self._promotion_drain_task`。
- **per-item 异常处理**: `_promotion_drain_loop` (dispatch.py:1578-1621) 内层对每个 session_id 独立 try/except，捕获 RuntimeError（含 `_closed` 分支）和通用 Exception，均写日志后继续处理下一项。单 session 异常不会导致 drain loop 退出。
- **取消与 close**: `close()` (dispatch.py:1526-1529) 在 `_closed=True` 后 cancel `_promotion_drain_task` 并 await。`_promotion_drain_loop` 外层 catch CancelledError 后 re-raise，确保 asyncio 正确传播取消。
- **关闭后入队**: `wake_queue_promotion()` (dispatch.py:613-614) 先检查 `_closed`，关闭后抛出 RuntimeError，不入队也不创建新 task。
- **测试覆盖**:
  - `test_wake_queue_promotion_uses_tracked_async_promotion_task` (test_dispatch_scheduler.py:2052): 验证 sync wakeup → async promotion task → compact 完成 → attempt 创建。
  - `test_wake_queue_promotion_logs_promotion_task_exception` (test_dispatch_scheduler.py:2103): 验证 promotion 内异常被记录为 WARNING，task 继续存活。
  - `test_scheduler_close_cancels_tracked_promotion_task` (test_dispatch_scheduler.py:2140): 验证 close 取消并等待 promotion task 完成。

结论：promotion drain task 生命周期管理完整，close 后不会遗留 task（Finding 2 的 shutdown 竞态为已有 drain_loop 统一模式的低风险 tradeoff）。

### 6-无缺陷-`create_task` 所有权与清理

对审查问题 #4 的逐项确认：

| 位置 | task | 创建 | 追踪 | 取消 | 清理 |
|------|------|------|------|------|------|
| dispatch.py:603 | `_drain_task` | `wake_dispatch` | `self._drain_task` | `close()` cancel + await | ✓ |
| dispatch.py:626 | `_promotion_drain_task` | `wake_queue_promotion` | `self._promotion_drain_task` | `close()` cancel + await | ✓ |
| dispatch.py:1987 | `_consume_worker_events` | `_start_worker` | `self._active_tasks` set + `add_done_callback(discard)` | `close()` loop cancel + await | ✓ |
| local_proxy.py:208 | `_active_anext` | `__anext__` | `self._active_anext` | `close()` cancel + await | ✓ |
| engine/runners/openai/runner.py:630 | `response_task` | runner 内部 | 局部变量 | finally 块 cancel | ✓ |

`dayu/host` 内所有 `create_task` 均有明确的 owner、lifecycle tracker 和 cleanup path。`dayu/engine` 内的 `create_task` 在 runner 内部管理，不在本次 review scope。

结论：无孤儿 task 风险。

### 7-无缺陷-Budget 边界收紧不会破坏合理配置

对审查问题 #5 的逐项确认：

- `MIN_CONTEXT_HARD_THRESHOLD_TOKENS = 2` (context_policy.py:134) 是极端保守值。hard_threshold_tokens < 2 意味着 compact 后上下文预算仅剩 0 或 1 token，不具备 dispatch 条件。
- 显式传入 `hard_threshold_tokens >= 2`：通过校验。
- 自动计算 `hard_threshold_tokens = input_budget_tokens - minimum_protection_tokens`：校验 `>= 2`。仅当 `input_budget_tokens - minimum_protection_tokens < 2` 时拒绝。
- 实际配置场景：context_window_size=1000, reserved_output_tokens=100 → input_budget=900。需要 minimum_protection_tokens ≤ 898 才能使自动计算的 hard_threshold ≥ 2。任何生产配置都会远大于此边界。
- 最小可行配置示例：context_window_size=10, reserved_output_tokens=5 → input_budget=5。hard_threshold_tokens=2 需要 minimum_protection_tokens ≤ 3。仍然可行。
- 真正会被拒绝的配置：context_window_size=3, reserved_output_tokens=1, minimum_protection_tokens=1 → input_budget=2, hard_threshold=1 < 2 → ValueError。这种配置本身就不具备 compact 后 dispatch 的可能性。
- 测试覆盖: `test_budget_estimate_rejects_non_dispatchable_hard_threshold` (test_context_budget.py:228), `test_context_budget_policy_rejects_non_dispatchable_hard_threshold` (test_context_policy.py:54) 覆盖拒绝路径和接受边界。

结论：边界收紧是语义正确的防守，不会误伤任何合法生产配置。

### 8-未修复-低-`BudgetEstimate` 与 `ContextBudgetPolicy` 的 `hard_threshold_tokens` 校验存在语义重复

- **入口/函数**: `BudgetEstimate.__post_init__` → `ContextBudgetPolicy.__post_init__`
- **文件(行号)**: `dayu/host/context_budget.py:208-211` (BudgetEstimate), `dayu/host/context_policy.py:111-114` (ContextBudgetPolicy)
- **输入场景**: `hard_threshold_tokens=1` 的 `BudgetEstimate` 或 `ContextBudgetPolicy` 构造。
- **实际分支**: 两个 `__post_init__` 各自校验 `hard_threshold_tokens >= MIN_CONTEXT_HARD_THRESHOLD_TOKENS`。
- **预期行为**: 策略层把关即可；`BudgetEstimate` 是 `ContextBudgetPolicy` 的计算产物，其 hard_threshold_tokens 来自 policy 的 hard_threshold_tokens 字段（显式）或 `input_budget - minimum_protection`（自动计算）。如果 policy 层已拒绝 < 2 的值，BudgetEstimate 不会收到 < 2 的 hard_threshold_tokens（除非直接构造 BudgetEstimate 绕过 policy 校验）。
- **实际行为**: 两处校验提供了纵深防御——即使有人绕过 `ContextBudgetPolicy` 直接构造 `BudgetEstimate`，也会被拒绝。这不是 bug 而是防御性设计。
- **直接证据**: `context_budget.py:208-211` 和 `context_policy.py:111-114` 存在相同校验语义。
- **影响**: 无可观测负面影响。语义重复但方向一致，不会产生冲突。
- **建议改法和验证点**: 不需要修改。这是有意为之的纵深防御。
- **修复风险**: N/A
- **严重程度**: 低。不算缺陷，但作为 re-review 完整性记录。

## Open Questions

- 无。

## Residual Risk

1. **`_drain_loop` / `_promotion_drain_loop` 静默退出**: Finding 1 描述的风险在 diff 之前已存在。本 diff 新增的 `_promotion_drain_loop` 复用了相同模式，暴露面与之前版本相当。当前 per-item 异常捕获已覆盖几乎所有可预见故障，实际触发概率极低。建议后续单独 task 加固。
2. **`ingest()` sync API 语义变更**: `ingest()` 现在在遇到 reactive compaction 场景时抛出 `RuntimeError` 而非静默处理。所有已知内部调用方已适配，但对外部调用方（如果有）是 breaking change。README 和 docstring 已更新说明。
3. **`_promotion_drain_loop` 与 `_drain_loop` 异常处理模式差异**: `_drain_loop` 对通用 Exception 做 catch-all 不 re-raise（静默退出），`_promotion_drain_loop` 对通用 Exception 仅内层 per-item 捕获、外层仅 catch CancelledError。两种模式的行为差异在极端故障下表现不同，但当前都是保守安全侧。
4. **测试未覆盖 `_drain_loop` / `_promotion_drain_loop` 整体异常退出场景**: 现有测试覆盖了 per-item 异常（test_dispatch_scheduler.py:2103），但未覆盖外层循环因非预期异常退出的场景。考虑到触发概率，此项风险低。
5. **AGENTS.md/CLAUDE.md 与 code fix 混合 commit**: 文档变更（措辞收紧、删除具体示例、增加朴素接口约束）与 root cause fix（线程桥移除）无直接因果关系。混合在同一个 commit 中不造成正确性风险，但会降低 git history 的可追溯性——未来读者可能难以区分"约束文档更新"和"代码行为修复"的边界。从 project CLAUDE.md 的 commit 风格看，commits 通常按 feature slice 组织，混合在同一个 slice commit 中可以接受。

## Conclusion

**PASS**

线程桥移除核心修复完整到位，无隐形 sync-async bridge 残留。`ingest` / `ingest_async` 拆分语义清晰，所有生产代码调用方已适配。Promotion drain task 生命周期管理完整，create_task 所有权明确。Budget 边界收紧不会破坏合理配置。测试覆盖了 async retry、promotion task 生命周期、异常处理和 budget 边界拒绝路径。

发现的 2 个 finding（`_drain_loop` 静默退出、close 竞态丢 session_id）均为已有 `_drain_loop` 模式的一致性问题，非本 diff 引入的回归，不影响 ship/merge 决策。
