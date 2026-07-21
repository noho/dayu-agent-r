# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 4 Code Review Fix

- 角色：AgentCodex
- gate：`code-review-fix-slice-4`
- accepted base：`24efe9bd`
- 裁决真源：`docs/reviews/wu-host-session-event-delivery-01-slice4-code-review-controller-adjudication.md`
- 结论：`READY_FOR_REREVIEW`
- artifact path：`docs/reviews/wu-host-session-event-delivery-01-slice4-fix-codex.md`

## Scope 与 owner 判断

本轮完整核对了 `AGENTS.md`、Controller adjudication、AgentDS/AgentMiMo 两路 reviewer artifact、
`docs/host/design.md` 的 Service exact-five 状态机章节及 accepted plan S4。当前 design 文件中该章节实际编号为
§4.5；accepted plan 与 reviewer artifact 仍以“4.7 五类 disposition”引用同一冻结语义。本 fix 不修改
design、plan、Controller control/adjudication、reviewer artifacts、此前 implementation artifact或 umbrella handbook。

三个 accepted findings 的动机均由直接代码/命令证据确认成立：

- `S4-CR-F01` 的 owner 是 CLI session lifecycle contract tests；生产分支不应为覆盖率改写。
- `S4-CR-F02` 的 owner 是 `_cancel_prompt_turn_after_local_request` 的 prompt cancel arbitration；已经自然完成的
  submit terminal 是唯一应返回的结果真源。
- `S4-CR-F05` 的 owner 是 Service sole consumer/capacity-one slot；event-processing exception 必须经现有
  exact-five `_IteratorFailed` first-commit，不能从 task handle 或旁路读取。

`S4-CR-F03/F04` 保持 Controller 的 rejected disposition：没有新增 startup operator log，也没有给
`_wait_for_durable_terminal` 增加 retry 次数、timeout、backoff或其它 fail-fast 预算。

## 修复结果

### S4-CR-F01 — 已修复

- 只在 `tests/cli/test_prompt_command.py` 增加 owner-contract tests，不为覆盖率修改生产控制流。
- 新增 prompt caller lifecycle close-failure 测试，断言正常 terminal 后 display close failure 由 CLI lifecycle
  owner 原 identity 传播、renderer与 watcher各关闭一次且不发 Host cancel。
- F02 的 race test 同时覆盖新的 prompt done barrier，但每个测试都包含业务 identity、source、cancel与cleanup断言，
  不存在无业务断言的 coverage fixture。
- 使用独立 `COVERAGE_FILE` 复核：`432 statements / 84 miss / 80.56%`，达到 `>=80%`。

### S4-CR-F02 — 已修复

- `dayu/cli/session_execution.py` 在 `finish_thinking_display()` 返回后、取消 `submit_task`或调用 Host cancel前，
  检查 `submit_task.done()`；已自然完成时直接 `return await submit_task`。
- deterministic test 用显式 CLI 私有 executor 中的同步 barrier 冻结 finish-thinking 窗口；冻结期间让
  `submit_task`自然完成，再释放 renderer。
- 测试断言返回对象与原 terminal 是同一 identity，`source=LIVE_EVENT`、`terminal_event_id`不变，Host
  `cancel_run`调用数为零，display最终关闭一次。

### S4-CR-F05 — 已修复

- `dayu/service/entrypoint_runtime.py::_consume_host_events` 继续让 `asyncio.CancelledError` 原样传播；
  `_observation_result_from_event(...)` 的其它 `Exception` 由 sole consumer first-commit 为既有
  `_IteratorFailed` 后立即退出。
- 没有新增第六类 outcome、Future、queue、task callback或 `task.exception()` 旁路。
- deterministic test 在 Host activity → Service DTO 投影 owner 注入原始失败，使用 `asyncio.wait_for` 证明不 hang，
  并断言 stable reason 精确为 `session_event_iterator_failed_before_terminal`、原投影异常保持 direct cause、
  不走 durable recovery、iterator恰好关闭一次且 `aclose()` 时没有 active `anext()`。

