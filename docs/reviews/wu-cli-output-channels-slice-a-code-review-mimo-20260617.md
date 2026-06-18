# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/wu-cli-output-channels-slice-a-code-review-mimo-20260617.md`
- Included scope: `dayu/cli/arg_parsing.py`, `dayu/cli/main.py`, `tests/cli/test_arg_parsing.py`, `tests/cli/test_fins_commands.py`, `tests/README.md`
- Excluded scope: `dayu/runtime/log.py`（未修改），Host/Engine/Service 文件
- Parallel review coverage: 无

## Findings

### 1-未修复-中-finally 中 set_level_from_flags 异常可能导致文件未关闭

- **入口/函数**: `main()`
- **文件(行号)**: `dayu/cli/main.py:103-113`
- **输入场景**: runner 正常执行或抛异常后，finally 中的 `runtime_log.set_level_from_flags(...)` 抛出异常（例如 `_resolve_level` 中 `log_level` 参数非法）
- **实际分支**: finally 块中先调用 `set_level_from_flags` 恢复 stderr handler，再调用 `log_stream.close()`
- **预期行为**: 无论恢复 stderr 是否成功，日志文件都应该被关闭
- **实际行为**: 如果 `set_level_from_flags` 抛异常，`log_stream.close()` 不会被调用，文件句柄泄漏
- **直接证据**: `main.py:103-113`，finally 块中两个操作没有独立保护：
  ```python
  finally:
      if close_log_stream:
          runtime_log.set_level_from_flags(...)  # 如果抛异常
          log_stream.close()  # 这行不会执行
  ```
- **影响**: 文件句柄泄漏。虽然 `_resolve_level` 在正常 CLI 使用中不太可能抛异常（`args.log_level` 来自 argparse choices），但在异常累积场景下可能发生
- **建议改法**: 在 finally 中用 try/finally 包裹恢复 stderr 的操作，确保 close 总是执行：
  ```python
  finally:
      if close_log_stream:
          try:
              runtime_log.set_level_from_flags(...)
          finally:
              log_stream.close()
  ```
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-测试未覆盖 plan 要求的连续调用场景

- **入口/函数**: 测试
- **文件(行号)**: `tests/cli/test_arg_parsing.py`
- **输入场景**: 第一次 `main(... --log-file ...)` 成功后，第二次 `main(...)` 不带 `--log-file`
- **实际分支**: 测试只覆盖单次调用场景
- **预期行为**: plan 要求验证 "一次 `main(... --log-file <tmp> ...)` 失败后，下一次不带 `--log-file` 的日志写入 stderr 不抛 `ValueError`，且不写入已关闭文件"
- **实际行为**: 测试未覆盖此场景
- **直接证据**: `test_arg_parsing.py` 中没有连续调用测试；`test_main_configures_runtime_log_file_stream` 只验证单次调用
- **影响**: 如果 handler 清理不完整，连续调用可能出现 `ValueError: I/O operation on closed file` 或日志写入已关闭文件
- **建议改法**: 新增测试覆盖连续调用场景：第一次使用 `--log-file` 成功，第二次不使用 `--log-file`，验证日志正常写入 stderr 且不抛异常
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无

## Residual Risk

- **连续调用场景测试缺失**: plan 明确要求覆盖 "一次失败后，下一次不带 --log-file" 的场景，当前测试未覆盖。虽然 handler 清理逻辑看起来正确，但缺少回归保护。
- **handler close 语义**: `_reset_marker_handlers` 只 remove 不 close handler，依赖 main() 的 finally 块管理文件生命周期。如果未来有其他入口调用 `configure()` 时传入文件 stream，可能需要额外的 close 语义。当前实现正确，但设计依赖调用方遵守约定。

## Positive Observations

- `--log-file` 参数位置正确：在 `global_parent` 中注册，支持 command 前后位置
- 与 `--debug`/`--verbose` 正交性正确：`--log-file` 只改变 stream，不改变 log_level
- Fins direct UI 与 log 分离正确：测试验证了日志文件只接收诊断，stdout/stderr 用户 UI 保持原通道
- 异常路径覆盖良好：覆盖了 KeyboardInterrupt、SystemExit、RuntimeError（runner boom）
- finally 中恢复 stderr 后再关闭文件的顺序正确
