# WU-TOOL-01 Slice 3 Re-review Artifact

- **Review gate**: re-review (post-fix)
- **Branch**: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- **Approved plan**: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- **Controller adjudication**: `docs/reviews/wu-tool-01-code-review-slice3-controller-adjudication-20260601.md`
- **Fix artifact**: `docs/reviews/wu-tool-01-fix-slice3-codex-20260601.md`
- **Re-review scope**: CR3-1 / CR3-2 修复确认；当前未提交 Slice 3 + fix diff
- **Date**: 2026-06-01

---

## CR3-1 Status: CLOSED

`_diagnostic_refs_for_duplicate()` 当前代码（`tool_runtime.py:2534-2553`）：

```python
if duplicate_decision.diagnostic_message is None:
    raise ValueError("duplicate decision requires diagnostic_message")
ref = self._diagnostic_emitter.emit(
    ToolTraceDiagnosticRecord(
        reason_code=_duplicate_reason_code(duplicate_decision.kind),
        message=duplicate_decision.diagnostic_message,
    )
)
```

确认：
- 使用 `duplicate_decision.diagnostic_message`，符合 plan 7.11。
- null guard 检查 `diagnostic_message`，与使用字段自洽。
- `DuplicateDecision.diagnostic_message` 在 `_decision_for_accepted_entry` 中填充为 `self._policy.messages.attempt_scope_diagnostic`，语义正确。

**注意**：`git diff HEAD` 中 `tool_runtime.py` 无净变更。可能原因：fix 恢复了 Slice 2 的 accepted 行为，而 Slice 2 commit 已包含正确实现，Slice 3 implementation 未实际修改此文件（或修改后被 fix 回退至与 HEAD 一致）。fix artifact "Changed Files" 表述 `dayu/host/tool_runtime.py` 在当前 diff 中无对应变更，列为 non-blocking documentation note。

---

## CR3-2 Status: CLOSED

`test_candidate_and_ack_carry_duplicate_diagnostic_refs`（`test_toolruntime_diagnostics.py:186-223`）：

```python
configured_action_message = "配置化 hard stop duplicate message"
configured_diagnostic_message = "配置化 attempt-scope duplicate diagnostic"
# ...
messages=DuplicateGovernanceMessages(
    hard_stop=configured_action_message,
    attempt_scope_diagnostic=configured_diagnostic_message,
),
# ...
assert governed_candidate.policy_decision.message == configured_action_message       # hard_stop → policy decision
assert governed_outcome.result.message == configured_action_message                   # hard_stop → failure outcome
assert diagnostics.records[0].message == configured_diagnostic_message                # attempt_scope_diagnostic → diagnostic
```

确认：
- 分别配置 `hard_stop` action message 与 `attempt_scope_diagnostic` diagnostic message。
- policy decision / governed failure outcome 断言使用 `configured_action_message`。
- diagnostic record 断言使用 `configured_diagnostic_message`。
- 三处断言语义分离，符合 plan 7.11。

---

## Findings

### Non-blocking: fix artifact "Changed Files" 包含 `tool_runtime.py` 但当前 diff 无对应变更

fix artifact 声称 Changed Files 包含 `dayu/host/tool_runtime.py`，但 `git diff HEAD` 不包含该文件变更。不影响正确性追踪（当前代码内容已确认正确），但文档表述不精确。

---

## Verification

### 1. `_diagnostic_refs_for_duplicate` 使用 `diagnostic_message`

**PASS**。`tool_runtime.py:2545-2550` 确认使用 `duplicate_decision.diagnostic_message`。

### 2. test 区分 hard_stop action message 与 attempt_scope_diagnostic diagnostic message

**PASS**。`test_toolruntime_diagnostics.py:189-223` 确认三处断言分别使用正确消息字段。

### 3. tool_trace duplicate_scope 透传

**PASS**。
- `tool_trace.py:78` 定义 `_FIELD_DUPLICATE_SCOPE`。
- `_extract_canonical_trace`（`:482`）提取 `duplicate_scope`。
- `_extract_diagnostic_trace` / `_extract_usage_trace` 传 `None`，语义正确。
- `_trace_summary`（`:728`）接受并写入 `duplicate_scope`。
- 测试 `test_tool_trace_projection.py:352-355`（hot row）和 `:391-394`（cold line）断言 `trace_summary["duplicate_scope"]`。

### 4. accept barrier scope/prior refs

**PASS**。
- `test_toolruntime_accept_barrier.py:505-514` 断言 `duplicate_scope.kind == "attempt"`、`attempt_id == reuse.attempt_id`、`reuse_prior_event_refs` 匹配 prior accepted event ref。
- `_reuse_candidate`（`:875-876`）和 allow candidate（`:529-531`）正确填充 `DuplicateGovernanceScope`。

### 5. duplicate governance scope assertions

**PASS**。
- `test_toolruntime_duplicate_governance.py:533-535` 断言 governed candidate `duplicate_scope.kind == "attempt"`、`attempt_id == _ATTEMPT_ID`。
- `_governed_duplicate_candidate` helper（`:1155-1157`）同样断言。
- `test_different_attempt_produces_different_duplicate_key`（`:785-790`）断言两个 attempt 各自 scope 的 `attempt_id`。

### 6. 测试与类型检查

```bash
source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_toolruntime_duplicate_governance.py -v
# Result: 52 passed

source .venv/bin/activate && pyright
# Result: 0 errors, 0 warnings, 0 informations
```

---

## Conclusion

| Category | Count | Details |
|---|---|---|
| Blocking findings | **0** | CR3-1 和 CR3-2 均已关闭 |
| Non-blocking findings | 1 | fix artifact "Changed Files" 表述不精确（`tool_runtime.py` 无净 diff） |

**Remaining blocking findings: 0**

CR3-1（`_diagnostic_refs_for_duplicate` 使用 `diagnostic_message`）和 CR3-2（测试区分 action message 与 diagnostic message）均已正确修复。tool_trace duplicate_scope 透传、accept barrier scope/prior refs、duplicate governance scope assertions 均保持正确。52 测试通过，pyright 无报错。Slice 3 通过 re-review gate。
