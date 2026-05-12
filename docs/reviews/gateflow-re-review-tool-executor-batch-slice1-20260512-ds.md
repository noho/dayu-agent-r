# Gateflow Re-Review: ToolExecutor Batch — Slice 1 Fix Verification

- **Date**: 2026-05-12
- **Reviewer**: DeepSeek (Re-Review Agent)
- **Re-Review Target**: 6 accepted Controller fixes from Slice 1 reviews
- **Fix Artifact**: `docs/reviews/gateflow-fix-tool-executor-batch-slice1-20260512.md`
- **Implementation Artifact**: `docs/reviews/gateflow-implementation-tool-executor-batch-slice1-20260512.md`
- **Original Reviews**:
  - `docs/reviews/code-review-tool-executor-batch-slice1-20260512-mimo.md`
  - `docs/reviews/code-review-tool-executor-batch-slice1-20260512-ds.md`
- **Review Type**: Gateflow-governed fix verification re-review

## 结论

**所有 6 项 accepted fix 均已正确实施，验证通过。** 无新增 regression，无新发现 correctness 问题。

---

## 逐项验证

### FIX-1 | CR-06/Mimo-F3: 生产代码 — 删除 accepted/awaiting 间的 `_is_cancelled()` 短路

**验证位置**: `dayu/engine/agent.py:1585-1644`

**验证方法**: 逐行走读 `_execute_tool_batch` 的 accepted 发射→awaiting 发射→late-cancel 检查段。

**验证结果**:
- 行 1585-1609: `TOOL_RESULT_ACCEPTED` emit 循环完成后，直接进入行 1611 的 `if awaiting_records:` 分支，**无中间 `_is_cancelled()` 检查**。
- 行 1611-1644: awaiting records 的 `TOOL_AWAITING` emit 与 `RUN_SUSPENDED` 终端正常产出。
- 行 1646: `_is_cancelled()` 检查移至 awaiting 分支**之后**、batch_done 产出之前，仅阻止下一轮 Runner 调用，不再吞掉 awaiting/suspend。
- 语义符合 commit-edge：executor 返回的 records 是已接受事实，late cancellation 不得回滚。

**测试覆盖**: `test_late_cancel_after_accepted_before_awaiting_does_not_swallow_suspend` 精确覆盖该路径——在 `TOOL_RESULT_ACCEPTED` emit 后触发 cancel，断言 terminal 为 `RUN_SUSPENDED`，无 `RUN_CANCELLED`，且仍有 1 个 `TOOL_AWAITING` 事件。

**通过**: ✓

---

### FIX-2 | CR-01: 测试 — all-cancelled 批次 fallback 语义

**验证位置**: `tests/engine/test_agent_phase3_tool_call.py:2034`

**验证方法**: 阅读测试实现，运行测试。

**验证结果**:
- 测试 `test_all_cancelled_batch_does_not_trigger_failed_fallback_and_continues` 构造 2 个全部 `ToolCancelledOutcome` 的批次。
- 断言 `cancelled_count == 2`, `failed_count == 0`, `completed_count == 0`。
- 断言 terminal 为 `FINAL_ANSWER`（未被 fallback 截断），`degraded is False`。
- 断言 runner 调用次数为 2（第一轮 tool_script + 第二轮 final_script），证明 `_all_records_failed` 返回 `False` 且 `_consecutive_failed_tool_batches` 被正确重置。

**测试通过**: ✓ (44 passed, 含本测试)

---

### FIX-3 | CR-02: 测试 — `ToolCancelledOutcome.__post_init__` 构造期校验

**验证位置**: `tests/contracts/test_tool_outcome_exhaustive.py:143-171`

**验证方法**: 阅读测试实现，运行测试。

**验证结果**:
- `test_cancelled_rejects_invalid_reason`: 传入非白名单 `reason="not_a_real_reason"`，断言 `ValueError`。
- `test_cancelled_rejects_empty_message`: 传入合法 reason 但 `message=""`，断言 `ValueError`。
- 两测试均使用 `pytest.raises(ValueError)` 精确捕获异常类型。

