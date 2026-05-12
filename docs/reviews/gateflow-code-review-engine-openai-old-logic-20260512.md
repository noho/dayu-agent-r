# Gateflow Code Review: Engine/OpenAI OLD reliable logic absorption

review gate name: code review
reviewed target: 当前工作区相对 `f111f7f docs: checkpoint engine openai review` 的全部未提交 diff；重点核对 `docs/reviews/gateflow-implementation-engine-openai-old-logic-20260512.md` 声明的 Engine/OpenAI OLD reliable logic absorption 实现，以及新增 `docs/host/tracking.md`。
artifact path: `docs/reviews/gateflow-code-review-engine-openai-old-logic-20260512.md`

## Findings

### 1-未修复-[中]-Provider response 自判失败分支丢失 provider_request_id

- **入口/函数**: `_AsyncAgent._classify_iteration(...)` 与 `_AsyncAgent._continuation_tool_call_failure(...)`
- **文件(行号)**: `dayu/engine/agent.py:839`, `dayu/engine/agent.py:1279`, `dayu/engine/agent.py:1287`, `dayu/engine/agent.py:1294`, `dayu/engine/agent.py:1326`
- **输入场景**: Runner 已收到 provider response header `x-request-id=req_tool`，并已产出 `RunnerDoneData(..., provider_request_id="req_tool")`；但该 response 被 Agent 侧判定为非法，例如 `RunnerToolCallsCompletedData` 后 `finish_reason != TOOL_CALLS`、工具被禁用时 provider 仍返回 tool calls、tool calls 为空、`finish_reason=TOOL_CALLS` 但缺少 completed tool call data，或 continuation 轮返回 tool call 信号。
- **实际分支**: `_consume_runner_event` 在 `RunnerDoneData` 分支把 `state.provider_request_id` 写为 `data.provider_request_id`，但后续 `_classify_iteration` / `_continuation_tool_call_failure` 为这些 provider-response validation failures 构造 `RunFailedData(provider_request_id=None)`。
- **预期行为**: 当前实现文档声明 `provider_request_id` 由 Agent 提升到 provider-response 失败的 `run_failed`，因此上述由已完成 provider response 直接触发的失败应携带 `state.provider_request_id`。
- **实际行为**: `run_failed.data.provider_request_id` 为 `None`，调用方无法从失败事件关联到触发该非法响应的 provider request。
- **直接证据**: `dayu/engine/agent.py:1154-1175` 已把 `RunnerDoneData.provider_request_id` 写入 `state.provider_request_id` 并产出 `IterationCompletedData(provider_request_id=...)`；但 `dayu/engine/agent.py:1281-1300` 和 `dayu/engine/agent.py:1327-1331` 在同一状态机里返回 `RunFailedData(..., provider_request_id=None)`；`dayu/engine/agent.py:844-849` 的 continuation 非法工具调用分支同样写 `None`。`dayu/engine/README.md:180` 明确写该字段会提升到 provider-response 失败的 `run_failed`。
- **影响**: 观测与排障契约漂移。HTTP/protocol error 路径能关联 request id，但工具响应形态非法这类同样来自 provider response 的失败静默丢失 request id，Host/trace 无法稳定按 provider request 追踪对应响应。
- **建议改法和验证点**: 将这些已完成 provider response 的 Agent 自判失败分支改为使用 `state.provider_request_id`；新增测试覆盖至少 `finish_reason` mismatch、tools disabled but provider returned tool calls、continuation returned tool call 三类场景，断言 `iteration_completed` 与最终 `run_failed` 携带同一 request id。若某个分支被定义为非 provider 失败，应同步收窄 README 口径并说明理由。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision status**: pending-controller-decision

## Reviewer Conclusion

未通过当前 code review gate。主要实现路径整体接近目标：header 采集、retry exhausted final attempt id、HTTP JSON object `raw_payload`、effective non-stream 降级、Content-Type fallback、强类型工具观测事件、导出与 terminal set 均有直接代码与测试证据支撑；但 provider-response 自判失败分支仍存在 request id 契约漂移，需要修复或由 controller 明确裁决为非目标。

## Open Questions

- `EngineRunOutcomeFailed` 是否需要在本 work unit 内同步携带 `provider_request_id`：implementation artifact 将其列为 later phase/work unit，README 也只承诺 `run_failed` 事件，不承诺 `run_agent_and_wait` outcome。本 review 不将其作为 blocker，但该残余风险需要 controller 保持跟踪。

## Residual Risk

- 现有测试覆盖了 HTTP/protocol/done 主链路的 provider request id，但未覆盖 Agent 自判 provider-response validation failure 分支；finding 1 指向该缺口。
- `docs/host/tracking.md` 当前只记录语义级重复工具调用治理与 tool result capping/truncation 属于 Host/ToolRuntime 后续事项，未写成 Engine TODO 或已实现能力，未发现分层口径问题。
- 未发现 Host 反向依赖、metadata 承载契约事实、`event_id` / `sequence` 恢复、或新增工具观测事件进入 `TERMINAL_ENGINE_EVENT_TYPES` 的问题。

## Validation Evidence

- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_http_error_event.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_sse_invalid_utf8_chunk.py tests/engine/test_engine_event_contract.py tests/engine/contracts/test_runner_events.py tests/engine/test_agent_phase2.py -q` -> `61 passed in 0.15s`
- `source .venv/bin/activate && pyright` -> `0 errors, 0 warnings, 0 informations`
- `git diff --check f111f7f --` -> passed

## Reviewed Coverage

- OpenAI runner request id extraction and HTTP retry/error paths: `dayu/engine/runners/openai/runner.py`
- SSE / non-stream parser request id propagation and protocol error paths: `dayu/engine/runners/openai/sse_parser.py`, `dayu/engine/runners/openai/non_stream_parser.py`, `dayu/engine/runners/openai/tool_call_aggregator.py`
- Engine event contract, package exports, terminal set, and Agent RunnerEvent lifting: `dayu/engine/contracts/engine_events.py`, `dayu/engine/contracts/runner_events.py`, `dayu/engine/contracts/__init__.py`, `dayu/engine/__init__.py`, `dayu/engine/agent.py`
- Tests added or changed under `tests/engine` and `tests/engine/runners/openai`
- Documentation updates: `dayu/engine/README.md`, `docs/host/tracking.md`
