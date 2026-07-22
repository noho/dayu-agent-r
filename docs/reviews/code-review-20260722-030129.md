# Code Review — AgentDS independent adversarial pass

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-host-session-event-delivery-01`
- Base: `24efe9bd` (accepted Slice 3)
- Output file: `docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-ds.md`
- Review timestamp: `20260722-030129`
- Included scope: 所有 unstaged + staged + uncommitted working tree changes relative to `24efe9bd`，覆盖 S4 allowlist 所列 production (`dayu/service/entrypoint_runtime.py`, `dayu/cli/session_execution.py`, `dayu/cli/runtime_display.py`, `dayu/cli/activity.py`, `dayu/cli/run_view.py`)、test (`tests/service/test_entrypoint_runtime.py`, `tests/service/test_entrypoint_runtime_interactive_path.py`, `tests/service/test_entrypoint_runtime_prompt_path.py`, `tests/cli/test_transient_delivery_interruption_path.py`, `tests/cli/test_prompt_command.py`, `tests/cli/test_interactive_command.py`, `tests/cli/test_runtime_display.py`, `tests/cli/test_activity_renderer.py`, `tests/cli/test_interactive_run_view.py`) 与 README (`dayu/README.md`, `dayu/service/README.md`, `tests/README.md`) 文件。
- Excluded scope: `docs/host/issues-implementation-control.md`（Controller-owned dirty change，按用户指令排除）；S1–S3 冻结的 Host production/test 文件（本 review 只检查 S4 消费其 public contract 的一致性，不审计 Host 内部实现）。
- Design documents consulted: `docs/host/design.md`, `docs/host/wu-host-session-event-delivery-01-plan.md` (S4 frozen contract), `AGENTS.md`/`CLAUDE.md`, `docs/reviews/wu-host-session-event-delivery-01-slice4-implementation-codex.md`。
- Parallel review coverage: 无 subagent；本 review 为单人独立走读。

## Findings

### 1-FINDING-中-`_cancel_prompt_turn_after_local_request` 缺少 `submit_task.done()` 提前返回，与 interactive 路径不一致

- **入口/函数**: `_cancel_prompt_turn_after_local_request`
- **文件(行号)**: `dayu/cli/session_execution.py:963-967`
- **输入场景**: prompt 模式下，用户在 `submit_task` 已实际完成、但 `asyncio.wait(FIRST_COMPLETED)` 恰好选中 `sigint_task` 之后、`_cancel_prompt_turn_after_local_request` 进入前，submit_task 在 `await runtime_display.finish_thinking_display()`（line 964）期间完成。
- **实际分支**: `submit_task.cancel()` 返回 `False`，`await submit_task`（suppress CancelledError 但不 suppress 正常返回值）返回已完成的 `EntrypointRunTerminalResult`，该值被丢弃。随后检查 `accepted_run.run_id`（此时非空），进入 `_cancel_prompt_run_waiting_for_terminal_or_second_sigint`，发起多余的 Host cancel，并最终从 cancel 路径获得 terminal result，而不是直接使用 submit_task 已有的 terminal result。
- **预期行为**: 与 interactive 路径（`_cancel_interactive_turn_after_first_sigint` line 1307-1308: `if submit_task.done(): return await submit_task`）一致，在 cancel 前先检查 submit_task 是否已自然完成，若已完成则直接返回其 terminal result。
- **实际行为**: submit_task 的 terminal result 被丢弃；多余的 Host cancel 被发起；最终 terminal 来自 cancel/outbox 路径而非 submit/live 路径。
- **直接证据**:
  - `dayu/cli/session_execution.py:963-967`：`submit_task.cancel()` 无条件执行；没有 `if submit_task.done()` 提前返回。
  - `dayu/cli/session_execution.py:1307-1308`：interactive 路径有 `if submit_task.done(): return await submit_task` 保护。
  - `dayu/cli/session_execution.py:964`：`await runtime_display.finish_thinking_display()` 是异步点，为 race window 提供时间。
- **影响**: 多余 Host cancel 调用；terminal 来源从 live event 降级为 outbox read（语义劣化但结果等价）；code path 不对称增加维护负担。
- **建议改法和验证点**: 在 `_cancel_prompt_turn_after_local_request` 中 `submit_task.cancel()` 之前加入 `if submit_task.done(): return await submit_task` 检查，与 interactive 路径对齐。验证：构造 submit_task 在 finish_thinking_display 期间完成的时序测试，断言不产生多余 cancel 请求且 terminal source 为 LIVE_EVENT。
- **修复风险**: 低。仅增加提前返回分支，不改变既有 cancel 路径语义。
- **严重程度**: 中

### 2-FINDING-中-`startup_reconnect_entrypoint_session` 在 delivery interruption 恢复成功后 silence watcher close error

- **入口/函数**: `startup_reconnect_entrypoint_session`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:1125-1145, 1178-1181`
- **输入场景**: startup reconnect 期间遇到 `_DeliveryInterrupted`（line 1126），watcher 关闭（line 1125: `cleanup_error = await _close_watch_and_wait_runtime(runtime)`）时产生 `cleanup_error`，但后续 durable recovery 成功（line 1129-1137，terminal 已添加），且不存在进一步的 active Run 需要处理。loop 退出后，`runtime.closed` 已为 True（跳过 line 1178-1179），`terminal_results` 非空（跳过 line 1180-1181），cleanup_error 被完全丢弃。
- **实际分支**: line 1125 赋值 cleanup_error → line 1129 durable recovery 成功 → line 1145 `continue` → loop 继续，无更多 active/queued idle → line 1173 `break` → line 1178-1179 跳过 → line 1180-1181 因 `terminal_results` 非空跳过。
- **预期行为**: 与 plan 4.7 中 delivery recovery 路径对齐：cleanup error 应通过 `_emit_cleanup_diagnostic` 将去敏诊断传递给 CLI（如果调用方提供了 activity callback）。但 startup 路径 `on_activity=None`，因此诊断自然为 no-op——然而 cleanup error 本身仍被静默丢弃，丧失了 operator observability。
- **实际行为**: watcher `aclose` 失败（可能表示 Host resource 泄漏或 iterator 未正确释放）被完全静默，无日志、无 diagnostic、无异常。
- **直接证据**:
  - line 1125：`cleanup_error = await _close_watch_and_wait_runtime(runtime)` 捕获 close 错误。
  - line 1140-1144：cleanup_error 仅在 recovery 失败时被包含在异常链中；recovery 成功时不使用。
  - line 1178-1181：两个保护条件恰好都跳过，cleanup_error 完全丢失。
  - plan 4.7：disposition 要求 "terminal/恢复成功+close failure仍返回同一terminal，最多一次固定sanitized diagnostic"。startup 路径的 delivery recovery 成功 + close failure 未产生 diagnostic。
