# Code Review — PR #45 Fix Re-Review

> Role-scoped re-review：仅验证 controller-accepted fixes，不重开 rejected items。

## Scope

- Mode: current changes（uncommitted fix pass）
- Branch: `host/phase_0_design`
- Base: `main`
- Output file: `docs/reviews/pr-45-re-review-20260512-mimo.md`
- Included scope: controller-accepted fixes 的生产代码与测试验证
- Excluded scope: rejected items（README test restoration、cancelled meta projection、
  design truth-source wording、event-order test enrichment、
  `_make_failed_or_cancelled_terminal` naming）
- Parallel review coverage: 无（主 reviewer 逐项验证）

## Verification Summary

| # | Fix Item | 文件 | 验证结果 |
|---|---------|------|---------|
| 1 | `AgentPolicy.__post_init__` 校验 `max_iterations` 与 `fallback_prompt` | `agent_policy.py` | PASS |
| 2 | `await_or_cancel` 外层 `CancelledError` 清理 target task | `cancellation.py` | PASS |
| 3 | `ToolCancelledOutcome` docstring 层中立化 | `tool_outcome.py` | PASS |
| 4 | `ToolCancelledOutcome.message` `strip()` 拒纯空白 | `tool_outcome.py` | PASS |
| 5 | `BatchToolExecutionContext.timeout_seconds` 负值校验 | `tool_call.py` | PASS |
| 6 | `BatchToolExecutionRequest.calls` 空元组校验 | `tool_call.py` | PASS |
| 7 | `EngineRunOutcomeFailed.provider_request_id` 透传 | `agent_run.py` + `agent.py` | PASS |
| 8 | `tool_calls_batch_done` awaiting 语义文档化 | `engine_events.py` + `README.md` | PASS |

## Verification Details

### 1. AgentPolicy validation — PASS

- **文件**: `dayu/engine/contracts/agent_policy.py:68-96`
- **验证**: `__post_init__` 校验 `max_iterations >= 1`（行 76-77）、
  `fallback_prompt.strip() != ""`（行 91-92），与 fix artifact 描述一致。
- **测试**: `tests/engine/test_agent_phase3_tool_call.py:750` —
  `test_agent_policy_rejects_invalid_values` 覆盖 `max_iterations` in (0, -1)、
  `fallback_prompt` in ("", "   ", "\n\t")。
- **adversarial check**: 校验顺序合理，先数值后字符串；`strip()` 语义与
  `continuation_prompt` 校验一致。

### 2. await_or_cancel CancelledError cleanup — PASS

- **文件**: `dayu/runtime/cancellation.py:137-141`
- **验证**: `except asyncio.CancelledError` 分支调用
  `_cancel_task_and_wait(target_task)` 后 re-raise，与 fix artifact 描述一致。
- **测试**: `tests/runtime/test_cancellation.py:231` —
  `test_await_or_cancel_outer_cancel_closes_target` 验证外层 cancel 后
  target task 被取消并 done。
- **adversarial check**: 异常处理在 `try` 块内、`finally` 之前，确保
  `cancel_watcher` 清理在 `finally` 中仍执行。`_cancel_task_and_wait`
  内部 `suppress(CancelledError)` 吞掉 target 的 `CancelledError`，不干扰
  外层 re-raise。路径完整。

### 3. ToolCancelledOutcome docstring — PASS

- **文件**: `dayu/contracts/tool_outcome.py:87-95`
- **验证**: docstring 写"取消终态不计入连续失败工具批次计数，由消费侧自行解释。
  本契约层不感知任何 Engine 内部计数器或字段名"，已层中立化。
- **adversarial check**: 无 `_consecutive_failed_tool_batches` 引用残留。

### 4. ToolCancelledOutcome.message whitespace — PASS

- **文件**: `dayu/contracts/tool_outcome.py:123`
- **验证**: `self.message.strip() == ""` 拒绝纯空白，与 fix artifact 描述一致。
- **测试**: `tests/contracts/test_tool_outcome_exhaustive.py:174` —
  `test_cancelled_rejects_whitespace_message` 覆盖 "   "、"\t"、"\n"、"  \t  \n"。
