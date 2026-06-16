# Code Review: WU-CLI-SESSION-01 S5

## Scope

- Mode: current changes
- Branch: `wu-cli-session-01`
- Base: `653c9966` (accepted plan commit)
- Output file: `docs/reviews/code-review-wu-cli-session-01-s5-mimo-20260616.md`
- Included scope:
  - `dayu/cli/commands/session.py`
  - `dayu/cli/commands/prompt.py`
  - `dayu/cli/commands/interactive.py`
  - `dayu/cli/arg_parsing.py`
  - `tests/cli/test_session_command.py`
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_interactive_command.py`
  - `tests/README.md`
  - `docs/reviews/wu-cli-session-01-s5-implementation-codex.md`
- Excluded scope: `docs/host/issues-implementation-control.md`（controller bookkeeping）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Detail

### 1. session resume 是否只解析已有 OPEN Session，不 create/ensure

- `--session-id` selector：`_resolve_existing_session_target` 调用 `host.get_session(session_id)`（`session.py:353`），`NOT_FOUND` 时抛 `CliSessionUsageError`（`session.py:356`），`CLOSED` 时抛 `CliSessionUsageError("session is closed and cannot be resumed")`（`session.py:359-361`）。
- `--label + --kind` selector：调用 `host.list_sessions()` 后按 `item.slot == slot` 匹配（`session.py:376-378`），`CLOSED` 时抛 usage error（`session.py:379-382`），无匹配时抛 `"no session found for label ..."`（`session.py:388-390`）。
- 不调用 `create_session`、`ensure_session`、`get_session_by_label`。
- 测试 `test_session_resume_prompt_by_session_id_resolves_and_submits_without_create` 断言 `host.calls == ["get_session:session-1", "submit:session-1"]`（`test_session_command.py:754`）。
- 测试 `test_session_resume_closed_session_returns_usage_error_without_submit` 断言 `host.submit_requests == []`（`test_session_command.py:862`）。
- 测试 `test_session_resume_missing_label_returns_usage_error_without_create` 断言 `host.submit_requests == []`（`test_session_command.py:903`）。
- **结论**：只解析已有 OPEN Session，不 create/ensure。

### 2. session.py 是否只做 selector resolution / mode 校验 / 路由

- `_run_session_resume` 按 mode 分支：prompt 调用 `_prepare_prompt_existing_session_execution` + `_execute_prompt_on_existing_session`；interactive 调用 `_prepare_interactive_existing_session_execution` + `_execute_interactive_on_existing_session`（`session.py:246-289`）。
- session.py 不包含 submit、watch、cancel、SIGINT、terminal render 逻辑。
- **结论**：只做 selector / mode / 路由，未复制 prompt/interactive 业务路径。

### 3. prompt.py / interactive.py existing-session 窄入口是否复用原路径

- prompt.py：`_run_prompt_command_async`（默认入口）调用 `_prepare_prompt_existing_session_execution` → `_ensure_prompt_session` → `_execute_prompt_on_existing_session`（`prompt.py:157-174`）。session resume 直接调用同一个 `_execute_prompt_on_existing_session`（`session.py:258`），复用 `_submit_prompt_turn_handling_sigint` 和 `render_prompt_terminal_result`。
- interactive.py：`_run_interactive_command_async`（默认入口）调用 `_prepare_interactive_existing_session_execution` → `_ensure_interactive_session` → `_execute_interactive_on_existing_session`（`interactive.py:204-221`）。session resume 直接调用同一个 `_execute_interactive_on_existing_session`（`session.py:279`），复用 `_run_interactive_repl`。
- 默认 prompt/interactive 行为未变：两个默认入口仍先 create/ensure，再调用同一窄入口。
- **结论**：正确复用原 runtime、run overrides、SIGINT、watcher、terminal render。

### 4. FollowupBehavior.QUEUE，不做 steer / wait-resume

- prompt.py 提交使用 `behavior=FollowupBehavior.QUEUE`（`prompt.py:364`）。
- interactive.py 提交使用 `behavior=FollowupBehavior.QUEUE`（`interactive.py:463`）。
- 不使用 `STEER`，不调用 `wait-resume`，不恢复旧 Agent/Runner/Attempt。
- 测试 `test_prompt_existing_session_execution_does_not_create_or_ensure` 断言 `behavior is FollowupBehavior.QUEUE` 和 `target_run_id is None`（`test_prompt_command.py:584-585`）。
- **结论**：正确使用 QUEUE。

### 5. TOCTOU HostApiError stderr 是否包含 selector / session_id / Host context

- `_resume_host_error_message` 格式为 `"selector={target.selector} session_id={target.session_id} host_code=... host_message=..."`（`session.py:585-588`）。
- 测试 `test_session_resume_by_label_toctou_error_includes_selector_and_host_context` 断言 stderr 包含 `"--label proj.v1 --kind prompt"`、`"session-A"`、`"conflict"`（`test_session_command.py:907+`）。
- **结论**：TOCTOU 错误上下文完整。

### 6. prompt mode prompt 参数、interactive mode 拒绝 prompt、ticker 传递

- `_require_resume_prompt` 校验 `args.session_prompt` 非空（`session.py:485-491`）。
- `_reject_interactive_resume_prompt` 拒绝 `args.session_prompt is not None`（`session.py:503-506`）。
- `_prepare_prompt_existing_session_execution` 从 `args.ticker` 提取 ticker 并传入 `new_cli_invocation` 和 `_prompt_context_slot_values`（`prompt.py:205-214`）。
- `_prepare_interactive_existing_session_execution` 同样处理 ticker（`interactive.py:250-259`）。
- **结论**：参数校验和传递正确。

### 7. private helper cross-module import 是否过度耦合

- session.py 导入 `_execute_prompt_on_existing_session`、`_prepare_prompt_existing_session_execution`、`_execute_interactive_on_existing_session`、`_prepare_interactive_existing_session_execution`。
- plan S5 明确要求"先在原模块内拆出 execute-on-existing-session 窄入口"，stop condition 为"如果为了复用 prompt/interactive core 需要把大量私有状态跨模块导入，先在原模块内拆出窄入口"。
- session.py 不直接组装 Service runtime 或构造 Host submit request，只调用窄入口。
- **结论**：符合 plan stop condition，耦合程度在可接受范围内。

### 8. 类型签名 / docstring / AGENTS 约束

- 所有新增和修改函数均有完整中文 docstring。
- 无 `Any`、`object`、无类型参数或无类型返回值。
- `_ExistingSessionTarget` 和 `_PurgeTarget` 为 `frozen=True, slots=True` dataclass。
- `_session_context_slot_values` 返回 `dict[str, JsonValue]`。
- **结论**：符合 AGENTS 约束。

## Open Questions

无。

## Residual Risk

- `session resume --label` 的 list-resolve 与 submit 之间存在 TOCTOU，plan 已记录为可接受，Host submit precondition 是最终 truth。
- session.py 导入 prompt.py / interactive.py 的 `_` 前缀私有函数；当前耦合程度可控，但如果 prompt/interactive 的窄入口签名变化，session.py 需要同步修改。这是 plan 已接受的结构性耦合。
- 仅运行 S5 指定测试（57 passed + 35 passed）与全项目 pyright（0 errors），未运行全量 pytest。
