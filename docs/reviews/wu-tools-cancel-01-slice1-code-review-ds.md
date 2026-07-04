# Code Review — WU-TOOLS-CANCEL-01 Slice S1

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: accepted plan commit `4723ec61` (`gateflow: accept plan for WU-TOOLS-CANCEL-01`)
- Output file: `docs/reviews/wu-tools-cancel-01-slice1-code-review-ds.md`
- Included scope: uncommitted diff 相对 `4723ec61` 的 7 个文件（`dayu/host/tool_runtime.py`, `dayu/host/local_proxy.py`, `dayu/host/dispatch.py`, `dayu/runtime/interruptible_process.py`, `tests/host/test_active_cancel_dispatch.py`, `tests/host/test_local_proxy_engine_ingest.py`, `tests/host/test_toolruntime_executor.py`, `tests/runtime/test_interruptible_process.py`）
- Excluded scope: 已提交 plan gate markdown、`docs/host/issues-implementation-control.md` 的状态文字更新（非代码实现，仅总控元数据）
- Parallel review coverage: 无（单手 review）
- Review target: accepted plan `docs/host/wu-tools-cancel-01-tool-provider-interrupt-plan.md` S1 expected assertions + adversarial failure pass

## Findings

### F01-未修复-中-`_dispatch_tool_call_with_bounds` 外层 CancelledError 导致 capsule/capsule_task 资源泄漏

- **入口/函数**: `ToolRuntimeExecutor._dispatch_tool_call_with_bounds` → `wait_for_or_cancel`
- **文件(行号)**: `dayu/host/tool_runtime.py:3069-3073`
- **输入场景**: Host active cancel 触发 Engine runner 取消 → `ToolExecutor.execute()` task 被 cancel → CancelledError 在 `await wait_for_or_cancel(...)` 抛出
- **实际分支**: CancelledError 从 `wait_for_or_cancel` 透传，直接向上传播；`capsule_task`（仍在 event loop 中运行）和 `capsule`（未 close）均未清理
- **预期行为**: 外层 CancelledError 应触发 capsule interrupt/close 后传播，或至少保证 capsule 资源在函数退出前已关闭
- **实际行为**: `capsule_task = asyncio.create_task(capsule.run())` 创建的任务继续在事件循环中运行；对于 `ProcessBackedToolExecutionCapsule`，子进程继续运行且无人 terminate/kill，进程 handle、result queue、feeder thread 全部泄漏；对于 `AsyncDirectToolExecutionCapsule`，工具 callable 继续异步执行且无人消费结果
- **直接证据**:
  1. `wait_for_or_cancel` 文档明确声明"不拥有 pending task"（`dayu/runtime/cancellation.py:158`），不取消也不捕获 CancelledError
  2. `_dispatch_tool_call_with_bounds` 没有任何 try/except/finally 包裹 `wait_for_or_cancel` 调用来在 CancelledError 路径上清理 capsule（`dayu/host/tool_runtime.py:3064-3094`）
  3. 旧代码使用 `await_or_cancel_or_timeout`，其 `except asyncio.CancelledError` 块会 `await _cancel_task_and_wait(target_task)` 后再 re-raise（`dayu/runtime/cancellation.py:270-272`）；新代码丧失了这个保障
  4. `_execute_one` (`dayu/host/tool_runtime.py:2827-2829`) 和 `execute` (`dayu/host/tool_runtime.py:2740`) 均无 capsule cleanup 的 try/except
  5. 生产可达路径：用户 Esc → Host cancel → Engine runner task cancel → `ToolExecutor.execute()` task cancel → `_dispatch_tool_call_with_bounds` 收到 CancelledError
- **影响**: 资源泄漏（子进程、线程、队列），尤其 process_backed 路径是 S1 验证的核心非协作 cancel 机制，泄漏直接破坏 Esc interrupt 资源释放目标
- **建议改法和验证点**: 在 `_dispatch_tool_call_with_bounds` 中用 try/finally 确保无论何种 exit 路径 capsule 都被 close；或改为在 finally 中调用 `_interrupt_capsule_after_wait` 的 cleanup 子集（至少 close）。需要在 `_interrupt_capsule_after_wait` 中添加幂等保护（当前已通过 capsule.close() 的各自实现具备）。验证点：新增测试外层 task cancel `_dispatch_tool_call_with_bounds` 后 capsule 资源已释放，process_backed 子进程不会继续运行
- **修复风险（中）**: 需要重构 `_dispatch_tool_call_with_bounds` 的控制流，从当前的线性分支（WaitCompleted/WaitCancelled/WaitTimedOut）改为 try/finally 包围，确保 `WaitCompleted` 路径的 `await capsule.close()` 和 cancel/timeout 路径的 interrupt+close 都受 finally 保护。`WaitCompleted` 分支当前在 finally 中 close 后再 return（`dayu/host/tool_runtime.py:3082-3085`），这部分语义需要保留
- **严重程度（中）**

### F02-未修复-低-`_DefaultLocalWorkerHandle.on_cancel` 后台 close task 异常静默

