# Gateflow Re-Review: Tool Executor Batch — Slice 1 (mimo)

- **Date**: 2026-05-12
- **Branch**: `host/phase_0_design`
- **Agent**: AgentOpus (deepreview re-review gate)
- **Fix artifact**: `docs/reviews/gateflow-fix-tool-executor-batch-slice1-20260512.md`
- **Implementation artifact**: `docs/reviews/gateflow-implementation-tool-executor-batch-slice1-20260512.md`
- **Original review**: `docs/reviews/code-review-tool-executor-batch-slice1-20260512-mimo.md`
- **Scope**: 仅验证 Controller accepted 的修复项；不重新审查 controller-rejected 的设计决策。

## Verification Results

### 1. Late-cancel check removal (ACCEPT-3)

**Fix claim**: 删除 `_execute_tool_batch` 中 accepted-events emit 之后、tool_awaiting emit 之前的 `if self._is_cancelled()` 短路。

**Verification**:

- `agent.py:1585-1609`: accepted records 循环 emit `TOOL_RESULT_ACCEPTED`。
- `agent.py:1611-1644`: 紧接进入 awaiting_records 循环 emit `TOOL_AWAITING`，随后 `_make_suspended_terminal_with_close`。
- accepted-events 与 tool_awaiting 之间无 `self._is_cancelled()` 检查。
- awaiting 全部 emit 完毕后、`return` 之前，无 late-cancel 短路。
- `agent.py:1646-1648`: `_is_cancelled()` 检查位于 awaiting/SUSPENDED 路径 *之后*，仅在无 awaiting（纯 accepted batch）时才可能命中，阻止下一轮 Runner——这正是 commit-edge 语义。

**Direct evidence**:

```python
# agent.py:1585-1644 — accepted → awaiting → SUSPENDED，中间无 cancel 检查
for record in accepted_records:
    yield self._make_event(event_type=EngineEventType.TOOL_RESULT_ACCEPTED, ...)
# ← 无 if self._is_cancelled(): ...
if awaiting_records:
    for awaiting in awaiting_records:
        yield self._make_event(event_type=EngineEventType.TOOL_AWAITING, ...)
    yield await self._make_suspended_terminal_with_close(...)
    return
```

**Verdict**: ✅ PASS — late-cancel 短路已删除，accepted→awaiting→SUSPENDED 路径无中断。

---

### 2. Test: all-cancelled batch does not trigger fallback (ACCEPT-4)

**Fix claim**: 新增 `test_all_cancelled_batch_does_not_trigger_failed_fallback_and_continues`。

**Verification**:

- 测试位于 `tests/engine/test_agent_phase3_tool_call.py:2034-2096`。
- 两个 cancelled outcome（`approval_denied` + `host_cancelled`），零 completed，零 failed。
- 断言：`FINAL_ANSWER` 终态、`cancelled_count == 2`、`failed_count == 0`、`runner.call_count == 2`（走了下一轮）。
- 覆盖 `_all_records_failed` 中 `cancelled 不计入失败` 语义。

**Verdict**: ✅ PASS — 测试存在、逻辑正确、覆盖 all-cancelled 边界。

---

### 3. Test: all-awaiting batch suspends (ACCEPT-4)

**Fix claim**: 新增 `test_all_awaiting_batch_suspends_with_empty_accepted_records`。

**Verification**:

- 测试位于 `tests/engine/test_agent_phase3_tool_call.py:2099-2147`。
- 两个 awaiting outcome，零 accepted。
- 断言：`RUN_SUSPENDED` 终态、`awaiting_events == 2`、`accepted_events == []`、`suspended.accepted_records == ()`、`suspended.awaiting_records` 含两条（tc_1, tc_2）、`runner.call_count == 1`。

**Verdict**: ✅ PASS — 测试存在、覆盖 empty-accepted-records 边界。

---

### 4. Test: late-cancel after accepted before awaiting (ACCEPT-4 + ACCEPT-3)

**Fix claim**: 新增 `test_late_cancel_after_accepted_before_awaiting_does_not_swallow_suspend`。

**Verification**:

- 测试位于 `tests/engine/test_agent_phase3_tool_call.py:2151-2216`。
- 同批一个 completed（tc_1）、一个 awaiting（tc_2）。
- 在 `TOOL_RESULT_ACCEPTED`（tc_1）emit 后、`TOOL_AWAITING`（tc_2）emit 前触发 cancel token。
- 断言：终态为 `RUN_SUSPENDED`（非 `RUN_CANCELLED`）；`awaiting_events == 1`；`cancel_events == []`；`suspended.accepted_records` 含 tc_1；`suspended.awaiting_records` 含 tc_2。