## 变更文件

本 fix 相对 code-review 输入只追加修改：

- `dayu/cli/session_execution.py`
- `dayu/service/entrypoint_runtime.py`
- `tests/cli/test_prompt_command.py`
- `tests/service/test_entrypoint_runtime.py`
- `docs/reviews/wu-host-session-event-delivery-01-slice4-fix-codex.md`

以上 production/test 均在 accepted S4 allowlist 内。未修改 Controller-owned
`docs/host/issues-implementation-control.md` 或任何既有 review/implementation artifact。

## 验证

所有 Python 命令均在 `source .venv/bin/activate` 后运行。

1. 三项 focused：

   ```text
   pytest \
     tests/cli/test_prompt_command.py::test_prompt_cancel_returns_submit_terminal_completed_during_finish \
     tests/cli/test_prompt_command.py::test_prompt_terminal_surfaces_display_close_failure_from_caller_lifecycle \
     tests/service/test_entrypoint_runtime.py::test_submit_event_projection_failure_first_commits_iterator_failed -q
   -> 3 passed
   ```

2. S4 focused matrix：

   ```text
   pytest tests/service/test_entrypoint_runtime.py \
     tests/service/test_entrypoint_runtime_prompt_path.py \
     tests/service/test_entrypoint_runtime_interactive_path.py \
     tests/cli/test_transient_delivery_interruption_path.py \
     tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
     tests/cli/test_runtime_display.py tests/cli/test_activity_renderer.py \
     tests/cli/test_interactive_run_view.py tests/cli/test_thinking_renderer.py -q
   -> 196 passed
   ```

3. 隔离单文件 coverage：

   ```text
   COVERAGE_FILE=workspace/tmp/.coverage-codex-s4-session-execution \
     pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
     --cov=dayu.cli.session_execution --cov-report=term-missing --cov-fail-under=80 -q
   -> 93 passed; 432 statements / 84 miss / 80.56%
   ```

4. 完整 `pyright`：`0 errors, 0 warnings, 0 informations`。
5. S4 changed-Python allowlist scoped Ruff：`All checks passed!`。
6. 全仓 `ruff check dayu tests utils` 仍报告 141 项既有跨域 lint baseline；命中均不属于本 fix 文件，
   本轮没有越权修改。四个本 fix Python 文件与完整 S4 changed-Python allowlist均已单独验证为零错误。
7. `git diff --check`：通过。
8. 旧 delivery 语义 scan：空。
9. Service relay/queue/`task.exception()` side-channel scan：空。
10. `dayu/service/entrypoint_runtime.py` startup logging scan：空。

测试输出只有既有 edgartools deprecation warnings；不影响断言或退出码。

## README decision

本轮只补现有 S4 测试层内的 owner-contract cases，并修正冻结的内部 race/disposition；没有新增测试层级、命令、
CLI参数、用户工作流或公开语义。`tests/README.md` 已包含 S4 focused 命令与 exact-five/cleanup 边界，故不机械修改；
其它 README trigger同样未新增。

## Finding 状态与 residual risk

| Finding | 最终状态 | 证据 |
|---|---|---|
| `S4-CR-F01` | 已修复 | 隔离 coverage `80.56%` |
| `S4-CR-F02` | 已修复 | finish-thinking barrier test；同一 live terminal；零 Host cancel |
| `S4-CR-F03` | rejected，未修改 | startup logging scan为空 |
| `S4-CR-F04` | rejected，未修改 | 未增加 retry/timeout/backoff语义 |
| `S4-CR-F05` | 已修复 | projection failure fail-fast/stable disposition/exactly-once close test |

当前 accepted findings 已全部修复，无未分类 residual risk。全仓 Ruff 141 项是当前 S4 allowlist之外的既有仓库基线，
不由本 fix 扩散；edgartools warnings同为既有第三方告警。本轮未 commit、未 push。下一入口是原 AgentDS/AgentMiMo
对 `S4-CR-F01/F02/F05` 做独立 re-review。
