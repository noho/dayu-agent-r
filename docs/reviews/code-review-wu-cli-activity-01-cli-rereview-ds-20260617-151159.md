# WU-CLI-ACTIVITY-01 CLI Review Fixes Targeted Re-Review

## Scope

- Mode: current changes (targeted re-review of review fixes)
- Branch: wu-cli-activity-01
- Base: main
- Output file: docs/reviews/code-review-wu-cli-activity-01-cli-rereview-ds-20260617-151159.md
- Fix artifact: docs/reviews/wu-cli-activity-01-cli-review-fix-codex.md
- Previous review: docs/reviews/code-review-wu-cli-activity-01-cli-ds-20260617-145226.md
- Review focus: four specific findings from previous review

### Findings Under Review

| # | Previous Severity | Description |
|---|---|---|
| 1 | 中 | prompt 路径第二次 Ctrl+C 缺少本地退出机制；Esc 仍为第一次 cancel 且 terminal-first 需保持 |
| 2 | 中 | `CliActivityRenderer._last_hidden_title` 在 visible 期间未设置导致首次隐藏时无状态提示 |
| 3 | 中 | `TtyRunningKeyMonitor.start()` 中 thread 启动失败后终端无法恢复 |
| 4 | — | No regression to stdout/stderr separation, non-TTY behavior, pyright, or existing tests |

## Findings

未发现实质性问题。四项 review 目标均验证通过。

## 逐项验证

### 1. prompt 第二次 Ctrl+C 本地退出 + terminal-first-wins — 已修复

**生产代码变更** (`dayu/cli/commands/prompt.py`):

- **`_cancel_prompt_turn_after_local_request`**（行 429-476）重写：
  - 新增 `sigint_monitor: CliSigintMonitor` 和 `observed_sigint_count: int` 参数
  - 调用 `render_cancel_requested()` 后委托给新增函数 `_cancel_prompt_run_waiting_for_terminal_or_second_sigint`
  - Esc 路径传 `observed_sigint_count=observed_sigint_count`（进入运行态前的计数，即 0）——Esc 不递增 SIGINT 计数
  - Ctrl+C 路径传 `observed_sigint_count=first_sigint_count`（第一次 SIGINT 后的计数）

- **`_cancel_prompt_run_waiting_for_terminal_or_second_sigint`**（行 479-540）新增：
  - 双路 `asyncio.wait((cancel_task, second_sigint_task), FIRST_COMPLETED)` 模式
  - `cancel_task` 先完成 → 返回 terminal result（**terminal-first-wins**）
  - `second_sigint_task` 先完成 → `render_local_exit_after_cancel()` → cancel cancel_task → 返回 `None`
  - finally 块清理 `second_sigint_task`

- **`_submit_prompt_turn_handling_sigint`**: 三路并发 while 循环（行 392-426），Ctrl+T toggle 支持与 interactive 一致

**调用链追踪**:

```
Ctrl+C 路径:
  _submit_prompt_turn_handling_sigint (sigint_task 完成)
  → _cancel_prompt_turn_after_local_request(observed_sigint_count=first_sigint_count)
    → _cancel_prompt_run_waiting_for_terminal_or_second_sigint
      → cancel_task vs second_sigint_task[wait_next(first_sigint_count)]
        → cancel_task 先完成 → return terminal  ✓ terminal-first-wins
        → second_sigint_task 先完成 → return None → EXIT_KEYBOARD_INTERRUPT  ✓ 本地退出

Esc 路径:
  _submit_prompt_turn_handling_sigint (key_task=CANCEL_RUN)
  → _cancel_prompt_turn_after_local_request(observed_sigint_count=0)
    → _cancel_prompt_run_waiting_for_terminal_or_second_sigint
      → cancel_task vs second_sigint_task[wait_next(0)]
        → cancel_task 先完成 → return terminal  ✓ terminal-first-wins
        → second_sigint_task 先完成 → return None → EXIT_KEYBOARD_INTERRUPT  ✓ Esc 后 Ctrl+C 仍可本地退出
```

**测试覆盖**:

- `test_prompt_second_sigint_exits_after_cancel_request`: 使用 `_SecondSigintAfterCancelMonitor` + `block_cancel_after_record=True`，验证第二次 SIGINT 后返回 `None`、stderr 含 "cancel requested" 和 "local process exiting"
- `test_prompt_cancel_terminal_wins_over_second_sigint`: `cancel_terminal` 即时完成 → 验证 terminal result 被返回，不被 SIGINT 覆盖
- `test_prompt_esc_requests_cancel_after_run_id`: Esc 触发 cancel，验证 Host cancel request 正确且 terminal result 返回

结论：**已修复**。prompt 路径现在与 interactive 路径有对等的第二次 SIGINT 本地退出和 terminal-first-wins 语义。Esc 仍只作第一次 cancel。

### 2. `CliActivityRenderer` 隐藏时展示最新可见 activity 标题 — 已修复

**生产代码变更** (`dayu/cli/activity.py`):

- **行 113**: `self._last_hidden_title = activity.title` 移到 `if not self._visible:` 守卫（行 114）**之前**
- 修复前: `_last_hidden_title` 仅在 `_visible=False` 时写入 → visible 期间为空 → 首次 toggle 到 hidden 时无提示
- 修复后: 每条通过 dedupe/sequence 校验的 activity 都更新 `_last_hidden_title` → toggle 到 hidden 时始终有最新标题

**路径追踪**:

