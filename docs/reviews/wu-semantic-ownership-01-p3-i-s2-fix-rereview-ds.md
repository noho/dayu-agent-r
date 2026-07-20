# WU-SEMANTIC-OWNERSHIP-01 P3-I S2 Fix Re-Review (DS)

## Scope

- Mode: current changes (fix for DS-F1 and DS-F2)
- Branch: `phaseflow/host-issues-control`
- Base: previous S2 DS review (`wu-semantic-ownership-01-p3-i-s2-code-review-ds.md`)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-fix-rereview-ds.md`
- Re-review target: fix commit addressing DS-F1 and DS-F2 per controller adjudication
- Included scope:
  - `dayu/cli/session_execution.py` (3 cursor sites — S2 production change)
  - `tests/cli/test_prompt_command.py` (新增 DS-F2 cursor 写失败传播测试)
  - `tests/cli/test_interactive_command.py` (新增 DS-F1 cursor 断言 + DS-F2 cursor 写失败传播测试)
- Excluded scope: untracked `docs/cli_ci*`、旧 code-review 文件、S1 public entrypoints
- Review sources:
  - Original DS review: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-ds.md`
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-controller-adjudication.md`
  - Fix report: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-fix-codex.md`

## DS-F1 Closure — interactive `terminal is None` cursor 不推进断言

### 原始 Finding

> `test_interactive_repl_returns_130_on_second_sigint` 只断言 `exit_code == EXIT_KEYBOARD_INTERRUPT`，未断言 cursor record 仍为空。

### Fix 内容

在 `test_interactive_repl_returns_130_on_second_sigint` 末尾新增 cursor 断言（`tests/cli/test_interactive_command.py` 第 1979-1987 行）：

```python
cursor_record = await read_cli_terminal_cursor(
    workspace_root=tmp_path,
    session_id="session-1",
)
assert cursor_record.terminal_cursor == OutboxTerminalCursor(event_sequence=0)
assert cursor_record.seen_terminal_event_ids == ()
```

### 执行路径验证

`_run_interactive_repl` 第 847-848 行（生产代码）：

```python
if terminal is None:
    return EXIT_KEYBOARD_INTERRUPT
```

该提前返回在 cursor 推进代码（第 853-858 行）之前，结构保证了 `terminal is None` 时 cursor 不会被推进。测试新增的断言直接验证了这一不变量。

### 闭合判定: **已关闭** ✅

- 生产代码结构正确：`terminal is None` 提前返回在 cursor 推进之前（第 847 vs 853 行）。
- 测试断言有效：验证 cursor 保持初始状态 `OutboxTerminalCursor(event_sequence=0)` 且 `seen_terminal_event_ids` 为空。
- 该测试在 `pytest tests/cli/test_interactive_command.py` 中通过。

---

## DS-F2 Closure — prompt/startup/interactive 三个 cursor 写失败传播测试

### 原始 Finding

> `advance_cli_terminal_cursor` 在三个调用点均未捕获异常，异常确实向上传播。但无测试注入 cursor 写入失败来证明异常不被吞、renderer 退出码不被替代返回。

### Fix 内容

新增三个 cursor 写失败传播测试，外加测试辅助函数 `_raise_cli_terminal_cursor_error`：

| 测试 | 文件 | 覆盖路径 | 终端状态 |
|---|---|---|---|
| `test_prompt_cursor_write_failure_propagates_after_terminal_render` | `test_prompt_command.py` | `execute_prompt_on_session` | FAILED |
| `test_interactive_startup_cursor_write_failure_propagates_after_terminal_render` | `test_interactive_command.py` | `_run_existing_session_startup_reconnect` | LOST |
| `test_interactive_turn_cursor_write_failure_propagates_after_terminal_render` | `test_interactive_command.py` | `_run_interactive_repl` | LOST |

### 执行路径验证

#### Prompt 路径（`test_prompt_command.py`）

1. `monkeypatch.setattr(session_execution, "advance_cli_terminal_cursor", _raise_cli_terminal_cursor_error)`
2. Host 返回 FAILED terminal → `render_prompt_terminal_result(terminal)` 执行
3. `await advance_cli_terminal_cursor(...)` → `_raise_cli_terminal_cursor_error` → `raise CliTerminalCursorError("cursor write failed")`
4. 异常从 `execute_prompt_on_session`（第 374 行，无 try/except）向上传播
5. 测试 `pytest.raises(CliTerminalCursorError, match="cursor write failed")` 捕获 ✅

#### Startup reconnect 路径（`test_interactive_command.py`）

1. `monkeypatch.setattr(session_execution, "advance_cli_terminal_cursor", _raise_cli_terminal_cursor_error)`
2. `monkeypatch.setattr(session_execution, "startup_reconnect_entrypoint_session", fake_startup_reconnect)` — 返回 LOST terminal
3. `execute_interactive_on_session` → `_run_existing_session_startup_reconnect`（第 419 行）
4. Render → `await advance_cli_terminal_cursor(...)`（第 522 行）→ raise
5. 异常穿过 `_run_existing_session_startup_reconnect` → `execute_interactive_on_session`（第 419 行无 try/except）→ 测试
6. `pytest.raises(CliTerminalCursorError)` 捕获 ✅

#### Interactive turn 路径（`test_interactive_command.py`）

