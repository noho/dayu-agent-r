# PR Review: WU-CLI-DEBUG-STREAM-01

## Scope

- Mode: PR
- PR: #158
- Title: WU-CLI-DEBUG-STREAM-01 debug stream diagnostics
- Author: noho
- Head branch: wu-cli-debug-stream-01
- Base branch: main
- URL: https://github.com/noho/dayu-agent-r/pull/158
- Reviewer: AgentMiMo
- Date: 2026-06-20
- Output file: docs/reviews/pr-review-wu-cli-debug-stream-01-mimo-20260620.md

## Review Checklist Results

### 1. Issue #148 需求满足度

**结论：满足。**

- `--debug`（`log_level="debug"`，level 10）不输出高频 per-delta stream diagnostics：`STREAM_DEBUG_LOG_LEVEL = 9 < 10`，delta ingest / heartbeat / SSE done-token 均使用 level 9，被 DEBUG 阈值抑制。直接证据：`dayu/runtime/log_levels.py:16`、`dayu/host/engine_ingest.py:3264-3265`、`dayu/engine/runners/openai/runner.py:897-898`、`dayu/engine/runners/openai/sse_parser.py:347-351`。
- `--debug-stream` 启用 STREAM_DEBUG（level 9），同时输出普通 DEBUG 和 stream diagnostics。直接证据：`dayu/runtime/log.py:240-241`。
- Precedence 正确：`debug_stream` > `log_level` > `quiet` > `debug` > `verbose` > `info` > default。`--debug-stream` 始终优先于 `--log-level`、`--quiet`、`--debug`。设计文档明确记录此为 intentional。直接证据：`dayu/runtime/log.py:240-241`（`_resolve_level` 首个判断）。
- 普通 DEBUG 诊断（`runner.attempt.start`、`runner.http.post`、`runner.http.response`）保持 `logging.DEBUG` 不变。直接证据：`dayu/engine/runners/openai/runner.py` diff 未改动这些日志行。

### 2. 用户 follow-up 处理

**结论：已正确处理。**

- 未来站点 reminder residual：PR review artifacts 记录用户已拒绝该 residual 为 unnecessary，当前代码无任何残留。diff 中未发现 future-site 相关实现代码。
- `--log-level critical`：`LOG_LEVEL_CHOICES` 已包含 `"critical"`（`dayu/cli/arg_parsing.py:22`），`LogLevel.CRITICAL` 枚举值为 `logging.CRITICAL`（`dayu/runtime/log.py:102`），测试覆盖 `("prompt", "hello", "--log-level", "critical"), "critical", False`（`tests/cli/test_arg_parsing.py` parametrize）。与 README `可选 debug、verbose、info、warn、error、critical` 对齐。

### 3. PR Body 准确性

**结论：准确。**

- 160 tests passed：实际运行 `pytest tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/cli/test_arg_parsing.py tests/host/test_logging.py tests/engine/runners/openai/test_runner_diagnostics.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q` 结果 `160 passed, 3 warnings`。✅
- pyright 0 errors：实际运行 `python -m pyright dayu/ tests/ utils/` 结果 `0 errors, 0 warnings, 0 informations`。✅
- Residual Risks None：经审查未发现未记录的残余风险。✅

### 4. 分层边界、LLM-facing 文本约束、README 触发规则、tests README

**结论：正确。**

- 分层边界：`--debug-stream` 仅通过 CLI → `runtime_log.set_level_from_flags()` 配置，不传入 Host / Engine request contract。`dayu.runtime.log_levels` 是层中立基础设施，Engine/Host 导入 `STREAM_DEBUG_LOG_LEVEL` 常量不违反分层约束。
- LLM-facing 文本约束：本 PR 不涉及 prompt、tool schema、Host/Engine 投影给 LLM 的文本内容。无违反。
- README 触发规则：`dayu/cli/` 变更 → 根目录 `README.md` 已更新（全局参数表、prompt/interactive 参数表、示例、说明）。`tests/` 变更 → `tests/README.md` 已更新（logging 测试覆盖描述、diagnostics 测试覆盖描述、`--debug-stream` 不进入旧执行参数）。
- tests/README.md 覆盖事实：新增的 `--debug-stream` 不进入旧 Agent 执行参数、`--debug-stream` 诊断不污染 stdout、STREAM_DEBUG 级别契约、delta ingest stream-debug gating、runner diagnostics stream-debug gating 均有对应测试覆盖。README 描述与测试实际行为一致。

### 5. memory_repair.catch_up.budget_exhausted

**结论：无回归。**

当前代码中 `memory_repair.py` 的 `MemoryProjectionRepairStopReason` 只有 `IDLE` / `TARGET_REACHED` / `FAILURE`，无 `budget_exhausted`。`dispatch.py` 中的 `retry_repair_budget_exhausted` 是 dispatch retry 语义，与 memory repair stop reason 无关。本 PR 未改动 `memory_repair.py` 或 `dispatch.py`。无回归证据。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `--log-level stream_debug` 被 argparse 拒绝（`stream_debug` 不在 `LOG_LEVEL_CHOICES` 中），但 `LogLevel.STREAM_DEBUG` 枚举存在。这是 intentional 设计：`--debug-stream` 是获取 STREAM_DEBUG 的唯一规范路径，`--log-level` 只接受标准级别。若未来需要通过 `--log-level` 指定 STREAM_DEBUG，需同步更新 `LOG_LEVEL_CHOICES`。当前不构成风险。
- `--debug-stream --quiet` 组合下 `--debug-stream` 静默覆盖 `--quiet`。help 文本已警告"不要与互相矛盾的日志等级参数组合使用"，但 argparse 不做硬校验。当前可接受。

## Conclusion

**PASS**

PR #158 正确实现 Issue #148 的全部需求：`--debug` 不再输出高频 per-delta stream diagnostics；`--debug-stream` 启用 STREAM_DEBUG 级别覆盖普通 DEBUG + stream delta / idle heartbeat / SSE done-token / Host per-delta ingest；precedence 设计合理且有测试覆盖；`--log-level critical` 已对齐；分层边界未被突破；160 tests passed、pyright 0 errors、tests/README.md 覆盖事实准确。无 must-fix findings。
