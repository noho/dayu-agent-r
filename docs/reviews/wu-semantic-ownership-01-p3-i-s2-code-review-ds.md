# Code Review

## Scope

- Mode: current changes (uncommitted S2 changes only)
- Branch: phaseflow/host-issues-control
- Base: main
- Output file: docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-ds.md
- Work unit: WU-SEMANTIC-OWNERSHIP-01 P3-I
- Slice: S2 CLI Terminal Cursor After Successful Render
- Included scope:
  - `dayu/cli/session_execution.py` (3 sites: prompt, startup reconnect, interactive repl)
  - `tests/cli/test_prompt_command.py` (2 new tests)
  - `tests/cli/test_interactive_command.py` (2 new tests + 1 helper)
- Excluded scope: S1 public entrypoints (committed), unrelated `docs/cli_ci*`, old code-review files
- Parallel review coverage: 无

### Review sources

- Plan: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`
- Implementation report: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-controller-validation.md`

## Findings

### 1-未修复-低-交互式 `terminal is None` 路径缺少显式 cursor 不推进断言

- **入口/函数**: `_run_interactive_repl` → `_submit_interactive_turn_handling_sigint` → `_cancel_interactive_turn_after_first_sigint` → `_wait_for_run_id_or_local_exit`
- **文件(行号)**: `tests/cli/test_interactive_command.py`，缺少等价于 prompt 路径 `test_prompt_sigint_before_run_id_does_not_advance_terminal_cursor` 的交互式测试
- **输入场景**: 交互式 REPL 中第二次 SIGINT（本地退出，`terminal is None`）
- **实际分支**: `_run_interactive_repl` 第 847 行 `if terminal is None: return EXIT_KEYBOARD_INTERRUPT` 在 cursor 推进代码（第 853 行）之前提前返回
- **预期行为**: cursor 不得推进
- **实际行为**: cursor 确实不会推进——代码结构保证了提前返回在 cursor 推进之前。现有测试 `test_interactive_repl_returns_130_on_second_sigint` 验证了退出码为 `EXIT_KEYBOARD_INTERRUPT`，但未断言 cursor record 仍为空
- **直接证据**: `dayu/cli/session_execution.py` 第 847-848 行（提前返回）与第 853-858 行（cursor 推进）的执行顺序；`tests/cli/test_interactive_command.py` 第 1792-1823 行测试只断言 `exit_code == EXIT_KEYBOARD_INTERRUPT`，无 cursor 断言
- **影响**: 仅测试覆盖缺口——代码行为正确，但交互式路径缺少对 cursor 不变量的直接回归保护
- **建议改法和验证点**: 在 `test_interactive_repl_returns_130_on_second_sigint` 增加 `read_cli_terminal_cursor` 断言，或新增独立测试 `test_interactive_second_sigint_does_not_advance_terminal_cursor`，参考 prompt 路径的 `test_prompt_sigint_before_run_id_does_not_advance_terminal_cursor` 写法
- **修复风险（低）**: 纯测试补充，不修改生产代码
- **严重程度（低）**: 代码行为正确，仅测试覆盖缺口

### 2-未修复-低-cursor 写入失败异常传播路径无测试覆盖

- **入口/函数**: `execute_prompt_on_session` / `_run_existing_session_startup_reconnect` / `_run_interactive_repl` 中的 `await advance_cli_terminal_cursor(...)`
- **文件(行号)**: `dayu/cli/session_execution.py` 第 374、522、853 行
- **输入场景**: cursor store 写入失败（磁盘满、权限不足、JSON 腐坏等）
- **实际分支**: `advance_cli_terminal_cursor` 抛出 `CliTerminalCursorError`，三个调用点均未捕获，异常向上传播
- **预期行为**: 异常传播为本地 CLI delivery persistence failure，renderer 退出码不被返回
- **实际行为**: 异常确实传播——三个调用点均无 `try/except` 包裹 `advance_cli_terminal_cursor`。但无测试注入 cursor 写入失败来证明：(1) 异常不被吞，(2) renderer 退出码不被替代返回
- **直接证据**: `dayu/cli/session_execution.py` 第 374-379、522-527、853-858 行均直接 `await advance_cli_terminal_cursor(...)` 无异常处理；plan 第 100-101 行明确要求"propagate that exception as a local CLI delivery persistence failure"
- **影响**: 仅测试覆盖缺口——plan 将 cursor 写入失败后的重复展示风险标记为可接受的 local-delivery trade-off，但无回归测试保护该行为不被后续重构破坏（例如有人加 `try/except` 吞异常并返回 `render_exit_code`）
- **建议改法和验证点**: 新增参数化测试，mock `advance_cli_terminal_cursor` 为 `raise CliTerminalCursorError(...)`，断言异常不被捕获且 `render_exit_code` 不被返回
- **修复风险（低）**: 纯测试补充
- **严重程度（低）**: plan 已接受该 trade-off，当前代码行为正确