1. `monkeypatch.setattr(session_execution, "advance_cli_terminal_cursor", _raise_cli_terminal_cursor_error)`
2. `run_startup_reconnect=False` 跳过 startup
3. `_run_interactive_repl` → submit "触发终态" → Host 返回 LOST terminal
4. Render → `await advance_cli_terminal_cursor(...)`（第 853 行）→ raise
5. 异常穿过 `_run_interactive_repl` → `execute_interactive_on_session`（第 426 行无 try/except）→ 测试
6. `pytest.raises(CliTerminalCursorError)` 捕获 ✅

### Monkeypatch 目标验证

`session_execution.py` 第 62-63 行：

```python
from dayu.cli.session_terminal_cursor import (
    advance_cli_terminal_cursor,
```

三个调用点（第 374、522、853 行）使用未限定名 `await advance_cli_terminal_cursor(...)`，查找链解析到模块级 import。测试 monkeypatch `session_execution.advance_cli_terminal_cursor` 正确替换了该引用。

### 闭合判定: **已关闭** ✅

- 三个路径的 cursor 写失败传播均有测试覆盖。
- 每个测试验证异常不被捕获（`pytest.raises`）且 renderer 退出码不被替代返回（因为异常在 return 之前抛出）。
- 三个测试在 `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_terminal_cursor.py` 中全部通过（100 passed）。

---

## 新增变更逐项走读

### 生产代码三站点一致性

| 站点 | 文件行号 | cursor 推进条件 | 非成功 exit code 返回 | `terminal is None` 提前返回 |
|---|---|---|---|---|
| `execute_prompt_on_session` | 371-380 | 无条件（render 后） | cursor 推进后在 return 之前 | 第 371-372 行，cursor 之前 |
| `_run_existing_session_startup_reconnect` | 520-530 | 无条件（render 后） | cursor 推进后在 return 之前 | N/A（startup 无 None 路径） |
| `_run_interactive_repl` | 847-861 | 无条件（render 后） | cursor 推进后在 return 之前 | 第 847-848 行，cursor 之前 |

三个站点逻辑一致：
- **render 总是在 cursor 推进之前**：保证只有成功渲染的 terminal 才推进 cursor。
- **cursor 推进总是在 return render_exit_code 之前**：保证 cursor 推进后才能返回。
- **`terminal is None` 提前返还在 cursor 推进之前**：保证无 terminal 时不推进 cursor。
- **cursor 写失败不捕获**：`CliTerminalCursorError` 向上传播，renderer exit code 不被返回。

### Host/Service 语义边界

- `terminal.terminal_event_id` 和 `terminal.event_sequence` 仅被读取，不修改。
- `terminal_status`、`final_answer`、`error_message`、`cancel_reason` 不受 cursor 推进影响。
- renderer exit code 由 `render_prompt_terminal_result` / `render_interactive_terminal_result` / `InteractiveRunView.render_terminal_result` 产生，cursor 推进不改写。

### 测试辅助函数重复

`_raise_cli_terminal_cursor_error` 在 `test_prompt_command.py` 和 `test_interactive_command.py` 中各定义一次，签名和实现完全一致。这是测试文件独立性的合理选择——每个测试文件自包含其 fixture/helper，不跨文件依赖。不报告为 finding。

---

## Findings

未发现实质性问题。

---

## Open Questions

- **Render 异常与 cursor 一致性**：三个站点均先 render 后 advance cursor。若 render 成功（stdout 已写入）但 `advance_cli_terminal_cursor` 失败，cursor 不会推进，导致下次 reconnect 重复展示已渲染 terminal。这是 plan 明确接受的 local-delivery trade-off，当前测试已覆盖 cursor 写失败传播行为，无需额外处理。

- **Startup reconnect 中 `startup.terminal_results` 为空时 cursor 不动**：`_run_existing_session_startup_reconnect` 第 520 行 `for terminal in startup.terminal_results` 空迭代直接 `return EXIT_SUCCESS`，无 cursor 操作。行为正确——无新 terminal 可渲染时无 cursor 需要推进。

---

## Residual Risk

| 风险 | 严重度 | 说明 |
|---|---|---|
| cursor 写失败后 terminal 重复展示 | 低 | Plan 已接受的 local-delivery trade-off；atomic write（`tempfile` + `os.replace`）降低 corruption 风险 |
| render 本身抛异常时 cursor 不推进 | 低 | 三个站点 render 在 cursor 之前；若 render 抛异常，cursor 不动，下次 reconnect 会重新拉取该 terminal。当前 render 实现不抛异常，风险低 |
| 测试均用非 SUCCESS 状态测 cursor 写失败 | 信息 | cursor 推进逻辑与 terminal status 无关，测试覆盖充分；若未来 cursor 推进依赖 status 字段，需补充 SUCCESS 路径的写失败测试 |

---

## Re-Review Verdict

**pass** — DS-F1 和 DS-F2 均已关闭。三个执行路径的 cursor 推进逻辑正确一致，cursor 写失败传播行为在三个路径均有测试覆盖。未发现新问题。生产代码语义边界清晰，不修改 Host/Service terminal facts，不改写 renderer exit code。

### 验证结果

- `pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_terminal_cursor.py -q`: **100 passed**
- `pyright dayu/ tests/ utils/`: **0 errors, 0 warnings, 0 informations**
- `git diff --check`: **passed**