```
record() visible=True:
  → 通过 dedupe/sequence 校验
  → self._last_hidden_title = activity.title  (行 113)  ← 始终执行
  → if not self._visible: (行 114) → False → print to stderr (行 116)

toggle_visible() visible→hidden:
  → self._visible = False (行 127)
  → self._last_hidden_title is not None → True  ← 现在有值
  → print("Activity hidden: {title}", file=stderr) (行 129-131)
```

**测试覆盖**:

- `test_activity_renderer_toggle_hidden_reports_latest_visible_activity`: renderer 以 `visible=True` 初始化 → 记录 activity → `toggle_visible()` → 验证 stderr 含 "Activity hidden: 工具批次完成"

结论：**已修复**。

### 3. `TtyRunningKeyMonitor.start()` 在 thread 启动失败时恢复终端 — 已修复

**生产代码变更** (`dayu/cli/run_keys.py`):

- **行 161-180**: `thread.start()` 用 `try/except RuntimeError` 包裹
- 修复前: `self._thread.start()` 在 try/except 外，`RuntimeError` 不被捕获，终端留在 cbreak 模式
- 修复后（行 171-180）:
  ```python
  try:
      thread.start()
  except RuntimeError:
      _restore_terminal_attrs(fd, original_attrs)  # 恢复终端
      self._thread = None
      self._loop = None
      self._fd = None
      self._original_attrs = None
      self._started = False
      return
  ```
  - `_restore_terminal_attrs(fd, original_attrs)` 恢复终端属性到原始状态
  - 所有内部状态重置（`_thread`, `_loop`, `_fd`, `_original_attrs`, `_started`），允许重试
  - `_started` 在 `thread.start()` 之前置位（行 164）→ 失败时复位（行 179），避免死锁

**测试覆盖**:

- `test_tty_running_key_monitor_restores_terminal_when_thread_start_fails`: monkeypatch `threading.Thread` 为 `_FailingThread`（`start()` 抛出 `RuntimeError`）→ 创建 pty → `monitor.start()` → 验证 `termios.tcgetattr` 恢复后的 lflag 与原始值一致（ECHO/ICANON/ISIG/IEXTEN 位）

结论：**已修复**。

### 4. 无回归 — 确认

- **测试**: 97 passed（前次 review 为 85 passed），3 个 edgar deprecation warnings
- **pyright**: 0 errors, 0 warnings, 0 informations
- **stdout/stderr 分离**: 现有测试 `test_prompt_tty_activity_writes_stderr_and_final_answer_stays_stdout`、`test_interactive_tty_activity_finishes_before_next_prompt` 通过，验证 activity→stderr、final answer→stdout
- **non-TTY**: `CliActivityRenderer` 的 `enabled` 默认仍为 `self._stderr.isatty()`，`new_running_key_monitor` 的非 TTY 分支返回 `NoopRunningKeyMonitor`
- **覆盖率**: activity 88%, composer 94%, run_keys 89%

结论：**无回归**。

## 新增测试清单

| 测试 | 覆盖项 |
|---|---|
| `test_activity_renderer_toggle_hidden_reports_latest_visible_activity` | Fix 2: visible→hidden 时输出最新 activity 标题 |
| `test_tty_running_key_monitor_restores_terminal_when_thread_start_fails` | Fix 3: thread 启动失败后终端恢复 |
| `test_prompt_second_sigint_exits_after_cancel_request` | Fix 1: 第二次 Ctrl+C 本地退出 |
| `test_prompt_cancel_terminal_wins_over_second_sigint` | Fix 1: terminal-first-wins |
| `test_prompt_esc_requests_cancel_after_run_id` | Fix 1: Esc cancel 路径 |
| `test_prompt_ctrl_t_toggles_running_activity_without_cancel` | Ctrl+T toggle 不发起 cancel |
| `test_prompt_tty_activity_writes_stderr_and_final_answer_stays_stdout` | stdout/stderr 分离 |
| `test_interactive_esc_requests_cancel_after_run_id` | interactive Esc cancel |
| `test_interactive_tty_activity_finishes_before_next_prompt` | interactive 两轮不乱序 |
| `test_activity_renderer_outputs_visible_activity_to_stderr` | renderer 基础输出 |
| `test_activity_renderer_deduplicates_and_ignores_older_sequences` | dedupe + sequence |
| `test_activity_renderer_cancel_messages` | cancel/local-exit 消息 |

## Open Questions

无。

## Residual Risk

- `Esc` 按单字节 `\x1b` 处理；某些终端 escape sequence 以 `\x1b` 开头，运行态下可能误触 cancel——延续前一轮实现，fix artifact 已记录
- prompt cancel 等待只监听第二次 SIGINT，不监听第二次 Esc 本地退出——fix artifact 已说明这是 "Esc 是第一次取消请求、Ctrl+C 计数决定本地退出" 的裁决语义
- `_SecondSigintAfterCancelMonitor` 测试用 monitor 的 `install()` 和 `close()` 是 no-op，不安装 OS signal handler——依赖 `wait_next` 的异步驱动而非真实信号，覆盖了逻辑路径但未覆盖 signal handler 集成

## 验证结果

- `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py -q`: **97 passed**, 3 warnings
- `pyright dayu/cli/ tests/cli/`: **0 errors, 0 warnings, 0 informations**

## 复审结论

**非阻断**。四项 review 目标均验证通过：

1. prompt 第二次 Ctrl+C 本地退出 + terminal-first-wins — **已修复**
2. `CliActivityRenderer` 隐藏时展示最新可见 activity 标题 — **已修复**
3. `TtyRunningKeyMonitor.start()` thread 启动失败终端恢复 — **已修复**
4. 无回归 — **确认**（97 passed, pyright 0 errors）
