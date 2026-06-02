# WU-TOOL-02 Slice 3 Code Review — AgentMiMo

## Review Target

- Branch: `refactor/wu-tool-02-accept-candidate-cleanup`
- Slice: Slice 3 `Duplicate / diagnostics candidate inspection 迁移`
- Artifact scope: current uncommitted workspace diff
- Reviewer: AgentMiMo

## Source Documents

- Plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Handoff: `docs/reviews/wu-tool-02-slice3-implementation-handoff-20260602.md`
- Implementation report: `docs/reviews/wu-tool-02-slice3-implementation-report-20260602.md`

## Changed Files

| File | Status |
|---|---|
| `tests/host/test_toolruntime_duplicate_governance.py` | Modified |
| `tests/host/test_toolruntime_diagnostics.py` | Modified |
| `docs/host/host-core-followup-implementation-control.md` | Modified (gate/status update only) |
| `dayu/host/tool_runtime.py` | **No change** (verified: `git diff` empty) |

## Review Checklist

### 1. 只迁移 duplicate/diagnostics tests 的 candidate inspection 路径

**PASS.** 两个测试文件的 candidate 读取路径从旧 flat field 迁移到组合结构：

- `candidate.duplicate_key` → `_candidate_duplicate(candidate).duplicate_key`
- `candidate.duplicate_decision` → `_candidate_duplicate(candidate).duplicate_decision`
- `candidate.duplicate_scope` → `_candidate_duplicate(candidate).duplicate_scope`
- `candidate.policy_decision` → `candidate.governance.policy_decision`
- `candidate.diagnostic_refs` → `candidate.diagnostics.diagnostic_refs`
- `candidate.reuse_prior_event_refs` → `_candidate_duplicate(candidate).reuse_prior_event_refs`
- `candidate.normalized_arguments_digest` → `candidate.call.normalized_arguments_digest`
- `candidate.outcome_digest` → `result.outcome_digest` (with `result is not None` guard)
- `candidate.payload_digest` → `result.payload_digest` (with `result is not None` guard)
- `candidate.semantic_input_digest` → `candidate.idempotency.semantic_input_digest`

`dayu/host/tool_runtime.py` 无变更，已由 Slice 1/2 完成生产代码迁移。

### 2. 未改变 production duplicate governance/diagnostics semantics

**PASS.** 确认 `tool_runtime.py` 无未提交变更（staging area 和 working tree 均为空）。duplicate governance 生产行为、diagnostic emitter 行为、EventLog payload 均未触及。

### 3. attempt-scoped duplicate scope、prior refs、policy reason/message、diagnostic refs 仍被断言

**PASS.** 逐项核查：

- **attempt-scoped duplicate scope**: `test_duplicate_governed_matrix_produces_diagnostics` 中断言 `duplicate_scope.kind == "attempt"` 且 `duplicate_scope.attempt_id == _ATTEMPT_ID`。`test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs` 中断言跨 attempt scope 不同。✅
- **prior refs retention**: `test_reuse_references_prior_refs_without_second_result_fact` 断言 reuse prior refs 等于第一个 ack 的 accepted_event_refs。`test_duplicate_key_excludes_index_in_iteration` 断言 prior refs 非空。✅
- **policy reason/message**: `test_governed_duplicate_candidate_validation_rejects_policy_mismatch`、`test_governed_duplicate_candidate_validation_rejects_reason_mismatch`、`test_governed_duplicate_candidate_validation_rejects_message_mismatch` 均保留完整验证。`test_plain_policy_rejection_does_not_carry_duplicate_prior_refs` 断言 `policy_decision.reason_code`。✅
- **diagnostic refs**: `test_candidate_and_ack_carry_duplicate_diagnostic_refs` 断言 `candidate.diagnostics.diagnostic_refs` 非空且 ack diagnostic refs 等于 candidate diagnostics refs。`test_duplicate_governed_matrix_produces_diagnostics` 断言 `governed_candidate.diagnostics.diagnostic_refs` 非空。✅

### 4. 没有旧 flat field compatibility branch

**PASS.** grep 扫描两个测试文件中所有 `candidate.` 后跟旧 flat field 名的模式，结果为零匹配。所有 candidate 字段访问均通过 `candidate.call.*`、`candidate.governance.*`、`candidate.diagnostics.*`、`candidate.idempotency.*`、`candidate.result.*` 路径。

### 5. test helper 函数设计

新增 test-local helper 函数：

- `_candidate_duplicate(candidate)` — 返回非空 `ToolAcceptDuplicateGovernance`
- `_candidate_duplicate_decision(candidate)` — 返回 `DuplicateDecisionKind`
- `_candidate_duplicate_scope(candidate)` — 返回非空 `DuplicateGovernanceScope`
- `_candidate_reuse_prior_event_refs(candidate)` — 返回 `tuple[HostEventRef, ...]`

helper 设计合理：单点 assert `duplicate is not None` / `duplicate_scope is not None`，所有调用处复用，避免重复。`_accepted_ack()` helper 同步迁移，逻辑正确。

### 6. negative validation tests 的 replace 模式

`test_governed_duplicate_candidate_validation_rejects_missing_prior_refs`、`test_governed_error_candidate_validation_rejects_allow_policy`、`test_duplicate_candidate_validation_rejects_missing_duplicate_message` 等验证用例使用嵌套 `replace` 修改 governance → duplicate 子结构，符合 frozen dataclass 的组合结构修改模式。✅

### 7. diagnostics test `_accepted_ack` helper

diagnostics test 的 `_accepted_ack()` helper 读取路径已迁移：使用 `candidate.call.tool_call_id`、`candidate.governance.policy_decision`、`candidate.result`、`candidate.governance.duplicate`、`candidate.diagnostics.diagnostic_refs`、`candidate.idempotency.semantic_input_digest`。governed_ref 条件只检查 `policy_decision.kind is not ToolPolicyDecisionKind.ALLOW`（不含 REUSE），因 diagnostics 测试不覆盖 REUSE 场景，合理。✅

### 8. 验证报告可信度

Implementation report 声称：32 tests passed，0 pyright errors。

独立验证结果：

- `pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py`: **32 passed in 0.31s** ✅
- `pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py`: **0 errors, 0 warnings, 0 informations** ✅

验证报告可信，无需补测试或补 pyright。

## Findings

无 blocking finding。

## Conclusion

**Code review PASS.** Slice 3 仅迁移了 duplicate governance 与 diagnostics tests 的 candidate inspection 路径，未改变任何生产代码。所有 attempt-scoped duplicate scope、prior refs、policy reason/message、diagnostic refs 断言均保留。无旧 flat field compatibility branch。验证报告可信。
