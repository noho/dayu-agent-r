# Code Review — WU-CLI-DEBUG-STREAM-01 Slice 3 (AgentDS)

## 结论：PASS

## Scope

- Mode: current changes
- Branch: wu-cli-debug-stream-01
- Base: main（默认）
- Output file: docs/reviews/code-review-wu-cli-debug-stream-01-slice3-ds-20260620.md
- Included scope:
  - `tests/cli/test_interactive_command.py`（新增 2 处 test + parametrize 扩展）
  - `tests/cli/test_prompt_command.py`（新增 2 处 test + parametrize 扩展）
  - `docs/host/issues-implementation-control.md`（gate bookkeeping）
- Excluded scope: 生产代码（plan Slice 3 禁止范围），README（deferred to Slice 4）
- Parallel review coverage: 无

## 审查方法

按 deepreview Current Changes Mode 执行。沿真实调用链逐行走读 `parse_cli_args → cli_main.main → command runner → unsupported_execution_option_names`，以及 `set_level_from_flags → configure → handler` 日志装配路径。执行 adversarial failure pass。

验证结果：`pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q` → 56 passed（3 个既有 edgar 弃用 warning）；`python -m pyright tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py` → 0 errors；`git diff --check` clean。

## Findings

未发现实质性问题。

### 逐条核对用户指定的重点审查项

**1. 改动严格限于 plan 允许范围**

Plan Slice 3 允许文件：`tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py`、以及需要 `ParsedCliArgs.debug_stream` 的构造辅助测试。实际 diff 仅修改这两个测试文件（外加控制文档 bookkeeping）。新增 imports（`unsupported_execution_option_names`）是必要的测试入口依赖。无生产代码改动。✓

控制文档更新（`docs/host/issues-implementation-control.md`）为 gate bookkeeping：gate 状态从 `implementation` 切换到 `review`，加入 Slice 3 artifact 引用和验证结果。不改变 plan scope、状态机或架构边界。非 scope 违规。

**2. `--debug-stream` 被验证为全局日志开关，不被 `unsupported_execution_option_names` 当作旧 Agent execution option**

`unsupported_execution_option_names()` 位于 `dayu/cli/agent_entrypoint.py:232`，通过检查 `ParsedCliArgs` 上具体的旧字段（`debug_sse`、`debug_tool_delta`、`thinking` 等）生成 unsupported 列表。`--debug-stream` 映射到 `args.debug_stream`（全局布尔字段），不在任何 if 分支中，不会被列入。

新增测试：
- `test_prompt_debug_stream_is_not_unsupported_execution_option()`（`test_prompt_command.py:1283`）——用 `parse_cli_args(("prompt", "--debug-stream", "请总结收入变化"))` 验证 `"--debug-stream" not in unsupported_execution_option_names(args)`。
- `test_interactive_debug_stream_is_not_unsupported_execution_option()`（`test_interactive_command.py:1359`）——对 interactive 同样验证。

通过全 CLI 路径的 stdout cleanliness 测试（传 `--debug-stream` 经 `cli_main.main()` 成功退出）提供了额外的集成验证。✓

**3. prompt/interactive stdout cleanliness 覆盖 `--debug-stream`，且不误测 stderr/log file 行为**

新增 parametrize entry：将 `"--debug-stream"` 加入既有 `("--verbose", "--debug", "--debug-stream")` 参数化列表。

调用链验证：
- `cli_main.main()` 在 `dayu/cli/main.py:98` 调用 `set_level_from_flags(stream=log_stream, ...)`，`log_stream` 是文件 handle（`_open_log_file` 或 `_open_default_log_file` 返回值），**不是** `sys.stdout`。
- 日志 handler（`dayu/runtime/log.py:270`）写目标 `stream=log_stream`（文件），不在 `capsys` 捕获范围内。
- `cleanup finally` block（`main.py:118-130`）将 handler 临时重定向到 `sys.stderr`，但此时无应用日志产生。

