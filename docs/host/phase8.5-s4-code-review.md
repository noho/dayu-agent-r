# P8.5 Slice 4 Code Review

- Review gate name: `code review`
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: Slice 4 — Compact / RunInput / SSE Partial Semantic Cleanup
- Reviewed target: current uncommitted diff after Slice 3 commit `d204132`
- Approved plan: `docs/host/phase8.5-plan.md`
- Implementation artifact: `docs/host/phase8.5-s4-implementation-report.md`
- Reviewer conclusion: `fail`
- Artifact path: `docs/host/phase8.5-s4-code-review.md`

## Scope Evidence Summary

- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` hot fact no longer carries inline raw payload fields; it now carries blob id, sha256, and byte size refs for input messages and tool schemas (`dayu/host/contracts.py:356-393`, `dayu/host/_run_event_serializer.py:1127-1181`).
- `run_input_raw_payloads` schema matches the plan columns, allowed payload kinds, unique key, and `(session_id, run_id)` index (`dayu/host/_run_input_raw_payload_store.py:26-48`).
- The writer is called inside the same `HostStorage.transaction()` as EventLog append (`dayu/host/_run_harness.py:2331-2345`); rollback behavior is covered by `tests/host/test_phase7_tool_trace_projection.py:530-558`.
- The reader validates missing row, hash mismatch, byte size mismatch, invalid JSON, and kind mismatch in code (`dayu/host/_run_input_raw_payload_store.py:291-336`). Tests cover missing row, hash mismatch, invalid JSON, kind mismatch, and rollback, but do not directly cover byte size mismatch.
- Trace projection reads side-store rows and raises `ProjectionSchemaError` on side-store read failure instead of synthesizing fake raw payloads (`dayu/host/_tool_trace_projection.py:493-528`).
- The non-transactional observer path records failures before checkpoint advance, and checkpoint success is only advanced after `process_non_transactional` succeeds (`dayu/host/_event_observer.py:391-431`).
- Host RunEventType remains provider-neutral; no provider-specific RunEventType was added (`dayu/host/contracts.py:40-70`).
- Serializer registry is closed over current RunEventType values and does not add an old inline EventLog compatibility reader (`dayu/host/_run_event_serializer.py:143-197`, `dayu/host/_run_event_serializer.py:1338-1367`).

## Findings

### S4-CR-01-未修复-[高]-usage malformed 协议错误后仍会产出成功完成事件并可能驱动工具执行

- **入口/函数**: OpenAI SSE parser 的 `_handle_usage()` / `_finalize_success()`；下游 Engine `_classify_iteration()`。
- **文件(行号)**: `dayu/engine/runners/openai/sse_parser.py:416-438`, `dayu/engine/runners/openai/sse_parser.py:452-504`, `dayu/engine/agent.py:1234-1311`, `tests/engine/runners/openai/test_event_flow_ordering.py:15-17`
- **输入场景**: SSE 先收到合法 tool call delta，再收到 malformed `usage`，随后收到 `finish_reason="tool_calls"` / `[DONE]`。最小复现验证输出为：`runner_tool_call_delta` -> `provider_protocol_error usage_field_malformed` -> `runner_tool_calls_completed` -> `runner_done`。
- **实际分支**: `_handle_usage()` 在 token 字段非 `int` 时只 yield `RunnerProtocolErrorData(error_code="usage_field_malformed")` 并 `return`，没有设置 `_terminated` / `_fatal_terminated`，也没有 yield `RunnerDoneData(ERROR)`；后续 `[DONE]` 继续进入 `_finalize_success()`，当 `_tool_calls_seen` 为真时会 finalize aggregator 并 yield `RunnerToolCallsCompletedData`。
- **预期行为**: Slice 4 plan 要求 SSE provider/protocol failure data 携带 bounded partial summary，且该 diagnostic 不驱动 tool execution；现有 ordering test 文档也写明 `PROVIDER_PROTOCOL_ERROR` 出现时必须紧随 `RUNNER_DONE(ERROR)`，不得再出现成功 completed 事件。
- **实际行为**: `usage_field_malformed` 已经是 `PROVIDER_PROTOCOL_ERROR`，但同一次 Runner stream 之后仍能产出 `RUNNER_TOOL_CALLS_COMPLETED` 或 `RUNNER_CONTENT_COMPLETED` 以及非 ERROR `RUNNER_DONE`。在 tool call 场景下，Agent 会在 `_classify_iteration()` 中把 `state.tool_calls` 分类为 `_ToolCallsDecision`，从而继续执行工具。
- **直接证据**: `sse_parser.py:429-437` 构造 `RunnerProtocolErrorData` 后直接返回；`sse_parser.py:468-487` 在 `_tool_calls_seen` 时产出 `RunnerToolCallsCompletedData`；`agent.py:1251-1293` 对 `state.tool_calls is not None` 且 `finish_reason is TOOL_CALLS` 的分支会生成工具调用决策；`test_event_flow_ordering.py:15-17` 记录了错误必须 Done(ERROR) 且不得再出现 successful completed 的不变量。
- **影响**: provider 协议错误后的工具执行不应发生；当前会把 malformed usage 之后的完成事件当作成功路径，造成错误状态、错误 terminal 语义，甚至在协议错误后执行工具。
- **建议改法和验证点**: 把 `usage_field_malformed` 收口为 fatal protocol error：设置 terminal 状态并立即 yield `RunnerDoneData(FinishReason.ERROR)`，或统一抽取 fatal protocol error helper，确保 invalid UTF-8 / invalid JSON / payload not object / malformed usage 行为一致。新增测试覆盖 malformed usage 后不得出现 `RUNNER_CONTENT_COMPLETED` / `RUNNER_TOOL_CALLS_COMPLETED`，并且 Done 必须是 ERROR；尤其要覆盖合法 partial/complete tool call + malformed usage 不会驱动工具执行。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高
- **Controller decision status**: `pending-controller-decision`

### S4-CR-02-未修复-[中]-partial_tool_calls summary 并未真正有界

- **入口/函数**: OpenAI `ToolCallAggregator.partial_summaries()`。
- **文件(行号)**: `docs/host/phase8.5-plan.md:655-657`, `dayu/engine/runners/openai/tool_call_aggregator.py:186-200`, `dayu/engine/runners/openai/tool_call_aggregator.py:320-348`
- **输入场景**: provider 连续发送大量 tool call indices，或在 `function.name` 中流式发送超长字符串，然后 SSE 中途触发 invalid JSON / invalid UTF-8 / payload not object / usage malformed。
- **实际分支**: `feed()` 对每个 resolved index 都在 `_partials_by_index` 保留一个 `_PartialToolCall`，并对 `function.name` 直接 `partial.name += name`；`partial_summaries()` 遍历全部 partial，把完整 `partial.name` 作为 `name_fragment` 写入 summary，没有最大条数、最大 name 长度或截断标记。
- **预期行为**: Plan 要求 provider/protocol failure data 只加入 bounded `partial_tool_calls` summary，并且不包含 raw argument payload。这里不仅 arguments 要避免 raw payload，summary 本身也必须在数量和字符串长度上有硬边界，才能进入 Engine / Host EventLog / trace。
- **实际行为**: `arguments` 被压成 byte size + sha256，但 `name_fragment` 与 summary item 数量仍是 provider 可控的无界数据。错误事件会经 `ProviderProtocolErrorData.partial_tool_calls` 进入 Host serializer 和 trace record。
- **直接证据**: `tool_call_aggregator.py:186-200` 无限制创建 partial 并累积 name；`tool_call_aggregator.py:327-348` 无限制遍历全部 partial，且 `name_fragment=partial.name or None`。Plan 在 `docs/host/phase8.5-plan.md:655-657` 明确要求 bounded summary。
- **影响**: 恢复了 P8.5 想从 EventLog hot row 移除的无界 provider-controlled payload 风险；极端流可放大 `PROVIDER_PROTOCOL_ERROR` 事件、trace JSONL 和 analyzer 内存占用。
- **建议改法和验证点**: 为 partial summary 增加模块级常量边界，例如最大 summary 条数、最大 `name_fragment` 字节数/字符数，并在被截断时保留可诊断的 hash/byte size/截断标记。新增测试覆盖超长 name 和大量 partial index，断言 serialized `partial_tool_calls` 大小受控且仍不包含 raw arguments。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中
- **Controller decision status**: `pending-controller-decision`

## Open Questions And Residual Risk

- `byte_size_mismatch` reader 分支在生产代码中存在，但指定测试集没有直接覆盖该 failure code；建议修复 pass 顺手补一条最小测试，避免未来 hash / byte 校验顺序改动时漏保护。
- Provider stream transport-layer read failure 仍按 implementation report 归入后续 provider adapter 扩展测试范围；本 review 未把它作为 Slice 4 blocker。

## Validation Run

```bash
source .venv/bin/activate && python -m pyright dayu/engine/ dayu/host/ tests/engine/ tests/host/
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/host/test_phase4_overflow_retry.py tests/host/test_phase7_run_input_context_fact.py tests/host/test_phase7_contract_serializer.py -q
# 25 passed

source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py -q
# 16 passed

source .venv/bin/activate && pytest tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_event_flow_ordering.py -q
# 13 passed

source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q
# 17 passed
```