- **入口/函数**: `_DefaultLocalWorkerHandle.on_cancel`
- **文件(行号)**: `dayu/host/local_proxy.py:137-170`
- **输入场景**: Host active cancel 触发 `on_cancel` → `asyncio.create_task(self.close())` 创建后台 task → `self.close()` 执行过程中抛出非预期异常
- **实际分支**: 异常存储在 asyncio Task 对象中，task 引用保存在 `self._cancel_close_task`；下次 `on_cancel` 调用会覆盖引用，旧 task 被 GC 时 asyncio 日志输出 "Task exception was never retrieved"
- **预期行为**: 后台 close task 异常应至少以 WARNING 级别记录，或在 task 上通过 `add_done_callback` 注册异常日志
- **实际行为**: 异常可能延迟到 GC 时才以 asyncio 默认格式输出，缺乏结构化上下文（local_worker_id、cancel reason 等）
- **直接证据**: `asyncio.create_task(self.close())` 的返回值存于 `self._cancel_close_task` 但从未被 await 或注册 done callback（`dayu/host/local_proxy.py:156-157`）
- **影响**: 调试困难——close 路径的异常难以关联到具体 worker/cancel reason
- **建议改法和验证点**: 在创建 task 后调用 `self._cancel_close_task.add_done_callback(_log_close_task_exception)`，在 callback 中用 `task.exception()` 检查并以 WARNING 级别记录。验证点：monkeypatch close 使其 raise，确认日志中有 local_worker_id + exception 信息
- **修复风险（低）**: 纯观测性改动，不改变执行语义
- **严重程度（低）**

### F03-未修复-低-`_interrupt_capsule_after_wait` 中 `capsule.close()` 异常会吞掉 governed failure 返回

- **入口/函数**: `_interrupt_capsule_after_wait`
- **文件(行号)**: `dayu/host/tool_runtime.py:3114-3117`
- **输入场景**: cancel/timeout 触发 `_interrupt_capsule_after_wait` → terminate/kill 成功 → `await capsule.close()` 抛出非预期异常
- **实际分支**: 异常从 `_interrupt_capsule_after_wait` 向上传播 → `_dispatch_tool_call_with_bounds` 向上传播 → `_execute_one` 向上传播 → 调用方收到异常而非 governed failure outcome
- **预期行为**: close failure 应记录 diagnostic，但不阻止 cancel/timeout 的 governed failure outcome 正确返回
- **实际行为**: 如果 close 失败（例如 `InterruptibleProcessHandle.close()` 中 `join_thread` 因未知原因抛异常），完整的 cancel/timeout interrupt 成果（process 已终止）被丢弃，Engine 收到的是异常而非结构化 outcome
- **直接证据**: `await capsule.close()` 位于 `_interrupt_capsule_after_wait` 末尾（`dayu/host/tool_runtime.py:3117`），无 try/except 包裹；调用方 `_dispatch_tool_call_with_bounds` 在 cancel/timeout 分支中先调用 `_interrupt_capsule_after_wait` 再返回 governed failure（`dayu/host/tool_runtime.py:3089-3102`），若前者抛异常则后者不会执行
- **影响**: close 资源释放异常可能遮蔽已完成的 interrupt 成果，使 Engine 收到未预期异常而非 cancel/timeout outcome
- **建议改法和验证点**: 在 `_interrupt_capsule_after_wait` 内将 `await capsule.close()` 包裹在 try/except 中，异常以 WARNING 记录但不阻止正常 return。验证点：monkeypatch capsule.close 使其 raise，确认 cancel/timeout 仍正确返回 governed failure
- **修复风险（低）**: 纯防御性改动
- **严重程度（低）**

## Open Questions

1. **F01 是否在 S1 现有测试中被触发？** 当前测试 `test_tool_runtime_process_backed_cancel_does_not_wait_for_natural_completion` 是通过 token.cancel() 触发 cancel，不是通过外层 task.cancel()。outer task cancel 路径未被覆盖。需要新增测试。

2. **`InterruptibleProcessHandle.close()` 在 `_started=False` 时 queue 资源是否泄漏？** 经核查，`close()` 中 `_result_queue.close()` 和 `join_thread()` 不受 `_started` 条件控制，始终执行。确认无泄漏。

3. **`tests/host/test_local_proxy_engine_ingest.py` 的修改是否为 scope finding？** 审查结论：该文件不在 S1 plan "Exact allowed changes" 的 explicit file list 中（plan 列出 `tests/host/test_public_cancel_smoke.py` or focused equivalent），但新增测试 `test_default_local_worker_cancel_closes_active_event_stream` 直接验证 S1 核心行为（local worker `on_cancel` 关闭 event stream），属于 focused equivalent，不构成 scope overrun。但需要注意：该文件同时被 `test_local_proxy_engine_ingest.py` 已有测试覆盖 S1 未改动路径，本次新增测试合理。

## Residual Risk

1. **`thread_backed` OS 线程泄漏**: `ThreadBackedToolExecutionCapsule.close()` 取消 wrapper task 后底层 OS thread 可能继续运行到自然结束。这是 plan 明确接受的设计取舍——thread_backed 不承诺 hard interrupt。测试 `test_thread_backed_capsule_does_not_claim_thread_termination` 正确断言了此行为。风险在于：如果 S2 错误地将 thread_backed 用于生产路径（违反 plan Section 7.1 表格），cancel 后 OS 线程仍运行并可能产生外部副作用。S2 review 必须严格检查无 thread_backed 进入生产非协作 cancel 路径。

2. **`InterruptibleProcessHandle.wait()` 忙等轮询**: 当前 `wait()` 以 `asyncio.sleep(0.02)` 固定间隔轮询。在进程刚启动或即将退出时，最多延迟 20ms 检测退出。对 production-grade tool execution（通常秒级），此延迟可忽略。但如果未来将此 helper 用于更低延迟场景，需重新评估。

3. **F01 修复后需验证现有测试不变**: F01 的 try/finally 重构涉及 `_dispatch_tool_call_with_bounds` 控制流变更，需确保现有 63 个 focused tests（58 host + 3 runtime + 2 local proxy cancel）全部通过且无行为语义退化。

4. **无 outer task cancel 测试覆盖**: 当前所有 capsule cancel 测试通过 token.cancel() 触发，无测试覆盖外层 task cancel（CancelledError 从 `asyncio.wait` 透传）路径。若 F01 被接受，修复后必须补 outer task cancel + process_backed cleanup 的验证用例。
