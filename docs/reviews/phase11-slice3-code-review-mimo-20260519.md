# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase-11-recovery
- Base: 2e89558 (accepted Slice 2)
- Output file: docs/reviews/phase11-slice3-code-review-mimo-20260519.md
- Included scope: `dayu/host/recovery.py`, `dayu/host/dispatch.py`, `dayu/host/open_host.py`, `dayu/host/durable/run_transition.py`, `tests/host/test_recovery_dispatch.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_open_host_runtime.py`, `dayu/host/README.md`, `tests/README.md`, `docs/host/implementation-control.md`
- Excluded scope: `dayu/engine/**`, `dayu/service/**`, `dayu/fins/**`, public API surface
- Parallel review coverage: 无

## Review Checklist Verification

逐项核对用户指定的 review focus：

1. **RECOVERING dispatch creates new Attempt/execution/dispatch in one transaction**: `start_recovery_run_with_starting_attempt_in_transaction` 在一个 write transaction 内完成 `RUN_STARTED` append、Run status update、`ATTEMPT_STARTED` append、Attempt insert、dispatch record insert。`_close_positive_orphan` 在同一 scan transaction 内串联 orphan closeout 与 recovery dispatch。验证通过。
2. **Wakes scheduler after commit**: `scan()` 在 `transaction_runner.run_write(operation)` 返回后才遍历 `result.pending_dispatches` 调用 `dispatch_wakeup_port.wake_dispatch()`。验证通过。
3. **Recovery does not call WorkerProxy**: recovery 只创建 PENDING dispatch record 并 wake scheduler，不直接调用 worker factory 或 WorkerProxy。验证通过。
4. **open_host runs scan before ready**: `open_host.__aenter__` 在 scheduler 注册后、`_LOGGER.info("host.open.ready")` 前执行 `StartupRecoveryScanner(...).scan()`。验证通过。
5. **RunInputBuilder uses canonical EventLog/payload descriptors not old Attempt/projection/memory**: `test_recovery_attempt_rebuilds_current_prompt_from_same_run_eventlog_descriptor` 验证 recovery Attempt 从同一 Run 的 `USER_INPUT_ACCEPTED` EventLog descriptor 重建消息，不从旧 Attempt snapshot 读取。验证通过。
6. **Old execution late event rejected**: `test_late_old_execution_event_after_recovery_dispatch_is_rejected` 验证旧 `execution_id` 的 terminal event 被 `EngineEventIngestor` reject，不写入 `RUN_SUCCEEDED`。验证通过。
7. **No RECOVERING cancel**: diff 不包含 `cancel_run` 或 `cancel_session_runs` 对 RECOVERING 状态的处理，与 Slice 4 计划一致。验证通过。
8. **No Engine/public API/schema changes**: diff 不修改 `dayu/engine/**`，不新增 public API 或 schema 字段。验证通过。
9. **Docs/tests/pyright**: 39 tests passed, pyright 0 errors。`dayu/host/README.md` 和 `tests/README.md` 已同步更新。验证通过。
10. **Slice 2 tracked item lose_recovering_run_in_transaction precondition**: 该函数检查 `run.status == RECOVERING` 和 `run.current_attempt_id == source_attempt_id`。调用方 `_classify_recovering` 从同一 transaction 的 `read_non_terminal_runs` 读取 `run.current_attempt_id` 并透传。在 Slice 3 recovery dispatch 后 run 回到 RUNNING 状态，后续 scan 走 `_classify_active_or_cancelling` 路径，不进入 `lose_recovering_run_in_transaction`。RECOVERING + count >= limit 路径中，`current_attempt_id` 仍指向 closeout 设置的 source attempt，CAS 前置条件成立。验证通过。

## Findings

### 001-未修复-低-模块 docstring 与 Slice 3 新增行为不一致

- **入口/函数**: `dayu/host/recovery.py` 模块 docstring
- **文件(行号)**: `dayu/host/recovery.py:1-7`
- **输入场景**: 阅读模块 docstring 了解模块职责边界
- **实际分支**: 模块 docstring 声称"不创建新的 recovery Attempt"
- **预期行为**: docstring 应反映模块当前职责，包括创建 recovery Attempt / execution / dispatch record
- **实际行为**: Slice 3 新增 `_start_recovery_dispatch_or_ready` 方法，通过 `start_recovery_run_with_starting_attempt_in_transaction` 创建 recovery Attempt、execution 和 dispatch record，但模块 docstring 未更新
- **直接证据**: `dayu/host/recovery.py:6` 写"不创建新的 recovery Attempt"，但 `dayu/host/recovery.py:490-509` 调用 `start_recovery_run_with_starting_attempt_in_transaction` 创建新 Attempt
- **影响**: 开发者阅读 docstring 会误判模块职责边界；不影响运行时行为
- **建议改法和验证点**: 更新模块 docstring，将"不创建新的 recovery Attempt"改为描述当前职责，包括 startup orphan closeout、recovery dispatch 创建、scheduler wake
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- `RECOVERING` public cancel 和 `cancel_session_runs` 支持归属 Slice 4，当前未实现。
- 多进程 harness 和 runtime lane hardening 归属 Slice 5，当前未实现。
- Startup recovery 仍依赖 Slice 1 positive orphan proof 语义；heartbeat stale 单独不构成 proof。
- Recovery dispatch limit 基于 canonical EventLog `RUN_STARTED(start_reason=recovery)` 计数，未引入新 schema。
- `start_recovering_run_row` 将 RECOVERING 转回 RUNNING（与 reactive compaction recovery 一致），但 README 中 `RECOVERING` 状态描述仅覆盖"正在创建新 Attempt"的瞬态语义，未说明 recovery dispatch 成功后 run 回到 RUNNING 的完整生命周期。此为文档精度问题，不影响正确性。
