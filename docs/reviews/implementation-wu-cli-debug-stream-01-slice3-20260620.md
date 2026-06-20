# WU-CLI-DEBUG-STREAM-01 Slice 3 Implementation

## 结论

Slice 3 已完成。实现只修改 prompt / interactive CLI 测试，未修改生产代码、控制文档或 README。

## 动机判断

本切片目标成立。`--debug-stream` 是全局 CLI 日志开关，语义上不属于旧 Agent execution option；如果被误加入 `unsupported_execution_option_names()`，prompt / interactive 会在 command runner 层 fail fast，破坏 Slice 1/2 已建立的全局日志装配语义。prompt / interactive 现有测试已经通过 `cli_main.main(...)` 路由全局 flags，因此适合补充最小聚焦断言；argparse 解析矩阵仍由 `tests/cli/test_arg_parsing.py` 承担，不重复扩展。

## 改动

- `tests/cli/test_prompt_command.py`
  - 将 `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout` 参数化扩展到 `--debug-stream`。
  - 新增 `test_prompt_debug_stream_is_not_unsupported_execution_option`，用真实 `parse_cli_args(...)` 结果验证 `unsupported_execution_option_names(...)` 不返回 `--debug-stream`。
- `tests/cli/test_interactive_command.py`
  - 将 `test_interactive_verbose_debug_diagnostics_do_not_pollute_stdout` 参数化扩展到 `--debug-stream`。
  - 新增 `test_interactive_debug_stream_is_not_unsupported_execution_option`，用真实 `parse_cli_args(...)` 结果验证 `unsupported_execution_option_names(...)` 不返回 `--debug-stream`。

旧 unsupported flag 断言保持不变，仍覆盖：

- `--debug-sse`
- `--debug-tool-delta`
- `--debug-sse-sample-rate`
- `--debug-sse-throttle-sec`

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`
  - 通过：`56 passed`
  - 仅有既有 `edgar` 依赖弃用 warning。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过：无输出。

## README 触发判断

本次修改命中 `tests/` README 检查触发条件。`tests/README.md` 的 CLI 覆盖描述当前仍只写 `--verbose` / `--debug` stdout cleanliness；该描述属于 Slice 4 "README / tests README update" 的批准范围。Slice 3 允许文件不包含 README，因此本轮不修改 README，留给 Slice 4 统一同步。

## 残余风险

- 未新增 argparse 解析重复测试；按计划继续依赖 `tests/cli/test_arg_parsing.py` 的全局 flag 解析覆盖。
- 未处理 `memory_repair.catch_up.budget_exhausted`，该项按计划为已修复 bug 的噪音项，Slice 3 未发现实际回归证据。