## Open Questions

无。

## Residual Risk

- **Cursor 写入失败后已渲染 terminal 可能重复展示**：这是 plan 明确接受的 local-delivery trade-off——cursor store 使用原子写入（`tempfile` + `os.replace`），corruption 风险低；重复展示比静默丢失 cursor 写入失败更安全
- **交互式 `terminal is None` 路径缺少 cursor 不变量测试**：见 Finding 1，代码结构正确但测试未显式覆盖
- **`InteractiveRunView.render_terminal_result` 退出码一致性**：已验证 `TerminalInteractiveRunView.render_terminal_result` 委托到 `render_interactive_terminal_result`，退出码语义一致；若未来新增其他 `InteractiveRunView` 实现，需确保其 `render_terminal_result` 返回与 `render_interactive_terminal_result` 一致的退出码语义，否则 `_run_interactive_repl` 的 `render_exit_code != EXIT_SUCCESS` 判断可能产生意外行为——此为 interface contract 风险，非本 slice 引入

## 逐项 Review Focus 验证

| Review Focus | 结论 | 证据 |
|---|---|---|
| cursor advances after render returns for prompt/startup/interactive all terminal statuses | ✅ 通过 | 三个站点均将 `advance_cli_terminal_cursor` 调用移到 `if render_exit_code == EXIT_SUCCESS` 条件之外（或移到 exit check 之前） |
| terminal None path does not advance cursor | ✅ 通过 | Prompt 第 371-372 行、Interactive 第 847-848 行提前返回在 cursor 代码之前；prompt 路径有显式测试验证 |
| cursor write exception remains uncaught local delivery persistence failure | ✅ 通过 | 三个调用点均无 `try/except`，`CliTerminalCursorError` 向上传播 |
| renderer exit code is returned unchanged after cursor advancement | ✅ 通过 | Prompt 用局部变量 `render_exit_code` 保存后返回；Startup/Interactive 在 cursor 推进后检查 `render_exit_code != EXIT_SUCCESS` |
| Host/Service terminal facts are not mutated or reconstructed | ✅ 通过 | 只读 `terminal.terminal_event_id`、`terminal.event_sequence`；不修改 `terminal_status`、`final_answer`、`error_message`、`cancel_reason` |
| startup reconnect loop advances cursor before returning non-success | ✅ 通过 | `_run_existing_session_startup_reconnect` 第 522 行 cursor 推进在第 528 行 exit check 之前 |
| tests prove non-success status cursor behavior and negative local interrupt behavior | ⚠️ 部分通过 | 非成功状态 cursor 推进：三个参数化测试覆盖 prompt/startup/interactive 的 FAILED/CANCELLED/LOST；负向本地中断：prompt 路径有显式测试，交互式路径缺 cursor 不变量断言（Finding 1） |
| no overbroad S1/README/Host/Service changes | ✅ 通过 | git diff 仅包含 `session_execution.py`、`test_prompt_command.py`、`test_interactive_command.py` |

## Verdict

**pass-with-findings** — 2 个低严重度 findings，均为测试覆盖缺口，无代码缺陷。实现严格遵循 plan，三个执行路径的 cursor 推进逻辑正确，Host/Service 终端事实未被修改。
