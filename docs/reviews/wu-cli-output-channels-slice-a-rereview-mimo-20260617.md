# Code Review Re-Review

## Scope

- Mode: re-review
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/wu-cli-output-channels-slice-a-rereview-mimo-20260617.md`
- Included scope: `dayu/cli/main.py`, `tests/cli/test_arg_parsing.py`
- Fix artifact: `docs/reviews/wu-cli-output-channels-slice-a-fix-20260617.md`

## Findings Status

### 1-已修复-中-finally 中 set_level_from_flags 异常可能导致文件未关闭

- **状态**: 已修复
- **原问题**: `main.py:103-113` finally 块中先调用 `set_level_from_flags` 恢复 stderr handler，再调用 `log_stream.close()`。如果 `set_level_from_flags` 抛异常，`log_stream.close()` 不会被调用，文件句柄泄漏。
- **修复内容**:
  1. 移除 `close_log_stream` 布尔标志，改用 `opened_log_stream is not None` 作为清理判据（`main.py:74, 104`）
  2. 用嵌套 `try/finally` 包裹恢复 stderr 操作，确保 `opened_log_stream.close()` 总是执行（`main.py:103-115`）
  3. 新增测试 `test_main_closes_log_file_when_restoring_stderr_fails`（`test_arg_parsing.py:650-713`）验证恢复 stderr 失败时文件仍被关闭
- **直接证据**:
  - `main.py:103-115`:
    ```python
    finally:
        if opened_log_stream is not None:
            try:
                runtime_log.set_level_from_flags(...)
            finally:
                opened_log_stream.close()
    ```
  - `test_arg_parsing.py:712-713`: `assert events == ["configure-file", "restore-stderr", "close"]` 和 `assert log_stream.closed`
- **验证结论**: 修复正确。嵌套 `try/finally` 确保无论 `set_level_from_flags` 是否抛异常，文件都会被关闭。

### 2-已修复-低-测试未覆盖 plan 要求的连续调用场景

- **状态**: 已修复
- **原问题**: 测试只覆盖单次调用场景，未覆盖 "一次 `main(... --log-file ...)` 后，下一次 `main(...)` 不带 `--log-file`" 的场景。
- **修复内容**: 新增测试 `test_main_restores_stderr_for_consecutive_log_file_and_stderr_calls`（`test_arg_parsing.py:540-582`）
- **直接证据**:
  - `test_arg_parsing.py:561-575`: 第一次调用使用 `--log-file`，第二次不使用
  - `test_arg_parsing.py:578-582`: 断言第一次诊断进入日志文件，第二次诊断进入 stderr，且互不污染
- **验证结论**: 修复正确。测试验证了连续调用场景下日志文件 handler 不会污染后续默认 stderr 调用。

## Additional Fixes (from DS findings)

### DS-001: 已修复 - close_log_stream 布尔标志与实际文件流分离

- **状态**: 已修复
- **原问题**: `log_stream = opened_stream` 与 `close_log_stream = True` 分离，存在理论信号中断赋值窗口。
- **修复内容**: 移除 `close_log_stream`，用 `opened_log_stream` 本身作为清理真源。
- **直接证据**: `main.py:74, 104` 使用 `opened_log_stream is not None` 而非独立布尔标志。

### DS-002: 已修复 - _open_log_file docstring 与实现不一致

- **状态**: 已修复
- **原问题**: docstring 声称 `raises OSError`，但实现捕获 `OSError` 并返回 `None`。
- **修复内容**: docstring 改为说明本函数不主动抛出文件打开异常。
- **直接证据**: `main.py:127-128` docstring 说明 "本函数不主动抛出文件打开异常；打开失败通过 usage diagnostic 与 `None` 返回值表达"。

### DS-003: 已修复 - 缺少 --log-file + KeyboardInterrupt 组合清理测试

- **状态**: 已修复
- **原问题**: 缺少 `--log-file` + runner `KeyboardInterrupt` 的组合清理测试。
- **修复内容**: 新增测试 `test_main_restores_stderr_before_closing_log_file_on_keyboard_interrupt`（`test_arg_parsing.py:716-780`）
- **直接证据**: `test_arg_parsing.py:778-780` 验证退出码为 130 且事件顺序为 `["configure-file", "restore-stderr", "close"]`

## Residual Risk

- **多进程并发写同一个 `--log-file`**: 仍可能交错，这是 Slice A 计划已接受的限制，本次未扩展为文件锁或 tee。
- **`--log-file` 不自动创建父目录**: 打开失败返回 usage error，符合当前设计。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py` - 70 passed, 3 warnings
- `source .venv/bin/activate && pyright dayu/cli/arg_parsing.py dayu/cli/main.py tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py` - 0 errors, 0 warnings, 0 informations
