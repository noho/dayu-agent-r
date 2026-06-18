# Code Review — Re-review

## Scope

- Gate: Code review fix re-review
- Original review: `docs/reviews/wu-cli-output-channels-slice-a-code-review-ds-20260617.md`
- Fix report: `docs/reviews/wu-cli-output-channels-slice-a-fix-20260617.md`
- Branch: `wu-cli-activity-01`
- Review date: 2026-06-17
- Focus: 核对 DS finding 001/002/003 的修复状态；仅走读受影响的代码路径与测试

## Finding Status

每个 finding 沿修复后代码路径逐行走读，按 未修复/已修复/部分修复/证据失效 裁决。

### 001-已修复-main() 中 close_log_stream 布尔 shadow state 替换为 opened_log_stream 单变量真源

- **原始入口**: `dayu/cli/main.py:78-84`（`log_stream = opened_stream` 与 `close_log_stream = True` 分离赋值）
- **修复后代码**: `dayu/cli/main.py:74,81,84,104-115`

**证据链**：

1. 初始化：`opened_log_stream: TextIO | None = None`（行 74）——单变量承载"是否已打开日志文件"语义。
2. 赋值：`opened_log_stream = _open_log_file(args.log_file)`（行 81）——单语句赋值，消除原 `log_stream + close_log_stream` 两条语句之间的信号窗口。
3. 清理判据：`if opened_log_stream is not None:`（行 104）——直接以变量值判断清理，消除 shadow state 不一致风险。
4. 文件关闭防护：`try: set_level_from_flags(...) finally: opened_log_stream.close()`（行 105-115）——即使 stderr handler 恢复失败，嵌套 `finally` 也保证文件必定 close。

**裁决依据**：原 finding 指出的根因（布尔 shadow state 与 stream 引用分离赋值）已消除；`opened_log_stream` 作为唯一真源，赋值点单一，清理判据直接来自该变量。修复完整。

### 002-已修复-_open_log_file() docstring 与实现不一致

- **原始入口**: `dayu/cli/main.py:125` docstring `:raises OSError:` 与 `dayu/cli/main.py:134` `except OSError` 矛盾
- **修复后代码**: `dayu/cli/main.py:122-129`

**证据链**：

1. 修复后 docstring `:raises Exception:` 行后跟随说明：`本函数不主动抛出文件打开异常；打开失败通过 usage diagnostic 与 ``None`` 返回值表达。`（行 127-128）
2. 实现仍为捕获 `OSError` → 打印 diagnostic → 返回 `None`（行 135-142），与 docstring 一致。
3. 无新增 `:raises` 子句与实现不一致。

**裁决依据**：docstring 已明确表达函数不抛出文件打开异常，捕获路径与 `None` 返回语义自洽。修复完整。

### 003-已修复-缺少 --log-file + runner KeyboardInterrupt 的组合清理测试

- **原始缺口**: 无 `--log-file` + `KeyboardInterrupt` runner 的组合测试
- **修复后测试**: `test_main_restores_stderr_before_closing_log_file_on_keyboard_interrupt`

**证据链**（沿测试代码走读）：

1. 测试构造 `_TrackingLogStream` + fake `_open_log_file` + spy `set_level_from_flags` + `_raise_keyboard_interrupt` runner。
2. 调用 `cli_main.main(("prompt", "请分析收入变化", "--log-file", "dayu.log"))`。
3. 断言退出码为 `EXIT_KEYBOARD_INTERRUPT`（130）。
4. 断言事件顺序为 `["configure-file", "restore-stderr", "close"]` —— 证明 `finally` 块先恢复 stderr 再关闭文件。
5. 断言 `log_stream.closed` —— 证明文件已关闭。

**裁决依据**：测试完整覆盖了 `KeyboardInterrupt` + `--log-file` 路径下的退出码、handler 恢复/文件关闭顺序、资源释放。修复完整。

## 附加验证（超出 DS findings 范围，但属于本轮 fix 变更集）

fix 变更集中还包含了 MiMo review 的 finding 修复与若干加固措施，沿代码路径快速验证：

- **`log_level_for_cleanup` 捕获**（`dayu/cli/main.py:75,79`）：在 `runner(args)` 执行前保存 `args.log_level`，清理时使用捕获值而非 `args` 读取值。这防止 runner 修改 `args.log_level` 后清理使用错误 level。行为正确，无副作用。
- **嵌套 `try/finally` 文件关闭**（`dayu/cli/main.py:105-115`）：见 finding 001 分析，即使 stderr 恢复失败文件也不会泄漏。
- **连续调用测试** `test_main_restores_stderr_for_consecutive_log_file_and_stderr_calls`：验证第一次 `--log-file` 后第二次无 `--log-file` 时诊断正确回到 stderr，且不继续写已关闭日志文件。断言精确覆盖 log 文件内容、stderr 内容、互不污染。
- **恢复失败仍 close 测试** `test_main_closes_log_file_when_restoring_stderr_fails`：验证 `set_level_from_flags` 恢复 stderr 抛出 `ValueError` 后，文件仍在嵌套 `finally` 中关闭。事件顺序为 `configure-file → restore-stderr → close`，文件已关闭。

以上加固措施消除了原实现中 stderr 恢复失败会导致文件泄漏的隐患，并补上了跨调用 handler 污染测试，属于实质性质量提升。

## Open Questions

- 无。

## Residual Risk

- 多进程并发写同一 `--log-file` 仍可能交错：计划已接受，本次 fix 未扩展。
- 信号在 `_open_log_file()` 返回后、`opened_log_stream =` 赋值前触发 `KeyboardInterrupt` 可能导致文件泄漏：该窗口为单条 `STORE_FAST` 字节码，Python 信号处理器不在字节码执行中途投递异常。实际不可触发，且 OS 进程退出时回收 FD，无需额外处理。
- Slice B/C 未实现，不在本次范围。
