# Gateflow Re-review: Engine/OpenAI OLD provider request id

- **review gate name**: re-review
- **reviewed target**: controller-accepted finding `1-Provider response 自判失败分支丢失 provider_request_id`
- **source review artifact**: `docs/reviews/gateflow-code-review-engine-openai-old-logic-20260512.md`
- **fix artifact**: `docs/reviews/gateflow-fix-engine-openai-old-logic-provider-request-id-20260512.md`
- **artifact path**: `docs/reviews/gateflow-re-review-engine-openai-old-logic-20260512.md`

## Scope

本次只复核 accepted finding 1 是否已修复；未重新审全部实现，未裁决 Gateflow gate 是否整体通过，未进入 commit、PR 或 closeout。

## Re-review Conclusion

finding 1: **fixed**。

`dayu/engine/agent.py` 中由已完成 provider response 触发的 Agent 自判失败分支已改为透传 `state.provider_request_id`。未发现 fix 引入新的 blocker；未发现 scope 扩大；未发现非 provider-response 失败被错误填入 request id。

## Evidence

- `dayu/engine/agent.py:1154-1175` 在 `RunnerDoneData` 分支仍将 `data.provider_request_id` 写入 `state.provider_request_id`，并在 `ITERATION_COMPLETED` 中透传同一个 provider request id。
- `dayu/engine/agent.py:1279-1300` 中 tool-call finish_reason mismatch、tools disabled、empty tool calls 三个自判失败分支均使用 `state.provider_request_id`。
- `dayu/engine/agent.py:1326-1332` 中 `finish_reason=TOOL_CALLS` 或已见 tool-call signal 但缺少 completed tool-call data 的失败分支使用 `state.provider_request_id`。
- `dayu/engine/agent.py:829-849` 中 continuation 轮非法 tool call 分支使用 `state.provider_request_id`。
- `dayu/engine/agent.py:1727-1735` 中 force-answer 兜底收到 tool-call decision 的失败分支使用 `state.provider_request_id`。
- `dayu/engine/agent.py:1260-1268` 的 runner abnormal stop、`dayu/engine/agent.py:1706-1712` 的 force-answer missing terminal、`dayu/engine/agent.py:1742-1749` 的 force-answer empty content 等非 provider-response 自判失败仍为 `provider_request_id=None`。

## Test Coverage Review

新增/更新测试覆盖了 source review 要求的至少三类场景：

- `tests/engine/test_agent_phase3_tool_call.py:1094-1127`: tool-call completed data 与 `finish_reason` mismatch，断言 `iteration_completed.provider_request_id` 与 terminal `run_failed.provider_request_id` 均为 `req_mismatch`。
- `tests/engine/test_agent_phase3_tool_call.py:1055-1091`: tools disabled 但 provider 返回 tool calls，断言 terminal `run_failed.provider_request_id` 为 `req_tools_disabled`；同一参数化测试还确认 runner unsupported 等非 provider request id 场景仍为 `None`。
- `tests/engine/test_agent_phase3_tool_call.py:1130-1161`: `finish_reason=TOOL_CALLS` 但缺少 completed tool-call data，断言 terminal `run_failed.provider_request_id` 为 `req_missing_tool_calls`。
- `tests/engine/test_agent_phase3_tool_call.py:1685-1714`: continuation 轮返回 tool call，断言 terminal `run_failed.provider_request_id` 为 `req_continuation_tool`，并断言未执行工具。
- `tests/engine/test_agent_phase3_tool_call.py:1540-1575`: force-answer 返回非法 tool call，断言 terminal `run_failed.provider_request_id` 为 `req_force_tool`。

## Validation Commands

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py -q`
  - result: passed, `33 passed in 0.15s`
- `source .venv/bin/activate && pyright`
  - result: passed, `0 errors, 0 warnings, 0 informations`

## New Blocker Check

- **new blocker**: none found.
- **scope expansion**: none found within the accepted finding 1 re-review scope.
- **non-provider failure request id contamination**: none found. Reviewed nearby `RunFailedData` construction sites and confirmed non provider-response failures keep `provider_request_id=None`.

## Open Questions And Residual Risk

- `EngineRunOutcomeFailed` 是否也应携带 `provider_request_id` 仍沿用 source review artifact 的 later work unit residual risk；本次 accepted finding 1 只要求 `run_failed` 事件，不扩大到 outcome contract。
