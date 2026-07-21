# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 4 — AgentMiMo Re-Review

- Reviewer: AgentMiMo
- Date: 2026-07-22T03:22:41
- Base: `24efe9bd` (accepted Slice 3)
- Branch: `phaseflow/wu-host-session-event-delivery-01`
- Re-review gate: `code-rereview-slice-4`
- Controller adjudication: `docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-controller-adjudication.md`
- Codex fix artifact: `docs/reviews/wu-host-session-event-delivery-01-slice4-fix-codex.md`
- 首次 review artifact: `docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-mimo.md`

## Verdict

**PASS**

## Accepted Finding Closure Status

### S4-CR-F01 — 已关闭（coverage >= 80%）

- 验证命令：`COVERAGE_FILE=workspace/tmp/.coverage-rereview-s4-session-execution pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py --cov=dayu.cli.session_execution --cov-report=term-missing --cov-fail-under=80 -q`
- 结果：`432 statements / 84 miss / 80.56%`，通过 `>=80%` gate ✓
- 新增测试 `test_prompt_terminal_surfaces_display_close_failure_from_caller_lifecycle` 断言 display close failure 由 CLI lifecycle owner 原 identity 传播、renderer 与 watcher 各关闭一次且不发 Host cancel
- 无无业务断言的覆盖率夹具

### S4-CR-F02 — 已关闭（finish-thinking race done barrier）

- 代码验证：`session_execution.py:965`（prompt path）和 `session_execution.py:1309`（interactive path）均在 `finish_thinking_display()` 返回后、cancel 前检查 `submit_task.done()`；已自然完成时直接 `return await submit_task`
- 测试验证：`test_prompt_cancel_returns_submit_terminal_completed_during_finish`
  - 使用 `_BlockingFinishThinkingDisplay` 冻结 finish-thinking 窗口
  - 冻结期间让 `submit_task` 自然完成
  - 释放后断言：返回对象与原 terminal 同一 identity、`source=LIVE_EVENT`、`terminal_event_id` 不变、Host `cancel_run` 调用数为零、display 最终关闭一次
- 未发起多余 Host cancel，保留原 terminal identity/source ✓

### S4-CR-F05 — 已关闭（event processing exception first-commit）

- 代码验证：`entrypoint_runtime.py:1335-1396` 的 `_consume_host_events`：
  - `asyncio.CancelledError` 原样传播（line 1337-1338）✓
  - `StopAsyncIteration` → `_IteratorEnded`（line 1339-1344）✓
  - `HostApiError` + `DELIVERY_INTERRUPTED` → `_DeliveryInterrupted`（line 1345-1366）✓
  - 其它 `HostApiError` → `_IteratorFailed`（line 1358-1366）✓
  - `anext(watcher)` 的其它 `Exception` → `_IteratorFailed` first-commit 后退出（line 1367-1375）✓
  - `_observation_result_from_event` 的 `asyncio.CancelledError` → 原样传播（line 1386-1387）✓
  - `_observation_result_from_event` 的其它 `Exception` → `_IteratorFailed` first-commit 后退出（line 1388-1396）✓
- 未新增第六类 outcome、Future、queue、task callback 或 `task.exception()` 旁路 ✓
- 测试验证：`test_submit_event_projection_failure_first_commits_iterator_failed`
  - monkeypatch `_entrypoint_activity_from_host_event` 注入原始失败
  - 断言 `EntrypointRuntimeError("session_event_iterator_failed_before_terminal")`
  - 断言 `__cause__` 是原始投影异常
  - 断言不走 durable recovery（`read_outbox_requests == []`）
  - 断言 `watcher.closed_count == 1`
  - 断言 `watcher.close_observed_active_anext is False`（iterator 恰好关闭一次且无 active `anext()`）

## Rejected Finding Boundary Verification

### S4-CR-F03 — 边界未被实施

- `startup_reconnect_entrypoint_session` 无 activity/thinking callback 或 callback execution port
- startup logging scan 结果为空

### S4-CR-F04 — 边界未被实施

- `_wait_for_durable_terminal` 使用固定 `poll_interval_seconds` 轮询，无 retry 次数、timeout、backoff 或 fail-fast 预算
- 未将 `outbox_lagged_max_attempts` 复制到 recovery 路径

## New Finding Scan

未发现实质性问题。

扫描范围：
- `dayu/service/entrypoint_runtime.py`：exact-five 状态机、sole consumer、cleanup 顺序、callback shield、exception 处理、durable recovery
- `dayu/cli/session_execution.py`：display controller lifecycle、prompt/interactive cancel 仲裁、done barrier、caller cleanup error chain
- `dayu/cli/runtime_display.py`：`EntrypointCallbackExecutionPort` 实现、executor 隔离
- 全部 S4 focused tests

扫描结果：
- 无 `hasattr`/`getattr` 滥用
- 无 `cast()` 在生产代码中
- 无 `task.exception()` 旁路
- 无 `object`/`Any` 无类型签名
- 旧 delivery 语义 scan 空（无 `_TRANSIENT_WATCH_BUFFER_CAPACITY`、`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、`session_live_stream`、`reason_code="slow_consumer"` 残留）
- Service relay 彻底删除：queue、drain task、`_WatcherFailure`、`_WatcherQueueItem` 均已移除
- cleanup 顺序正确：stop consumer → await consumer → `aclose()` iterator → `mark_closed()`

## Validation Summary

| 检查项 | 结果 |
|---|---|
| 三项 focused tests | 3 passed ✓ |
| S4 focused tests | 187 passed ✓ |
| 隔离 session_execution.py coverage | 80.56% ✓ |
| 隔离 entrypoint_runtime.py coverage | 86.46% ✓ |
| pyright (full) | 0 errors, 0 warnings, 0 informations |
| git diff --check | clean |
| 旧 delivery 语义 scan | 空 |
| host suite regression | 2067 passed, 2 skipped, 6 deselected ✓ |

## Residual Risk

无。三项 accepted findings 已全部关闭，rejected 边界未被实施，无新 material findings。