**测试通过**: ✓ (含在 44 passed 中)

---

### FIX-4 | CR-04: 测试 — all-awaiting 批次挂起

**验证位置**: `tests/engine/test_agent_phase3_tool_call.py:2099`

**验证方法**: 阅读测试实现，运行测试。

**验证结果**:
- `test_all_awaiting_batch_suspends_with_empty_accepted_records` 构造 2 个全部 `ToolAwaitingOutcome` 的批次。
- 断言 2 个 `TOOL_AWAITING` 事件，0 个 `TOOL_RESULT_ACCEPTED` 事件。
- 断言 terminal 为 `RUN_SUSPENDED`。
- 断言 `suspended.accepted_records == ()`，`len(suspended.awaiting_records) == 2`。
- 断言 runner 调用次数为 1（未进入下一轮）。

**测试通过**: ✓ (含在 44 passed 中)

---

### FIX-5 | Mimo-F1: 文档 — `docs/host/design.md` 旧契约命名清理

**验证位置**: `docs/host/design.md`

**验证方法**: `rg "ToolExecutionContext|ToolExecutionRequest" docs/host/design.md`

**验证结果**:
- 旧 `ToolExecutionContext` 无残留（仅 `BatchToolExecutionContext`，行 657/667）。
- 旧 `ToolExecutionRequest` 无残留（仅 `ToolCallRequest` 和 `BatchToolExecutionRequest`，行 1198）。
- 所有引用均已更新为批式契约名。

**通过**: ✓

---

### FIX-6 | CR-03/Mimo-F3: 实现 artifact — `TOOL_CALLS_BATCH_READY` 发射时机表述

**验证位置**: `docs/reviews/gateflow-implementation-tool-executor-batch-slice1-20260512.md` §1 与 §4.1

**验证方法**: 读取 artifact 中被引用行，确认措辞。

**验证结果**:
- §1 (行 26): "输入侧预校验（duplicate / 已执行 id 检查）通过后、`ToolExecutor.execute` 调用前发射一次"
- §4.1 (行 139): "输入侧预校验（duplicate / 已执行 id 检查）通过后、`ToolExecutor.execute` 调用前发射一次"
- 旧"bijection 校验完成后"表述已全部替换。
- 补充说明该事件不承诺 post-executor bijection 通过语义。

**通过**: ✓

---

## 自动化验证

| 验证项 | 结果 |
| --- | --- |
| `pytest tests/contracts/test_tool_outcome_exhaustive.py tests/engine/test_agent_phase3_tool_call.py` | 44 passed |
| `pytest tests/contracts tests/engine` (full) | 345 passed, 0 failed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `rg "ToolExecutionRequest|ToolExecutionContext" --type py dayu/ tests/` | 零残留（全部为 `BatchTool*` 前缀） |
| `rg "ToolExecutionRequest|ToolExecutionContext" docs/host/design.md` | 零残留 |

## 未重开的 Controller-Rejected 决策

以下原始 finding 被 controller rejected，未重新审查（无新 evidence）：

| Finding | 处置 | 理由 |
| --- | --- | --- |
| CR-05: `_ToolOutcomeRecord` 重命名 | controller-rejected | 计划中为非硬性建议 |
| Mimo-F2: CancelledError 归因 | controller-rejected/deferred | 当前 commit-edge 取舍是有意设计 |
| Mimo-F4: all-cancelled 计入失败 | controller-rejected | cancelled 不计入失败是有意设计 |
| Mimo-F5: cancelled LLM `ok:false` 信封 | controller-rejected | 自定义投影格式是有意区分 |

## Residual Risk

- Host / ToolRuntime 的 `ToolCallable`→`ToolExecutor` 装配实现仍未进入 Slice 1（fix artifact §5 已记录）。
- `ALLOWED_TOOL_CANCELLED_REASONS` 仍为三值集合；未来扩展需单独设计决策。

## 最终判定

**PASS** — 所有 6 项 accepted fix 均已正确实施，全部测试通过，pyright 零错误，旧类型零残留。无新发现 correctness 回归。
