# WU-TOOLS-CANCEL-01 Slice S1 Re-Review — AgentDS

## Scope

- Mode: current changes (re-review of fix gate)
- Branch: `phase/wu-tools-cancel-01`
- Base: accepted plan commit `4723ec61`
- Controller adjudication: `docs/reviews/wu-tools-cancel-01-slice1-code-review-controller-adjudication.md`
- Fix artifact under review: `docs/reviews/wu-tools-cancel-01-slice1-fix-codex.md`
- Re-review artifact path: `docs/reviews/wu-tools-cancel-01-slice1-rereview-ds.md`
- Included scope: fix diff over the original S1 implementation — `dayu/host/tool_runtime.py`, `dayu/host/local_proxy.py`, `dayu/runtime/interruptible_process.py`, `dayu/host/dispatch.py`, 以及对应测试文件
- Excluded scope: 已提交 plan gate markdown、总控元数据、前序 review/fix artifact（仅作为输入参考）
- Parallel review coverage: 无（单手 re-review）

## Verdict

**pass** — 0 blocking findings。所有 5 项 controller accepted findings 已正确关闭。无新增 material finding。Tests 全部通过，pyright 零错误，无 S1 scope 扩张、无 public contract/schema/EventLog/Engine 变更、无 S2 生产工具迁移。

## Closure Matrix

| Finding | Source | Verdict | Evidence |
|---|---|---|---|
| DS F01 outer `CancelledError` can leak capsule/capsule task | AgentDS | **CLOSED** | `_dispatch_tool_call_with_bounds` 增加 `except asyncio.CancelledError` 分支（`tool_runtime.py:3076-3082`），调用 `_interrupt_capsule_after_wait` 后再 re-raise。新增测试 `test_tool_runtime_outer_task_cancel_closes_process_capsule`（`test_toolruntime_executor.py:1465`）验证 outer task cancel → terminate failed → kill completed → capsule closed → callable 未调用。 |
| MiMo 01 executor terminate→kill escalation integration test missing | AgentMiMo | **CLOSED** | 新增 `test_tool_runtime_process_backed_cancel_kills_when_terminate_is_ignored`（`test_toolruntime_executor.py:1500`），使用忽略 SIGTERM 的 `_IgnoreTerminateProcessTarget`，在 ToolRuntime executor 层验证 token.cancel() → terminate supported 但未 completed → kill supported 且 completed → governed failure `tool_runtime_cancelled`。 |
| DS F02 `on_cancel` background close task exception not logged | AgentDS | **CLOSED** | `_DefaultLocalWorkerHandle.on_cancel`（`local_proxy.py:159-165`）添加 `add_done_callback` 注册 `_log_cancel_close_task_exception`。helper 函数（`local_proxy.py:193-218`）在 `task.result()` 抛 `Exception` 时以 WARNING 记录 `local_worker_id`、`reason`、`error_type`。新增测试 `test_default_local_worker_cancel_logs_background_close_failure`（`test_local_proxy_engine_ingest.py:321`）monkeypatch close 使其 raise，验证日志包含 `cancel_close_failed`、worker_id、reason、error_type。 |
| DS F03 `capsule.close()` exception hides governed cancel/timeout outcome | AgentDS | **CLOSED** | `_interrupt_capsule_after_wait` 中 `await capsule.close()` 包裹在 try/except Exception 中（`tool_runtime.py:3134-3148`），异常以 WARNING 记录 `capsule_close_failed` + `session_id`/`run_id`/`attempt_id`/`execution_id`/`mode`/`reason`/`error_type`，不阻止正常 return。新增测试 `test_tool_runtime_interrupt_close_failure_keeps_governed_cancel_outcome`（`test_toolruntime_executor.py:1539`）使用 `_CloseFailingCapsuleFactory`（close 抛 RuntimeError），验证 governed cancel 仍正确返回 + `capsule_close_failed` 日志存在。 |
| MiMo 02 `_run_process_target` catches `BaseException` | AgentMiMo | **CLOSED** | `_run_process_target`（`interruptible_process.py:291`）改为 `except Exception`，`SystemExit` / `KeyboardInterrupt` 自然传播使子进程以非零 exitcode 退出，父进程通过 `process_exited_without_result` 收口。 |

## New Findings

未发现新增实质性问题。以下为 fix 实现中的防御性检查点，均已正确处置：

