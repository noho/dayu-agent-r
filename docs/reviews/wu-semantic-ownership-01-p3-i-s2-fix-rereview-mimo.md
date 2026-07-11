# P3-I S2 Fix Re-Review

## Scope

- Mode: current changes (uncommitted S2 fix changes only)
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-fix-rereview-mimo.md`
- Included scope:
  - `dayu/cli/session_execution.py` — 三处 cursor 推进条件变更
  - `tests/cli/test_prompt_command.py` — 新增 2 个测试 + 1 个 helper
  - `tests/cli/test_interactive_command.py` — 新增 4 个测试 + 2 个 helpers
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-ds.md` — DS 原始 review
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-fix-codex.md` — Codex fix report
- Excluded scope: S1 public entrypoints、README、Host/Engine/Service 代码、docs/cli_ci*、旧 code-review 文件
- Parallel review coverage: 无

## Review Sources

- DS Review: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-ds.md`
- Codex Fix Report: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-fix-codex.md`
- MiMo Original Review: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-mimo.md`

## DS-F1 验证：interactive `terminal is None` cursor 不推进测试

**状态：✅ 已关闭**

**修复内容**：
- 在 `test_interactive_repl_returns_130_on_second_sigint` 中增加了 cursor 断言
- 断言 cursor 停留在 `OutboxTerminalCursor(event_sequence=0)` 且 `seen_terminal_event_ids == ()`

**代码变更** (`tests/cli/test_interactive_command.py`):
```python
cursor_record = await read_cli_terminal_cursor(
    workspace_root=tmp_path,
    session_id="session-1",
)
assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=0)
assert cursor_record.seen_terminal_event_ids == ()
```

**验证**：
- 测试通过 ✅
- 覆盖了 interactive REPL 中第二次 SIGINT（本地退出，`terminal is None`）路径 ✅
- 与 prompt 路径的 `test_prompt_sigint_before_run_id_does_not_advance_terminal_cursor` 对称 ✅

## DS-F2 验证：cursor 写失败传播测试

**状态：✅ 已关闭**

**修复内容**：
新增了三个 cursor 写入失败传播测试：

1. **`test_interactive_startup_cursor_write_failure_propagates_after_terminal_render`**
   - mock `advance_cli_terminal_cursor` 抛出 `CliTerminalCursorError`
   - 断言异常被传播（`pytest.raises(CliTerminalCursorError, match="cursor write failed")`）
   - 覆盖 startup reconnect 路径 ✅

2. **`test_interactive_turn_cursor_write_failure_propagates_after_terminal_render`**
   - 同上，覆盖 interactive turn 路径 ✅

3. **`test_prompt_cursor_write_failure_propagates_after_terminal_render`**
   - 同上，覆盖 prompt 路径 ✅

**测试验证**：
```
tests/cli/test_prompt_command.py::test_prompt_cursor_write_failure_propagates_after_terminal_render PASSED
tests/cli/test_interactive_command.py::test_interactive_startup_cursor_write_failure_propagates_after_terminal_render PASSED
tests/cli/test_interactive_command.py::test_interactive_turn_cursor_write_failure_propagates_after_terminal_render PASSED
```

## 代码变更验证

### `execute_prompt_on_session` (session_execution.py:371-380)

**旧代码**：
```python
if render_exit_code == EXIT_SUCCESS:
    await advance_cli_terminal_cursor(...)
return render_exit_code
```

**新代码**：
```python
await advance_cli_terminal_cursor(...)
return render_exit_code
```

**验证**：
- `terminal is None` 路径：保持原行为，直接返回 `EXIT_KEYBOARD_INTERRUPT`，不推进 cursor ✅
- `terminal is not None` 路径：render → advance cursor → return exit code ✅
- cursor 写入异常：不捕获，向上抛出 ✅
- renderer exit code 不受 cursor 推进影响 ✅

### `_run_existing_session_startup_reconnect` (session_execution.py:520-530)