断言 `captured.out.strip() == "prompt answer"`（prompt）或 `captured.out.strip() == "answer for run-1"`（interactive）是强断言——任何额外 stdout 输出（包括 `[STREAM_DEBUG]` 记录）都会导致失败。`"[VERBOSE]" not in captured.out` 和 `"[DEBUG]" not in captured.out` 是额外的防御性断言。`"Activity:" not in captured.err` 确保 activity stream 不在 stderr 泄露。

stderr 行为：`capsys.readouterr()` 同时捕获 stdout 和 stderr，但日志写文件不写 stderr（cleanup block 除外）。测试不依赖 stderr 或 log file 内容，只验证 stdout 清洁度。✓

**4. 旧 unsupported flags 断言保持**

以下测试未修改：
- `test_prompt_command_rejects_unsupported_old_execution_flags`（`test_prompt_command.py:1268`）——参数化覆盖 `--thinking`、`--web-provider`、`--enable-tool-trace`、`--doc-limits-json`。
- `test_prompt_command_reports_all_unsupported_old_execution_flags`（`test_prompt_command.py:1295`）——覆盖 `--debug-sse`、`--debug-tool-delta`、`--debug-sse-sample-rate`、`--debug-sse-throttle-sec`、`--tool-trace-dir`、`--max-duplicate-tool-calls`、`--duplicate-tool-hint-prompt`、`--fins-limits-json`。
- `test_interactive_unsupported_old_flag_exits_with_usage_error`（`test_interactive_command.py:1346`）——覆盖 `--thinking`。
- `test_interactive_reports_all_unsupported_old_execution_flags`（`test_interactive_command.py:1371`）——覆盖完整旧 flag 集合。

所有断言（错误码 `EXIT_USAGE_ERROR`、错误消息 `"unsupported option"`、具体 flag 名称 string match）保持不变。✓

**5. 测试无 brittle coupling、无重复解析矩阵、无 LLM-facing 文本问题**

- **Brittle coupling**: 新测试直接使用 `parse_cli_args()` 和 `unsupported_execution_option_names()` 的公共接口，不依赖内部实现细节、不 mock 内部函数、不依赖 log file 内容或 handler 配置。
- **重复解析矩阵**: 未新增 argparse 解析参数化矩阵。argparse 的 `--debug-stream` 全局 flag 解析和组合行为由 `tests/cli/test_arg_parsing.py`（Slice 1）覆盖。Slice 3 只做聚焦的 unsupported 守卫验证和 stdout cleanliness 验证。
- **LLM-facing 文本**: 测试 docstring 为中文开发者文档，非 LLM-facing content（不进入 scene prompt、tool schema、Host/Engine message、memory/compact/evidence material）。`ParseCliArgs` 调用传入的中文 prompt `"请总结收入变化"` 不构成 LLM-facing 文本质量风险。

无 `memory_repair.catch_up.budget_exhausted` 相关代码触发——该项按 plan 目标排除，且修改的测试文件中没有任何 memory_repair 引用。✓

**6. `memory_repair.catch_up.budget_exhausted`**

按用户指令不作为 finding。确认 diff 中无 memory_repair 相关代码或测试变更。无实际回归证据。

## Open Questions

无

## Residual Risk

- Slice 3 不验证 `--debug-stream` + `--debug` 组合对 stdout 的影响——该组合由 Slice 1 的 `tests/cli/test_arg_parsing.py` 覆盖（解析正确性）和 `tests/runtime/test_log.py` 覆盖（运行时级别解析）。
- Slice 3 不验证 `--debug-stream` 对 log file 内容的正确性（流诊断记录确实出现在 log file），该行为由 Slice 2 的 `tests/host/test_logging.py` 和 `tests/engine/runners/openai/test_runner_diagnostics.py` 覆盖。
- `test_{prompt,interactive}_verbose_debug_diagnostics_do_not_pollute_stdout` 的 docstring 写 `"verbose/debug 诊断"` 但 parametrize 现包括 `--debug-stream`；不影响测试正确性，可在 Slice 4 统一刷新。