- **影响**: 生产环境中 watcher 资源泄漏无法观测；iterator 释放失败被静默。
- **建议改法和验证点**: 在 startup 的 delivery-recovery-success 路径（line 1129-1137 成功后，`continue` 前）加入结构化日志记录 `cleanup_error`（如 `event=watcher_cleanup, outcome=failed, reason=close_error`）。由于 startup 无 activity/thinking callback，diagnostic 不可用；至少需要 operator log。验证：构造 close error + recovery success 场景，断言日志产生且 terminal_results 仍正确。
- **修复风险**: 低。仅增加日志，不改变 control flow 或 terminal result。
- **严重程度**: 中

### 3-FINDING-低-`_read_outbox_terminal` 在 LAGGED 状态下无最大重试保护，依赖外层 timeout

- **入口/函数**: `_read_outbox_terminal`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:2218-2248`
- **输入场景**: outbox projection 持续处于 LAGGED 状态（Host projection 延迟），且目标 Run terminal 尚未投影到 outbox。`_read_outbox_terminal` 返回 `None`（line 2248），调用方 `_wait_for_durable_terminal`（line 1874-1885）在 `get_run` 确认终态后调用 `_read_outbox_terminal`，若返回 None 则 `sleep` 并重试。
- **实际分支**: `_read_outbox_terminal` line 2243-2248：`projection_status not FAILED and not CAUGHT_UP` → LAGGED → has_more=False → 未命中目标 → return None。
- **预期行为**: 按 plan 设计，`_wait_for_durable_terminal` 不持有内部 timeout，调用方负责通过 task cancellation 控制等待生命周期。但 `_read_outbox_terminal` 作为被调方，对 LAGGED 无条件返回 None，导致 `_wait_for_durable_terminal` 进入 sleep → retry → get_run → _read_outbox_terminal → None 的无限循环。plan 虽明确"不持有内部 timeout"，但此行为缺乏 bounded retry 或 exponential backoff，在极端 projection delay 场景下会产生密集的 `get_run` 调用。
- **实际行为**: `_wait_for_durable_terminal` 在每次 `poll_interval_seconds` sleep 后重试 `get_run` + `_read_outbox_terminal`。`_read_outbox_terminal` 每次内部又可能发起多个 outbox read 调用（has_more=True 的分页推进）。LAGGED 时的返回使得外层无差别的固定间隔重试，无退避。
- **直接证据**:
  - `dayu/service/entrypoint_runtime.py:1874-1885`：`while True` 循环，无最大迭代次数或退避。
  - `dayu/service/entrypoint_runtime.py:2243-2248`：LAGGED 时无条件 return None。
  - 对比 startup 路径 `_read_session_outbox_terminal_backfill`（line 2160-2166）：LAGGED 时有 `outbox_lagged_max_attempts` 上限。
- **影响**: 在 outbox projection 持续延迟的退化场景下，产生无节制的 Host public API 调用；不导致数据错误，但可能加剧退化。
- **建议改法和验证点**: 为 `_read_outbox_terminal` 增加可配置的 LAGGED 最大重试次数（类似 startup backfill 的 `outbox_lagged_max_attempts`），或在 `_wait_for_durable_terminal` 中加入退避策略。验证：构造持续 LAGGED 场景，断言在指定次数后 fail fast 而非永久循环。
- **修复风险**: 低。仅增加 bounded retry，不改变正常路径行为。需注意与 plan "不持有内部 timeout" 的兼容——bounded retry 不等于绝对 timeout，仍依赖外层 cancellation。
- **严重程度**: 低

### 4-FINDING-低-`_entrypoint_activity_kind_from_host` 的 `AssertionError` 未被 consumer 捕获，会导致 consumer task 静默崩溃

- **入口/函数**: `_entrypoint_activity_kind_from_host` → `_observation_result_from_event` → `_consume_host_events`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:1973-1997, 1376-1396, 1422-1457`
- **输入场景**: Host public API 返回了 `HostActivityKind` 的新增成员（例如未来 Host 扩展了新的 activity kind），而 Service 的映射表未更新。`_entrypoint_activity_kind_from_host` 在 line 1997 抛出 `AssertionError`。
- **实际分支**: `AssertionError` 在 `_entrypoint_activity_from_host_event`（line 1926）中抛出 → 传播到 `_activity_from_live_event` → 传播到 `_observation_result_from_event`（line 1443）→ 传播到 `_consume_host_events`（line 1376）。`_consume_host_events` 的 try/except 只捕获 `asyncio.CancelledError`（line 1337）、`StopAsyncIteration`（line 1339）、`HostApiError`（line 1345）和 `Exception`（line 1367——但只覆盖 `anext(watcher)` 调用，不覆盖 `_observation_result_from_event` 调用）。
- **预期行为**: consumer task 崩溃后，`_close_watch_and_wait_runtime` 在 `await runtime.consumer_task`（line 1839）时 re-raise `AssertionError`，进而通过 caller 的异常处理传播。但 coordinator 在 `wait_for_result()` 处永久挂起，因为没有 result 被 commit。
- **实际行为**: `AssertionError` 导致 consumer task 崩溃（task 状态变为 exception），coordinator 的 `wait_for_result()` 永远不返回。仅当 coordinator 被取消或 timeout 时才发现问题。
- **直接证据**:
  - line 1376：`result = await _observation_result_from_event(...)` 在 try 块内。
  - line 1337-1375：try/except 覆盖了 `anext(watcher)` 的异常但未覆盖 `_observation_result_from_event` 的异常。
  - line 1997：`raise AssertionError(f"unexpected HostActivityKind: {kind}")` 是 `AssertionError`（继承 `Exception`），不会被 `asyncio.CancelledError` catch。