**旧代码**：
```python
render_exit_code = render_interactive_terminal_result(terminal)
if render_exit_code != EXIT_SUCCESS:
    return render_exit_code
await advance_cli_terminal_cursor(...)
```

**新代码**：
```python
render_exit_code = render_interactive_terminal_result(terminal)
await advance_cli_terminal_cursor(...)
if render_exit_code != EXIT_SUCCESS:
    return render_exit_code
```

**验证**：
- cursor 推进发生在 exit check 之前 ✅
- 即使 renderer 返回非 `EXIT_SUCCESS`，cursor 也会推进 ✅
- cursor 写入异常：不捕获，向上传播 ✅

### `_run_interactive_repl` (session_execution.py:847-861)

**旧代码**：
```python
render_exit_code = render_interactive_terminal_result(terminal)
if render_exit_code != EXIT_SUCCESS:
    return render_exit_code
await advance_cli_terminal_cursor(...)
```

**新代码**：
```python
render_exit_code = render_interactive_terminal_result(terminal)
await advance_cli_terminal_cursor(...)
if render_exit_code != EXIT_SUCCESS:
    return render_exit_code
```

**验证**：
- cursor 推进发生在 exit check 之前 ✅
- `effective_run_view` 路径和 `render_interactive_terminal_result` 路径都做了相同修改 ✅
- cursor 写入异常：不捕获，向上传播 ✅

## 测试覆盖验证

### Exit Code Mapping

renderer exit code 不受 cursor 推进影响。对照 `dayu/cli/output.py` 的映射：

| HostTerminalStatus | Prompt exit code | Interactive exit code |
|---|---|---|
| `FAILED` | `EXIT_FAILURE` (1) | `EXIT_SUCCESS` (0) |
| `CANCELLED` | `EXIT_KEYBOARD_INTERRUPT` (130) | `EXIT_SUCCESS` (0) |
| `LOST` | `EXIT_FAILURE` (1) | `EXIT_FAILURE` (1) |

测试参数化中的 `expected_exit_code` 与上述映射一致 ✅

### 新增测试覆盖

| 测试 | 覆盖路径 | 断言 |
|---|---|---|
| `test_prompt_existing_session_advances_terminal_cursor_after_rendering_non_success_terminal` | prompt 路径 | exit_code + cursor 推进 |
| `test_prompt_cursor_write_failure_propagates_after_terminal_render` | prompt 路径 | cursor 异常传播 |
| `test_prompt_sigint_before_run_id_does_not_advance_terminal_cursor` | prompt terminal=None | exit_code + cursor 不推进 |
| `test_interactive_startup_reconnect_advances_terminal_cursor_after_rendering_non_success_terminal` | startup 路径 | exit_code + cursor 推进 |
| `test_interactive_startup_cursor_write_failure_propagates_after_terminal_render` | startup 路径 | cursor 异常传播 |
| `test_interactive_existing_session_advances_terminal_cursor_after_rendering_non_success_turn` | interactive turn 路径 | exit_code + cursor 推进 |
| `test_interactive_turn_cursor_write_failure_propagates_after_terminal_render` | interactive turn 路径 | cursor 异常传播 |
| `test_interactive_repl_returns_130_on_second_sigint` (扩展) | interactive terminal=None | exit_code + cursor 不推进 |

## 新问题检查

**未发现新问题** ✅

- `_raise_cli_terminal_cursor_error` 在两个测试文件中重复定义：测试文件中的私有 helper，保持每个测试文件自包含是合理的
- `_startup_terminal_result` helper：用于构造 startup terminal result，符合测试模式
- 退出码映射：与 renderer policy 一致
- 测试全部通过：100 passed
- pyright 类型检查：0 errors

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **Cursor 写入失败后已渲染 terminal 可能重复展示**：这是 plan 明确接受的 local-delivery trade-off，当前测试已覆盖该行为的传播路径

## Verdict

**pass** — DS-F1 和 DS-F2 均已正确关闭，测试覆盖完整，未引入新问题。生产代码变更符合 plan 要求，三个执行路径的 cursor 推进逻辑正确，Host/Service 终端事实未被修改。
