# wu-cli-smoke-01 interactive cancel/activity 修复记录

## 结论

Pass。

本次修复没有修改 Host canonical EventLog / Host DB 治理事实的事实层语义；修复点集中在 public projection、waiting terminal 同源错误消息、CLI cancel 用户回显、interactive runtime display 默认模式保持。

## Root Cause

1. 双份 `in_progress`：
   - DB 中 `RUN_STARTED` 与 `ATTEMPT_RUNNING` / `ATTEMPT_STARTED` 是不同治理事实，应保留。
   - public activity projection 把 Run lifecycle 与 Attempt governance event 都投影成同义用户状态，导致用户看到重复的“运行已开始”。

2. 双份 `waiting`：
   - DB 中 `TOOL_AWAITING` 与 `RUN_WAITING` 是不同治理事实，应保留。
   - public activity projection 同时把两者投影成工具等待；`TOOL_AWAITING` 有工具名，`RUN_WAITING` 只能形成泛化等待，导致一条工具名等待和一条泛化等待重复出现。

3. Ctrl+C 显示 `cli_sigint`：
   - `cli_sigint` 是 CLI 到 Host cancel command 的内部 reason，用于 trace / idempotency / audit。
   - CLI terminal output 直接打印了 Host terminal result 的 `cancel_reason`，泄漏内部治理标识。

4. `wait_result_failed` 后 CLI 显示 `Host run failed without error message`：
   - Fins / wait adapter failed outcome 已有 `ToolResultFailure.message`。
   - waiting terminal transition 只把 `reason=wait_result_failed` 写入 `RUN_FAILED` payload，没有把同源 outcome message 写入 terminal payload。
   - read_api 无法得到 public `error_message`，CLI 只能 fallback。

5. 第三轮不明显进入 waiting：
   - interactive `--detail` 初始使用 activity view，但每轮 terminal result 后固定把 view mode 重置为 transcript。
   - 后续长事务 activity 仍被记录，但不再实时显示，表现为 Thinking/工具后 waiting 不明显。

## Public Projection 规则

- Canonical EventLog / Host DB 保留 `RUN_*`、`ATTEMPT_*`、`TOOL_*` 治理事实。
- Public activity 只暴露用户可理解、非重复状态。
- `ATTEMPT_*` 默认不投影为 public activity。
- `TOOL_AWAITING` 是唯一工具等待 public activity。
- `RUN_WAITING` 保留 canonical/timeline 事实，但不重复投影 waiting activity。
- Terminal public `error_message` 必须来自同源 wait/tool outcome，经 Host terminal payload 投影，不由 CLI fallback 猜。
- Cancel 内部 reason 与用户回显分离：Host 仍保留 `cli_sigint`，CLI 对用户显示 `Cancelled.`。

## 实现边界

- `dayu/host/read_api.py`
  - 收窄 activity allowlist：移除 `ATTEMPT_STARTED` lifecycle activity 投影，`RUN_WAITING` 不再走 `_tool_awaiting_activity`。
  - `TOOL_AWAITING` 保持为工具等待 public activity。

- `dayu/host/durable/run_transition.py`
  - `WaitingRunTerminalInput` 增加 `message: str | None`。
  - waiting terminal `RUN_FAILED` / `RUN_LOST` payload 在存在 message 时写入 `message`。

- `dayu/host/waiting.py`
  - failed wait terminal message 来自 `ResolveWaitFailedOutcome.result.message` 和可选 `hint`。
  - lost wait terminal message 来自 `ResolveWaitLostOutcome.message`。

- `dayu/cli/output.py`
  - `cli_sigint` 映射为用户文案 `Cancelled.`。
  - 其他 cancel reason 仍按原 reason 显示，空 reason 使用既有 fallback。

- `dayu/cli/run_view.py`
  - 保存 `_default_mode`。
  - terminal result 后恢复到配置默认 mode；`--detail` 的 activity mode 不再在第一轮后静默降级。

## 测试矩阵

| 覆盖点 | 测试 |
| --- | --- |
| `TOOL_AWAITING` 唯一等待 activity，`RUN_WAITING` 静默 | `tests/host/test_host_activity_event_projection.py` |
| `ATTEMPT_STARTED` 默认不投影 public activity | `tests/host/test_host_activity_event_projection.py` |
| failed/lost wait terminal payload 携带同源 message | `tests/host/test_resolve_wait_command.py` |
| prompt/interactive 不泄漏 `cli_sigint` | `tests/cli/test_output.py` |
| `--detail` 终态后保持 activity 默认 mode | `tests/cli/test_interactive_run_view.py` |
| prompt/interactive command 高层路径未回归 | `tests/cli/test_prompt_command.py`, `tests/cli/test_interactive_command.py` |

## 验证命令

```bash
source .venv/bin/activate && pytest tests/host/test_host_activity_event_projection.py tests/host/test_resolve_wait_command.py tests/cli/test_output.py tests/cli/test_interactive_run_view.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q
```

结果：`113 passed, 3 warnings`。warnings 均来自 `edgar` 依赖 deprecation。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

## README

已检查：

- `dayu/host/README.md`：Host 边界与取消承诺已有说明，本次 public projection 规则属于实现细节，不扩写。
- `tests/README.md`：新增 focused 测试未改变测试层级、运行方式或维护规则，不更新。
- `README.md`：未记录 Ctrl+C 精确输出文案，不更新用户手册。

## 残余风险

- 本次验证是 focused 自动化测试与类型检查，未重新跑 SEC/provider 真实下载烟测；外部网络、SEC/provider 状态仍可能导致真实下载失败。
- `Cancelled.` 文案是 CLI 用户输出收敛，内部 trace / audit 仍保留 `cli_sigint`，后续若其他 UI 直接展示 Host cancel reason，需要在对应 UI adapter 做同类 public mapping。

## Review Finding 跟进：MiMo F-1

结论：Pass。

补测内容：

- 只修改测试，不修改生产逻辑。
- 在 `tests/host/test_resolve_wait_command.py` 的 failed wait fixture 中加入可选非空 `hint`。
- `test_resolve_wait_failed_and_lost_close_run_without_resume_attempt` 使用 `hint="retry after provider recovery"`。
- 断言 `RUN_FAILED` payload 的 `message` 为 `provider failed retry after provider recovery`，覆盖 `_failed_wait_terminal_message` 的 `hint is not None` 分支。

验证命令：

```bash
source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py -q
```

结果：`10 passed`。

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。