- **影响**: Host activity kind 扩展后，Service 未同步更新会导致 coordinator 挂起；运行时表现不直观（hang 而非 fail fast）。
- **建议改法和验证点**: 在 `_consume_host_events` 中将 `_observation_result_from_event` 的异常也纳入 `except Exception` 处理，转换为 `_IteratorFailed` member 提交到 slot，使 coordinator 能通过 exact-five disposition 及时发现。验证：构造未知 activity kind 的 fake event，断言生成 `EntrypointRuntimeError` 而非 hang。
- **修复风险**: 低。增加一条异常捕获路径，不改变现有正常行为。
- **严重程度**: 低

## Open Questions

- 无。所有关键路径已沿真实代码走读完成，无阻碍判断的未决问题。

## Residual Risk

1. **Host→Service→CLI overflow E2E 测试的单点覆盖**：`tests/cli/test_transient_delivery_interruption_path.py::test_real_delivery_interruption_recovers_once_and_renders_terminal_once` 是唯一真实跨层 E2E 测试，使用真实 `open_host` + `ThreadPoolExecutor` + 阻塞 renderer。该测试的 mailbox capacity 固定为 32 items，仅覆盖一种 overflow 阈值。不同 capacity 值、多 subscription 并发 overflow、以及 overflow 发生在 activity（非 thinking）renderer 上的场景未被 E2E 覆盖。

