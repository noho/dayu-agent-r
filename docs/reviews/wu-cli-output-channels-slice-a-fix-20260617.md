# WU CLI Output Channels Slice A Fix

Gate: Code review fix
Work unit: Dayu CLI 输出通道拆分
Slice: A - 全局 `--log-file` 与日志 sink
Branch: `wu-cli-activity-01`
日期: 2026-06-17
执行者: AgentCodex

## Scope

本次只修复 Slice A code review findings。未做 Slice B `prompt --detail` / `--no-detail`，未做 Slice C interactive run view。

## Review Findings Status

- MiMo finding 1：接受，已修复。
  - 根因：`main()` 的 `finally` 先恢复 stderr handler，再关闭日志文件；若恢复 handler 抛异常，文件关闭不会执行。
  - 修复：清理条件改为 `opened_log_stream is not None`，移除 `close_log_stream`；恢复 stderr handler 外层使用 `try/finally`，确保已打开日志文件必定 close。
- MiMo finding 2：接受，已修复。
  - 根因：测试未覆盖第一次 `--log-file` 后第二次无 `--log-file` 的连续调用。
  - 修复：新增连续调用测试，确认第一次诊断进入 log file，第二次诊断进入 stderr，且第二次不继续写已关闭日志文件。
- DS finding 001：接受，已修复。
  - 根因：`log_stream = opened_stream` 与 `close_log_stream = True` 分离，存在理论信号中断赋值窗口。
  - 修复：用 `opened_log_stream` 本身作为清理真源，不再维护布尔 shadow state。
- DS finding 002：接受，已修复。
  - 根因：`_open_log_file()` docstring 声称 `raises OSError`，但实现捕获 `OSError` 并返回 `None`。
  - 修复：docstring 改为说明本函数不主动抛出文件打开异常，打开失败通过 usage diagnostic 与 `None` 表达。
- DS finding 003：接受，已修复。
  - 根因：缺少 `--log-file` + runner `KeyboardInterrupt` 的组合清理测试。
  - 修复：新增 `KeyboardInterrupt` 路径测试，确认返回 130 且事件顺序为 configure file -> restore stderr -> close。

## Changed Files

- `dayu/cli/main.py`
  - `opened_log_stream` 成为日志文件生命周期的唯一清理判据。
  - `finally` 中恢复 stderr handler 与 close 日志文件改为嵌套 `try/finally`。
  - `_open_log_file()` docstring 修正为与实现一致。
- `tests/cli/test_arg_parsing.py`
  - 新增连续调用测试。
  - 新增恢复 stderr 失败仍 close 日志文件测试。
  - 新增 `--log-file` + `KeyboardInterrupt` 清理顺序测试。
- `tests/README.md`
  - 同步 CLI 测试覆盖事实。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py`
  - 结果：70 passed, 3 warnings。
  - warnings：来自 `edgar` 依赖 deprecation warning，非本次修复引入。
- `source .venv/bin/activate && pyright dayu/cli/arg_parsing.py dayu/cli/main.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py`
  - 结果：0 errors, 0 warnings, 0 informations。

## README Decision

- `tests/README.md`：已更新。原因是本次新增了 CLI main 日志清理与连续调用测试事实。
- 其他 README：不更新。原因是本次没有修改 Engine / Host / Fins / Config，也没有改变 `UI -> Service -> Host -> Engine` 分层关系或装配边界。

## Residual Risks

- 多进程并发写同一个 `--log-file` 仍可能交错；这是 Slice A 计划已接受的限制，本次未扩展为文件锁或 tee。
- `--log-file` 仍不自动创建父目录；打开失败返回 usage error，符合当前设计。
- Slice B/C 仍未实现，按用户要求不在本次处理。