**Verdict**: ✅ PASS — 测试存在、精确覆盖 accepted→awaiting 间 cancel race，与 ACCEPT-3 生产代码修复配合。

---

### 5. ToolCancelledOutcome validation tests (ACCEPT-4)

**Fix claim**: 新增 `test_cancelled_rejects_invalid_reason` 和 `test_cancelled_rejects_empty_message`。

**Verification**:

- `test_cancelled_rejects_invalid_reason` 位于 `tests/contracts/test_tool_outcome_exhaustive.py:143-156`：非白名单 reason `"not_a_real_reason"` → `pytest.raises(ValueError)`。
- `test_cancelled_rejects_empty_message` 位于 `tests/contracts/test_tool_outcome_exhaustive.py:159-171`：空 message `""` → `pytest.raises(ValueError)`。

**Verdict**: ✅ PASS — 两个测试存在、覆盖 `__post_init__` 校验防御。

---

### 6. Stale host docs contract names (ACCEPT-1)

**Fix claim**: `docs/host/design.md` 5 处更新旧契约名。

**Verification**:

| 位置 | 旧值 | 预期新值 | 实际值 | 状态 |
| --- | --- | --- | --- | --- |
| L657 | `ToolExecutionContext` | `BatchToolExecutionContext` | `BatchToolExecutionContext` | ✅ |
| L667 | `ToolExecutionContext` | `BatchToolExecutionContext` | `BatchToolExecutionContext` | ✅ |
| L1151 | `ToolExecutionRequest` | `ToolCallRequest` | `ToolCallRequest` | ✅ |
| L1159 | `ToolExecutionRequest(name="fetch_more", ...)` | `ToolCallRequest(name="fetch_more", ...)` | `ToolCallRequest(name="fetch_more", arguments=...)` | ✅ |
| L1198 | `ToolExecutor.execute(ToolExecutionRequest{...})` | `ToolExecutor.execute(BatchToolExecutionRequest{...})` | `ToolExecutor.execute(BatchToolExecutionRequest{calls=[ToolCallRequest{name="fetch_more"}], context=...})` | ✅ |

全局确认：`grep "ToolExecutionContext" docs/host/design.md` 返回 0 结果；`grep "ToolExecutionRequest" docs/host/design.md` 返回 0 结果。

**Verdict**: ✅ PASS — 5 处全部更新，无残留旧名。

---

### 7. READY timing artifact wording (ACCEPT-2)

**Fix claim**: implementation artifact §1 与 §4.1 将 `TOOL_CALLS_BATCH_READY` 发射时机从"bijection 校验完成后"更正为"输入侧预校验通过后、execute 前"。

**Verification**:

- §1（行 26-30）: "`TOOL_CALLS_BATCH_READY` 仅在 `_execute_tool_batch` 内部、输入侧预校验（duplicate / 已执行 id 检查）通过后、`ToolExecutor.execute` 调用前发射一次，不在 runner-event 分类时重复发射。post-executor bijection 校验失败时本批不再产生 `BATCH_DONE`，由 `RUN_FAILED` 终结"。✅
- §4.1（行 139-143）: 同上表述，补充"该事件语义为「batch 已构造完成并即将提交执行」，不承诺 post-executor bijection 校验已通过"。✅
- 代码验证：`agent.py:1480` READY 在 `agent.py:1539` executor 调用之前；`agent.py:1547-1552` bijection 在 executor 返回之后。代码行为与更新后的 artifact 描述一致。

**Verdict**: ✅ PASS — artifact wording 已更正，与代码行为一致。

---

## Validation Commands & Results

```text
$ source .venv/bin/activate && pytest tests/contracts/test_tool_outcome_exhaustive.py tests/engine/test_agent_phase3_tool_call.py
44 passed in 0.20s

$ source .venv/bin/activate && pytest tests/contracts tests/engine
345 passed in 1.19s

$ source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

## Findings

未发现实质性问题。

所有 accepted 修复项均已正确实现：

1. 生产代码中 accepted→awaiting 间的 late-cancel 短路已删除（commit-edge 语义恢复）。
2. 5 个新增测试覆盖 all-cancelled、all-awaiting、late-cancel race、ToolCancelledOutcome validation 边界。
3. `docs/host/design.md` 5 处旧契约名全部更新，无残留。
4. implementation artifact READY timing 表述已更正。

## Residual Risk

- **无新增 residual**。本次 re-review 仅验证 accepted fixes 的实现正确性；controller-rejected 设计决策（CancelledError 归因 / all-cancelled fallback / cancelled LLM 投影 / `_ToolOutcomeRecord` 命名）不在此 gate 范围。
- 全量测试 345 passed、pyright 0 errors，与 fix artifact §4 声明一致。

## Final Verdict

**PASS** — 所有 accepted fixes 验证通过，无新增缺陷。
