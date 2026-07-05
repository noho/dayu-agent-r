# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: commit `4723ec61` (accepted plan)
- Output file: `docs/reviews/wu-tools-cancel-01-slice1-code-review-mimo.md`
- Included scope: `4723ec61` 之后 workspace 的 uncommitted S1 implementation diff
- Excluded scope: 已提交的 plan gate 文档、`main` 上无关改动
- Parallel review coverage: 无

## Findings

### 01-未修复-中-terminate-then-kill 升级路径在 ToolRuntimeExecutor 层缺乏显式集成测试

- **入口/函数**: `ToolRuntimeExecutor._interrupt_capsule_after_wait(...)` / `ToolRuntimeExecutor._dispatch_tool_call_with_bounds(...)`
- **文件(行号)**: `dayu/host/tool_runtime.py:3100-3143`
- **输入场景**: process-backed capsule 工具执行中，用户触发 cancel 或 timeout，子进程忽略 SIGTERM
- **实际分支**: `_interrupt_capsule_after_wait` 调用 `terminate` → `terminate.supported=True, terminate.completed=False` → 调用 `kill`
- **预期行为**: plan S1 expected assertions 要求 "terminate path succeeds before kill when worker cooperates" 和 "hard kill path is exercised when terminate does not exit"。`tests/runtime/test_interruptible_process.py` 覆盖了 runtime helper 级别；`tests/host/test_toolruntime_executor.py:test_tool_runtime_process_backed_cancel_does_not_wait_for_natural_completion` 只验证 cancel 后不等自然结束、elapsed < 2s、callable 未被调用、governed failure 正确。该测试的 `_SleepingProcessTarget` 默认响应 SIGTERM（标准 `time.sleep` 行为），因此 terminate 成功，**kill 路径从未被触发**。
- **实际行为**: 没有测试用例在 ToolRuntimeExecutor 集成层验证 terminate 失败 → kill 升级路径。runtime helper 级测试已覆盖，但 executor 集成层缺失。
- **直接证据**: `tests/host/test_toolruntime_executor.py` 中 `_SleepingProcessTarget` 使用 `time.sleep()`，默认 SIGTERM 终止；无 `_IgnoreTerminateTarget` 等价物传入 `_ProcessCapsuleFactory`。
- **影响**: 若 S2 生产工具迁移中 process-backed capsule 遇到忽略 SIGTERM 的子进程，executor 层的 terminate → kill 升级逻辑未被集成测试锁定，回归风险中等。
- **建议改法和验证点**: 在 `test_toolruntime_executor.py` 中新增一个测试用例，使用忽略 SIGTERM 的 process target（类似 `tests/runtime/test_interruptible_process.py:_IgnoreTerminateTarget`），验证 cancel 后 executor 的 `_interrupt_capsule_after_wait` 正确走 terminate → kill 升级路径，且 elapsed 远小于自然结束时间。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 02-未修复-低-`_run_process_target` 捕获 `BaseException` 可能掩盖子进程真实退出信号

- **入口/函数**: `_run_process_target(target, result_queue)`
- **文件(行号)**: `dayu/runtime/interruptible_process.py:278-298`
- **输入场景**: 子进程目标执行时收到 SIGTERM/SIGINT 等信号
- **实际分支**: `except BaseException as exc` 捕获 `KeyboardInterrupt`、`SystemExit` 以及信号引发的异常，将它们转为 `_ProcessFailed` 消息放入队列
- **预期行为**: 子进程被 terminate 时，信号处理应让进程正常退出（exitcode 非零），而非被捕获并转为业务失败消息。当前 `BaseException` 捕获范围过宽，可能将 SIGTERM 引发的 `SystemExit` 或 `KeyboardInterrupt` 作为 `_ProcessFailed` 写入队列，掩盖真实的退出信号。
- **实际行为**: 子进程收到 SIGTERM 时，如果 Python 默认信号处理器抛出 `SystemExit`，该异常被 `BaseException` 捕获并转为 `_ProcessFailed(error_type="SystemExit", message="")`，放入队列。父进程读取后可能将其误判为业务失败而非进程被中止。
- **直接证据**: `dayu/runtime/interruptible_process.py:291-297` 使用 `except BaseException` 而非 `except Exception`。
- **影响**: 低。在当前 S1 测试中，`_SleepingTarget` 使用 `time.sleep()`，SIGTERM 默认终止进程而非抛异常，因此不会触发此路径。`_IgnoreTerminateTarget` 也使用 `signal.signal(signal.SIGTERM, signal.SIG_IGN)` 忽略信号。但在 S2 生产工具迁移中，如果目标函数内部有自定义信号处理，SIGTERM 可能导致 `SystemExit` 被捕获并误报为业务失败。
- **建议改法和验证点**: 考虑将 `except BaseException` 改为 `except Exception`，让 `SystemExit` 和 `KeyboardInterrupt` 自然传播，子进程以非零 exitcode 退出，父进程通过 `process_exited_without_result` 路径收口。或者保留 `BaseException` 但在消息中区分信号引发的退出。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- S1 不迁移生产 Doc/Fins/Web 工具。生产 blocking 路径仍需 S2 迁移到 process-backed 或 request-abort-capable async adapter 后才能关闭 #87。
- `thread_backed` 模式明确不承诺 OS thread 硬中断，测试已证明。S2 中 thread-backed 只能用于 cooperative、短耗时、read-only 且 late side effect 可接受的路径。
- `InterruptibleProcessHandle.close()` 中 `join_thread()` 等待 feeder 线程完成；在极少数情况下（如 pipe 异常），feeder 线程可能延迟退出，受 dispatch `_safe_close_worker_handle` 的 3s grace 限制。
- late result quarantine 在 ToolRuntime accept barrier 和 Engine ingest barrier 已有独立覆盖，S1 未新增专门的 process-backed late result 隔离测试。

## Verdict

**pass-with-findings**: 0 blocking findings, 2 non-blocking findings (1 中 severity, 1 低 severity)。S1 实现正确对齐 accepted plan，capsule 抽象语义正确，process-backed helper 层中立且类型安全，local worker on_cancel → close 路径可靠，dispatch bounded close 不跳过 lane release，未越界进入 S2 范围。tests 覆盖 plan S1 绝大部分 expected assertions，仅 terminate-then-kill 升级路径在 executor 集成层缺失显式测试。
