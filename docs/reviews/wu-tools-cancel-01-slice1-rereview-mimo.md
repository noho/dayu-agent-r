# WU-TOOLS-CANCEL-01 Slice S1 Re-Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: accepted plan commit `4723ec61`
- Output file: `docs/reviews/wu-tools-cancel-01-slice1-rereview-mimo.md`
- Included scope: `4723ec61` 之后 workspace 的 uncommitted S1 implementation + fix diff
- Excluded scope: 已提交 plan gate 文档、`main` 上无关改动
- Parallel review coverage: 无

## Verdict

**pass**

## Blocking Findings Count

**0**

## Closure Matrix

| Finding | Source | Decision | Closure Status | Evidence |
|---|---|---|---|---|
| DS F01 outer `CancelledError` cleanup | AgentDS | accepted, blocking | ✅ closed | `dayu/host/tool_runtime.py:3076-3082` now catches `asyncio.CancelledError`, calls `_interrupt_capsule_after_wait(...)`, then re-raises. Test `test_tool_runtime_outer_task_cancel_closes_process_capsule` (line 1465) proves: outer task cancel → terminate (supported, not completed) → kill (supported, completed) → close called (1 time). Process-backed capsule with `_IgnoreTerminateProcessTarget` correctly escalates. |
| MiMo 01 executor terminate→kill integration test | AgentMiMo | accepted, non-blocking | ✅ closed | Test `test_tool_runtime_process_backed_cancel_kills_when_terminate_is_ignored` (line 1500) uses `_IgnoreTerminateProcessTarget(sleep_seconds=5.0)` via `_ObservedProcessCapsuleFactory`. Asserts: terminate.supported=True, terminate.completed=False, kill.supported=True, kill.completed=True. ToolRuntime-level path proves kill escalation, not just runtime helper. |
| DS F02 local worker background close task exception logging | AgentDS | accepted, non-blocking | ✅ closed | `dayu/host/local_proxy.py:159-165` attaches `add_done_callback(partial(_log_cancel_close_task_exception, local_worker_id=..., reason=...))`. Callback at line 193-219 logs `host.local_proxy.cancel_close_failed` with `local_worker_id`, `reason`, `error_type`. Test `test_default_local_worker_cancel_logs_background_close_failure` (line 321) asserts: log contains `host.local_proxy.cancel_close_failed`, `local_worker_id`, `reason=test_cancel_reason`, `error_type=RuntimeError`. |
| DS F03 capsule.close failure masks governed outcome | AgentDS | accepted, non-blocking | ✅ closed | `dayu/host/tool_runtime.py:3134-3148` wraps `await capsule.close()` in try/except, logs warning with session/run/attempt/execution ids, mode, reason, error_type. Test `test_tool_runtime_interrupt_close_failure_keeps_governed_cancel_outcome` (line 1539) uses `_CloseFailingCapsuleFactory`, asserts: cancel still returns `ToolFailedOutcome` with `hint="tool_runtime_cancelled"`, log contains `capsule_close_failed` and `error_type=RuntimeError`. |
| MiMo 02 `_run_process_target` catches `BaseException` | AgentMiMo | accepted, low-priority | ✅ closed | `dayu/runtime/interruptible_process.py:291` changed from `except BaseException` to `except Exception`. `SystemExit` and `KeyboardInterrupt` now propagate naturally; child process exits with non-zero exitcode, parent receives `process_exited_without_result` path. |

## New Findings

未发现实质性问题。

## Residual Risks

1. **S2 生产工具迁移未完成**: S1 不迁移 Doc/Fins/Web 生产工具到 process-backed 或 request-abort-capable adapter。生产 blocking 路径仍需 S2 迁移后才能关闭 #87。这是 plan 明确接受的范围限制。

2. **thread_backed 不承诺 OS thread 硬中断**: 测试 `test_thread_backed_capsule_does_not_claim_thread_termination` 正确断言 terminate/kill 均不支持。S2 必须严格检查无 thread_backed 进入生产非协作 cancel 路径。

3. **process-backed 测试依赖本地进程性能**: 新增的 executor hard-kill 测试等待子进程安装 SIGTERM ignore handler 后才触发 cancel。等待时间 0.8s 受本地性能影响，但已有 timeout 保护（2.0s），风险可控。

4. **late result quarantine 无专门测试**: late result 在 ToolRuntime accept barrier 和 Engine ingest barrier 已有独立覆盖，S1 未新增 process-backed late result 隔离测试。现有 barrier 已足够。

## Scope Compliance

- ✅ 无公共 contract/schema/EventLog/Engine 变更
- ✅ 无 S2 生产工具迁移
- ✅ 仅修改 S1 plan 允许的文件：`dayu/host/tool_runtime.py`, `dayu/host/local_proxy.py`, `dayu/host/dispatch.py`, `dayu/runtime/interruptible_process.py`, 对应测试文件
- ✅ 所有 61 个 S1 测试通过
- ✅ pyright 0 errors, 0 warnings

## Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py -q`
  - Result: `61 passed in 3.80s`
- `source .venv/bin/activate && pytest tests/host/test_local_proxy_engine_ingest.py -q`
  - Result: `8 passed in 0.28s`
- `source .venv/bin/activate && pytest tests/runtime/test_interruptible_process.py -q`
  - Result: `3 passed in 0.86s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`

## Conclusion

所有 5 个 accepted findings 已正确关闭，修复实现与证据一致，测试覆盖充分。S1 实现符合 accepted plan，无 scope 扩张，无 blocking findings。建议进入 slice acceptance gate。
