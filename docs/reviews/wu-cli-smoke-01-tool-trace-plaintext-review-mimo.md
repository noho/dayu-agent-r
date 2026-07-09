# Tool Trace 明文可审计性修复 Review

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: unstaged workspace changes (files modified but not committed)
- Output file: `docs/reviews/wu-cli-smoke-01-tool-trace-plaintext-review-mimo.md`
- Included scope: `dayu/engine/agent.py`, `dayu/engine/contracts/engine_events.py`, `dayu/host/run_input.py`, `dayu/host/engine_ingest.py`, `dayu/host/tool_trace.py`, `dayu/host/durable/tool_trace.py`, `dayu/host/durable/schema.py`, `docs/engine/design.md`, `docs/host/design.md`, `dayu/engine/README.md`, `dayu/host/README.md`, `tests/README.md`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_tool_trace_queries.py`
- Excluded scope: staged changes (`git diff --cached`), committed changes (`git diff main...HEAD`), CLI/UI/Service 层改动
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 分层正确性验证

**Host/Engine 分层正确**：

- `dayu/engine/agent.py:259-330`：`_runner_input_projection()` 使用 `match` 语句处理 `AgentMessage` 封闭联合，只暴露 `index`、`role`、`content`、`tool_call_id`、`tool_calls`。不包含 Host refs、provider headers、Authorization/API key 或 provider raw request。
- `dayu/engine/contracts/engine_events.py:59-93`：`RunnerInputMessageProjection` 和 `RunnerInputToolCallProjection` 是纯数据容器，字段类型明确（`str | None`、`tuple[RunnerInputToolCallProjection, ...]`），无 `Any` 或 `object`。
- `dayu/host/engine_ingest.py:4708-4757`：`_observed_runner_call_projection_body()` 在 Engine 中性投影基础上添加 `session_id`、`run_id`、`attempt_id`、`execution_id`、`runner_call_index` 等 Host 治理信息。分层边界清晰。

**Bounded payload 验证**：

- `dayu/host/engine_ingest.py:4861-4974`：`_limited_runner_call_manifest_body()` 的 hot payload 只保存 `runner_call_projection_artifact_ref`、`runner_call_projection_artifact_digest`、`runner_call_projection_artifact_size_bytes`。完整明文通过 projection payload descriptor 按需 resolve。
- `dayu/host/run_input.py:4529-4579`：`_runner_call_manifest_body()` 同样只保存 ref/digest/size，不内联大明文。

**完整 LLM-facing messages 验证**：

- `dayu/host/engine_ingest.py:4753-4756`：projection body 的 `messages` 字段保存完整 messages 数组。
- `dayu/host/engine_ingest.py:4770-4791`：`_observed_projection_message()` 为每条消息构造包含 `content` 明文的 projection。
- `dayu/host/run_input.py:4306-4366`：`_runner_call_projection_message()` 为 Host 路径的每条消息构造包含 `content` 明文的 projection。

**Schema snapshot 安全验证**：

- `dayu/host/run_input.py:4503-4526`：`_tool_schema_json()` 只保存 LLM-facing schema（`type`、`function.name`、`function.description`、`function.parameters`），不包含 provider secret。
- `dayu/host/run_input.py:4370-4386`：`_provider_state_projection()` 只保存 `provider` 和 `state_digest`（`sha256:{"thought_signature": ...}`），不保存 raw `thought_signature`。

**Resolver API 验证**：

- `dayu/host/durable/tool_trace.py:360-404`：`resolve_runner_call_projection_from_signal()` 从 signal 解析 manifest，再从 manifest 解析 projection ref/digest，最终读取并校验 projection payload。缺失 ref 时抛出 `HostDurableError`，不伪造。
- `dayu/host/durable/tool_trace.py:407-439`：`resolve_tool_trace_hot_row_payloads()` 从 hot row 或 source payload 解析 descriptor ref/digest，最终读取并校验 payload。
- `dayu/host/durable/tool_trace.py:442-488`：`read_tool_trace_json_payload()` 读取 descriptor、校验 expected_digest、读取 SQLite payload、校验实际 payload digest，四重校验确保数据完整性。

**Continuation 覆盖验证**：

- `dayu/host/engine_ingest.py:2747-2772`：当 `_has_complete_observed_input_projection(data)` 为 True（`len(data.input_projection) > 0 and len(data.input_projection) == data.message_count`）时，Host 写 complete manifest 和 projection payload。
- `dayu/host/engine_ingest.py:4884-4913`：`_limited_runner_call_manifest_body()` 中，当 `projection_descriptor` 存在时，diagnostic 为 None，message_entries 有内容；当 `projection_descriptor` 为 None 时，diagnostic 为 limited_signal，message_entries 为空列表。
- `dayu/host/engine_ingest.py:5855-5869`：`_resolution_from_limited_manifest_event()` 中，`continuation_limited_signal` 由 `_manifest_validation_status()` 决定，complete manifest 返回 `False`，limited_signal manifest 返回 `True`。

**测试覆盖验证**：

- `tests/host/test_engine_ingest_mapping.py:3565-3667`：`test_iteration_started_continuation_with_projection_writes_complete_manifest()` 验证 tool-loop continuation 携带 observed projection 时写 complete manifest，断言 `validation_status == "complete"`、`diagnostic is None`、`runner_call_projection_artifact_ref is not None`、`continuation_limited_signal is False`、message_entries 长度为 4、最后一条 message 的 projection_artifact_ref 与 hot payload 一致。
- `tests/host/test_run_input_builder.py:517-540`：`test_runner_call_manifest_is_bounded_and_does_not_inline_messages()` 验证大 prompt 不进 manifest，但通过 projection payload 可 resolve，且 `messages[-1]["content"]` 等于原始大 prompt，`messages[-1]["content_digest"]` 等于 manifest entry 的 content_digest。
- `tests/host/test_run_input_builder.py:699-757`：`test_tool_enabled_manifest_resolves_selected_schema_snapshot()` 验证 manifest 引用可恢复的 selected tool schema full JSON，断言 `lookup_filing` 在 schema names 中。
- `tests/host/test_tool_trace_queries.py:658-820`：`test_runner_call_projection_resolver_reads_manifest_projection_and_schema()` 验证 resolver 能从 signal 恢复明文 input（`# 当前时间`、`V（Visa Inc.）`）和 schema（`get_current_time`）。`test_tool_trace_row_resolver_reads_args_result_and_final_answer()` 验证 row resolver 能读取工具参数、工具结果 payload 和 terminal final answer。

