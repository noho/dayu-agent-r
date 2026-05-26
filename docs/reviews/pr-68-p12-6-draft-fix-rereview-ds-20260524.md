# PR 68 P12.6 Draft Fix Re-Review — DS

## Gate

- Gate: P12.6 draft PR fix re-review gate
- PR: https://github.com/noho/dayu-agent-r/pull/68
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Source adjudication: `docs/reviews/pr-68-p12-6-draft-review-controller-adjudication-20260524.md`
- Fix artifact under review: `docs/reviews/pr-68-p12-6-draft-fix-codex-20260524.md`
- Assigned scope: Independently re-review uncommitted PR fix for accepted findings A1-A8 only.

## Validation Commands

```bash
# 完整 PR matrix 测试
source .venv/bin/activate && python -m pytest \
  tests/host/test_memory_projection.py \
  tests/host/test_llm_compaction.py \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_compaction_contract.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_compact_artifact_store.py \
  tests/service/test_host_assembly.py \
  tests/runtime/test_config_loader.py \
  --tb=short -q
# Result: 315 passed in 5.27s

# 类型检查
source .venv/bin/activate && python -m pyright dayu/host/ tests/ --outputjson
# Result: 0 errors, 0 warnings, 0 informations

# 空白字符检查
git diff --check
# Result: passed (no output)
```

## Finding-by-Finding Verification

### A1 — 已修复 — Memory diagnostic reason schema mismatch

**Schema CHECK constraint** (`dayu/host/durable/schema.py:798-800`):
`evidence_backed_fact_superseded` 和 `minimum_preserve_item_covered` 已追加到 `host_memory_diagnostics` 表的 CHECK 约束中。

**测试覆盖** (`tests/host/test_memory_projection.py`):
`test_new_memory_diagnostic_reasons_are_persistable` 参数化覆盖两个新 reason，通过 `_WriteDiagnosticOperation` → `_ReadDiagnosticOperation` 完整验证 durable write/read 闭环。

**证据**:
```python
# schema.py 新增
'evidence_backed_fact_superseded',
'minimum_preserve_item_covered'
```
```python
# test parametrize
(MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_SUPERSEDED,
 MemoryDiagnosticReason.MINIMUM_PRESERVE_ITEM_COVERED)
```

**结论**: 已修复。

---

### A2 — 已修复 — LLM compaction timeout/cancellation handling

**Timeout 包装** (`dayu/host/llm_compaction.py:218-224`):
`compact()` 方法用 `try/except TimeoutError` 包裹 `_run_agent_request()`，捕获后调用 `_signal_timeout_cancellation()`，然后 `raise LLMCompactionProposalError("compactor proposal timed out") from exc`。

**Cancellation token signal** (`dayu/host/llm_compaction.py:105-116, 298-308`):
新增 `_CancellationSignalToken` Protocol 类（`runtime_checkable`），定义 `request_cancel(reason)` 接口。`_signal_timeout_cancellation()` 通过 `isinstance(cancellation_token, _CancellationSignalToken)` 检查是否支持写入取消，仅对可写 token 调用 `request_cancel("compactor_proposal_timeout")`。

**测试覆盖** (`tests/host/test_llm_compaction.py:655-684`):
`test_llm_context_compactor_applies_runner_timeout` 验证：
- 抛出 `LLMCompactionProposalError` 且消息匹配 `"proposal timed out"`
- `StubCancellationToken.is_cancelled()` 返回 `True`
- `StubCancellationToken.cancel_reason()` 返回 `"compactor_proposal_timeout"`

**结论**: 已修复。`_CancellationSignalToken` 使用 Protocol + isinstance 是合理设计——不可写 token（如 reactive compaction 的 Engine token）不会被错误 signal。

---

### A3 — 已修复 — Range endpoint label must resolve to exactly one canonical ref

**校验逻辑** (`dayu/host/llm_compaction.py:839-851`):
新增 `_single_range_endpoint_ref(refs, *, field_name)` 辅助函数，`len(refs) != 1` 时抛出 `ValueError`。

**调用点**: `_range_tuple()` (line 792-798) 和 `_optional_input_range()` (line 1184-1190) 均通过此函数获取 start/end ref，替代原来的 `start_refs[0]` / `end_refs[0]`。

