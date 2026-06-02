# WU-TOOL-02 Slice 3 Code Review — AgentDS

## Review Metadata

- reviewer: AgentDS
- gate: code review
- branch: `refactor/wu-tool-02-accept-candidate-cleanup`
- slice: Slice 3 — Duplicate / diagnostics candidate inspection 迁移
- plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- handoff: `docs/reviews/wu-tool-02-slice3-implementation-handoff-20260602.md`
- implementation report: `docs/reviews/wu-tool-02-slice3-implementation-report-20260602.md`
- review date: 2026-06-02

## Scope Verification

### Changed Files

| File | Change Type | In Scope |
|---|---|---|
| `tests/host/test_toolruntime_duplicate_governance.py` | test candidate inspection migration | yes |
| `tests/host/test_toolruntime_diagnostics.py` | test candidate inspection migration | yes |
| `dayu/host/tool_runtime.py` | 未修改 | N/A |

控制文档 `docs/host/host-core-followup-implementation-control.md` 的 gate 状态变更为计划内元数据更新，不计入 review scope。

### Unchanged Verification

- `dayu/host/tool_runtime.py`: zero diff — production code untouched.
- `dayu/host/tool_trace.py`: untouched.
- `dayu/host/compaction_evidence.py`: untouched.
- `dayu/host/compact_material.py`: untouched.
- `dayu/host/memory.py`: untouched.

## Review Findings

### Finding 1 — 未修复 — 建议 — diagnostics `_accepted_ack` 的 `reuse_prior_event_refs` 路径与 duplicate_governance 测试不同步

- 文件: `tests/host/test_toolruntime_diagnostics.py`
- 位置: `_accepted_ack()` helper（line 414+）
- 描述: diagnostics 测试 `_accepted_ack` 直接访问 `candidate.governance.duplicate.reuse_prior_event_refs`，而 duplicate_governance 测试新增了 `_candidate_reuse_prior_event_refs()` 辅助函数访问同一字段。两处访问路径等价，但 helper 封装提供更清晰的断言语义和统一的 None-safe 行为。
- 严重程度: 建议（suggestion），非 blocking。当前实现语义正确（duplicate 为 None 时回退 `()`），但若后续 `ToolAcceptDuplicateGovernance.reuse_prior_event_refs` 字段语义或类型变化，两处需要分别适配，增加维护成本。
- 建议: 可以考虑将 `_candidate_reuse_prior_event_refs` 提取为共享 test helper，或在 diagnostics 测试中也引入相同的局部 helper，消除重复。

### 无 blocking finding

## Review Criteria — 逐项确认

### 1. 是否只迁移 duplicate/diagnostics tests 的 candidate inspection 路径

**通过。** diff 确认仅测试文件变更，production 代码零变更。`git diff HEAD -- dayu/host/tool_runtime.py` 为空。

通过 `rg` 验证两个测试文件中不存在旧 flat field 直接访问 `candidate.<field>` 模式（`session_id`、`run_id`、`duplicate_key`、`duplicate_decision`、`reuse_prior_event_refs`、`diagnostic_refs` 等全部命中 0 条）。

### 2. 是否未改变 production duplicate governance/diagnostics semantics

**通过。** 无 production 代码变更。duplicate governance 的 attempt-scoped key、scope、owner/waiter、durable missing、reuse、policy enforcement 路径的语义不变；diagnostic emitter 的 emit、ref format、trace payload 语义不变。

### 3. attempt-scoped duplicate scope、prior refs、policy reason/message、diagnostic refs 是否仍被断言

**通过。** 逐项核实：

- **duplicate scope 为 attempt**: `test_duplicate_governed_matrix_produces_diagnostics` 断言 `duplicate_scope.kind == "attempt"` 与 `duplicate_scope.attempt_id == _ATTEMPT_ID`（line 537-540）。`test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs` 仍断言 cross-attempt 场景下不同 attempt_id。`test_fresh_toolruntime_handle_same_attempt_is_in_memory_non_durable_restart_behavior` 仍断言同 attempt 内 scope 一致。
- **reuse prior refs**: `test_reuse_references_prior_refs_without_second_result_fact` 断言 `_candidate_reuse_prior_event_refs(reuse_candidate) == accept_port.acks[0].accepted_event_refs`。`test_same_attempt_concurrent_reuse_waits_for_owner_accept` 同路径。
- **policy reason/message 校验**: `test_governed_duplicate_candidate_validation_rejects_policy_mismatch`、`_rejects_reason_mismatch`、`_rejects_message_mismatch`、`_rejects_allow_policy`、`_rejects_missing_prior_refs` 五个 negative validation test 全部保留且语义一致，通过 `replace` 操作修改 `governance.policy_decision` / `governance.duplicate` 子结构。
- **diagnostic refs**: `test_candidate_and_ack_carry_duplicate_diagnostic_refs` 断言 `governed_candidate.diagnostics.diagnostic_refs` 非空、`governed_ack.diagnostic_refs == governed_candidate.diagnostics.diagnostic_refs`。`test_rejected_accept_governed_error_emits_diagnostic_ref` 与 `test_timeout_governed_error_emits_diagnostic_ref` 仍通过 emitter 级 diagnostic records 断言。

