# Gateflow Implementation Artifact: Engine/OpenAI OLD reliable logic absorption

日期：2026-05-12
work gate：implementation
work unit：吸收 OLD OpenAI/Engine 中应进入当前 Engine 的可靠逻辑
approved plan：`docs/reviews/gateflow-plan-provider-request-id-20260512.md`

## Assigned Scope

- 落地 `provider_request_id` 采集与 Runner/Engine 透传。
- 在 OpenAI-compatible Runner 内执行 `RunnerSpec.supports_streaming=False` 的 non-stream 降级。
- 吸收 HTTP retry/error 诊断细节：provider request id、HTTP JSON object error body `raw_payload`、最终失败 attempt request id。
- HTTP 200 且 effective stream 为 `True` 时，对未知或非 JSON `Content-Type` fallback 到 SSE parser。
- 恢复强类型 Engine 工具观测事件：`tool_call_delta`、`tool_calls_batch_ready`、`tool_calls_batch_done`。

## Explicit Non-goals

- 未实现语义级重复工具调用治理。
- 未实现 tool result capping/truncation。
- 未实现工具批次并发。
- 未引入 Host 依赖。
- 未恢复 `event_id` / `sequence`。
- 未使用 `metadata` 承载契约事实。
- 未修改 `docs/host/tracking.md`。

## Changed Files

- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/__init__.py`
- `dayu/engine/agent.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `tests/engine/contracts/test_runner_events.py`
- `tests/engine/runners/openai/_sse_helpers.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `tests/engine/runners/openai/test_non_stream_response.py`
- `tests/engine/runners/openai/test_non_stream_thought_strip.py`
- `tests/engine/runners/openai/test_old_protocol_parity_regressions.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_sse_invalid_utf8_chunk.py`
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_package_exports.py`
- `dayu/engine/README.md`

## Implementation Status

1. `provider_request_id` 采集与透传：完成。
   - OpenAI-compatible Runner 仅从 response header `x-request-id` 提取，大小写不敏感，空白视为 `None`。
   - HTTP error、SSE parser、non-stream parser、tool call aggregator、`RunnerDoneData` 均透传 response-level id。
   - Agent 将 id 提升到 `IterationCompletedData`、provider-response `RunFailedData` 与 `ContextCompactionRequestedData`；非 provider 失败显式 `None`。

2. `supports_streaming=False` non-stream 降级：完成。
   - Runner 内部计算 effective options；payload 写 `stream=False`，且不写 `stream_options`。
   - 未改变 `RunnerCallOptions` dataclass。

3. HTTP retry/error 成熟细节：完成。
   - `RunnerHTTPErrorData.raw_payload` 保留 HTTP JSON object error body。
   - 非 JSON error body 的 `raw_payload` 保持 `None`，message 保留 body text 或 HTTP fallback。
   - retry exhausted 使用最终失败 attempt 的 provider request id。
   - 未改变 retry 策略。

4. HTTP 200 unknown `Content-Type` fallback：完成。
   - effective stream true + `text/event-stream`：SSE。
   - effective stream true + content type 不含 JSON：SSE fallback。
   - content type 含 JSON 或 effective stream false：non-stream JSON。
   - 解析失败沿用现有 protocol error / `RunnerDoneData(ERROR)` 语义。

5. 强类型 Engine 工具观测事件：完成。
   - 新增 `EngineEventType.TOOL_CALL_DELTA`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALLS_BATCH_DONE`。
   - 新增 `ToolCallDeltaData`、`ToolCallBatchItemData`、`ToolCallsBatchReadyData`、`ToolCallsBatchDoneData`。
   - `runner_tool_call_delta` 仍保留 Runner 内部事件；`tool_call_requested` 仍表示即将执行单个工具。
   - `tool_calls_batch_done` 未加入 `TERMINAL_ENGINE_EVENT_TYPES`。

## Validation Commands / Results

- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_http_error_event.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_sse_invalid_utf8_chunk.py tests/engine/test_engine_event_contract.py tests/engine/contracts/test_runner_events.py -q`
  - Result：41 passed in 0.18s
- `source .venv/bin/activate && pytest tests/engine -q`
  - First run：1 failure，原因是 `tests/engine/test_agent_phase3_tool_call.py` 仍有一个 direct `parse_non_stream_response(...)` 未传 `provider_request_id`。
  - Fix：补齐 `provider_request_id=None`。
  - Re-run result：312 passed in 1.14s
- `source .venv/bin/activate && pytest tests/engine/runners/openai tests/engine -q`
  - Result：312 passed in 1.11s
- `source .venv/bin/activate && pyright`
  - Result：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - Result：passed

## Documentation Decision

- 已更新 `dayu/engine/README.md`。
- 未更新根目录 `README.md`：本 slice 未改变项目级用户命令、配置入口或 CLI 使用方式。
- 未更新 `tests/README.md`：测试分层与运行约定未变化，仅新增和更新现有 Engine/OpenAI runner 测试。
- 未更新 `docs/engine/design.md`：当前 README 已覆盖公共事件、provider request id、streaming 降级和 Content-Type 分流语义。

## Residual Risks / Uncovered Areas

- fixed in current slice：provider request id header 提取、HTTP JSON object raw payload、retry exhausted final attempt id、unknown content type SSE fallback、tool observation event contract 均有测试覆盖。
- accepted as covered by current scope：没有改变 retry 策略；本 slice 只补诊断事实与解析分流。
- later phase/work unit：`EngineRunOutcomeFailed` 仍不携带 `provider_request_id`，本 handoff 只要求 Engine event data 透传。
- later phase/work unit：工具批次仍为串行执行；并发执行是显式非目标。
- no new issue required：未发现 blocker 或需要 controller 裁决的 plan gap。

## Completion Signal

- 五项目标均已在当前 Engine 代码与测试内落地。
- 指定测试命令和 pyright 已通过。
- 文档已按触发规则同步。

## Stop Condition Status

- 未触发 blocker。
- 未进入 commit / PR / closeout。
- 等待 controller 进入 code review gate。
