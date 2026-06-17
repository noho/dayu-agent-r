# Code Review — WU-CLI-SESSION-01 S5

## Scope

- Mode: current changes
- Branch: wu-cli-session-01
- Base: 653c9966 (accepted plan commit)
- Output file: docs/reviews/code-review-wu-cli-session-01-s5-ds-20260616.md
- Included scope:
  - `dayu/cli/commands/session.py` — `_run_session_resume`、`_resolve_existing_session_target`、`_resume_host_error_message`、mode 校验/prompt 校验
  - `dayu/cli/commands/prompt.py` — `_prepare_prompt_existing_session_execution`、`_execute_prompt_on_existing_session`、`_PreparedPromptExistingSessionExecution`
  - `dayu/cli/commands/interactive.py` — `_prepare_interactive_existing_session_execution`、`_execute_interactive_on_existing_session`、`_PreparedInteractiveExistingSessionExecution`
  - `dayu/cli/arg_parsing.py` — `_register_session_resume_action` 增加 `--ticker`
  - `tests/cli/test_session_command.py` — 5 个 resume 测试 + `_FakeSessionHost` 扩展（`get_session_status`、`submit_error`、`submit_requests`）+ `_FakeResumeCapture`
  - `tests/cli/test_prompt_command.py` — existing-session 窄入口单元测试
  - `tests/cli/test_interactive_command.py` — existing-session 窄入口单元测试
  - `tests/README.md`
  - `docs/reviews/wu-cli-session-01-s5-implementation-codex.md`
- Excluded scope:
  - `docs/host/issues-implementation-control.md`（controller bookkeeping）
  - S1/S2/S3/S4/S6 slice 文件（不在 S5 scope）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项确认

**1. session resume 只解析已有 OPEN Session，不 create/ensure**

`_resolve_existing_session_target`（`session.py:332-390`）分两路：

- `--session-id`（`session.py:346-366`）：`host.get_session(session_id)` → NOT_FOUND 时包装为 `CliSessionUsageError` → 非 OPEN 时 `CliSessionUsageError("session is closed and cannot be resumed")`
- `--label + --kind`（`session.py:367-390`）：`slot_ref_for_cli_label(kind, label)` → `host.list_sessions()` → 匹配 `item.slot == slot` → 检查 `item.status is not SessionStatus.OPEN` → CLOSED 抛 `CliSessionUsageError` → 无匹配抛 `CliSessionUsageError("no session found...")`

整个 `session.py` 无 `create_session`、`ensure_session`、`ensure_or_create_entrypoint_session` 调用。无 `get_session_by_label` 新增。无 `dayu.host.durable.*` import。

测试覆盖（`test_session_command.py`）：
- `test_session_resume_closed_session_returns_usage_error_without_submit`（行 823）：CLOSED → `EXIT_USAGE_ERROR`，`host.calls == ["get_session:session-closed"]`，`host.submit_requests == []`
- `test_session_resume_missing_label_returns_usage_error_without_create`（行 865）：缺失 label → `EXIT_USAGE_ERROR`，`host.calls == ["list_sessions"]`，`host.submit_requests == []`

**2. session.py 只做 selector resolution / mode 校验 / 路由**

`_run_session_resume`（`session.py:235-289`）的职责拆解：

1. `_require_resume_mode(args.mode)` → prompt 或 interactive（`session.py:246`）
2. prompt 模式：`_require_resume_prompt(args)` + `_prepare_prompt_existing_session_execution(...)` + `_resolve_existing_session_target(...)` + `_execute_prompt_on_existing_session(...)`（`session.py:247-269`）
3. interactive 模式：`_reject_interactive_resume_prompt(args)` + `_prepare_interactive_existing_session_execution(...)` + `_resolve_existing_session_target(...)` + `_execute_interactive_on_existing_session(...)`（`session.py:270-289`）

`session.py` 未复制 submit/watch/cancel 业务路径。所有 submit 逻辑仍在 `prompt.py:_submit_prompt_turn_handling_sigint`（行 323）和 `interactive.py:_run_interactive_repl` 中。

**3. prompt.py / interactive.py existing-session 窄入口复用原逻辑**

`_prepare_prompt_existing_session_execution`（`prompt.py:177-241`）：
- `resolve_workspace_root` + `resolve_explicit_config_dir` → 原 prompt 路径
- `new_cli_invocation(command_name=..., scenario=..., ticker=...)` → `command_name` 由调用方注入（session/prompt）
- `prepare_entrypoint_runtime(scene_id=scenario, context_slot_values=_prompt_context_slot_values(ticker=ticker), ...)` → 原 runtime assembly
- `service_run_overrides_from_args(args, ...)` → 原 run overrides

`_execute_prompt_on_existing_session`（`prompt.py:244-272`）：
- `_submit_prompt_turn_handling_sigint(host=host, runtime=..., session_id=session_id, ...)` → 复用 SIGINT cancel
- `render_prompt_terminal_result(terminal)` → 复用 terminal render

默认 `_run_prompt_command_async`（`prompt.py:148-174`）仍先 `_ensure_prompt_session` 再 `_execute_prompt_on_existing_session`，默认行为未变。

交互式同理：`_run_interactive_command_async`（`interactive.py:190-221`）仍先 `_ensure_interactive_session` 再 `_execute_interactive_on_existing_session`。

**4. --session-id 用 get_session；label + kind 用 list_sessions + S3 slot truth**