- **adversarial check**: `strip()` 语义与 `ToolAwaitSpec.resume_token` 校验一致。

### 5. BatchToolExecutionContext.timeout_seconds — PASS

- **文件**: `dayu/contracts/tool_call.py:112-118`
- **验证**: `timeout_seconds is not None and (not math.isfinite() or <= 0)` 时
  抛 `ValueError`，等价于"必须为 None 或有限正数"。
- **测试**: `tests/contracts/test_tool_call.py:162-179` —
  `test_batch_tool_execution_context_accepts_none_or_finite_positive` 和
  `test_batch_tool_execution_context_rejects_non_positive_and_non_finite`
  覆盖 None、1.5、0.0、-1.0、-0.0001、inf、nan。
- **adversarial check**: `math.isfinite()` 对 `inf` 和 `nan` 均返回 `False`，
  覆盖完整。`-0.0` 的 `<= 0` 为 `True`（`-0.0 == 0.0`），会被拒绝，
  与正数语义一致。

### 6. BatchToolExecutionRequest.calls — PASS

- **文件**: `dayu/contracts/tool_call.py:140-143`
- **验证**: `not self.calls` 拒绝空元组。
- **测试**: `tests/contracts/test_tool_call.py:182-192` —
  `test_batch_tool_execution_request_rejects_empty_calls` 和
  `test_batch_tool_execution_request_accepts_non_empty_calls`。
- **adversarial check**: `not ()` 为 `True`，`not (x,)` 为 `False`，逻辑正确。

### 7. EngineRunOutcomeFailed.provider_request_id — PASS

- **文件**: `dayu/engine/contracts/agent_run.py:130`（字段定义）
- **验证**: `provider_request_id: str | None` 字段存在，docstring 说明语义。
- **agent.py 三处构造**:
  - 行 2449: `_ERROR_MISSING_TERMINAL` 路径，传 `None`（非 provider 失败）。
  - 行 2473: `RUN_FAILED` 路径，传 `data.provider_request_id`（provider 失败）。
  - 行 2503: 另一 `_ERROR_MISSING_TERMINAL` 路径，传 `None`。
- **测试**: `tests/engine/test_agent_phase2.py:1068` —
  `test_run_agent_and_wait_preserves_provider_request_id`。
- **adversarial check**: `RunFailedData.provider_request_id`（`engine_events.py:401`）
  类型为 `str | None`，与 `EngineRunOutcomeFailed.provider_request_id` 类型一致，
  透传无类型漂移。

### 8. tool_calls_batch_done awaiting docs — PASS

- **文件**: `dayu/engine/contracts/engine_events.py:198-203`（docstring）
- **验证**: `ToolCallsBatchDoneData` docstring 明确"本事件仅在本批不含
  `ToolAwaitingOutcome` 时产出"，并描述 awaiting 路径的事件序列。
- **README**: `dayu/engine/README.md:384` 补充说明
  "`tool_calls_batch_done` 不是终态"及 awaiting 混合批次语义。
- **adversarial check**: docstring 与 README 语义一致，无矛盾。

## Findings

未发现实质性问题。

所有 8 项 controller-accepted fix 均已按 fix artifact 描述正确实现，
生产代码逻辑完整，测试覆盖充分，pyright 无新增错误。

## Open Questions

- 无。

## Residual Risk

1. **README 接口事实漂移无自动化守护**（rejected item，不在本 scope）：
   Engine README 内容与代码事实可能漂移而不被发现。
2. **失败路径事件顺序无完整守护**（rejected item，不在本 scope）：
   当前仅 success 路径有完整事件序列断言。
3. **`_make_failed_or_cancelled_terminal_with_close` 命名/行为不一致**
   （documented item，不在本 scope）：当前由 `run_messages.finally` 兜底，
   无运行时泄漏，后续 Engine 内部 refactor 统一。

## 验证

- `pytest tests/runtime tests/contracts tests/engine`：**401 passed**
- `pyright`：**0 errors, 0 warnings, 0 informations**

## 结论

**PASS**。全部 controller-accepted fix 验证通过，无新增 findings。
