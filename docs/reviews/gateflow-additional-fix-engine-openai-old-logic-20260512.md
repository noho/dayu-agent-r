# Gateflow Additional Fix Artifact

## Scope

- Work gate name: `fix`
- Current gate: user additional review fix
- Source review artifacts:
  - `docs/reviews/code-review-20260512-0933.md`
  - `docs/reviews/code-review-20260512-0937.md`
- Allowed code scope:
  - `dayu/engine/agent.py`
  - `tests/engine/test_agent_phase3_tool_call.py`
  - `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- Non-goals:
  - 不启动 `$gateflow` / `/gateflow`
  - 不重新做 plan / review
  - 不进入 commit / PR / closeout
  - 不修改 OpenAI runner 生产行为
  - 不修改 `docs/host/tracking.md` 或 `dayu/engine/README.md`

## Accepted Findings Fixed

| Source | Finding / risk | Fix status |
| --- | --- | --- |
| `code-review-20260512-0933.md` finding 1 | `_handle_final_decision` 调用方不可达 fallback 缺少类型守卫 | fixed-pending-re-review：不可达 fallback 改为 `assert_never(continuation_decision)` |
| `code-review-20260512-0933.md` finding 4 | `_call_tool_executor` CancelledError 归因限制需要说明 | fixed-pending-re-review：docstring 记录 Engine 对 `CancelledError` + cancelled token 的有意归因取舍 |
| `code-review-20260512-0933.md` residual risk | `_is_terminal` 与 `TERMINAL_ENGINE_EVENT_TYPES` 重复维护 | fixed-pending-re-review：`_is_terminal` 直接复用 `TERMINAL_ENGINE_EVENT_TYPES` |
| `code-review-20260512-0933.md` residual risk | provider_request_id 正常 SSE / 非流式成功路径缺少 Agent/Engine 断言 | fixed-pending-re-review：新增 OpenAI Runner fake session + Agent 集成测试，覆盖 SSE 与非流式成功响应到 `IterationCompletedData` 的传递 |
| `code-review-20260512-0937.md` finding 3 | 工具超时-取消竞争测试依赖 executor 内部取消行为 | fixed-pending-re-review：新增 runner close 阶段触发 token 的 late cancel 测试，executor 不从自身 `CancelledError` handler 触发 token |

## Rejected Findings Recorded

| Source | Finding | Decision |
| --- | --- | --- |
| `code-review-20260512-0937.md` finding 1 | runner 异常路径 commit boundary | rejected-with-reason |
| `code-review-20260512-0937.md` finding 2 | RunSuspendedData snapshot 一致性 | rejected-with-reason |
| `code-review-20260512-0937.md` finding 4 | EngineEvent 移除 event_id / sequence | rejected-with-reason |
| `code-review-20260512-0933.md` finding 2 | `_is_sse_response` fallback | rejected-with-reason |
| `code-review-20260512-0933.md` finding 3 | 工具超时策略真源 | rejected-with-reason |
| `code-review-20260512-0933.md` finding 5 | `await_or_cancel` coroutine 清理 | no-fix / positive already-fixed behavior |

## Changed Files

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `docs/reviews/code-review-20260512-0933.md`
- `docs/reviews/code-review-20260512-0937.md`
- `docs/reviews/gateflow-additional-fix-engine-openai-old-logic-20260512.md`

## Validation

| Command | Result |
| --- | --- |
| `source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py::test_tool_execution_timeout_wins_over_runner_close_cancel tests/engine/runners/openai/test_streaming_capability_and_content_type.py::test_sse_success_provider_request_id_reaches_agent_iteration_completed tests/engine/runners/openai/test_streaming_capability_and_content_type.py::test_non_stream_success_provider_request_id_reaches_agent_iteration_completed -q` | passed: 3 passed |
| `source .venv/bin/activate && pyright dayu/engine/agent.py tests/engine/test_agent_phase3_tool_call.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py` | passed: 0 errors |
| `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/runners/openai -q` | passed: 234 passed |
| `source .venv/bin/activate && pyright` | passed: 0 errors |
| `git diff --check` | passed |

## Documentation Decision

本次改动没有改变公共接口、CLI、配置入口或 README 职责内的用户可见行为；按 handoff 限制不修改 `dayu/engine/README.md`。review artifact 与 fix artifact 已同步记录裁决和修复状态。

## Residual Risk Classification

| Risk | Classification | Status |
| --- | --- | --- |
| `_call_tool_executor` 无法区分 executor 自发 `CancelledError` 与 token 同时取消 | accepted residual risk | 已在 docstring 明确归因取舍；不引入复杂身份追踪 |
| `_is_sse_response` effective stream + 非 JSON HTTP 200 继续按 SSE fallback | accepted by controller | 保持 OLD-compatible 行为不变 |
| `ToolExecutionContext.timeout_seconds` 被误解为独立超时真源 | accepted by controller | 保持 Engine 握手等待边界；不改变契约 |
| Additional fix re-review 尚未执行 | pending re-review | 当前状态为 fixed-pending-re-review |

## Completion Signal

Accepted findings 已按 handoff 范围修复并留痕；required validation 已通过；等待 additional re-review。