2. **`asyncio.CancelledError` 与 `BaseException` 的 cause chain**：Service 的异常链大量使用 `raise primary_error from cleanup_error`，其中 primary_error 可能为 `asyncio.CancelledError`（继承 `BaseException`）。Python 3.11+ 的 `BaseException.__cause__` 支持已验证，但跨版本（如未来 Python 3.12/3.13）的行为变化未做兼容性测试。

3. **README 审计完整性**：`dayu/host/README.md` 和 `dayu/config/README.md` 按各自 Agent更新约束审计后决定不修改（Codex 报告称 accepted base 已准确记录 item-bound/per-Session contract 与 packaged 512/4）。本 review 未独立逐行验证这两个 README 是否完全反映 S4 后的最新事实。根 `README.md` diff 为空，符合 plan 预期。

4. **pyright + scan 结果**：Codex 报告显示 `0 errors, 0 warnings, 0 informations`，旧 delivery 语义 scan 为空，relay/queue/default-executor scan 为空。本 review 未独立重新运行这些命令，依赖 Codex 的验证报告。

## 结论

**FINDINGS** — 4 个 material findings（2 个中，2 个低），无严重级别 finding。

核心 Service exact-five state machine、stop arbitration、generation handshake、callback scheduling/shield、cleanup double-fault chain、CLI executor lifecycle exactly-once close 均按 plan 4.7 与 S4 frozen contract 正确实现。未发现 stale relay/queue symbol、default executor leakage、hasattr/getattr loose parsing、或 semantic ownership drift。

所有 finding 的完整证据、owner boundary、建议修复与验证已在上方记录。

Review artifact path: `docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-ds.md`
