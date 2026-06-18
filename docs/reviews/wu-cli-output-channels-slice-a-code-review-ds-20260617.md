# Code Review

## Scope

- Mode: current changes (Slice A: 全局 --log-file 与日志 sink)
- Branch: wu-cli-activity-01
- Base: main
- Review date: 2026-06-17
- Output file: docs/reviews/wu-cli-output-channels-slice-a-code-review-ds-20260617.md
- Included scope:
  - `dayu/cli/arg_parsing.py` — `--log-file` 参数注册、`ParsedCliArgs.log_file` 字段
  - `dayu/cli/main.py` — 日志文件打开/装配/恢复/关闭生命周期
  - `tests/cli/test_arg_parsing.py` — 参数解析、main 日志装配 spy、恢复顺序测试
  - `tests/cli/test_fins_commands.py` — Fins direct --log-file 集成测试
  - `tests/README.md` — 测试覆盖描述同步
  - `docs/reviews/wu-cli-output-channels-slice-a-implementation-20260617.md` — 实现报告
  - `docs/reviews/wu-cli-output-channels-plan-20260617.md` — 已接受计划
- Excluded scope: Slice B (`prompt --detail`)、Slice C (interactive run view)、Slice D (文档收口)
- Parallel review coverage: 无（单 reviewer 全量覆盖）

## Findings

### 001-未修复-中-main() 在成功打开日志文件后缺少显式原子性赋值保证，close_log_stream 与 log_stream 赋值之间存在极窄信号中断窗口

- **入口/函数**: `main()` -> 日志文件打开后的赋值序列
- **文件(行号)**: `dayu/cli/main.py:78-84`
- **输入场景**: `--log-file <valid_path>` 且恰好在该窗口收到 SIGINT
- **实际分支**: `_open_log_file` 返回非 None → `log_stream = opened_stream` (行 82) 执行完毕 → `close_log_stream = True` (行 83) 未执行 → 信号中断
- **预期行为**: 文件应被关闭；若 `close_log_stream` 仍为 `False`，文件不会被关闭
- **实际行为**: 当前两行赋值之间仅隔一条 Python 语句，信号只能在字节码之间投递，实际不可触发。但代码结构上存在理论窗口
- **直接证据**: `dayu/cli/main.py:78-84` 中 `log_stream = opened_stream` 与 `close_log_stream = True` 分属两条语句，`finally` 块 (行 103-112) 依赖 `close_log_stream` 判断是否清理
- **影响**: 极低——信号中断概率可忽略不计（窗口约为一条 Python 字节码），且进程退出时 OS 会回收 FD
- **建议改法和验证点**: 将赋值合并为不可分割的原子操作（如 `log_stream, close_log_stream = opened_stream, True`）或把 `close_log_stream` 赋值提到 `_open_log_file` 调用之前（成功后保持 True，失败时重置）。实际收益微小，仅建议在风格一致性要求下采纳
- **修复风险（低）**: 简单赋值重排，不改变行为语义
- **严重程度（低）**: 信号中断窗口仅为理论存在，无实际可复现路径

### 002-未修复-低-_open_log_file docstring 声称透传 OSError 但实际捕获所有 OSError 子类并转为 None

- **入口/函数**: `_open_log_file()`
- **文件(行号)**: `dayu/cli/main.py:120-139`
- **输入场景**: 任意导致 `open()` 抛出 `OSError` 的路径（权限不足、父目录缺失、目录路径等）
- **实际分支**: `except OSError as exc:` (行 134) → 打印诊断 → 返回 `None`
- **预期行为**: 与 docstring 一致——要么抛出 OSError，要么说明"本函数不抛出 OSError"
- **实际行为**: 函数实现正确（捕获并转 usage error），但 docstring 行 125 写 `:raises OSError: 本函数捕获文件打开异常并转为 usage diagnostic。` 自相矛盾——"捕获"与"raises"冲突
- **直接证据**: `dayu/cli/main.py:125` docstring 行 `:raises OSError:`，但 `dayu/cli/main.py:134` `except OSError` 捕获所有 OSError 子类
- **影响**: 仅文档不一致，不影响运行时行为。会给后续维护者造成困惑
- **建议改法和验证点**: 将 docstring 改为 `:raises Exception: 本函数不主动抛出异常；文件打开失败通过返回 None 表达` 或类似表述
- **修复风险（低）**: 仅 docstring 修正
- **严重程度（低）**: 文档级不一致，不改变任何运行时行为

### 003-未修复-低-缺少 --log-file + runner KeyboardInterrupt 的组合测试，现有异常路径测试仅覆盖 RuntimeError

- **入口/函数**: `test_main_restores_stderr_before_closing_log_file_on_unexpected_exception` vs 未覆盖 `KeyboardInterrupt` 场景
- **文件(行号)**: `tests/cli/test_arg_parsing.py:523-584`
- **输入场景**: `--log-file <path>` + runner 抛出 `KeyboardInterrupt`
- **实际分支**: inner `finally` 块恢复 stderr handler + 关闭文件 → `KeyboardInterrupt` 传播到 outer `except KeyboardInterrupt`
- **预期行为**: 文件正确关闭，logger 恢复到 stderr
- **实际行为**: 当前实现正确（`finally` 块对所有异常类型统一处理），但缺少显式测试
- **直接证据**: `tests/cli/test_arg_parsing.py:354-366` `test_main_maps_keyboard_interrupt` 不传 `--log-file`；`:523-584` `test_main_restores_stderr_before_closing_log_file_on_unexpected_exception` 只 patch RuntimeError runner
- **影响**: 当前行为正确但无回归保护；若未来有人修改清理逻辑时引入 KeyboardInterrupt 专属路径 bug，不会被现有测试捕获
- **建议改法和验证点**: 新增测试：`test_main_closes_log_file_on_keyboard_interrupt`，验证 `--log-file` 下 runner 抛出 `KeyboardInterrupt` 后文件已关闭且 stderr handler 已恢复
- **修复风险（低）**: 新增测试，不改变生产代码
- **严重程度（低）**: `finally` 块语义保证当前行为正确，仅缺少针对性回归测试

## Open Questions

- 无。实现路径与计划对照无歧义，handler 生命周期逻辑完整可追踪。

## Residual Risk

- **多进程并发写同一 `--log-file`**：计划已明确接受为已知限制（不加文件锁或 tee），日志行可能交错。此风险已在 plan 与 implementation report 中记录，非实现缺陷。
- **`--log-file` 不自动创建父目录**：计划明确要求"父目录必须存在；打开失败返回 usage error"，实现完全匹配。无残余风险。
- **未测试极端长路径**：`_open_log_file` 不对路径长度做预校验；超过文件系统限制时 `open()` 抛出 `OSError` → 返回 usage error。此行为正确，风险闭合。
- **未测试文件权限拒绝**：与上述类似，`open()` 的 `PermissionError`（OSError 子类）会被 `except OSError` 捕获。无残余风险。
- **`conftest.py` StreamHandler close 与 sys.stderr 安全交互**：已确认 `logging.StreamHandler.close()` 内置 `sys.stderr` 安全检查，不会意外关闭 stderr。risk closed。
- **`_reset_marker_handlers` 不移除日志级别以外的 marker**：若未来引入其他 `_HANDLER_MARKER_ATTR` 标记的 handler（如 root logger handler），`_reset_marker_handlers` 会一并移除。当前仅 dayu namespace logger 使用，无冲突。若未来扩展 configure_root=True 路径，需注意此行为。