1. **`_interrupt_capsule_after_wait` 的防御性足够**：`request_interrupt`（ProcessBacked 为 no-op）、`terminate`/`kill`（best-effort 返回结果不抛异常）、`capsule_task.cancel()` + await（捕获 CancelledError）、`capsule.close()`（try/except with logging）——其中 terminate/kill 委托给 `InterruptibleProcessHandle`，该 handle 在 `_require_started()` 失败时会抛 `RuntimeError`，但正常执行路径中 `capsule.run()` 在首个 `await` 前已同步调用 `self._handle.start()`，因此 `_started` 已在 `asyncio.create_task(capsule.run())` 的第一个 event loop yield 前设为 True。

2. **`_safe_close_worker_handle` 3s grace timeout 不阻塞 lane release**：各调用点（`dispatch.py:2515`, `3193`, `3911`）中 `_safe_close_worker_handle` 和 `_safe_release_lane_token` 是顺序调用，close 超时仅记录 warning 后 return，lane token 始终在之后释放。

3. **`_log_cancel_close_task_exception` 的 except 顺序正确**：先 `except asyncio.CancelledError` 静默返回，再 `except Exception` 记录 warning。Python 3.11+ 中 `CancelledError` 继承 `BaseException`，此顺序可防止 CancelledError 被 Exception 误捕获。

## Verification

- `pytest tests/host/test_toolruntime_executor.py tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py -q`: **61 passed**
- `pytest tests/runtime/test_interruptible_process.py tests/host/test_local_proxy_engine_ingest.py -q`: **11 passed**
- `pytest tests/runtime/test_import_boundary.py tests/host/test_import_boundary.py tests/host/test_package_exports.py -q`: **39 passed**
- `pyright`: **0 errors, 0 warnings, 0 informations**
- `git diff 4723ec61 --stat`: 仅涉及 `dayu/host/dispatch.py`, `dayu/host/local_proxy.py`, `dayu/host/tool_runtime.py`, `docs/host/issues-implementation-control.md`, 及对应测试
- `git diff 4723ec61 --name-only -- dayu/contracts/ dayu/engine/`: 无变更
- untracked 文件仅 `dayu/runtime/interruptible_process.py`（新 runtime helper，S1 预期）和 `tests/runtime/test_interruptible_process.py`（对应测试）

## S1 Scope Boundary Check

| 检查项 | 结果 |
|---|---|
| 新增 public contract/schema | 否 — `dayu/contracts/` 无变更 |
| 变更 EventLog event type | 否 |
| 变更 Engine contract | 否 — `dayu/engine/` 无变更 |
| S2 生产工具迁移（Doc/Fins/Web） | 否 — 无任何 production tool adapter 变更 |
| `thread_backed` 进入生产 cancel 路径 | 否 — 仍仅用于测试和内部非关键路径 |
| `dayu.runtime` 反向依赖上层 | 否 — `interruptible_process.py` 仅依赖 `dayu.contracts.json_value` 和 stdlib |
| 新增 public Host cancel API | 否 — 仅内部 capsule/interrupt 机制 |

## Residual Risk

1. **极早 CancelledError 与 `_require_started()` 的边界交互**：若 outer execute task 在 `capsule.run()` 首个 await yield 前被取消（即 `_handle.start()` 尚未执行），`_interrupt_capsule_after_wait` 中 `capsule.terminate()` → `_require_started()` 会抛 `RuntimeError`，导致 `CancelledError` 被 RuntimeError 替代。此场景在当前生产路径不可达（Host cancel 传播需要完整 Engine runner task 生命周期），仅在合成测试中可能出现。若未来外层取消时机提前，建议在 `_interrupt_capsule_after_wait` 开头对 capsule 状态做防御性检查或在最外层兜底 catch。

2. **ProcessBacked capsule terminate/kill 未单独捕获 handle 层异常**：`_interrupt_capsule_after_wait` 调用 `capsule.terminate()` / `capsule.kill()` 后直接进入 `capsule_task.cancel()` 和 `capsule.close()`。如果 terminate/kill 因非预期原因抛异常（如 multiprocessing internal error），后续 cleanup 会被跳过。当前 terminate/kill 实现均 best-effort 且返回 `ToolInterruptStepResult` 而非抛异常，实际风险极低。

3. **S2 迁移风险不变**：S1 仍不迁移 production Doc/Fins/Web 工具到 process-backed 或 request-abort-capable async adapter，#87 closeout 仍需 S2。

## Open Questions

无。
