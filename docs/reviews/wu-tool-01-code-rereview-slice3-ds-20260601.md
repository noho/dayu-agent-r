# WU-TOOL-01 Slice 3 Code Re-review — DeepReview Artifact

- **Re-review gate**: code re-review（controller adjudication 后的 fix 验证）
- **Branch**: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- **Approved plan**: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- **Controller adjudication**: `docs/reviews/wu-tool-01-code-review-slice3-controller-adjudication-20260601.md`
- **First review**: MIMO (`wu-tool-01-code-review-slice3-mimo-20260601.md`), DS (`wu-tool-01-code-review-slice3-ds-20260601.md`)
- **Fix artifact**: `docs/reviews/wu-tool-01-fix-slice3-codex-20260601.md`
- **Re-review scope**: 仅验证 CR3-1 / CR3-2 是否关闭，以及连带检查项
- **Reviewer**: DeepReview specialist；只审查，不改文件
- **Date**: 2026-06-01

---

## CR3-1 Status: CLOSED

**Finding**: `_diagnostic_refs_for_duplicate` 是否使用 `duplicate_decision.diagnostic_message`

**当前代码状态**（`dayu/host/tool_runtime.py:2545-2550`）：

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

**验证结论**：

- null guard 检查 `diagnostic_message`，而非 `message`。✓
- emit 的 `message` 字段使用 `duplicate_decision.diagnostic_message`（即 `policy.messages.attempt_scope_diagnostic`），符合 approved plan 7.11。✓
- `_duplicate_decision_json()`（`tool_runtime.py:5136`）仍保留 `diagnostic_message` 字段输出，controller adjudication 确认此举 acceptable。✓

**注意**：`git diff HEAD -- dayu/host/tool_runtime.py` 无输出。当前 HEAD 中 `_diagnostic_refs_for_duplicate` 已经使用 `diagnostic_message`（Slice 2 accepted 状态）。原 Slice 3 diff 引入的回归（改用 `message`）可能位于未提交的 working tree 变更中，fix 将其恢复为与 HEAD 一致。见下方 "Non-blocking Documentation Note"。

---

## CR3-2 Status: CLOSED

**Finding**: `test_candidate_and_ack_carry_duplicate_diagnostic_refs` 是否区分 hard_stop action message 与 attempt_scope_diagnostic diagnostic message

**当前代码状态**（`tests/host/test_toolruntime_diagnostics.py:186-223`）：

```python
configured_action_message = "配置化 hard stop duplicate message"
configured_diagnostic_message = "配置化 attempt-scope duplicate diagnostic"
# ...
messages=DuplicateGovernanceMessages(
    hard_stop=configured_action_message,
    attempt_scope_diagnostic=configured_diagnostic_message,
),
# ...
# policy decision 使用 hard_stop message
assert governed_candidate.policy_decision.message == configured_action_message
# governed failure outcome 使用 hard_stop message
assert isinstance(governed_outcome, ToolFailedOutcome)
assert governed_outcome.result.message == configured_action_message
# diagnostic record 使用 attempt_scope_diagnostic message
assert diagnostics.records[0].message == configured_diagnostic_message
```

**验证结论**：

- 测试分别配置 `hard_stop`（action message）和 `attempt_scope_diagnostic`（diagnostic message），不再共用单一 `configured_message`。✓
- `policy_decision.message` 断言为 `configured_action_message`（hard_stop 治理动作消息）。✓
- `governed_outcome.result.message` 断言为 `configured_action_message`（governed failure outcome 使用 action message）。✓
- `diagnostics.records[0].message` 断言为 `configured_diagnostic_message`（diagnostic record 使用 attempt_scope_diagnostic）。✓
- 测试从 `dayu.host.tool_duplicate_governance` 导入 `DuplicateGovernanceMessages`，无兼容性 re-import。✓

---

## 连带检查项

### Q1: tool_trace duplicate_scope 透传

**结论: 正确，无回归。**

- `_FIELD_DUPLICATE_SCOPE` 常量定义（`tool_trace.py:78`）。
- `_extract_canonical_trace` 从 `TOOL_CALL_GOVERNED` payload 提取 `duplicate_scope`（`tool_trace.py:482`），使用 `_json_value_or_none`，类型为 `JsonValue`。
- `_extract_diagnostic_trace` 和 `_extract_usage_trace` 传递 `duplicate_scope=None`，语义正确。
- `_trace_summary` 签名新增 `duplicate_scope: JsonValue | None` 参数并写入 summary dict（`tool_trace.py:771`）。
- Cold line 和 hot row 均写入 `trace_summary`，cold/hot 一致。
- 测试覆盖：`test_tool_call_chain_projects_hot_rows_and_cold_lines`（`test_tool_trace_projection.py:349-355`、`385-394`）同时断言 hot row 和 cold line 中的 `trace_summary["duplicate_scope"]`。

