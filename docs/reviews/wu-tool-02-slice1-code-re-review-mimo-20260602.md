# WU-TOOL-02 Slice 1 Code Re-Review — AgentMiMo

## Re-Review Target

- Branch: `refactor/wu-tool-02-accept-candidate-cleanup`
- Diff: uncommitted workspace changes (post-fix)
- Gate: Slice 1 fix re-review
- Date: 2026-06-02

## Review Inputs

- Source review: `docs/reviews/wu-tool-02-slice1-code-review-mimo-20260602.md`
- DS review: `docs/reviews/wu-tool-02-slice1-code-review-ds-20260602.md`
- Controller adjudication: `docs/reviews/wu-tool-02-slice1-code-review-controller-adjudication-20260602.md`
- Fix report: `docs/reviews/wu-tool-02-slice1-fix-report-20260602.md`

## Finding 01 复核：`_validate_tool_accept_duplicate_governance` 对齐

**裁决: CLOSED**

Controller 要求：调整新 helper，使任何非 None duplicate decision 都要求 `duplicate_scope` 与 `duplicate_decision_message`，并保持只有 REUSE/HINT/REQUIRE_JUSTIFICATION/HARD_STOP/DURABLE_MISSING 要求 `duplicate_key`。

Fix 后代码（line 4027-4045）：

```python
if duplicate.duplicate_decision in (
    DuplicateDecisionKind.REUSE,
    DuplicateDecisionKind.HINT,
    DuplicateDecisionKind.REQUIRE_JUSTIFICATION,
    DuplicateDecisionKind.HARD_STOP,
    DuplicateDecisionKind.DURABLE_MISSING,
):
    if duplicate.duplicate_key is None:
        raise ValueError("duplicate decision requires duplicate_key")
if duplicate.duplicate_scope is None:
    raise ValueError("duplicate decision requires duplicate_scope")
if duplicate.duplicate_decision_message is None:
    raise ValueError("duplicate decision requires duplicate_decision_message")
```

与现有 `_validate_duplicate_fields` 的行为对齐分析：

| 场景 | 现有 `_validate_duplicate_fields` | Fix 后新 helper | 对齐 |
|---|---|---|---|
| `duplicate_decision=None` | early return，不校验 scope/message | N/A（新结构 `duplicate_decision` 类型为 `DuplicateDecisionKind`，不可为 None） | N/A |
| `duplicate_decision=ALLOW` | 不跳过 scope/message 校验（line 4171-4174 无条件执行）；不要求 key | 不要求 key（ALLOW 不在显式列表中）；要求 scope 和 message（无条件检查） | PASS |
| `duplicate_decision=REUSE/HINT/...` | 要求 key + scope + message | 要求 key + scope + message | PASS |
| `duplicate_decision=DURABLE_MISSING` | 要求 key + scope + message | 要求 key + scope + message | PASS |

Fix 精准对齐了 required fix 描述的语义。

## Finding 02/03 复核：rejected findings 未被无关处理

- **Finding 02**（`_validate_tool_accept_governance` 冗余 isinstance）：fix report 标注"未处理"。实际 diff 确认 `_validate_tool_accept_governance`（line 4059-4068）isinstance 检查保持不变。PASS — 未被无关处理。
- **Finding 03**（`_validate_tool_accept_result` payload 检查标注）：fix report 标注"未处理"。实际 diff 确认 `_validate_tool_accept_result`（line 3999-4003）payload_ref/payload_digest 检查保持不变。PASS — 未被无关处理。

## Production Behavior 确认

| 检查项 | 结果 |
|---|---|
| `ToolFactAcceptCandidate` 顶层字段 | 未变更 |
| Producer `_tool_fact_accept_candidate()` / `_tool_fact_reuse_accept_candidate()` | 未变更 |
| Accept barrier consumer helpers | 未变更 |
| Tests（5 个 allowed test files） | 未变更 |
| EventLog payload key / shape | 未变更 |
| Accepted evidence envelope | 未变更 |
| Duplicate governance 运行时行为 | 未变更 |
| Wait / memory / compaction / tool trace | 未变更 |
| `__all__` exports | 未新增 |
| `ToolFactKind.LOST` | 仍 unsupported |

新子结构和 validation helper 仍未接入任何生产代码路径。Fix 只修改了未接入 helper 的内部校验逻辑。

## 验证结果

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py
# 结果: 16 passed in 0.30s

source .venv/bin/activate && pyright dayu/host/tool_runtime.py
# 结果: 0 errors, 0 warnings, 0 informations
```

与 fix report 一致。独立复现通过。

## Fix 精确度

Diff 确认只修改了 `_validate_tool_accept_duplicate_governance` 函数体。其余 6 个 dataclass、7 个 validation helper、`ToolFactAcceptCandidate` 及所有 producer/consumer 代码均无变化。总控文档仅有 gate 状态行更新，属于 gate 流程文档。

## 结论

**Code re-review PASS。**

Accepted Finding 01 已关闭，新 helper 对齐现有 `_validate_duplicate_fields` 语义。Rejected Findings 02/03 未被无关处理。Production behavior 无变更。验证结果可信。
