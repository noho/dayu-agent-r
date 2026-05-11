# P8.5 Slice 4 Re-review

- Review gate name: `re-review`
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: Slice 4 — Compact / RunInput / SSE Partial Semantic Cleanup
- Source review artifact: `docs/host/phase8.5-s4-code-review.md`
- Fix artifact: `docs/host/phase8.5-s4-fix-report.md`
- Accepted findings reviewed: `S4-CR-01`, `S4-CR-02`
- Reviewed target: current workspace after fix pass
- Reviewer conclusion: `pass`
- Artifact path: `docs/host/phase8.5-s4-rereview.md`

## Scope Boundary

本次只复核 controller accepted findings：

- `S4-CR-01`: malformed `usage` 必须是 fatal；`usage_field_malformed` 后必须出现 `RunnerDone(ERROR)`，且不得再出现 tool call/content completed 或非错误 done；必须覆盖 tool-call 场景。
- `S4-CR-02`: `partial_tool_calls` summary 必须限制 item 数量和 `name_fragment` 长度；不得包含 raw arguments；测试必须覆盖大量 partials 和超长 name。

按 handoff 要求，额外只核验 fix pass 提到的 `byte_size_mismatch` side-store 测试是否存在并通过；未扩大到其它未接受 finding 或后续 slice 范围。

## Re-review Result

### S4-CR-01-fixed-usage malformed 已按 fatal protocol error 收口

- **入口/函数**: OpenAI SSE parser `_handle_usage()`
- **文件(行号)**: `dayu/engine/runners/openai/sse_parser.py:416`
- **复核结论**: fixed
- **直接证据**:
  - `usage` token 字段非 `int` 时，分支产出 `RunnerProtocolErrorData(error_code="usage_field_malformed", partial_tool_calls=...)`。
  - 同一分支随后设置 `self._fatal_terminated = True` 与 `self._terminated = True`，并立即产出 `RunnerDoneData(finish_reason=FinishReason.ERROR)`，然后 `return`。
  - 主解析循环在 `_terminated` 后返回，后续 `finish_reason="tool_calls"` / `[DONE]` 不再进入成功收口。
- **测试证据**:
  - `tests/engine/runners/openai/test_protocol_error.py:140` 覆盖合法 tool call delta 后接 malformed usage、后续 `finish_reason="tool_calls"` 与 `[DONE]` 的场景。
  - 断言事件序列精确为 `RUNNER_TOOL_CALL_DELTA -> PROVIDER_PROTOCOL_ERROR -> RUNNER_DONE`，`RunnerDone` finish reason 为 `ERROR`，并且没有 `RUNNER_TOOL_CALLS_COMPLETED` / `RUNNER_CONTENT_COMPLETED`。
- **fix 是否引入 blocker**: 未发现。

### S4-CR-02-fixed-partial summaries 已有数量与名称片段硬边界

- **入口/函数**: OpenAI `ToolCallAggregator.partial_summaries()`
- **文件(行号)**: `dayu/engine/runners/openai/tool_call_aggregator.py:40`, `dayu/engine/runners/openai/tool_call_aggregator.py:335`
- **复核结论**: fixed
- **直接证据**:
  - 模块级常量 `PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS = 16` 与 `PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS = 128` 明确给出硬边界。
  - `_bounded_name_fragment()` 对非空 name 只返回前 `PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS` 个字符。
  - `partial_summaries()` 只遍历排序后的前 `PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS` 个 partial。
  - summary 只写入 `arguments_byte_size` 与 `arguments_sha256`，没有写入 raw `arguments_buffer`。
- **测试证据**:
  - `tests/engine/runners/openai/test_protocol_error.py:86` 覆盖 `PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS + 7` 个 partial 和超长 function name。
  - 测试断言 summary item 数量被截断为最大值、索引只保留前 N 个、`name_fragment` 不超过最大长度且等于截断前缀。
  - 测试还断言 `arguments_byte_size` 和 `arguments_sha256` 保留诊断信息，并通过 `repr(partials)` 确认 raw argument 片段 `"should-not-appear"` 不泄漏。
- **fix 是否引入 blocker**: 未发现。

## Additional Requested Check

- `byte_size_mismatch` side-store 测试已存在：`tests/host/test_phase7_tool_trace_projection.py:654`。
- 该测试写入 run input raw payload 后构造错误 `byte_size` ref，并断言 `get_run_input_raw_payload()` 抛出 `RunInputRawPayloadReadError` 且错误匹配 `byte_size_mismatch`。
- 指定 host trace projection 测试集已通过，说明该新增测试当前可执行且通过。

## Validation Run

```bash
source .venv/bin/activate && python -m pyright dayu/engine/ tests/engine/ dayu/host/ tests/host/
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_event_flow_ordering.py -q
# 15 passed in 0.12s

source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py -q
# 17 passed in 0.15s

source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q
# 17 passed in 0.05s
```

## Open Questions And Residual Risk

- Accepted findings `S4-CR-01` 与 `S4-CR-02` 均已修复并由指定测试覆盖。
- 未发现 fix pass 引入新的 blocker。
- 剩余风险：本次 re-review 未扩大审查到未接受 finding、后续 provider adapter 扩展测试或全仓未提交 diff。

## Conclusion

`pass`
