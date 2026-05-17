# P9.5 S10 Code Review

日期：2026-05-17
审查 Agent：AgentMiMo
审查范围：当前工作区未提交 S10 diff

## 审查文件

- `dayu/host/dispatch.py`
- `dayu/host/waiting.py`
- `dayu/host/README.md`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_wait_cancel_late_result.py`

## 设计真源对齐

- 设计真源：`docs/host/design.md`
- 总控真源：`docs/host/implementation-control.md` §P9.5 S10 范围
- 实现 artifact：`docs/reviews/p9-5-s10-dispatch-runinput-non-recovery-cleanup-implementation-20260517.md`

## S10 边界检查

| 边界约束 | 是否违反 | 证据 |
|---|---|---|
| 不得夹带 Phase 11 recovery | 否 | 无 recovery 逻辑引入 |
| 不得夹带 RECOVERING dispatch | 否 | 无 RECOVERING 状态变更 |
| 不得夹带 orphan proof | 否 | 无 orphan 检测逻辑 |
| 不得夹带 RemoteProxy | 否 | 无远程执行变更 |
| 不得变更状态机语义 | 否 | 改动仅限 observability 与 catch-up 顺序 |
| lane token 只表示 runtime capacity claim | 否 | lane token 语义未变更 |
| late reject 只保留 bounded diagnostic / public rejection | 是 | `_LateRejectResult` 路径不触发 catch-up、不创建 resume Attempt |
| late reject 不得写 canonical tool fact | 否 | `_reject_late_result` 只写 `WAIT_LATE_RESULT_REJECTED` diagnostic event |
| late reject 不得推进 Run / 创建 resume Attempt | 否 | 测试断言无 `RESUME_REQUESTED` / `ATTEMPT_STARTED` 事件 |

## 验证结果

- `pytest tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py`：65 passed
- `python -m pyright dayu/host tests/host`：0 errors, 0 warnings, 0 informations
- `git diff --check`：通过，无输出

## Findings

### Finding 1: `_drain_loop` CancelledError 日志区分依赖 `self._closed` 时序

- 入口/函数：`_drain_loop` / `dispatch.py:520-526`
- 文件行号：`dayu/host/dispatch.py:520-526`
- 输入场景：`close()` 设置 `self._closed = True` 后取消 drain task
- 实际行为：CancelledError handler 使用 `self._closed` 区分 close-triggered 与 external cancellation
- 预期行为：正确区分两种取消来源
- 直接证据：`close()` 方法先设置 `self._closed = True`，再调用 `task.cancel()`；`_drain_loop` 的 CancelledError handler 读取 `self._closed` 选择日志模板
- 影响：正常 close 路径时序正确；极端情况下若 task 在 `close()` 设置 `_closed` 前被外部取消，会误记为 "externally"，但此场景在当前 scheduler lifecycle 中不实际发生
- 建议验证点：N/A（当前设计下 `close()` 是唯一取消 drain task 的入口）
- 严重程度：**info**（设计正确，日志区分合理）

### Finding 2: `_drain_loop` 异常退出后不重新启动

- 入口/函数：`_drain_loop` / `dispatch.py:528-534`
- 文件行号：`dayu/host/dispatch.py:528-534`
- 输入场景：`drain_once()` 抛出非 CancelledError 异常
- 实际行为：记录 warning 日志后 `_drain_loop` 正常返回，不重新启动
- 预期行为：implementation artifact 明确说明 "行为保持 logs only"，异常后是否重启由 scheduler lifecycle 负责
- 直接证据：`_drain_loop` 的 `except Exception` 分支只记录日志，不重启；implementation artifact §残余风险 第一条
- 影响：`drain_once()` 的单次异常不会导致 drain loop 重启；若 scheduler 需要持续运行，依赖外部 lifecycle 管理
- 建议验证点：确认 scheduler 的 `_drain_task` 生命周期管理是否覆盖异常后重启需求（当前不在 S10 范围）
- 严重程度：**info**（设计意图明确，非 S10 scope）

### Finding 3: `resolve_wait` catch-up 重排后，late rejection 路径的 projection 一致性

- 入口/函数：`resolve_wait` / `waiting.py:591-597`
- 文件行号：`dayu/host/waiting.py:591-597`
- 输入场景：cancelled wait 收到 late result
- 实际行为：`_LateRejectResult` 路径跳过 `catch_up_projection_best_effort`，直接抛出 `HostApiError`
- 预期行为：late rejection 只写 diagnostic，不触发 projection catch-up
- 直接证据：修改后的 `resolve_wait` 在 `_LateRejectResult` 检查前未调用 catch-up；测试 `test_late_result_after_cancel_writes_bounded_diagnostic` 断言 `projection.calls == 0`
- 影响：如果调用方依赖 rejection 后立即刷新 projection，需要通过后续成功 command 或显式 repair/catch-up 获得一致 read model
- 建议验证点：implementation artifact §残余风险 第三条已明确说明
- 严重程度：**low**（设计决策，非 bug）

## 测试覆盖分析

| 测试场景 | 覆盖状态 | 测试文件 |
|---|---|---|
| drain loop 空队列 sleep 日志 | 已覆盖 | `test_drain_loop_logs_empty_sleep_and_close` |
| drain loop close 取消日志 | 已覆盖 | `test_drain_loop_logs_empty_sleep_and_close` |
| drain loop 意外异常日志 | 已覆盖（既有） | `test_drain_loop_logs_unexpected_exception` |
| lane acquire 后 pre-accept cancel race | 已覆盖 | `test_cancel_race_after_lane_acquire_releases_lane_without_worker` |
| worker stream exception 资源释放 | 已覆盖（增强） | `test_worker_stream_exception_closes_run_lost_from_scheduler` |
| RunInputBuilder stale snapshot identity | 已覆盖 | `test_current_facts_reject_stale_snapshot_identity` (3 参数化) |
| late result rejection 不触发 catch-up | 已覆盖 | `test_late_result_after_cancel_writes_bounded_diagnostic` |
| late result rejection 不创建 resume Attempt | 已覆盖 | `test_late_result_after_cancel_writes_bounded_diagnostic` |
| late result rejection 不写 canonical fact | 已覆盖 | `test_late_result_after_cancel_writes_bounded_diagnostic` |

## README 同步检查

- `dayu/host/README.md:75`：新增 "不创建 resume Attempt，不触发 projection catch-up" 描述，与实现一致
- `dayu/host/README.md:121`：将 "与 `resolve_wait` 会在" 改为 "与成功的 `resolve_wait` 会在"，准确反映 catch-up 仅在成功 resolve 后触发
- 无越界描述，无遗漏行为说明

## 残余风险

1. `_drain_loop` observability 只记录日志，不改变后台任务重启或异常恢复策略
2. late rejection 后 projection 不立即 catch-up，调用方需通过后续成功 command 或显式 repair 获得一致 read model
3. lane token 语义未变更，仍为 runtime capacity cleanup，不提升为 Host ownership / fencing truth

## 结论

**通过**。0 blocking findings，3 info/low findings（均为设计意图确认，非 bug）。实现严格对齐 S10 范围，测试覆盖充分，README 同步正确。
