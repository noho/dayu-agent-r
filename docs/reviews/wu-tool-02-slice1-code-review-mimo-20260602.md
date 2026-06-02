# WU-TOOL-02 Slice 1 Code Review — AgentMiMo

## Review Target

- Branch: `refactor/wu-tool-02-accept-candidate-cleanup`
- Diff: uncommitted workspace changes
- Scope: Slice 1 `新增子结构与局部 validation helper`
- Allowed files: `dayu/host/tool_runtime.py`
- Review date: 2026-06-02

## Review Inputs

- Plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Implementation handoff: `docs/reviews/wu-tool-02-slice1-implementation-handoff-20260602.md`
- Implementation report: `docs/reviews/wu-tool-02-slice1-implementation-report-20260602.md`
- Design source: `docs/host/design.md` (ToolRuntime sections)
- Actual diff: `git diff HEAD` for `dayu/host/tool_runtime.py`

## Verification Commands

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py
# Result: 16 passed in 0.29s

source .venv/bin/activate && pyright dayu/host/tool_runtime.py
# Result: 0 errors, 0 warnings, 0 informations
```

## Changed Files

| 文件 | 变更类型 | 允许范围内 |
|---|---|---|
| `dayu/host/tool_runtime.py` | 新增子结构 + validation helper | 是 |
| `docs/host/host-core-followup-implementation-control.md` | gate 状态更新 | 是（gate 流程文档） |
| `docs/reviews/wu-tool-02-slice1-implementation-handoff-20260602.md` | 新增 handoff artifact | 是 |
| `docs/reviews/wu-tool-02-slice1-implementation-report-20260602.md` | 新增 report artifact | 是 |

未修改任何 tests、README、配置、schema、其它 production 文件。

## Scope Compliance

### ToolFactAcceptCandidate 顶层字段

**PASS** — `ToolFactAcceptCandidate` 完全未变更。diff 确认 `class ToolFactAcceptCandidate` 定义（line 565-654）无任何修改，所有顶层字段、`__post_init__` 逻辑和 validation 调用路径保持原样。

### Producer / accept barrier consumer / tests

**PASS** — 未迁移 `_tool_fact_accept_candidate()`、`_tool_fact_reuse_accept_candidate()`、`_accept_idempotency_scope()`、`_tool_result_payload()`、ack helper、EventLog payload helper 或任何 tests。现有 producer 和 consumer 代码路径无变更。

### EventLog payload / accepted evidence / duplicate governance / wait / memory / compaction / tool trace

**PASS** — 无行为变更。新子结构和 validation helper 未接入任何生产代码路径。

### Public API / exports

**PASS** — `__all__`（line 5657）未新增任何新子结构。7 个新 dataclass 和 7 个新 validation helper 均为模块私有。

### New dataclass 质量

**PASS** — 所有 7 个新 dataclass 均为 `@dataclass(frozen=True, slots=True)`，完整中文 docstring（含 `:param`、`:returns`、`:raises`），严格类型签名，无 `Any`、`object` 或无类型参数。字段类型与现有 `ToolFactAcceptCandidate` 对应字段一致。

### Validation helper 边界

**部分通过** — 见 Finding 01。

## Findings

### 01-未修复-低-`_validate_tool_accept_duplicate_governance` 对 ALLOW 决策的校验语义与现有 `_validate_duplicate_fields` 不一致

**位置**: `dayu/host/tool_runtime.py` line 4010-4042（新 helper） vs line 4146-4177（现有 helper）

**证据**: 现有 `_validate_duplicate_fields` 对所有非 None `duplicate_decision`（包括 ALLOW）均要求 `duplicate_scope` 和 `duplicate_decision_message` 非 None：

```python
# 现有代码 line 4155-4174
if candidate.duplicate_decision is None:
    return
# ... isinstance check ...
if candidate.duplicate_key is None:  # 仅 REUSE/HINT/REQUIRE_JUSTIFICATION/HARD_STOP/DURABLE_MISSING
    raise ValueError(...)
if candidate.duplicate_scope is None:          # ← 对所有非 None decision 生效，包括 ALLOW
    raise ValueError("duplicate decision requires duplicate_scope")
if candidate.duplicate_decision_message is None:  # ← 同上
    raise ValueError("duplicate decision requires duplicate_decision_message")
```

新 `_validate_tool_accept_duplicate_governance` 对 ALLOW 跳过了 key/scope/message 要求：

```python
# 新代码 line 4033-4039
if duplicate.duplicate_decision is not DuplicateDecisionKind.ALLOW:
    if duplicate.duplicate_key is None:
        raise ValueError(...)
    if duplicate.duplicate_scope is None:
        raise ValueError(...)
    if duplicate.duplicate_decision_message is None:
        raise ValueError(...)