### 4. 是否没有旧 flat field compatibility branch

**通过。** production 代码中不存在 `compat`、`@property` 转发、旧字段 facade、兼容 re-export 或兼容 wrapper。两个测试文件中通过 `rg` 确认无旧 flat field 直接访问残留。

### 5. 验证报告是否可信，是否需要补测试/pyright

**通过。** 独立验证结果:

```
tests/host/test_toolruntime_duplicate_governance.py: 29 passed
tests/host/test_toolruntime_diagnostics.py:           3 passed
total:                                               32 passed
```

```
pyright dayu/host/tool_runtime.py \
        tests/host/test_toolruntime_duplicate_governance.py \
        tests/host/test_toolruntime_diagnostics.py
→ 0 errors, 0 warnings, 0 informations
```

实现报告声称的 32 passed / 0 pyright errors 经独立复现确认。无需补测试或额外 pyright 修复。

## Additional Checks

### 测试 helper 质量

新增的四个局部 helper 函数 (`_candidate_duplicate`、`_candidate_duplicate_decision`、`_candidate_duplicate_scope`、`_candidate_reuse_prior_event_refs`) 全部提供中文 docstring 和完整类型标注，符合 CLAUDE.md 编码约束。helper 内使用了 `assert duplicate is not None` 的前置断言，使得调用方无需在每个断言点做 None check，提升了测试可读性。

### `_accepted_ack` 迁移正确性

两份测试文件中的 `_accepted_ack` helper 均已迁移为读取组合结构:
- `tool_call_id` → `candidate.call.tool_call_id`
- `policy_decision.kind` → `candidate.governance.policy_decision.kind`
- `outcome_digest` → `candidate.result.outcome_digest`
- `payload_digest` → `candidate.result.payload_digest`（增加 `result is not None` 守卫）
- `semantic_input_digest` → `candidate.idempotency.semantic_input_digest`
- `diagnostic_refs` → `candidate.diagnostics.diagnostic_refs`

所有路径等价，无语义变更。

### Negative validation test 的 replace 链

validation rejection tests 中的 `replace` 链式修改从顶层字段改为子结构替换:

```python
# Before (旧 flat field):
replace(governed_candidate, reuse_prior_event_refs=())

# After (组合结构):
duplicate = replace(_candidate_duplicate(governed_candidate), reuse_prior_event_refs=())
governance = replace(governed_candidate.governance, duplicate=duplicate)
replace(governed_candidate, governance=governance)
```

这是正确的两层 `replace` 链: 子对象 frozen dataclass 不可变，必须先 `replace` 子结构再 `replace` 组合根。语义等价，无引入额外行为。

### 总控文档同步

`docs/host/host-core-followup-implementation-control.md` gate 状态从 `implementation` 更新为 `review`，`implementation status` 更新为 `WU-TOOL-02 Slice 3 implemented; code review in progress`。这是计划内元数据更新，不在本 review scope 内。

## Verdict

**Code Review: PASS**

无 blocking finding。Slice 3 变更严格限定在 duplicate governance 与 diagnostics 测试的 candidate inspection 路径迁移，production 代码零变更，所有覆盖项断言保持完整，pyright 通过。Finding 1 为建议级，不阻塞 Slice 3 gate 推进。

## Residual Notes

- Slice 4（EventLog payload consumers regression）中若发现 `test_tool_trace_projection.py` 等文件仍有旧 flat field 直接访问 `candidate.`，建议届时统一为测试文件引入共享 helper，减少重复的路径访问模式。
- diagnostics 测试的 `_accepted_ack` 实现与 duplicate_governance 测试的 `_accepted_ack` 在 `reuse_prior_event_refs` 路径上有轻微风格差异（直接访问 vs. helper），在 Slice 4 或 Slice 5 时可考虑统一。
