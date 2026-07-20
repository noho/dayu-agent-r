# WU-SEMANTIC-OWNERSHIP-01 P2-A Implementation Review - AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-A`
- Gate: implementation review
- Accepted plan commit: `38477f63`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-controller-validation.md`

Review files:
- `dayu/cli/session_execution.py`
- `dayu/cli/host_api_errors.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`
- `dayu/cli/commands/fins.py`
- `tests/cli/test_import_boundary.py`
- `tests/cli/test_session_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_fins_commands.py`
- `tests/README.md`

## Verdict

**pass-with-findings**

实现正确解决了 DS 03 / DS 10 / DS 11 的 root cause，owner boundary 清晰，无阻断性问题。有两个低严重性观察点。

## Findings

### F-1（低）：session.py generic HostApiError catch 使用 inline format 而非 helper

**证据：**

`dayu/cli/commands/session.py:171` 的 generic `Exception` catch 使用 `f"dayu-cli session {args.session_action}: {exc}"` inline format。同文件 `:162-169` 的 `HostApiError` catch 已使用 `format_host_api_error(COMMAND_SESSION, exc, action=args.session_action)` helper。

`dayu/cli/host_api_errors.py:65-75` 的 `format_host_api_error` 生成 `dayu-cli {command} {action}: {context_parts}` 格式，与 session.py 的 inline format 仅差 selector context 部分（generic catch 不需要 selector）。

**影响：** 当前行为一致。若未来 helper core format 内部格式变化（如分隔符、字段顺序），generic path 不会同步更新，产生文本不一致风险。风险极低，因 generic path 只在非 HostApiError 异常时触发，且不含 selector context。

**Owner boundary：** CLI presentation helper 是 `host_api_errors`；session.py generic path 选择不经过 helper，因为它处理的不是 `HostApiError`。

**建议修复位置：** 不阻断。可在后续 P2-B/P2-C 或日常 cleanup 中统一。

### F-2（信息）：测试直接访问 session_execution 下划线 helper

**证据：**

`tests/cli/test_prompt_command.py:1361` 调用 `session_execution._submit_prompt_turn_handling_sigint`；`:1452` 访问 `session_execution._PromptAcceptedRunState`；`:1469` 调用 `session_execution._cancel_prompt_turn_after_local_request`。

这些是 `session_execution` 模块自身的内部状态机 helper，测试覆盖了 SIGINT cancel 竞争、run-id accepted 后 cancel、二次 SIGINT 本地退出等边界场景。

**影响：** Controller validation 已明确判定："Tests that still exercise `dayu.cli.session_execution` private state-machine helpers are acceptable as same-owner implementation tests and do not reintroduce the original cross-command private import problem."

原始 plan 的约束是"测试引用旧私有 helper 的地方必须迁移到新 public helper，或改用 command main path"——该约束针对的是 prompt/interactive command 模块的旧 `_prepare_*` / `_execute_*` 私有 helper 被其它 command 模块测试跨模块引用的问题。当前测试引用的是 `session_execution` 自身的私有 helper，属于同模块同 owner 的实现测试，不违反 plan 意图。

**Owner boundary：** 无边界违反。

**建议：** 无需行动。若后续要提升 public path 覆盖密度，可考虑通过 command main path 间接覆盖这些边界，但不阻断当前实现。

## Accepted Plan Compliance

| Plan requirement | Status | Evidence |
|---|---|---|
| `session.py` 不从 prompt/interactive 导入下划线私有符号 | ✅ closed | AST test `test_import_boundary.py` 自动化守卫；`session.py:36-43` 只导入 public `CliCommandUsageError`、`build_prompt_context_slot_values`、`CliInteractiveUsageError`、`build_interactive_context_slot_values` |
| prompt/interactive 内部也调用新 public helper | ✅ closed | `prompt.py:104` 调用 `prepare_prompt_session_execution`；`prompt.py:122` 调用 `execute_prompt_on_session`；`interactive.py:107` 调用 `prepare_interactive_session_execution`；`interactive.py:121` 调用 `execute_interactive_on_session` |
| 旧 `_prepare_*` / `_execute_*` 已删除且无同名转发 | ✅ closed | grep 确认 prompt.py / interactive.py 无 `_prepare_*_existing_session_execution` 或 `_execute_*_on_existing_session` |
| `session resume` 不跨 command 私有边界 | ✅ closed | `session.py:63-68` 导入 `session_execution` public API；`:267` 调用 `prepare_prompt_session_execution`；`:282` 调用 `execute_prompt_on_session`；`:298` / `:309` 同理 |
| context slot 构造仍在 command module | ✅ closed | `prompt.py:193-214` 的 `build_prompt_context_slot_values` 仍由 prompt command 拥有；`interactive.py:195-202` 的 `build_interactive_context_slot_values` 仍由 interactive command 拥有；`session_execution` 只接收已构造的 `context_slot_values` |
| RuntimeDisplayController 职责仍清晰 | ✅ closed | `session_execution.py:591-594` 创建 `RuntimeDisplayController` 调用它但不替代其职责；`session_execution.py:864-868` 在 REPL finally 中只调用 `close_activity()` |
| Fins CLI 不再构造 `_missing_result_event()` | ✅ closed | grep 确认 `_missing_result_event` 已从 fins.py 删除；`:727` 改为抛 `FinsDirectStreamContractViolation` |
| CLI 不再制造 fake business RESULT | ✅ closed | `test_fins_commands.py:899` 断言 `"Fins failure" not in captured.err` |
| HostApiError helper 符合 accepted policy | ✅ closed | `host_api_errors.py:91-97`：显式 session id NOT_FOUND -> usage；其余 -> failure |
| prompt/interactive 单独捕获 HostApiError | ✅ closed | `prompt.py:86-88`；`interactive.py:82-84`；测试 `test_prompt_command.py:931`、`test_interactive_command.py:906` 覆盖 |
| AST import boundary test | ✅ closed | `test_import_boundary.py` AST-level 断言 `session.py` 不从 prompt/interactive 导入下划线符号 |

## Validation Notes

Controller validation 已运行完整验证矩阵，结果通过：

- `pytest tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py` → `128 passed, 3 warnings`
- `pytest tests/cli/test_import_boundary.py` → `1 passed`
- `pyright` → `0 errors, 0 warnings, 0 informations`
- `git diff --check` → passed
- 扩展验证 → `156 passed, 3 warnings`

MiMo review 确认验证命令和结果可信。

## Propagation Audit

实现 artifact 的 propagation audit 条目已逐项验证：

1. **Session execution path**：prompt/interactive/session resume → command-local args + context slot → `session_execution` public helper → `entrypoint_runtime` → Host public API → CLI renderer。✅ 无 cross-command private import。
2. **Fins direct RESULT path**：Fins producer → Service `_ensure_result_event` → CLI `_consume_fins_direct_events` → renderer 或 `FinsDirectStreamContractViolation`。✅ 缺 RESULT 业务 fallback 只在 Service。
3. **HostApiError path**：Host raises → `host_api_errors` formats → prompt/interactive/session stderr + exit code。✅ command modules 不各自重建映射。
4. **Durable / trace / memory / audit / LLM-facing**：✅ P2-A 未修改。

## Residual Risks

| Risk | Owner | Destination |
|---|---|---|
| F-1: session.py generic catch inline format 与 helper format 潜在不一致 | session command | P2-B/C 或日常 cleanup |
| P2-B memory/test hardening 未触碰 | P2-B owner | 后续 sub WU |
| P2-C fallback prompt source-of-truth 未触碰 | P2-C owner | 后续 sub WU |
| 未运行全仓 pytest | — | 按 accepted plan 只运行指定 CLI tests、import boundary、pyright |