```

**影响**: Slice 1 阶段新 helper 未接入生产路径，无运行时影响。但 Slice 2 迁移组合根时，若允许 `ToolAcceptDuplicateGovernance(duplicate_decision=ALLOW, duplicate_scope=None, ...)` 构造成功，将与现有 `_validate_duplicate_fields` 的拒绝行为产生语义分歧。

**建议**: Slice 2 迁移前需裁决：ALLOW 决策是否应要求 `duplicate_scope` / `duplicate_decision_message`。若保持现有语义，新 helper 应将 `is not ALLOW` 改为对所有非 None decision 生效的统一检查。若 ALLOW 决策不需要 scope/message，则现有 `_validate_duplicate_fields` 也应同步修正。

### 02-未修复-低-`_validate_tool_accept_governance` 中对 typed dataclass 字段的 isinstance 检查冗余

**位置**: `dayu/host/tool_runtime.py` line 4053, 4059-4062

**证据**:

```python
if not isinstance(governance.policy_decision, ToolPolicyDecision):
    raise ValueError("policy_decision must be ToolPolicyDecision")
# ...
if governance.duplicate is not None and not isinstance(
    governance.duplicate, ToolAcceptDuplicateGovernance
):
    raise ValueError("duplicate must be ToolAcceptDuplicateGovernance")
```

`ToolAcceptGovernance` 的字段类型签名 `policy_decision: ToolPolicyDecision` 和 `duplicate: ToolAcceptDuplicateGovernance | None` 已由 frozen dataclass + slots 保证类型安全。运行时传入错误类型会在 dataclass 构造阶段即失败，这些 isinstance 检查是逻辑死代码。

**影响**: 无运行时影响。代码存在但永远不会触发。

**建议**: 移除冗余 isinstance 检查，保持 validation helper 只校验真正的内部 invariant。若保留为防御性编码，需在 docstring 中注明"防御性检查，正常路径不可达"。

### 03-未修复-低-`_validate_tool_accept_result` 中 payload_ref / payload_digest 一致性检查需确认 plan 意图

**位置**: `dayu/host/tool_runtime.py` line 3999-4003

**证据**: 新 helper 包含：

```python
if (
    result.payload_ref is not None
    and result.payload_digest != result.payload_ref.payload_digest
):
    raise ValueError("payload_digest must match payload_ref digest")
```

该检查与现有 `_validate_common_candidate_fields` line 4131-4135 完全一致。Plan 明确约束："本 work unit 不借结构拆分新增 payload digest 校验语义；`payload_ref` 存在时保持当前 descriptor 存在性校验与当前已有 candidate 校验，不扩大为新的等值规则或新持久化约束。"

**裁决**: 该检查是现有校验的精确复制，不是新增语义。严格来说符合 plan 意图（"保持当前已有 candidate 校验"），但建议 implementation agent 在 commit message 或代码注释中明确标注"镜像自 `_validate_common_candidate_fields`"，避免后续 reviewer 误判为新增约束。

## Adversarial Failure Pass

### 新子结构是否偷偷改变了 ToolFactAcceptCandidate 的构造语义？

**PASS** — 新子结构未被任何现有代码引用。`ToolFactAcceptCandidate.__post_init__` 未调用任何新 helper。Producer 和 consumer 代码路径无变更。

### 是否引入了 payload digest 新语义？

**PASS** — `_validate_tool_accept_result` 的 payload_ref/payload_digest 检查是现有 `_validate_common_candidate_fields` 的精确复制。无新增等值规则或持久化约束。

### ToolFactKind.LOST 是否意外获得了 accept 语义？

**PASS** — 新 helper 和 dataclass 均未涉及 LOST。现有 `ToolFactAcceptCandidate.__post_init__` 的 `else: raise ValueError("unsupported tool_fact_kind")` 仍然覆盖 LOST 拒绝。

### 是否有隐式 public API 泄漏？

**PASS** — `__all__` 未新增任何符号。新 dataclass 均为模块私有。

### 现有 16 个 accept barrier 测试是否仍通过？

**PASS** — `pytest tests/host/test_toolruntime_accept_barrier.py` 16 passed。

### pyright 是否通过？

**PASS** — `pyright dayu/host/tool_runtime.py` 0 errors。

## Implementation Report 可信度

**PASS** — 报告内容与实际 diff 一致：
- Changed files 准确
- 实现项与 diff 匹配（7 个 dataclass + 7 个 validation helper）
- 验证命令结果与本次独立复现一致
- "无 producer/consumer/test 迁移"确认正确
- "ToolFactKind.LOST 仍 unsupported"确认正确
- Residual risks 描述合理

## 补测试 / pyright 需求

**无需补测试** — Slice 1 新增的子结构和 helper 未接入生产路径，现有 16 个 accept barrier 测试已证明行为不变。新 helper 的直接测试属于 Slice 2 职责（测试跟着实现边界迁移）。

**无需额外 pyright** — 已通过。

## 结论

**Code review PASS**，附 3 个低严重 findings。

3 个 findings 均为低严重，不阻塞 Slice 1 合入：
- Finding 01（ALLOW 校验不一致）：Slice 1 阶段无运行时影响，但 Slice 2 迁移前必须裁决。
- Finding 02（冗余 isinstance）：纯代码质量问题，不影响行为。
- Finding 03（payload 检查标注）：建议性改进，已有精确复制的现有逻辑兜底。

Slice 1 的核心目标——新增子结构与局部 validation helper、不改变现有行为——已达成。
