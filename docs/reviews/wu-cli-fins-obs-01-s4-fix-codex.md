# WU-CLI-FINS-OBS-01 Slice S4 Fix

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S4-cli-fins-live-ui`
- Fix gate: accepted code review findings
- Controller artifact: `docs/reviews/wu-cli-fins-obs-01-s4-code-review-adjudication-20260615-195111.md`

## Motivation Judgment

两个 accepted findings 均成立：

- `render_fins_direct_terminal_result(...)` 已不在当前 Fins direct live command 路径中被调用，继续作为 public export 会制造误用入口。
- CLI output redaction 原先只匹配空白边界后的绝对路径，不能覆盖 `path=/tmp/a`、`key=/Users/a/b`、`error=C:\tmp\a` 这类常见嵌入格式。

## Changes

- `dayu/cli/output.py`
  - 移除 obsolete `render_fins_direct_terminal_result(...)` 函数及 `__all__` 导出。
  - 移除仅供旧 renderer 使用的 succeeded/cancelled 模板常量。
  - 增强 `_ABSOLUTE_PATH_PATTERN`，支持保留 `=`、`,`、`:`、括号、引号等分隔符并脱敏其后的 POSIX / Windows 绝对路径。
  - 新增 `_redact_absolute_path_match(...)`，让嵌入路径替换复用同一 `_safe_text_value(...)` 输出边界。

- `tests/cli/test_fins_commands.py`
  - 增加 focused tests，分别证明 progress message/payload、terminal success summary、failure message 中的嵌入绝对路径不会泄漏。
  - 扩展 fake event helper，允许测试注入定制 payload / terminal summary / failure summary。

- `tests/README.md`
  - 按当前测试手册职责，补充 CLI Fins 测试覆盖“嵌入绝对路径脱敏”的事实。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py -q`
  - Passed: `32 passed`
  - Warnings: existing `edgar` deprecation warnings only.

- `source .venv/bin/activate && python -m pyright dayu/cli/commands/fins.py dayu/cli/output.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py`
  - Passed: `0 errors, 0 warnings, 0 informations`
  - Note: pyright printed an available-version notice.

- `rg -n "render_fins_direct_terminal_result" dayu tests`
  - Passed: no current production or test caller remains.

- `git diff --check`
  - Passed.

## README Decision

- Updated `tests/README.md` because this fix adds concrete CLI test coverage and the file explicitly tracks current `tests/` facts.
- Did not update `dayu/README.md`, `dayu/host/README.md`, `dayu/engine/README.md`, `dayu/fins/README.md`, or `dayu/config/README.md` because this fix does not change project-level architecture, Host/Engine/Fins boundaries, config semantics, or runtime assembly.

## Deferred / Non-actions

- Did not change terminal fallback design.
- Did not modify Service, Fins runtime, Host, or Engine.
- Did not implement S5 logging assembly.
- Did not extend `upload_filings_from` into a live job.
- Did not add compatibility wrappers or replacement public API for the removed renderer.