### Q2: accept barrier scope / prior refs

**结论: 正确，断言增强。**

`test_event_sequence_monotonic_and_reuse_has_canonical_governance_only`（`test_toolruntime_accept_barrier.py`）新增断言：

- `duplicate_scope["kind"] == "attempt"` 且 `duplicate_scope["attempt_id"] == reuse.attempt_id`。✓
- `governed_payload["reuse_prior_event_refs"]` 等于 `[first.tool_result_event_ref]` 的 JSON 投影。✓
- `reuse.reuse_prior_event_refs == (first.tool_result_event_ref,)` — prior refs 来自同 Attempt 同 test scope 的 accept barrier 返回。✓

`test_duplicate_allow_does_not_append_governed_event` 和 `_reuse_candidate` helper 正确传入 `duplicate_scope=DuplicateGovernanceScope(kind="attempt", attempt_id=seeded.attempt_id)`。

### Q3: duplicate governance scope assertions

**结论: 正确，断言增强。**

`test_duplicate_governed_matrix_produces_diagnostics`（`test_toolruntime_duplicate_governance.py:533-535`）新增：

```python
assert governed_candidate.duplicate_scope is not None
assert governed_candidate.duplicate_scope.kind == "attempt"
assert governed_candidate.duplicate_scope.attempt_id == _ATTEMPT_ID
```

`_governed_duplicate_candidate` helper（`test_toolruntime_duplicate_governance.py:1155-1157`）同样新增 scope assertions。

### Q4: TOOL_CALL_GOVERNED payload duplicate_scope

**结论: 正确。**

`tool_runtime.py:3116-3118` 写入 `"duplicate_scope": _duplicate_scope_json(candidate.duplicate_scope)`，输出 `{"kind": "attempt", "attempt_id": "..."}`。`_duplicate_scope_json` 正确处理 `None` 输入返回 `None`。

### Q5: 无违规引入

- 无 durable ledger、EventLog 重建、schema change、兼容 wrapper/re-export。✓
- 无 `Any` / `object` / 无类型签名。✓
- 无 README 越界变更。✓

---

## Non-blocking Documentation Note

**Fix artifact Changed Files 表述不精确**

Fix artifact（`wu-tool-01-fix-slice3-codex-20260601.md`）列出 `dayu/host/tool_runtime.py` 为 Changed File，但 `git diff HEAD -- dayu/host/tool_runtime.py` 无输出。当前 HEAD 中 `_diagnostic_refs_for_duplicate` 已使用 `diagnostic_message`（这是 Slice 2 accepted 的正确行为）。

推测原 Slice 3 diff 引入的回归（从 `diagnostic_message` 改为 `message`）位于未提交的 working tree 修改中，fix 将其恢复为与 HEAD 一致——修复有效但无净 diff。这不影响 CR3-1 的关闭判断，因为实际代码行为正确。

**严重度**: Non-blocking。不影响代码正确性、测试覆盖或追踪能力。建议在 fix artifact 中注明"tool_runtime.py 无最终净 diff，回归在 working tree 阶段已恢复"。

---

## Verification

```bash
source .venv/bin/activate
python -m pytest tests/host/test_toolruntime_diagnostics.py \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_toolruntime_duplicate_governance.py -v
# Result: 52 passed

source .venv/bin/activate && pyright
# Result: 0 errors, 0 warnings, 0 informations
```

---

## Conclusion

| Category | Count | Details |
|---|---|---|
| **CR3-1** | **CLOSED** | `_diagnostic_refs_for_duplicate` 使用 `diagnostic_message`，null guard 自洽 |
| **CR3-2** | **CLOSED** | 测试区分 hard_stop action message 与 attempt_scope_diagnostic diagnostic message |
| Blocking findings remaining | **0** | — |
| Non-blocking notes | 1 | Fix artifact Changed Files 表述不精确（tool_runtime.py 无净 diff） |

**Remaining blocking findings: 0**

CR3-1 和 CR3-2 均已关闭。`_diagnostic_refs_for_duplicate` 正确使用 `duplicate_decision.diagnostic_message`（符合 approved plan 7.11），`test_candidate_and_ack_carry_duplicate_diagnostic_refs` 正确区分 hard_stop action message 与 attempt_scope_diagnostic diagnostic message。tool_trace duplicate_scope 透传、accept barrier scope/prior refs、duplicate governance scope assertions 均正确且测试覆盖充分。

Slice 3 可通过 code review gate。
