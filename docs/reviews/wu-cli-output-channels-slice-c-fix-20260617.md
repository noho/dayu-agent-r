# WU-CLI-OUTPUT-CHANNELS Slice C Fix

## Background

DS code review 发现 `TerminalInteractiveRunView.record_activity(...)` 没有沿用旧
`CliActivityRenderer` 的 activity 去重与乱序过滤。MiMo 未发现实质性问题。

## Fix

- `dayu/cli/run_view.py`
  - 新增 `_seen_activity_dedupe_keys`。
  - 新增 `_last_activity_event_sequence`。
  - `record_activity(...)` 入口按 `dedupe_key` 去重，并过滤小于已观察最大
    event sequence 的乱序 activity。
  - 模块级常量补 `Final[str]`，对齐同类 CLI 模块风格。

- `tests/cli/test_interactive_run_view.py`
  - 新增 `test_run_view_deduplicates_and_filters_out_of_order_activity`。
  - `_activity(...)` helper 支持注入 `dedupe_key` 与 `event_sequence`。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py -q`
  - 37 passed, 3 warnings
- `source .venv/bin/activate && pyright dayu/cli/activity.py dayu/cli/run_view.py dayu/cli/commands/interactive.py tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py`
  - 0 errors
- `git diff --check`
  - clean

## Residual Risk

- run view buffer 仍按当前 plan 不做有界裁剪；长 session 大 buffer 属于非 full-screen run view 的已知限制。
- 未修改 Host / Engine public API/contracts。
