# PR #45 Fix Re-Review

## Scope

- Mode: current changes (role-scoped re-review, not gateflow)
- Repository: `/Users/leo/workspace/dayu-agent-r`
- Branch: `host/phase_0_design`
- Base review artifacts:
  - `docs/reviews/pr-45-review-20260512-1455.md`
  - `docs/reviews/pr-45-review-20260512-1456.md`
- Fix plan: `docs/reviews/pr-45-fix-20260512.md`
- Output file: `docs/reviews/pr-45-re-review-20260512-ds.md`
- Included scope: controller-accepted fixes only (see table below)
- Excluded scope: rejected items — README test restoration, cancelled meta projection, design truth-source wording, event-order test enrichment, `_make_failed_or_cancelled_terminal` naming
- Parallel review coverage: 无

## Verification Summary

- `pytest tests/runtime tests/contracts tests/engine`: **401 passed**
- `pyright`: **0 errors, 0 warnings, 0 informations**

## Fix-by-Fix Verification

### 1455-#1: AgentPolicy `__post_init__` 校验 — PASS

- **文件**: `dayu/engine/contracts/agent_policy.py:71-93`
- `max_iterations < 1` → `ValueError`：已在 line 76-77 实现。
- `fallback_prompt.strip() == ""` → `ValueError`：已在 line 91-92 实现。
- docstring 已更新，列出新增校验项。
- 测试 `tests/engine/test_agent_phase3_tool_call.py::test_agent_policy_rejects_invalid_values` 新增 `max_iterations` (0, -1) 和 `fallback_prompt` ("", "   ", "\n\t") 的 fail-fast 用例。
- 测试 `tests/engine/test_agent_phase2.py::test_abnormal_stop_and_max_iterations_fail` 已适配：移除 `max_iterations=0` 构造，改用合法 policy (`max_iterations=1`) 走运行期 `max_iterations_exceeded` 路径，并新增独立 `pytest.raises(ValueError)` 守护构造期拒绝。
- 无副作用，不改动现有合法 policy 的行为。

### 1456-#2: `await_or_cancel` 外层 `CancelledError` 清理 — PASS

- **文件**: `dayu/runtime/cancellation.py:137-140`
- 新增 `except asyncio.CancelledError` 分支，调用 `await _cancel_task_and_wait(target_task)` 后 `raise`。
- docstring 已补充外层取消场景的描述与 `:raises asyncio.CancelledError:` 段。
- `finally` 块仍清理 `cancel_watcher`，不受影响。
- 测试 `tests/runtime/test_cancellation.py::test_await_or_cancel_outer_cancel_closes_target` 验证外层 `Task.cancel()` 后 target task 被取消并收口（`target_done.is_set()` 和 `target_received_cancel is True` 均断言）。
- 与同文件 `await_or_cancel_or_timeout` 的 CancelledError 处理模式一致。

### 1456-#4: `ToolCancelledOutcome` docstring 层中立化 — PASS

- **文件**: `dayu/contracts/tool_outcome.py:89-97`
- 已删除 `_consecutive_failed_tool_batches` 引用。
- 新文本："语义上取消不等同于失败：取消终态不计入连续失败工具批次计数，由消费侧自行解释。本契约层不感知任何 Engine 内部计数器或字段名。"
- 不再泄漏 Engine 内部实现细节，符合"设计下层组件接口时，必须假设上层组件不存在"约束。

### 1456-#5: `ToolCancelledOutcome.message` 空白校验 — PASS

- **文件**: `dayu/contracts/tool_outcome.py:123`
- 校验从 `not self.message` 改为 `self.message.strip() == ""`。
- docstring `:raises` 已更新为 "为空 / 纯空白时抛出"。
- 测试 `tests/contracts/test_tool_outcome_exhaustive.py::test_cancelled_rejects_whitespace_message` 覆盖 `"   "`, `"\t"`, `"\n"`, `"  \t  \n"` 四种纯空白输入。
- 与同包 `ToolAwaitSpec.__post_init__` 的 `strip() == ""` 模式一致。

### 1456-#6: `BatchToolExecutionContext.timeout_seconds` 校验 — PASS