## Open Questions

无。

## Residual Risk

1. **`_has_complete_observed_input_projection()` 只检查长度一致**：不检查每条消息的 content 是否非空或 tool_calls 是否完整。但 Engine 的 `_runner_input_projection()` 使用 `match` + `assert_never` 保证封闭联合完整性，实践中不会产生"长度一致但内容缺失"的 projection。风险低。

2. **`_limited_runner_call_manifest_body` 函数命名**：函数名含 "limited"，但当 `projection_descriptor` 存在时实际生成 complete manifest。函数名略有误导，但内部逻辑正确。建议后续重命名为 `_runner_call_manifest_body_from_engine_iteration` 或类似。风险低。

3. **Schema snapshot 包含完整 tool description 和 parameters**：这是 LLM-facing 内容，符合设计意图。但如果 tool description 包含业务敏感信息（如内部 API 端点、策略规则），这些会持久化到 SQLite。需要后续 retention/purge owner 处理。

4. **Provider state 只保存 digest**：`_provider_state_projection()` 只保存 `state_digest`，不保存 raw `thought_signature`。这意味着 analyzer 无法从 projection 恢复原始 thought_signature，只能验证 digest 是否匹配。符合安全要求，但限制了 debug 能力。

5. **Resolver API 只支持 SQLite JSON payload**：`read_tool_trace_json_payload()` 在 `descriptor.payload_kind is not PayloadKind.SQLITE_PAYLOAD` 时抛出异常。如果未来 payload 迁移到其他存储（如文件系统），resolver 需要扩展。

6. **测试未覆盖 projection 缺失时的 resolver 行为**：当前测试只覆盖了 projection 存在时的 resolve 路径。如果 manifest 的 `runner_call_projection_artifact_ref` 为 None，`resolve_runner_call_projection_from_signal()` 会抛出 `HostDurableError`，但没有测试验证这个行为。建议补充测试。

7. **`_observed_runner_call_projection_body()` 和 `_runner_call_projection_body()` 存在重复逻辑**：两个函数都构造 projection body，但一个用于 Engine continuation 路径，一个用于 Host RunInputBuilder 路径。字段结构略有不同（如 `iteration_id`/`iteration_index` 在 continuation 中有值，在 RunInputBuilder 中为 None）。这是合理的分层设计，但增加了维护成本。
