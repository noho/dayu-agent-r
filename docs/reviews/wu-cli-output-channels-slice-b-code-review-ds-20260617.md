# Code Review — Slice B: `prompt --detail/--no-detail`

## Scope

- Mode: current changes (Slice B only)
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/wu-cli-output-channels-slice-b-code-review-ds-20260617.md`
- Included scope:
  - `dayu/cli/arg_parsing.py` — `ParsedCliArgs.detail` 字段与 `--detail`/`--no-detail` 互斥组注册。
  - `dayu/cli/commands/prompt.py` — `detail` 参数从 parse 结果到 activity renderer 创建、`_submit_prompt_turn_handling_sigint` 的 `on_activity` 注册与 cancel 提示的全链路。
  - `tests/cli/test_arg_parsing.py` — parser 级正交性、互斥、默认值测试。
  - `tests/cli/test_prompt_command.py` — 集成测试：默认 no-detail、显式 detail、非 TTY detail、activity 不进入 `--log-file`、Ctrl+T toggle、Esc cancel。
  - `tests/README.md` — 测试覆盖事实同步。
  - `docs/reviews/wu-cli-output-channels-slice-b-implementation-20260617.md` — 实现报告。
- Excluded scope: Slice A（`--log-file`）、Slice C（interactive run view）、Host/Engine/Service 内部实现。
- Reference docs:
  - `CLAUDE.md` — 项目指令与约束。
  - `docs/reviews/wu-cli-output-channels-plan-20260617.md` — 已接受 plan。
- Parallel review coverage: 无，单 reviewer 全链路走读。

## Review method summary

沿 `parse_cli_args → run_prompt_command → _execute_prompt_on_existing_session → _submit_prompt_turn_handling_sigint → _cancel_prompt_turn_after_local_request` 完整主链路逐行走读，并检查 `session resume --mode prompt` 路径的 `detail` 默认值传递。对照 plan 检查每个 implementation decision 的执行情况。

## Findings

未发现实质性问题。

逐项验证结论如下：

### 1. 默认 no-detail 确实不注册 activity

- **入口**: `_run_prompt_command_async` (`prompt.py:161-188`)
- **参数链**: `args.detail` (默认 `False`, `arg_parsing.py:250`) → `detail=args.detail` (`prompt.py:187`) → `activity_renderer=_new_detail_activity_renderer() if detail else None` (`prompt.py:286`) → `renderer = activity_renderer` (`prompt.py:391`) → `on_activity=None if renderer is None else renderer.record` (`prompt.py:418`)
- **结论**: 当 `detail=False` 时，`on_activity=None` 传入 Service helper。Service helper 不会调用 `None` callback，因此不会产生任何 activity 格式化、去重或输出开销。
- **验证测试**: `test_prompt_default_no_detail_suppresses_activity_and_keeps_final_answer_stdout` (test_prompt_command.py:905-931) 通过 _FakeHost 推送 activity event 后断言 stderr 不含 `Activity:`，间接验证了 `on_activity` 未注册。

### 2. `--detail` 强制 `enabled=True` 且不污染 `--log-file`

- **入口**: `_new_detail_activity_renderer` (`prompt.py:302-314`)
- **创建参数**: `CliActivityRendererOptions(visible=True, enabled=True)` — 绕过 `CliActivityRenderer.__init__` 的 `isatty()` 自动检测 (`activity.py:70-76`)，在非 TTY 场景（如 pytest 捕获流、管道）也强制输出。
- **输出通道**: activity 始终写 `sys.stderr`（`activity.py:69`），不经过 Python logging 体系。`--log-file` 只 redirect `dayu.runtime.log` 的 handler stream，不触及 `CliActivityRenderer` 的 stderr 写入。
- **验证测试**: `test_prompt_detail_outputs_activity_for_non_tty_and_keeps_final_answer_stdout` (test_prompt_command.py:934-964) 验证非 TTY 下 `--detail` 输出 activity；`test_prompt_detail_activity_does_not_enter_log_file` (test_prompt_command.py:967-1005) 验证 `--detail --log-file <path>` 时 activity 只在 stderr、不在日志文件。

### 3. `--debug`/`--verbose` 不打开 detail

- **Parser 层隔离**: `--detail`/`--no-detail` 只在 `_register_prompt_command` 的 prompt 命令子解析器中注册 (`arg_parsing.py:444-458`)，使用互斥组。`--debug`/`--verbose` 等日志 flag 在 `_build_global_arguments_parent` 的全局父解析器中注册 (`arg_parsing.py:339-370`)，通过不同的 `dest` 字段写入 `log_level`。
- **参数语义分离**: `detail` (bool) 控制 UI activity 展示；`log_level` (str) 控制诊断日志等级。parser 层不存在隐式联动——没有任何代码在 `log_level` 变更时修改 `detail`，反之亦然。
- **验证测试**: `test_prompt_detail_flags_are_orthogonal_to_log_level` (test_arg_parsing.py:922-949) 参数化覆盖 5 种组合，包括 `--verbose` → `detail=False`、`--debug` → `detail=False`、`--detail --verbose` → `detail=True, log_level=verbose`。`test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout` (test_prompt_command.py:791-835) 验证 `--verbose`/`--debug` 下 activity 不出现。

### 4. existing-session / session resume 保持语义

- **`_execute_prompt_on_existing_session` 签名**: `detail: bool = False` (`prompt.py:259-265`)。参数默认值 `False` 与 namespace 默认值一致。
- **prompt 命令调用**: `detail=args.detail` 显式传入 (`prompt.py:187`)。
- **session resume 调用**: `session.py:258-263` 调用 `_execute_prompt_on_existing_session` 时**不传 `detail`**，使用默认值 `False`。这与 plan 一致——`session resume` 的 parser 未注册 `--detail`/`--no-detail`（`arg_parsing.py:577-597`），用户无法在 resume 场景下请求 activity 显示。
- **语义保持**: `session resume --mode prompt` 总是安静模式（无 activity），与 plan 中 "`--detail` 只属于 `prompt` 命令" 的设计一致。resume 的核心语义（在已有 Session 上 submit followup，不 create/ensure）未被 `detail` 改动影响。
- **验证测试**: `test_prompt_existing_session_execution_does_not_create_or_ensure` (test_prompt_command.py:730-788) 验证 existing-session 路径不调用 create/ensure，且 submit 参数正确。该测试不传 `detail`（默认 `False`），与生产 `session resume` 路径一致。

### 5. cancel activity 提示只在 detail 时输出

- **`render_cancel_requested` 调用点**: `_cancel_prompt_turn_after_local_request` (`prompt.py:496-497`)，有 `if activity_renderer is not None:` 门禁。
- **`render_local_exit_after_cancel` 调用点**: `_cancel_prompt_run_waiting_for_terminal_or_second_sigint` (`prompt.py:556-557`)，有 `if activity_renderer is not None:` 门禁。
- **`renderer.close()`**: `_submit_prompt_turn_handling_sigint` 的 `finally` 块 (`prompt.py:458-459`)，有 `if renderer is not None:` 门禁。
- **`renderer` 来源**: `renderer = activity_renderer` (`prompt.py:391`)，而 `activity_renderer` 只在 `detail=True` 时非 `None` (`prompt.py:286`)。
- **结论**: 所有 cancel 相关 UI 输出（`"Activity: cancel requested"`、`"Activity: cancelling; local process exiting"`）都只在实际创建了 `CliActivityRenderer` 时产生，即 `detail=True` 时。
- **验证测试**: `test_prompt_esc_requests_cancel_after_run_id` (test_prompt_command.py:1106-1151) 在 detail 模式下验证 cancel prompt 输出含 `"Activity: cancel requested"`。`test_prompt_sigint_before_run_id_returns_local_interrupt` (test_prompt_command.py:1369-1407) 在默认 no-detail 模式下（未传 `activity_renderer`）验证 cancel 不发 Host cancel 且不尝试输出 cancel 提示。

### 6. 测试覆盖真实路径

| 测试用例 | 文件:行号 | 覆盖的路径 |
|---|---|---|
| `test_prompt_detail_defaults_to_no_detail` | test_arg_parsing.py:909-919 | parser 默认值 |
| `test_prompt_detail_flags_are_orthogonal_to_log_level` | test_arg_parsing.py:922-949 | 5 种 flag 组合 |
| `test_prompt_detail_flags_are_mutually_exclusive` | test_arg_parsing.py:952-962 | 互斥组 rejection |
| `test_prompt_command_outputs_fast_live_terminal_and_converts_requests` | test_prompt_command.py:658-727 | prompt 主路径（无 activity 断言，因默认 no-detail） |
| `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout` | test_prompt_command.py:791-835 | `--verbose`/`--debug` 不输出 activity |
| `test_prompt_default_no_detail_suppresses_activity_and_keeps_final_answer_stdout` | test_prompt_command.py:905-931 | 默认 no-detail 不输出 activity |
| `test_prompt_detail_outputs_activity_for_non_tty_and_keeps_final_answer_stdout` | test_prompt_command.py:934-964 | `--detail` 非 TTY 输出 activity |
| `test_prompt_detail_activity_does_not_enter_log_file` | test_prompt_command.py:967-1005 | `--detail --log-file` 隔离 |
| `test_prompt_sigint_after_run_id_cancels_host_run` | test_prompt_command.py:1008-1061 | SIGINT cancel 路径（默认 no-detail） |
| `test_prompt_ctrl_t_toggles_running_activity_without_cancel` | test_prompt_command.py:1063-1103 | Ctrl+T toggle（detail 模式） |
| `test_prompt_esc_requests_cancel_after_run_id` | test_prompt_command.py:1106-1151 | Esc cancel（detail 模式，含 cancel 提示断言） |
| `test_prompt_second_sigint_exits_after_cancel_request` | test_prompt_command.py:1154-1192 | 二次 SIGINT 本地退出（detail 模式） |
| `test_prompt_cancel_terminal_wins_over_second_sigint` | test_prompt_command.py:1195-1227 | cancel terminal 竞争优先级 |
| `test_prompt_sigint_before_run_id_returns_local_interrupt` | test_prompt_command.py:1369-1407 | Run accepted 前 SIGINT（默认 no-detail） |
| `test_prompt_existing_session_execution_does_not_create_or_ensure` | test_prompt_command.py:730-788 | existing-session 路径（默认 no-detail） |

覆盖完整性评估：
- ✅ Parser 默认值、显式值、互斥、与 log level 正交。
- ✅ 集成路径：默认 no-detail 抑制 activity；`--detail` 非 TTY 输出；activity 不进入 `--log-file`。
- ✅ Cancel 路径：SIGINT before/after run_id、Esc cancel、二次 SIGINT 本地退出、cancel terminal 竞争。
- ✅ 运行态按键：Ctrl+T toggle（含 visible 状态断言）、Esc cancel（含 cancel 提示断言）。
- ✅ Existing-session 执行：不 create/ensure，submit 参数正确。
- ⚠️ 非实质性缺口：`session resume --mode prompt` 路径未单独覆盖"activity event 到达但不输出"的行为，但该路径与 `prompt` 命令复用同一 `_execute_prompt_on_existing_session(detail=False)`，代码路径等价；`test_prompt_default_no_detail_suppresses_activity_and_keeps_final_answer_stdout` 已覆盖同语义行为。
- ⚠️ 非实质性缺口：Ctrl+T 在 no-detail 模式下是静默 no-op——`renderer is None` 时不做任何反馈。当前行为合理（没有可 toggle 的内容），但用户在 no-detail 模式按下 Ctrl+T 得不到任何提示。这是 UX 偏好问题，不是 correctness issue。

## Open Questions

- 无。

## Residual Risk

- **`session resume` 永远不显示 activity**：`session resume` parser 未注册 `--detail`，且 `_run_session_resume` 调用 `_execute_prompt_on_existing_session` 时不传 `detail`。这是 plan 的设计决策（`--detail` 只属于 `prompt` 命令），当前实现一致。但如果未来有用户在 resume 场景需要 activity 显示，需要先扩展 `session resume` parser 并传递 `detail` 参数。当前无阻塞风险。
- **Ctrl+T 在 no-detail 模式下的静默行为**：低风险 UX 问题，不影响 correctness。如果后续有用户反馈，可以在 no-detail 模式输出一行提示（如 `"Activity display is disabled; use --detail to enable"`）。
- **Service helper `on_activity=None` 的 null-safety**：本 review 未走读 `dayu.service.entrypoint_runtime.submit_entrypoint_turn_and_wait` 内部实现。当前所有调用方在 `detail=False` 时正确传入 `None`，但如果 Service helper 未正确处理 `None` callback，可能导致 `TypeError`。从实现报告看，81 个测试全部通过（含 Service 路径），此风险实际上已被集成测试消除。

## Compliance check

对照 `CLAUDE.md` 约束检查：

- 分层架构：`prompt.py` 通过 Host public API 和 Service helper 访问下层，未反向依赖。✅
- 类型安全：`detail: bool` 类型明确，无 `Any`/`object`/无类型签名。✅
- Docstring：所有新增/修改函数提供中文 docstring。✅
- 禁止魔法值：`PROMPT_TURN_INDEX` 等常量定义为 `Final`。✅
- 兼容性：未引入兼容性 re-export/wrapper。✅
- 测试迁移：测试跟随实现边界迁移，未保留旧测试兼容逻辑。✅
