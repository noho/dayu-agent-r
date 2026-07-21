# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 4 Code Re-Review Controller Adjudication

- 日期：2026-07-22
- gate：`code-rereview-slice-4`
- base：accepted Slice 3 commit `24efe9bd`
- reviewers：AgentMiMo、AgentDS（独立并行）
- implementation owner：AgentCodex
- decision：`accepted-slice-4-ready-for-commit`

## 输入证据

- 首轮 Controller 裁决：`docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-controller-adjudication.md`
- AgentCodex fix：`docs/reviews/wu-host-session-event-delivery-01-slice4-fix-codex.md`
- AgentMiMo re-review：`docs/reviews/wu-host-session-event-delivery-01-slice4-code-rereview-mimo.md`
- AgentDS re-review：`docs/reviews/wu-host-session-event-delivery-01-slice4-code-rereview-ds.md`

两路 reviewer 未互读对方 artifact，均实际使用 `$deepreview --base 24efe9bd`，独立复核全部 Slice 4 workspace changes。两路 verdict 均为 `PASS`，但本裁决不以多数票为依据；以下逐项按 owner contract、直接代码与可复现测试证据裁决。

## Accepted finding closure

### S4-CR-F01：CLOSED

`dayu/cli/session_execution.py` 的隔离覆盖率已由首轮 Controller 复现的 `79.53%` 提升到 `80.56%`（`432 statements / 84 miss`），使用独立 `COVERAGE_FILE` 且 `--cov-fail-under=80` 成功退出。新增 `test_prompt_terminal_surfaces_display_close_failure_from_caller_lifecycle` 断言 caller lifecycle owner 原样传播 close failure、renderer/watcher 各关闭一次且不发 Host cancel，不是无业务语义的 coverage fixture。

裁决：接受修复，单文件覆盖率 acceptance 已满足。

### S4-CR-F02：CLOSED

`dayu/cli/session_execution.py::_cancel_prompt_turn_after_local_request` 在 `finish_thinking_display()` 返回后、`submit_task.cancel()` 前检查 `submit_task.done()`；若自然完成，直接 `return await submit_task`。确定性测试在 finish-thinking barrier 内完成 submit task，并断言返回对象保持原 terminal identity、`LIVE_EVENT` source 与 `terminal_event_id`，Host cancel 调用为零，display 精确关闭一次。

裁决：修复位于 CLI cancel arbitration owner，关闭 terminal 丢失与多余 Host cancel 竞态；无下游兼容分支。

### S4-CR-F05：CLOSED

`dayu/service/entrypoint_runtime.py::_consume_host_events` 现在显式让 `asyncio.CancelledError` 传播，并把 `_observation_result_from_event(...)` 的其它 `Exception` first-commit 为冻结 exact-five union 中既有 `_IteratorFailed` 后退出。没有新增第六类 outcome、queue、Future、task callback 或 `task.exception()` 旁路。确定性投影失败测试在超时保护内断言 stable reason、原异常 direct cause、不走 durable recovery、iterator 精确关闭一次且关闭时无 active `anext()`。

裁决：修复位于 Service sole-consumer / exact-five observation owner，消除了未提交 slot 导致 coordinator 永久等待的路径。

## Rejected finding boundary

### S4-CR-F03：REJECTED boundary preserved

startup reconnect 路径未新增 operator log、activity callback 或 callback execution port。既定设计只允许 Service 在具备现有 `on_activity` port 的 observation 路径至多发一次固定去敏 cleanup diagnostic；startup 没有该 port，零诊断属于冻结 contract。

裁决：保持首轮拒绝，不产生新 fix。

### S4-CR-F04：REJECTED boundary preserved

`_wait_for_durable_terminal` 仍按 typed polling interval 与 caller cancellation 等待 durable terminal，没有 retry count、timeout、backoff 或 fail-fast budget；`outbox_lagged_max_attempts` 仍只属于 startup bounded backfill。两条状态机未被混合。

裁决：保持首轮拒绝，不产生新 fix。

## New finding 与 residual risk 裁决

两路 reviewer 均报告零个新 material finding。AgentDS 记录三项非 material notes，Controller 逐项裁决如下：

1. E2E overflow 只选取代表性 capacity，而未做所有 capacity / subscription / renderer 组合：不构成缺陷。Host owner tests 已直接覆盖 `511 -> 512` 边界、in-flight retained counting、overflow、subscription admission；runtime/config/public contract tests直接覆盖 packaged defaults `512/4`，CLI E2E 负责跨层 interruption 路径而非重复 owner 参数笛卡尔积。无需当前 fix，也不产生 residual WU。
2. `BaseException.__cause__` 在未来 Python 版本的理论变化：项目冻结 Python 3.11，异常 chaining 是语言 contract；当前真实 cancellation/cleanup tests 已通过。无需当前 fix，也不产生 residual WU。
3. 全仓 Ruff 141 项既有跨域 baseline：Slice 4 changed-Python allowlist 为零错误，未由本 Slice 新增或扩散。不是本 WU finding。

## 独立验证结论

- AgentMiMo：三项 focused `3 passed`；S4 focused `187 passed`；Host suite `2067 passed, 2 skipped, 6 deselected`；`session_execution.py` `80.56%`；`entrypoint_runtime.py` `86.46%`；完整 pyright `0 errors`。
- AgentDS：S4 focused `196 passed`；affected suites `3443 passed, 9 skipped, 6 deselected`；stress `6 passed`；两文件 coverage `80.56%` / `86.46%`；完整 pyright `0 errors`；S4 scoped Ruff通过。
- 两路 `git diff --check`、旧 delivery semantic scan、Service relay/side-channel scan、default executor leakage scan均通过。

## Gate decision

`S4-CR-F01/F02/F05` 全部关闭，`S4-CR-F03/F04` 拒绝边界保持，无新 material finding、无 blocking open question、无未归属 residual risk。Slice 4 接受进入 Controller-owned accepted commit；commit 完成后的 next gate 为 full-WU aggregate deepreview，由 AgentMiMo与AgentDS继续独立并行使用 `$deepreview`。
