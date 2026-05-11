# P8.5 Slice 4 Fix Report

- Work gate: `fix`
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: Slice 4 — Compact / RunInput / SSE Partial Semantic Cleanup
- Source review artifact: `docs/host/phase8.5-s4-code-review.md`
- Implementation artifact: `docs/host/phase8.5-s4-implementation-report.md`
- Artifact path: `docs/host/phase8.5-s4-fix-report.md`

## Accepted Findings

- `S4-CR-01`: accepted。`usage_field_malformed` 必须按 fatal provider protocol error 收口，不得继续产出 successful completed / done，也不得驱动 tool execution。
- `S4-CR-02`: accepted。`partial_tool_calls` summary 必须对 item 数量和 `name_fragment` 长度有硬边界，且仍不得包含 raw arguments。

## Fix Status

- `S4-CR-01`: fixed。
  - `SSEParser._handle_usage()` 在 usage 字段非整数时产出 `RunnerProtocolErrorData(error_code="usage_field_malformed", partial_tool_calls=...)` 后，立即设置 fatal / terminated 状态并产出 `RunnerDoneData(FinishReason.ERROR)`。
  - 新增 tool-call 场景测试：合法 tool call delta 后接 malformed usage 与后续 `finish_reason="tool_calls"` / `[DONE]`，断言事件序列只允许 tool delta → protocol error → error done，不产出 `RUNNER_TOOL_CALLS_COMPLETED` 或 `RUNNER_CONTENT_COMPLETED`。
- `S4-CR-02`: fixed。
  - `ToolCallAggregator.partial_summaries()` 新增模块级硬边界：`PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS` 与 `PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS`。
  - summary 只返回排序后的前 N 个 partial，`name_fragment` 按字符数截断；仍保留 `arguments_byte_size` 与 `arguments_sha256`，不写入 raw argument payload。
  - 新增测试覆盖大量 partial indices 与超长 function name，断言 summary item 数量、name 长度与 raw arguments 泄漏边界。
- Non-blocking note: fixed opportunistically。
  - 新增 `byte_size_mismatch` side-store reader typed failure 测试。

## Changed Files

- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/engine/contracts/partial_tool_call.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/host/test_phase7_tool_trace_projection.py`
- `docs/host/phase8.5-s4-fix-report.md`

## Validation

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_event_flow_ordering.py -q
# 15 passed

source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py -q
# 17 passed

source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q
# 17 passed

source .venv/bin/activate && python -m pyright dayu/engine/ tests/engine/ dayu/host/ tests/host/
# 0 errors, 0 warnings, 0 informations
```

## Documentation Decision

- README 未更新：本 fix 没有改变已记录的对外行为描述，只把已声明的 fatal protocol error 与 bounded partial summary 语义补齐为真实实现。

## Residual Risks And Uncovered Areas

- Current-slice accepted findings: no unresolved accepted findings。
- New risks / open questions: none observed。
- Residual risk classification: low。Runner event ordering 已覆盖 malformed usage 的 tool-call 场景；Engine/Agent 层未新增执行工具集成测试，但 runner 事件序列已直接阻断 `RUNNER_TOOL_CALLS_COMPLETED`，不会给 Agent 的工具执行分类提供成功 tool-call 终态。
