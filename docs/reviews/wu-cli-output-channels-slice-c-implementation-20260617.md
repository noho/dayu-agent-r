# WU-CLI-OUTPUT-CHANNELS Slice C Implementation

## Scope

本 slice 实现 interactive 运行态 output channel 拆分：

- interactive command 不再直接创建 `CliActivityRenderer`。
- 新增 CLI 层 `InteractiveRunView` / `ActivitySink` 窄协议。
- activity 进入 run view activity buffer，不作为普通 stderr activity 行实时输出。
- Ctrl+T 从旧的 activity hide/show 语义迁移为 transcript/activity view switch。
- Esc / Ctrl+C cancel 仍保持 Host public cancel 语义。

未修改 Host / Engine public API/contracts。

## Implementation

- `dayu/cli/activity.py`
  - 新增 `format_cli_activity_line(...)`，复用既有 activity 单行格式化逻辑，避免 run view 复制格式规则。

- `dayu/cli/run_view.py`
  - 新增 `ActivitySink` Protocol。
  - 新增 `InteractiveRunView` Protocol。
  - 新增 `InteractiveRunViewMode` 与 `InteractiveRunViewOptions`。
  - 新增 `TerminalInteractiveRunView`：
    - 默认 transcript mode。
    - activity 到达时写入 activity buffer；只有当前 mode 为 activity 且 view enabled 时才输出 UI 行。
    - terminal result 经 `render_interactive_terminal_result(...)` 捕获后写入 transcript buffer；非 TTY 或 transcript mode 下保持原 stdout/stderr 用户通道输出。
    - Ctrl+T 调 `toggle_view()`，渲染当前 activity/transcript snapshot，不输出旧 `Activity hidden`。
    - cancel 提示通过 view 方法输出，不进入 logging。

- `dayu/cli/commands/interactive.py`
  - `_execute_interactive_on_existing_session(...)` 与 `_run_interactive_repl(...)` 支持注入 `InteractiveRunView`。
  - `_run_interactive_repl(...)` 默认创建 `new_interactive_run_view()`，并在 finally 中关闭 view。
  - `_submit_interactive_turn_handling_sigint(...)` 通过 `view.activity_sink().record_activity` 接收 Service activity。
  - `RunningKeyAction.TOGGLE_ACTIVITY` 改为 `view.toggle_view()`。
  - cancel path 改为 `view.render_cancel_requested()` / `view.render_local_exit_after_cancel()`。

- `tests/cli/test_interactive_run_view.py`
  - 覆盖 activity buffer、terminal transcript、view toggle、activity mode 下 terminal buffering、旧 `Activity hidden` 文本不输出。

- `tests/cli/test_interactive_command.py`
  - 旧 TTY activity stderr renderer 集成测试迁移为 run view buffer 测试。
  - Esc cancel 测试迁移为 run view cancel 提示。
  - 新增 Ctrl+T 集成测试，确认 Ctrl+T 只切 view，不触发 Host cancel。

- `tests/README.md`
  - 更新 CLI 测试覆盖事实。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py -q`
  - 30 passed, 3 warnings
- `source .venv/bin/activate && pytest tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py -q`
  - 36 passed, 3 warnings
- `source .venv/bin/activate && pyright dayu/cli/activity.py dayu/cli/run_view.py dayu/cli/commands/interactive.py tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py`
  - 0 errors
- `git diff --check`
  - clean

## Residual Risk

- 本 slice 没有引入 full-screen prompt_toolkit `Application.run_async()`。当前实现是非 full-screen run view，符合已接受 plan 的 stop condition。
- 在 activity view 下，terminal result 会进入 transcript buffer；切回 transcript view 时通过 UI snapshot 可见。非 TTY 或 transcript mode 下仍保持原 stdout/stderr 行为。
