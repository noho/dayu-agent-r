# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 4 Code Review Controller Adjudication

## 裁决范围

- Accepted base：`24efe9bd`。
- AgentMiMo artifact：`docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-mimo.md`。
- AgentDS artifact：`docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-ds.md`。
- Controller 排除自身维护的 `docs/host/issues-implementation-control.md`，逐项以 `docs/host/design.md`、accepted S4 plan 与直接代码/命令证据裁决，不按多数票放行。

## 结论

Decision=`fix-required`。五项 reviewer findings 中接受三项、拒绝两项；accepted findings 只能由 AgentCodex 修复，完成后必须交回原 reviewers 独立并行 re-review。

## Finding 裁决

### S4-CR-F01 — ACCEPTED（来源：MiMo finding 1）

- 事实：使用隔离文件重新执行
  `COVERAGE_FILE=workspace/tmp/.coverage-controller-s4-session-execution pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py --cov=dayu.cli.session_execution --cov-report=term --cov-fail-under=80 -q`
  得到 `430 statements / 88 miss / 79.53%`，命令因未达到 80% 明确失败；不是共享 `.coverage` 并发污染。
- Owner：CLI session lifecycle contract tests。
- Required fix：只补 owner-contract 测试，把 `dayu/cli/session_execution.py` 独立覆盖率提升到 `>=80%`；不得新增无业务断言的覆盖率夹具或修改生产分支凑数。复核必须使用独立 `COVERAGE_FILE`。

### S4-CR-F02 — ACCEPTED（来源：DS finding 1）

- 事实：`dayu/cli/session_execution.py:963-967` 在 `await runtime_display.finish_thinking_display()` 后无条件 cancel/await `submit_task`，正常完成的 `EntrypointRunTerminalResult` 会被丢弃；同 owner 的 interactive 路径在 `1307-1308` 已先检查 `submit_task.done()` 并直接返回。
- 影响：prompt 的 cancel/terminal race 会丢弃 live terminal、发起多余 Host cancel，并把结果来源降级到 cancel/durable path。
- Owner：`_cancel_prompt_turn_after_local_request` 的 prompt caller cancellation arbitration。
- Required fix：在发起 task cancellation / Host cancel 前，以与 interactive 路径同源的 done barrier 直接返回自然完成的 submit terminal；增加 deterministic test，使 submit 在 finish-thinking await 窗口完成，并断言不发 Host cancel、保留原 terminal identity/source。

### S4-CR-F03 — REJECTED（来源：DS finding 2）

- 冻结设计 `docs/host/design.md` 4.7 明确：terminal 或 delivery recovery 成功且 close 失败时仍返回同一 terminal，Service **通过现有 `on_activity`** 最多输出一次固定去敏 diagnostic；diagnostic callback 不存在时自然为零次。`startup_reconnect_entrypoint_session` 按设计没有 activity/thinking callback 或 callback execution port。
- 当前路径保留 terminal、不会让 cleanup error 覆盖 primary，符合“最多一次”与 callback-absent contract。reviewer 建议新增 operator logging 是新的输出通道/语义，不是 frozen S4 acceptance，也没有日志字段与去敏 shape 的设计授权。
- 不修改。

### S4-CR-F04 — REJECTED（来源：DS finding 3）

- `_wait_for_durable_terminal` 是 delivery interruption 后的 correctness recovery：在 public `get_run` 已终态后按 `poll_interval_seconds` 等待 Outbox terminal owner追平，由 caller cancellation 控制生命周期；它不是 tight loop，也不能因任意次数预算在 durable terminal 尚未可读时 fail fast。
- startup session-scoped backfill 的 `outbox_lagged_max_attempts` 用于 bounded startup entry，不是单目标 terminal recovery 的同一语义 owner。把该预算复制到 recovery 会把暂时 projection lag 变成新的 caller failure，违反 durable recovery 目标。
- 不修改；固定间隔调用频率已由现有 typed poll interval约束。

### S4-CR-F05 — ACCEPTED（来源：DS finding 4）

- 事实：`_consume_host_events` 的 `except Exception` 只包围 `anext(watcher)`；`_observation_result_from_event(...)` 位于其后。`_activity_from_live_event` / typed enum mapping 或其它 event processing exception 可使 consumer task带异常退出，却没有向 capacity-one slot first-commit 五类结果，coordinator 可永久停在 `wait_for_result()`。
- Owner：Service sole consumer 是所有 observation outcomes 的唯一 first-commit owner；不能依靠 cleanup 时读取 task exception形成第二通道。
- Required fix：`asyncio.CancelledError` 继续原样传播；event processing 的其它 exception 必须由 sole consumer first-commit 为 frozen exact-five 中的 `_IteratorFailed`（把无法消费的 public iterator item视为 stream failure）后退出。不得读取 `task.exception()`、新增第六类 outcome 或旁路 Future。增加 deterministic projection failure test，断言 coordinator fail fast、stable disposition与 iterator 精确一次关闭，不发生 hang。

## Fix gate

AgentCodex 只可修改 accepted S4 production/test allowlist与自己的 fix artifact；不得修改 Controller control/adjudication、两个 reviewer artifacts或通用 umbrella handbook。修复后至少运行：三项 focused tests、S4 focused、隔离单文件 coverage、完整 pyright、`git diff --check` 与必要 stale scans。