- `--session-id` → `host.get_session(session_id)`（`session.py:353`），NOT_FOUND → `CliSessionUsageError`（行 355-356）
- `--label + --kind` → `slot_ref_for_cli_label(kind, label)`（行 375，复用 S3 helper）→ `host.list_sessions()`（行 376）→ 匹配 `item.slot == slot`（行 378）
- CLOSED 两路均抛 `CliSessionUsageError` 且不 submit（`session.py:358-360`、`session.py:379-382`）
- 缺失 label → `CliSessionUsageError("no session found...")`（`session.py:388-390`）

**5. Submit TOCTOU HostApiError 包含完整上下文**

`_resume_host_error_message`（`session.py:572-589`）：
```
"dayu-cli session resume: "
f"selector={target.selector} session_id={target.session_id} "
f"{_host_error_context(error)}"
```
输出格式：`selector=... session_id=... host_code=... host_message=...`

测试 `test_session_resume_by_label_toctou_error_includes_selector_and_host_context`（`test_session_command.py:907-964`）断言：
- `"--label proj.v1 --kind prompt" in captured.err` — 原始 selector
- `"session-A" in captured.err` — resolved session_id
- `"invalid_state" in captured.err` — Host error code
- `"session closed before submit" in captured.err` — Host error message

**6. Prompt/interactive 参数校验正确**

- `_require_resume_prompt`（`session.py:477-492`）：`--mode prompt` 时 `args.session_prompt` 必填且非空白，否则 `CliSessionUsageError`
- `_reject_interactive_resume_prompt`（`session.py:495-506`）：`--mode interactive` 时 `args.session_prompt` 必须为 `None`，否则 `CliSessionUsageError`
- Parser 中 `--ticker` 已添加到 resume action（`arg_parsing.py:559`），与 prompt/interactive 业务上下文槽位对齐
- `_require_resume_mode`（`session.py:459-474`）：非 prompt/interactive → `CliSessionUsageError`

**7. FollowupBehavior.QUEUE，不做 steer / wait-resume / 旧 Agent 恢复**

- `prompt.py:364`：`behavior=FollowupBehavior.QUEUE, target_run_id=None`
- `interactive.py:463`：`behavior=FollowupBehavior.QUEUE, target_run_id=None`
- `session.py` 无 `FollowupBehavior.STEER`、无 `resolve_wait`、无 Run/Attempt 恢复

**8. 测试覆盖真实风险**

| 测试 | 覆盖风险 |
|---|---|
| `test_session_resume_prompt_by_session_id_resolves_and_submits_without_create` | `--session-id` → get_session → submit，不 create |
| `test_session_resume_interactive_by_label_resolves_and_reuses_session` | `--label` → list resolve → multi-turn 复用 |
| `test_session_resume_closed_session_returns_usage_error_without_submit` | CLOSED → fail fast，不 submit |
| `test_session_resume_missing_label_returns_usage_error_without_create` | 缺失 label → 不 create/ensure |
| `test_session_resume_by_label_toctou_error_includes_selector_and_host_context` | TOCTOU submit 错误完整上下文 |
| prompt/interactive existing-session 窄入口单元测试（`test_prompt_command.py:562`、`test_interactive_command.py:583`） | 窄入口独立可测 |

**9. Cross-module private import 符合 plan stop condition**

`session.py:36-45` 从 `prompt.py` 和 `interactive.py` import 私有符号：
```python
from dayu.cli.commands.interactive import (
    CliInteractiveUsageError,
    _execute_interactive_on_existing_session,
    _prepare_interactive_existing_session_execution,
)
from dayu.cli.commands.prompt import (
    CliCommandUsageError,
    _execute_prompt_on_existing_session,
    _prepare_prompt_existing_session_execution,
)
```

这些 import 是 CLI 命令包内部的 sibling module 依赖，符合 plan Slice S5 stop condition：先在 prompt.py/interactive.py 内拆出窄入口（`_prepare_*_existing_session_execution` + `_execute_*_on_existing_session`），再让 session.py 编排 selector + mode + 窄入口路由。session.py 没有直接组装 Service runtime 或 Host submit request，没有复制 submit/watch/cancel 业务路径。

**10. docstring / 类型签名 / AGENTS**

- 所有新增函数均有中文 docstring
- 无 `Any`、`object`、裸 dict/list 签名
- 无反向依赖
- 无兼容 wrapper
- `_PreparedPromptExistingSessionExecution`（`prompt.py:84-97`）与 `_PreparedInteractiveExistingSessionExecution`（`interactive.py:83-84`）为 typed dataclass，不承载 God object 职责
- pyright: 0 errors（implementation report 记录）

## Open Questions

无。

## Residual Risk

- `session resume --label` 的 list-resolve 与 submit 之间存在 plan 明确允许的 TOCTOU 窗口；S5 已在 submit HostApiError 输出中保留 selector、resolved session_id 与 Host code/message，最终状态以 Host submit precondition 为真源。
- `session resume` 不是 Host wait-resume，不恢复旧 Agent / Runner / Attempt。
- `session.py` 对 prompt.py/interactive.py 的私有符号 import 是 CLI 命令包内部的 sibling module 耦合；若未来 prompt.py/interactive.py 重构窄入口签名，session.py 的 import 需要同步更新。此耦合已被 plan Slice S5 stop condition 明确覆盖。
- 仅运行了 S5 指定 CLI 测试（57 passed + 35 arg_parsing passed）与全项目 pyright；未运行全量 pytest。