**测试覆盖** (`tests/host/test_llm_compaction.py`):
- `test_range_endpoint_label_with_multiple_refs_is_rejected`: 验证多 ref endpoint 抛出带 `"exactly one"` 消息的 `LLMCompactionProposalError`
- `test_range_endpoint_label_without_ref_is_rejected`: 验证零 ref endpoint 抛出带 `"no canonical source refs"` 消息的 `LLMCompactionProposalError`

**结论**: 已修复。

---

### A4 — 已修复 — Compact material provenance must preserve locator/artifact refs

**数据结构** (`dayu/host/compact_material.py:165-169`):
`RunInputMaterialBlock` 新增 `artifact_refs: tuple[str, ...] = ()` 和 `source_locator_refs: tuple[OpaqueEvidenceRef, ...] = ()` 字段，含 `__post_init__` 校验。

**传播路径**:
1. Factory `run_input_material_block()` (line 486-489) 接受并传递新字段
2. `build_accepted_tool_evidence_material_blocks()` (`dayu/host/run_input.py:1175-1176`) 从 `InitialEvidenceMaterial` 传递到 `RunInputMaterialBlock`
3. `_provenance_from_evidence_blocks()` (`dayu/host/compact_material.py:1647-1648`) 从 `source.artifact_refs` / `source.source_locator_refs` 读取，替代硬编码空 tuple

**测试覆盖** (`tests/host/test_compact_material.py`):
`test_evidence_labels_are_prompt_local_and_map_to_canonical_evidence` 使用非空 `artifact_refs=("artifact:evidence-map",)` 和含 `OpaqueEvidenceRef` 的 `source_locator_refs`，验证 round-trip 后字段完整保留。

**结论**: 已修复。

---

### A5 — 已修复 — Dispatch lag repair failure must not leave records permanently running

**行为变更** (`dayu/host/dispatch.py:2246-2263`):
`SNAPSHOT_LAG_OVER_THRESHOLD` 分支从 `return "skipped"`（仅释放 lane token）改为：
1. 调用 `self._safe_closeout_worker_startup_timeout(record, reason=_MEMORY_PROJECTION_REPAIR_REQUIRED_REASON, original_error=exc)` 做 terminal closeout
2. 在 `finally` 中释放 lane token
3. 返回 `"timed_out"`

**接口兼容性**: `_start_worker` 原本就有 `"timed_out"` 返回值（lines 1987, 2003, 2041, 2280, 2299, 2319）；`drain_once()` (line 1689-1690) 对 `"timed_out"` 正确递增计数器。

**测试覆盖** (`tests/host/test_dispatch_scheduler.py`):
`test_persistent_memory_lag_repair_failure_closes_starting_run` 验证：
- `result.timed_out == 1`
- `builder.calls == 2`（确认 retry 发生）
- `factory.created == 0`（无 worker 启动）
- `run.status == RunStatus.FAILED`
- `attempt.status == AttemptStatus.FAILED`
- `dispatch_record.status == DispatchRecordStatus.CANCELLED`
- `dispatch_record.cancelled_event_id is not None`

**结论**: 已修复。状态机正确从 RUNNING/DISPATCHING 转移到 FAILED/CANCELLED 终态。

---

### A6 — 已修复 — Evidence-backed facts must not be starved by lower-value stable blocks

**优先级调整** (`dayu/host/run_input.py:1917-1925`):
`_memory_stable_blocks()` block 顺序从 `goals → subjects → facts → assumptions` 改为 `goals → facts → subjects → assumptions`。evidence-backed facts block 现在先于 confirmed subjects block 消耗预算。

**测试覆盖** (`tests/host/test_run_input_builder.py`):
`test_stable_budget_prioritizes_evidence_backed_facts_over_subjects` 验证：
- 输出中包含 `"Memory evidence-backed facts:"` block
- 输出中不含 `"Memory confirmed subjects and methodology:"` block
- `stable:subjects` 被诊断为 `BUDGET_LIMIT_REACHED`

**存量测试适配**: `test_durable_memory_provider_uses_covered_snapshot` 的 content index 断言已更新，`contents[2]` 从 subjects 改为 facts，`contents[3]` 从 facts 改为 subjects。

**结论**: 已修复。

---

### A7 — 已修复 — Empty evidence labels must not disable evidence-backed guard rails

**检测逻辑** (`dayu/host/context_governance.py:213-225`):
新增 `_evidence_labels_missing_for_known_facts(request)` 辅助函数，在 `evidence_backed_fact_refs` 非空且 `material_pack.evidence_labels` 为空时返回 `True`。

