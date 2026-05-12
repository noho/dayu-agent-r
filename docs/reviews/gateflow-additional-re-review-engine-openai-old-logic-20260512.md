# Gateflow Additional Re-review Artifact

## Scope

- Review gate name: `additional re-review`
- Current gate: user additional re-review
- Reviewed fix artifact: `docs/reviews/gateflow-additional-fix-engine-openai-old-logic-20260512.md`
- Source review artifacts:
  - `docs/reviews/code-review-20260512-0937.md`
  - `docs/reviews/code-review-20260512-0933.md`
- Re-review boundary:
  - 只复核 controller accepted fixes 是否完成。
  - 只复核 source review artifacts 是否记录 controller decision、fix status、pending re-review status。
  - 不重新审全部 Engine/OpenAI 实现。
  - 不修代码，不进入 commit、PR 或 closeout。

## Reviewer Conclusion

本次 additional re-review 通过。5 个 controller accepted 修复项均已完成，2 个 source review artifact 已记录 findings 的 controller decision 与 fix status；accepted 项保持 `pending` re-review status，符合进入本轮 re-review 前的状态记录要求。本次复核未发现新的 blocker。

## Accepted Items

| Item | Status | Evidence |
| --- | --- | --- |
| 1. `_handle_final_decision` unreachable fallback replaced with `assert_never` or equivalent type guard | fixed | `dayu/engine/agent.py:592-624` 覆盖 `_FinalDecision` 与 `None` 两个分支后调用 `assert_never(continuation_decision)`；`dayu/engine/agent.py:23` 已导入 `assert_never`。 |
| 2. `_call_tool_executor` docstring/comment documents CancelledError attribution limitation; no complex behavior change required | fixed | `dayu/engine/agent.py:1553-1563` docstring 明确说明 `CancelledError` 加已取消 token 会归因为 run-level cancellation，executor 自发 `CancelledError` 与 token 同时取消也按该取舍处理，且未引入复杂身份追踪行为。 |
| 3. `_is_terminal` uses `TERMINAL_ENGINE_EVENT_TYPES` rather than duplicate hard-coded set | fixed | `dayu/engine/agent.py:2028-2036` 直接返回 `event.type in TERMINAL_ENGINE_EVENT_TYPES`；`dayu/engine/contracts/engine_events.py:409-416` 是 terminal 类型集合真源。 |
| 4. Tests assert provider_request_id reaches Agent/Engine `IterationCompletedData` in normal SSE and non-stream success paths | fixed | `tests/engine/runners/openai/test_streaming_capability_and_content_type.py:270-303` 覆盖 SSE success 到 Agent `IterationCompletedData.provider_request_id`；同文件 `343-379` 覆盖 non-stream success 到 Agent `IterationCompletedData.provider_request_id`。 |
| 5. Tests cover late cancellation during/after tool timeout cleanup without relying on executor triggering token from its own CancelledError handler | fixed | `tests/engine/test_agent_phase3_tool_call.py:1503-1531` 新增 runner close 触发 token 的 late cancel 测试；该用例使用 `_HangingToolExecutor()`，没有设置 `token_to_cancel_on_cancel`，token 由 `_ScriptedRunner.close()` 在 `tests/engine/test_agent_phase3_tool_call.py:208-217` 触发。 |
| 6. `docs/reviews/code-review-20260512-0937.md` and `docs/reviews/code-review-20260512-0933.md` contain controller decisions and fix statuses for all findings | fixed | `docs/reviews/code-review-20260512-0933.md:101-120` 记录 5 个 findings 与 residual risks 的 controller decision、fix status、re-review status；`docs/reviews/code-review-20260512-0937.md:112-127` 记录 4 个 findings 与 residual risks 的 controller decision/fix status/re-review status 或 classification/status。 |

## Source Artifact Status

### `docs/reviews/code-review-20260512-0933.md`

| Finding / risk | Controller decision recorded | Fix status recorded | Re-review status recorded |
| --- | --- | --- | --- |
| Finding 1 `_handle_final_decision` 不可达死代码 | yes: accepted | yes: fixed-pending-re-review | yes: pending |
| Finding 2 `_is_sse_response` fallback | yes: rejected-with-reason | yes: not-fixed-by-design | yes: not-applicable |
| Finding 3 工具执行超时策略 | yes: rejected-with-reason | yes: not-fixed-by-design | yes: not-applicable |
| Finding 4 `_call_tool_executor` CancelledError 归因限制 | yes: accepted | yes: fixed-pending-re-review | yes: pending |
| Finding 5 `await_or_cancel` coroutine 清理路径 | yes: no-fix / positive already-fixed behavior | yes: not-applicable | yes: not-applicable |
| provider_request_id 正常路径测试缺口 | yes: accepted | yes: fixed-pending-re-review | yes: pending |
| Agent 超时 / 取消竞速路径 | yes: covered by additional finding | yes: fixed-pending-re-review | yes: pending |
| `_is_terminal` 重复维护 | yes: accepted | yes: fixed-pending-re-review | yes: pending |

### `docs/reviews/code-review-20260512-0937.md`

| Finding / risk | Controller decision recorded | Fix status recorded | Re-review status recorded |
| --- | --- | --- | --- |
| Finding 1 runner 异常路径 commit boundary | yes: rejected-with-reason | yes: not-fixed-by-design | yes: not-applicable |
| Finding 2 `RunSuspendedData` 一致性不变量 | yes: rejected-with-reason | yes: not-fixed-by-design | yes: not-applicable |
| Finding 3 工具超时-取消竞争测试依赖 executor 内部行为 | yes: accepted | yes: fixed-pending-re-review | yes: pending |
| Finding 4 EngineEvent 移除 `event_id` / `sequence` | yes: rejected-with-reason | yes: not-fixed-by-design | yes: not-applicable |
| Residual risks | yes: classification recorded | yes: status recorded | yes: not applicable to rejected/accepted residual classifications |

## Validation

| Command | Result |
| --- | --- |
| `source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py::test_tool_execution_timeout_wins_over_runner_close_cancel tests/engine/runners/openai/test_streaming_capability_and_content_type.py::test_sse_success_provider_request_id_reaches_agent_iteration_completed tests/engine/runners/openai/test_streaming_capability_and_content_type.py::test_non_stream_success_provider_request_id_reaches_agent_iteration_completed -q` | passed: 3 passed |
| `source .venv/bin/activate && pyright dayu/engine/agent.py tests/engine/test_agent_phase3_tool_call.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py` | passed: 0 errors, 0 warnings, 0 informations |

## New Blocker Check

未发现新的 blocker。未重新审查全部 Engine/OpenAI 实现；结论仅覆盖本 handoff 指定的 accepted fixes 与 source review artifact 标注状态。

## Artifact Path

`docs/reviews/gateflow-additional-re-review-engine-openai-old-logic-20260512.md`
