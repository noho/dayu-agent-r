# Code Review

## Scope

- Mode: current changes
- Branch: wu-cli-debug-stream-01
- Base: main
- Output file: `docs/reviews/code-review-wu-cli-debug-stream-01-slice3-mimo-20260620.md`
- Included scope: unstaged diff（`tests/cli/test_interactive_command.py`、`tests/cli/test_prompt_command.py`、`docs/host/issues-implementation-control.md`）及 untracked artifact `docs/reviews/implementation-wu-cli-debug-stream-01-slice3-20260620.md`
- Excluded scope: 无
- Parallel review coverage: 无

## Design Source / Plan Reference

- 设计真源：`docs/host/design.md`、`docs/engine/design.md`
- 总控：`docs/host/issues-implementation-control.md`
- 计划：`docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md` Slice 3（lines 202–221）

## Findings

未发现实质性问题。

逐项审查说明：

### 1. 改动是否严格限于计划允许范围

计划 Slice 3 允许文件：`tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py`。

实际修改文件：
- `tests/cli/test_prompt_command.py` ✅
- `tests/cli/test_interactive_command.py` ✅
- `docs/host/issues-implementation-control.md`（gateflow 总控状态更新，非生产代码、非测试代码，属于 gate 流程的控制文档同步，计划未显式禁止）

无生产代码改动。`dayu/cli/` 下无任何文件被修改。符合计划意图。

### 2. `--debug-stream` 是否被验证为全局日志开关而非 unsupported execution option

`unsupported_execution_option_names`（`agent_entrypoint.py:232-265`）检查 12 个旧执行参数（`--thinking`、`--web-provider`、`--debug-sse`、`--debug-tool-delta` 等），不包含 `debug_stream`。这是正确设计：`--debug-stream` 是全局日志开关，定义在 `_build_global_arguments_parent()`（`arg_parsing.py:349-358`），通过 shared parent parser 注册到所有子命令。

新增测试：
- `test_interactive_debug_stream_is_not_unsupported_execution_option`（interactive_command.py:1359）：解析 `("interactive", "--debug-stream")` 后断言 `--debug-stream` 不在 `unsupported_execution_option_names(args)` 中。
- `test_prompt_debug_stream_is_not_unsupported_execution_option`（prompt_command.py:1283）：解析 `("prompt", "--debug-stream", "请总结收入变化")` 后同理断言。

两个测试均走完整的 `parse_cli_args` → `unsupported_execution_option_names` 链路，验证了生产代码的真实行为。✅

### 3. prompt/interactive stdout cleanliness 是否覆盖 `--debug-stream` 且不误测 stderr/log file 行为

原有 `test_interactive_verbose_debug_diagnostics_do_not_pollute_stdout` 和 `test_prompt_verbose_debug_diagnostics_do_not_pollute_stdout` 的 parametrize 从 `("--verbose", "--debug")` 扩展为 `("--verbose", "--debug", "--debug-stream")`。

测试逻辑：
- 调用 `cli_main.main()` 执行完整 CLI 链路
- `capsys.readouterr()` 捕获 stdout 和 stderr
- 断言 `exit_code == EXIT_SUCCESS`
- 断言 `captured.out.strip()` 等于预期答案（"answer for run-1" 或 "prompt answer"）
- 断言 `"[VERBOSE]" not in captured.out` 和 `"[DEBUG]" not in captured.out`

`--debug-stream` 启用 DEBUG 级别日志。如果诊断日志泄漏到 stdout，`captured.out.strip()` 不会等于纯答案文本，且 `[DEBUG]` 标记检查也会捕获。测试通过说明 stdout 未被污染。

测试不检查 stderr 或 log file 行为——这是正确边界。stdout cleanliness 测试的职责是验证用户结果通道不被诊断日志污染，不验证诊断日志本身的输出目标（那是 logging 配置的职责）。✅

### 4. 旧 unsupported flags 断言是否保持

- `test_interactive_unsupported_old_flag_exits_with_usage_error`（line 1346）：未修改，仍验证 `--thinking` 导致 `EXIT_USAGE_ERROR`。
- `test_prompt_command_rejects_unsupported_old_execution_flags`（line 1259）：未修改，仍验证 `--thinking`、`--web-provider`、`--enable-tool-trace`、`--doc-limits-json`。
- `test_interactive_reports_all_unsupported_old_execution_flags`（line 1371）：未修改。
- `test_prompt_command_reports_all_unsupported_old_execution_flags`（line 1295）：未修改。

全部保持。✅

### 5. 测试是否无 brittle coupling、无重复解析矩阵、无 LLM-facing 文本问题

- 新增测试使用公开 API（`parse_cli_args`、`unsupported_execution_option_names`），不依赖内部实现细节。
- 不重复 `test_arg_parsing.py` 已覆盖的解析矩阵，仅聚焦 prompt/interactive 命令的 unsupported option guard 和 stdout cleanliness。
- docstring 和断言文本不涉及 LLM-facing 内容，均为开发者可读的测试描述。✅

### 6. `memory_repair.catch_up.budget_exhausted`

控制文档明确记录此为已修复 bug，不在 Slice 3 实现范围内。diff 中未引入相关代码或断言。✅

## Open Questions

无。

## Residual Risk

- stdout cleanliness 测试对 `--debug-stream` 的覆盖依赖 `[DEBUG]` 标记检查。如果未来 stream-specific 诊断使用不同于 `[DEBUG]` 的标记格式（如 `[STREAM_DEBUG]`），该测试可能无法捕获泄漏。当前 Slice 1/2 实现中 stream 诊断仍使用标准 DEBUG 级别，因此风险不实际。Slice 4 README 更新时可补充说明。
- 控制文档 `issues-implementation-control.md` 的修改不在计划 Slice 3 显式允许文件列表中，但属于 gateflow 标准流程同步，不构成 scope violation。

## Verdict

**PASS**