**集成点** (`dayu/host/context_governance.py:71-72`):
在 `check_compaction_candidate()` 中调用，条件满足时添加 `CompactQualityIssue.EVIDENCE_LABELS_MISSING`。

**枚举定义** (`dayu/host/compaction.py:67`):
`CompactQualityIssue.EVIDENCE_LABELS_MISSING = "evidence_labels_missing"`

**测试覆盖** (`tests/host/test_compaction_contract.py`):
`test_quality_rejects_known_fact_refs_without_evidence_labels` 验证：
- `result.accepted is False`
- `CompactQualityIssue.EVIDENCE_LABELS_MISSING in result.rejection_reasons`

**结论**: 已修复。

---

### A8 — 已修复 — Accept barrier must reject missing payload descriptors

**存在性校验** (`dayu/host/tool_runtime.py:3339-3356`):
新增 `_candidate_payload_descriptor_exists(transaction, candidate)` 辅助函数，通过 `read_payload_descriptor()` 查询 payload descriptor，返回 `None` 时拒绝。`payload_ref is None` 时直接返回 `True`（无 ref 不需要校验）。

**调用点** (`dayu/host/tool_runtime.py:2026-2032`):
在 `accept_tool_fact()` 的事务内、写 accepted events 之前调用。descriptor 缺失时返回 `_rejected_ack(..., ToolAcceptRejectReason.PAYLOAD_REFERENCE_INVALID, ...)`。

**Import** (`dayu/host/tool_runtime.py:80`):
`from dayu.host.durable.payload import read_payload_descriptor`，使用已有的 durable store 读取能力，不跨越层边界。

**测试覆盖** (`tests/host/test_toolruntime_accept_barrier.py`):
`test_accept_rejects_missing_payload_descriptor_before_writing_events` 验证：
- `result` 为 `ToolFactRejectedAck` 实例
- `result.reason_code is ToolAcceptRejectReason.PAYLOAD_REFERENCE_INVALID`
- `_tool_events(...) == ()`（无事件被写入）

**结论**: 已修复。校验在 durable read 上执行，在写 accepted event 之前 fail-fast。

---

## Regression Check

逐项复查 fix artifact 提及的 regression 风险区域：

| 风险区域 | 检查方式 | 结论 |
|---------|---------|------|
| Schema CHECK | 两个新 reason 已追加，存量 reason 保留；参数化测试验证 durable round-trip | 无回归 |
| Timeout/cancellation | `_CancellationSignalToken` 使用 `isinstance` Protocol 检查，不可写 token 保持 no-op；原有非超时错误路径未变 | 无回归 |
| Range label | `_single_range_endpoint_ref` 仅影响 label 解析路径；存量单 ref 场景行为等价 | 无回归 |
| Provenance refs | 新字段默认值为空 tuple，存量调用方未传值时行为等价；`_provenance_from_evidence_blocks` 从 source 字段读取替代硬编码空 tuple | 无回归 |
| Dispatch closeout | `_safe_closeout_worker_startup_timeout` 是已有方法，`"timed_out"` 是已有返回值；仅 SNAPSHOT_LAG_OVER_THRESHOLD 分支从 skip 变为 terminal closeout | 无回归 |
| Stable memory priority | 仅调整 block 顺序，不引入新 block 或删除旧 block；存量测试 index 断言已适配新顺序 | 无回归 |
| Evidence label guard | 新增 fail-closed 检查，不影响存量正常路径（正常路径有 labels） | 无回归 |
| Accept barrier | 新增 durable read 在写之前，不影响存量正常路径（descriptor 存在时通过） | 无回归 |

## Verdict

**PASS**

全部 8 个 accepted findings (A1-A8) 均已修复，有直接的代码和测试证据。315 测试通过，pyright 零错误，无空白字符问题，无回归。

从 re-review 视角，PR fix 已就绪，可以执行 accepted PR review commit。

## Residual Notes

- A6 fix 防止了低优先级 block 饿死 evidence-backed facts，但若 evidence-backed facts block 自身超过 stable 预算，仍会触发 budget diagnostic 并被跳过。这是设计边界而非缺陷，已在 fix artifact residual risks 中记录。
- `_CancellationSignalToken` Protocol 的 `isinstance` 检查对非 Protocol 实现的 `CancellationToken` 是安全的 no-op，但未来若 `CancellationToken` 接口自身增加了 `request_cancel` 语义，需重新审视此 Protocol 的必要性。
