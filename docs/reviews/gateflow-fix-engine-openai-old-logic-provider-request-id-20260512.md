# Gateflow Fix Artifact: engine openai old logic provider request id

- **work gate name**: fix
- **source review artifact**: `docs/reviews/gateflow-code-review-engine-openai-old-logic-20260512.md`
- **controller-accepted finding ids**: `1-Provider response 自判失败分支丢失 provider_request_id`
- **artifact path**: `docs/reviews/gateflow-fix-engine-openai-old-logic-provider-request-id-20260512.md`

## Per-finding Fix Status

### 1-Provider response 自判失败分支丢失 provider_request_id

- **status**: fixed
- **fix summary**: `dayu/engine/agent.py` 中由已完成 provider response 直接触发的 Agent 自判失败分支改为使用 `state.provider_request_id`，包括 tool-call finish_reason mismatch、tools disabled、empty tool calls、tool-call signal 缺少 completed data、continuation 非法 tool call，以及 force-answer illegal tool call 的兜底失败构造。
- **scope note**: 未修改 retry 策略、Host tracking、Host 依赖、event_id/sequence 或其它 rejected/deferred findings。

## Changed Files

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `docs/reviews/gateflow-fix-engine-openai-old-logic-provider-request-id-20260512.md`

## Validation Commands And Results

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py -q`
  - result: passed, `33 passed in 0.21s`
- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q`
  - result: passed, `53 passed in 0.17s`
- `source .venv/bin/activate && pytest tests/engine/runners/openai tests/engine -q`
  - result: passed, `313 passed in 1.11s`
- `source .venv/bin/activate && pyright`
  - result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - result: passed

## Test Coverage Added Or Updated

- `finish_reason` mismatch 时，断言 `iteration_completed.provider_request_id` 与 terminal `run_failed.provider_request_id` 均为同一 provider request id。
- tools disabled 但 provider 返回 tool calls 时，断言 `run_failed.provider_request_id` 保留 provider request id。
- tool-call signal 缺少 completed tool-call data、continuation 返回 tool call、force-answer 返回非法 tool call 时，断言 `run_failed.provider_request_id` 不丢失。

## Documentation Decision

- 未更新 README。现有 `dayu/engine/README.md` 已声明 provider-response 失败会提升 `provider_request_id` 到 `run_failed`；本次是让实现与既有文档一致，未改变接口、命令、分层或测试运行约定。

## New Risks Or Open Questions

- 未引入新的 Host tracking、retry 或外部协议行为风险。
- 当前 worktree 在本 fix 前已有多处 dirty changes；本 artifact 只记录本次 accepted finding 1 的修复，不裁决其它变更。

## Residual Risk Classification

- **residual risk**: `EngineRunOutcomeFailed` 是否也应携带 `provider_request_id` 仍按 source review artifact 记录为 later phase/work unit，不属于本次 accepted finding 1 的修复范围。
- **classification**: deferred-with-owner by controller / later work unit。
