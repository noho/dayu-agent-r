# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main` (uncommitted changes only)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-mimo.md`
- Included scope:
  - `dayu/cli/session_execution.py` — 三处 cursor 推进条件变更
  - `tests/cli/test_prompt_command.py` — 新增 2 个测试
  - `tests/cli/test_interactive_command.py` — 新增 2 个测试 + 1 个 helper
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-controller-validation.md`
- Excluded scope: S1 public entrypoints、README、Host/Engine/Service 代码、docs/cli_ci*、旧 code-review 文件
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Detailed Walk-through

### `execute_prompt_on_session` (session_execution.py:371-380)

旧代码仅在 `render_exit_code == EXIT_SUCCESS` 时推进 cursor。新代码移除条件判断，render 后无条件推进 cursor，然后返回 renderer exit code。

- `terminal is None` 路径：保持原行为，直接返回 `EXIT_KEYBOARD_INTERRUPT`，不推进 cursor。✅
- `terminal is not None` 路径：render → advance cursor → return exit code。顺序正确。✅
- cursor 写入异常（`CliTerminalCursorError`）：不捕获，向上抛出。renderer exit code 不会被返回，因为异常发生在 return 之前。与 plan 要求一致。✅
- Host/Service terminal facts：仅读取 `terminal.terminal_event_id` 和 `terminal.event_sequence`，不修改任何 terminal 状态字段。✅

### `_run_existing_session_startup_reconnect` (session_execution.py:520-530)

旧代码：render → if non-success → return（不推进 cursor）→ advance cursor。新代码：render → advance cursor → if non-success → return。

- cursor 推进发生在非 success 判断之前。即使 renderer 返回非 `EXIT_SUCCESS`，cursor 也会推进。✅
- 多个 startup terminal 场景：每个 terminal 独立 render → advance cursor → 判断 exit code。如果某个 terminal 的 exit code 非 success，直接 return，但该 terminal 的 cursor 已经推进。✅
- cursor 写入异常：不捕获，向上传播。✅

### `_run_interactive_repl` (session_execution.py:850-861)

旧代码：render → if non-success → return → advance cursor → turn_index++。新代码：render → advance cursor → if non-success → return → turn_index++。

- cursor 推进和 turn_index 推进都发生在 non-success 判断之前。✅
- `effective_run_view` 路径和 `render_interactive_terminal_result` 路径都做了相同修改。✅
- `turn_index` 仅在 cursor 推进之后、且 render 成功（非 non-success）时才自增。✅

### Exit Code Mapping 验证

renderer exit code 不受 cursor 推进影响。对照 `dayu/cli/output.py` 的映射：

| HostTerminalStatus | Prompt exit code | Interactive exit code |
|---|---|---|
| `FAILED` | `EXIT_FAILURE` (1) | `EXIT_SUCCESS` (0) |
| `CANCELLED` | `EXIT_KEYBOARD_INTERRUPT` (130) | `EXIT_SUCCESS` (0) |
| `LOST` | `EXIT_FAILURE` (1) | `EXIT_FAILURE` (1) |

测试参数化中的 `expected_exit_code` 与上述映射一致。✅

### 测试覆盖分析

**test_prompt_existing_session_advances_terminal_cursor_after_rendering_non_success_terminal**
- 参数化：`FAILED`/`CANCELLED`/`LOST`
- 断言：exit_code == renderer policy exit code，cursor == event_sequence=2，seen_ids == ("terminal-run-1-2",)
- 覆盖：render 后 cursor 推进 + renderer exit code 不被改写。✅

**test_prompt_sigint_before_run_id_does_not_advance_terminal_cursor**
- 场景：submit 前 SIGINT，`terminal is None`
- 断言：exit_code == EXIT_KEYBOARD_INTERRUPT，cursor == event_sequence=0，seen_ids == ()
- 覆盖：negative case — 无 terminal 时不推进 cursor。✅

**test_interactive_startup_reconnect_advances_terminal_cursor_after_rendering_non_success_terminal**
- 参数化：`FAILED`/`CANCELLED`/`LOST`
- 断言：exit_code == renderer policy exit code，cursor == event_sequence=5，seen_ids == ("terminal-startup",)
- 覆盖：startup reconnect 路径 cursor 推进 + 非 success exit code 正确返回。✅

**test_interactive_existing_session_advances_terminal_cursor_after_rendering_non_success_turn**
- 参数化：`FAILED`/`CANCELLED`/`LOST`
- 断言：exit_code == renderer policy exit code，cursor == event_sequence=2，seen_ids == ("terminal-run-1",)
- 覆盖：interactive turn 路径 cursor 推进 + renderer exit code 不被改写。✅

### Scope 边界验证

- 无 Host/Service/Engine 代码变更。✅
- 无 README 变更。✅
- 无 S1 public entrypoint 变更。✅
- 仅修改 `session_execution.py` 和对应测试文件。✅

## Open Questions

无。

## Residual Risk

- 测试未覆盖 cursor 写入异常（`CliTerminalCursorError`）的传播行为。这是 plan 中明确记录的已知残余风险，当前不阻塞 ship。
- 测试未覆盖 render 调用本身抛异常时 cursor 不推进的行为（即 render 异常阻止 cursor 推进）。当前 render 函数实现不抛异常，风险低。