- **文件**: `dayu/contracts/tool_call.py:105-118`
- `__post_init__` 校验 `timeout_seconds is None or (math.isfinite() and > 0)`。
- 拒绝 `0.0`, `-1.0`, `-0.0001`, `math.inf`, `math.nan`。
- 测试 `tests/contracts/test_tool_call.py`：
  - `test_batch_tool_execution_context_accepts_none_or_finite_positive` — 接受 `None` 和 `1.5`。
  - `test_batch_tool_execution_context_rejects_non_positive_and_non_finite` — 拒绝所有非法值。

### 1456-#7: `BatchToolExecutionRequest.calls` 非空校验 — PASS

- **文件**: `dayu/contracts/tool_call.py:130-141`
- `__post_init__` 校验 `not self.calls` → `ValueError`。
- docstring `:param calls` 已标注 "非空：批式执行至少包含一次调用"。
- 测试 `tests/contracts/test_tool_call.py`：
  - `test_batch_tool_execution_request_rejects_empty_calls` — 空元组被拒。
  - `test_batch_tool_execution_request_accepts_non_empty_calls` — 非空元组合法。

### 1456-#8: `EngineRunOutcomeFailed` 透传 `provider_request_id` — PASS

- **文件**: `dayu/engine/contracts/agent_run.py:130`
  - dataclass 新增字段 `provider_request_id: str | None`，含中文 docstring。
- **文件**: `dayu/engine/agent.py`
  - 路径一（事件流无终态，line 2454）：`provider_request_id=None`。
  - 路径二（RUN_FAILED，line 2478）：`provider_request_id=data.provider_request_id`。
  - 路径三（兜底 missing terminal，line 2508）：`provider_request_id=None`。
- 测试 `tests/engine/test_agent_phase2.py::test_run_agent_and_wait_preserves_provider_request_id` 验证 RUN_FAILED 携带 `provider_request_id` 时 `EngineRunOutcomeFailed` 正确透传。
- `EngineRunOutcomeCancelled` 路径不受影响（不涉及此字段）。

### 1456-#9: awaiting 路径不产出 `tool_calls_batch_done` 文档化 — PASS

- **文件**: `dayu/engine/contracts/engine_events.py:198-204`
  - `ToolCallsBatchDoneData` docstring 新增完整段说明：本批含 awaiting 时 Engine 以 `tool_awaiting` + `run_suspended` 收口，不产出本事件。
- **文件**: `dayu/engine/README.md:386`
  - 工具观测段新增说明段，与 docstring 一致。
- 两处文档语义一致，明确调用方依赖批处理完整性时需识别 awaiting 路径。

## Rejected Items Absence Verification

以下 rejected 项已逐项检查 diff，确认**未**出现在本次变更中：

| Rejected Item | 状态 |
| --- | --- |
| README 测试恢复 (`test_engine_readme_phase2.py`) | 未出现 |
| cancelled outcome 投影 `meta` | 未出现 |
| `docs/{engine,host}/design.md` truth-source 声明恢复 | 未出现 |
| 失败路径事件顺序测试 enrichment | 未出现 |
| `_make_failed_or_cancelled_terminal_with_close` 重命名/行为统一 | 未出现 |

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

1. **README 接口事实漂移无自动化守护**（延续 1456-#1 rejected）：当前 Engine README 与代码接口事实的一致性无自动化回归检测，漂移只能在 code review 或集成问题中被发现。
2. **失败路径事件顺序无完整守护**（延续 1456-#3 rejected）：仅 success 路径有精确事件序列断言；protocol error / HTTP error 等失败路径的相对顺序仍由集成行为隐式保证。
3. **`test_abnormal_stop_and_max_iterations_fail` 断言弱化**：原 `exceeded[-1].data.error_code == "max_iterations_exceeded"` 断言被移除，改为仅 `isinstance(data, RunFailedData)`。虽然 `max_iterations < 1` 已在 contract 构造期 fail-fast 守护，但运行期 `max_iterations_exceeded` 错误码的回归检测不再被此测试覆盖。
4. **cancelled outcome 投影不含 `meta`**（明确不修）：与 handoff 决策一致，不作为本次 scope 内风险。
