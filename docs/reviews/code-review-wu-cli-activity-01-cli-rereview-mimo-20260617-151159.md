# Code Review

## Scope

- Mode: current changes (targeted re-review)
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/code-review-wu-cli-activity-01-cli-rereview-mimo-20260617-151159.md`
- Included scope: 四项 CLI review fix 的定向验证
- Excluded scope: 仅验证指定四项修复，不重复完整 CLI review
- Parallel review coverage: 无

## 验证项

### 1. Prompt first cancel → second Ctrl+C exits locally；terminal-first still wins

**修复位置**: `dayu/cli/commands/prompt.py:434-531`

**改动**: `_cancel_prompt_turn_after_local_request` 新增 `sigint_monitor` + `observed_sigint_count` 参数（行 440-441），委托给 `_cancel_prompt_run_waiting_for_terminal_or_second_sigint`（行 466）。新函数与 interactive 侧 `_cancel_run_waiting_for_terminal_or_second_sigint` 结构一致：`asyncio.wait(FIRST_COMPLETED)` 竞争 `cancel_task` 与 `second_sigint_task`（行 518-521）。

**Esc 语义验证**: Esc 触发 `RunningKeyAction.CANCEL_RUN` 时传入 `observed_sigint_count=sigint_monitor.count`（行 362, 412），即运行态前的计数。后续 Ctrl+C 作为"第一次 SIGINT"进入 `_cancel_prompt_run_waiting_for_terminal_or_second_sigint`，第二次 Ctrl+C 触发本地退出。与 Ctrl+C 触发路径（传入 `first_sigint_count`，行 422）语义一致：第一次请求 cancel，第二次本地退出。

**测试覆盖**:
- `test_prompt_second_sigint_exits_after_cancel_request`（行 1068）: `_SecondSigintAfterCancelMonitor` + `block_cancel_after_record=True` → result=None，cancel 已发，"Activity: cancel requested" + "local process exiting" 写入 stderr ✅
- `test_prompt_cancel_terminal_wins_over_second_sigint`（行 1109）: `cancel_terminal=SUCCEEDED` + `_SecondSigintAfterCancelMonitor` → result 非 None，terminal_status=CANCELLED ✅
- `test_prompt_esc_requests_cancel_after_run_id`（行 960）: `_FakeRunningKeyMonitor(CANCEL_RUN)` → cancel 已发，result 非 None ✅

**结论**: ✅ 修复正确。

### 2. CliActivityRenderer retains latest visible activity title when toggled hidden

**修复位置**: `dayu/cli/activity.py:113`

**改动**: `_last_hidden_title = activity.title` 从 `if not self._visible:` 分支内移到分支前（行 113），变为无条件赋值。无论 renderer 当前可见或隐藏，最新 activity 标题始终被记录。

**修复前行为**: `_last_hidden_title` 仅在 `not self._visible` 时更新。若 renderer 从 visible → hidden 切换，`toggle_visible()` 打印的 `_last_hidden_title` 可能是 None 或更早的隐藏 activity 标题。

**修复后行为**: 每次 `record()` 都更新 `_last_hidden_title`。visible → hidden 切换时展示最新已见 activity 标题。

**测试覆盖**: `test_activity_renderer_toggle_hidden_reports_latest_visible_activity`（行 84）: visible renderer 收到 activity 后 toggle → stderr 包含 "Activity hidden: 工具批次完成" ✅

**结论**: ✅ 修复正确。

### 3. TtyRunningKeyMonitor.start restores terminal attrs if thread.start fails after cbreak

**修复位置**: `dayu/cli/run_keys.py:171-180`

**改动**: `thread.start()` 包裹在独立 `try/except RuntimeError` 中（行 171-180）。若 `thread.start()` 失败（如线程资源不足），立即调用 `_restore_terminal_attrs(fd, original_attrs)` 恢复终端，并重置 `_thread/_loop/_fd/_original_attrs/_started` 为初始值。

**修复前行为**: `thread.start()` 在 `try` 块外（行 165-170 原始代码），若 `setcbreak` 成功但 `thread.start()` 失败，终端留在 cbreak 模式且 `_started=True`，`close()` 不会恢复（因为 `_fd` 和 `_original_attrs` 已赋值但线程未运行）。

**修复后行为**: `thread.start()` 失败时终端立即恢复，状态完全回滚到 `start()` 前。

**结论**: ✅ 修复正确。

### 4. No regression to stdout/stderr, non-TTY, pyright/tests

- **85 项测试全部通过**（prompt 22 + interactive 21 + activity renderer 6 + composer 6 + entrypoint runtime 26 + 其他 4）
- **pyright 零错误**
- **stdout/stderr 分离**: activity 写 stderr，final answer 写 stdout（`test_prompt_tty_activity_writes_stderr_and_final_answer_stays_stdout` 行 827、`test_interactive_tty_activity_finishes_before_next_prompt` 行 879）
- **non-TTY**: `CliActivityRenderer` 默认按 `stderr.isatty()` 决定 enabled；`NoopRunningKeyMonitor` 不产生按键事件
- **tests/README.md** 已更新覆盖描述

**结论**: ✅ 无回归。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- 无新增风险。四项修复均通过直接代码走读和测试验证。

## 结论

**非阻断**。四项 CLI review fix 全部验证通过：
1. Prompt cancel → second Ctrl+C 本地退出 + terminal-first-wins ✅
2. Activity renderer visible → hidden 展示最新标题 ✅
3. TtyRunningKeyMonitor thread.start 失败恢复终端 ✅
4. 无回归（85 tests, pyright 0 errors） ✅
