# WU-TOOL-02 Slice 1 Code Re-Review — AgentDS

## Review Metadata

- **Reviewer**: AgentDS
- **Date**: 2026-06-02
- **Gate**: code re-review (fix gate)
- **Branch**: `refactor/wu-tool-02-accept-candidate-cleanup`
- **Scope**: Slice 1 fix — `_validate_tool_accept_duplicate_governance` 对齐现有 `_validate_duplicate_fields`
- **Prior DS Review**: `docs/reviews/wu-tool-02-slice1-code-review-ds-20260602.md`（无 findings）
- **MiMo Review**: `docs/reviews/wu-tool-02-slice1-code-review-mimo-20260602.md`（3 findings）
- **Controller Adjudication**: `docs/reviews/wu-tool-02-slice1-code-review-controller-adjudication-20260602.md`
- **Fix Report**: `docs/reviews/wu-tool-02-slice1-fix-report-20260602.md`

## Accepted Finding Status

| Finding | 来源 | 严重度 | 裁决 | Status |
|---|---|---|---|---|
| 01 `_validate_tool_accept_duplicate_governance` ALLOW 校验不一致 | MiMo | 低 | accepted | **closed** |
| 02 `_validate_tool_accept_governance` isinstance 冗余 | MiMo | 低 | rejected | 未处理（符合裁决） |
| 03 payload_ref/payload_digest 检查需确认 plan 意图 | MiMo | 低 | rejected | 未处理（符合裁决） |

## Finding 01 Close Verification

### 旧代码（fix 前）

```python
if duplicate.duplicate_decision is not DuplicateDecisionKind.ALLOW:
    if duplicate.duplicate_key is None:
        raise ValueError(...)
    if duplicate.duplicate_scope is None:
        raise ValueError(...)
    if duplicate.duplicate_decision_message is None:
        raise ValueError(...)
```

问题：`scope` 和 `message` 要求仅在 `is not ALLOW` 分支内，ALLOW 决策可绕过 scope/message 非 None 检查。

### 新代码（fix 后）

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

### 与现有 `_validate_duplicate_fields`（line 4152）逐项对齐

| 校验项 | 新 helper（fix 后） | 现有 `_validate_duplicate_fields` | 对齐 |
|---|---|---|---|
| `duplicate_key` 可选非空文本 | `_require_optional_non_empty_text` (4020) | `_require_optional_non_empty_text` (4160) | ✓ |
| `duplicate_decision` isinstance | 4027-4028 | 4163-4164 | ✓ |
| `duplicate_scope` isinstance（非 None 时） | 4029-4032 | —（现有 candidate 不单独检查 scope 类型） | 无分歧 |
| `duplicate_key` 要求于特定决策 | 4033-4041：REUSE/HINT/REQUIRE_JUSTIFICATION/HARD_STOP/DURABLE_MISSING | 4165-4176：同枚举 | ✓ |
| `duplicate_scope` 必非 None（所有决策） | 4042-4043：无条件 | 4177-4178：无条件 | ✓ |
| `duplicate_decision_message` 必非 None（所有决策） | 4044-4045：无条件 | 4179-4180：无条件 | ✓ |
| message 非空白 | 4023-4025：`_require_optional_non_empty_text`（前置） | 4181-4183：`_require_non_empty_text`（后置） | ✓ 语义等价 |

**结论**：Finding 01 已正确关闭。ALLOW 决策的 scope/message 要求已与现有 `_validate_duplicate_fields` 语义对齐——所有非 None duplicate decision 一律要求 `duplicate_scope` 和 `duplicate_decision_message` 非 None，仅特定决策枚举要求 `duplicate_key`。

## Rejected Findings 确认

- **Finding 02**（isinstance 冗余）：代码未变，`isinstance` 检查仍保留。符合 controller "不为此做额外 churn" 的裁决。✓
- **Finding 03**（payload 检查标注）：代码未变，payload_digest/payload_ref 一致性检查仍为现有 candidate validator 的精确镜像。符合 controller "已有精确复制的现有逻辑兜底" 的裁决。✓

## 独立验证

| 验证项 | 命令 | 结果 |
|---|---|---|
| Accept barrier tests | `pytest tests/host/test_toolruntime_accept_barrier.py` | 16 passed |
| Pyright | `pyright dayu/host/tool_runtime.py` | 0 errors, 0 warnings |

## 行为不变确认

- `ToolFactAcceptCandidate` 顶层字段未变。✓
- Producer（`_tool_fact_accept_candidate`、`_tool_fact_reuse_accept_candidate`）未迁移。✓
- Accept barrier consumer 未迁移。✓
- Tests 未迁移。✓
- 新 helper 在 Slice 1 仍未接入任何生产代码路径。✓
- EventLog payload / accepted evidence / duplicate governance / wait / memory / compaction / tool trace 行为不变。✓

## Changed Files

| 文件 | 变更 | 合规 |
|---|---|---|
| `dayu/host/tool_runtime.py` | `_validate_tool_accept_duplicate_governance` 逻辑修正 | ✓ |
| `docs/host/host-core-followup-implementation-control.md` | 状态行更新 + 日志 | ✓（gate 流程文档） |

与 fix report 一致。

## Verdict

**Code re-review pass。** Finding 01 已正确关闭，rejected findings 02/03 未被无关处理，production behavior 未变，验证结果可信。
