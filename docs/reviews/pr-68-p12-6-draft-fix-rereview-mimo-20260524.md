# PR 68 P12.6 Draft Fix Re-Review — MiMo

## Gate

- Gate: P12.6 draft PR fix re-review gate
- PR: https://github.com/noho/dayu-agent-r/pull/68
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Source fix artifact: `docs/reviews/pr-68-p12-6-draft-fix-codex-20260524.md`
- Source adjudication: `docs/reviews/pr-68-p12-6-draft-review-controller-adjudication-20260524.md`
- Assigned scope: 独立复审 A1-A8 修复，确认每个 accepted finding 已修复或指出剩余 blocker，检查回归风险

## Verdict

**PASS**

所有 8 个 accepted findings (A1-A8) 均已正确修复，测试覆盖充分，无阻断回归。

## Finding 复审详情

### A1 — PASS — Memory diagnostic reason schema mismatch

- **修复方式**: `schema.py` CHECK 约束已追加 `evidence_backed_fact_superseded` 和 `minimum_preserve_item_covered`。
- **直接证据**: `dayu/host/durable/schema.py:797-798` 两个新 reason 值已加入 CHECK 列表。
- **测试**: `test_new_memory_diagnostic_reasons_are_persistable` 参数化测试写入并读回两个 reason，验证 durable store 持久化成功。
- **回归检查**: 无。纯 schema 扩展，不删除已有 reason 值。

### A2 — PASS — LLM compaction timeout/cancellation handling

- **修复方式**: `LLMContextCompactor.compact()` 内部 `_run_agent_request` 调用包裹 try/except `TimeoutError`，调用 `_signal_timeout_cancellation()` 通知可写 Host cancellation token，然后抛出 `LLMCompactionProposalError("compactor proposal timed out")`。
- **直接证据**: `dayu/host/llm_compaction.py:219-236` try/except 包裹；`dayu/host/llm_compaction.py:104-117` `_CancellationSignalToken` 协议定义；`dayu/host/llm_compaction.py:300-312` `_signal_timeout_cancellation()` helper。
- **测试**: `test_llm_context_compactor_applies_runner_timeout` 验证 (1) 异常被包装为 `LLMCompactionProposalError`，(2) cancellation token 被 signal 且 reason 为 `"compactor_proposal_timeout"`。
- **回归检查**: 无。`_CancellationSignalToken` 使用 `runtime_checkable` Protocol + `isinstance` 检查，非可写 token（如 `_NeverCancelledToken`）静默跳过 signal，行为安全。

### A3 — PASS — Range endpoint label must map to exactly one canonical ref

- **修复方式**: 新增 `_single_range_endpoint_ref()` 校验 `len(refs) != 1` 时抛出 `ValueError`；在 `_range_tuple()` 和 `_optional_input_range()` 两处调用点均接入。
- **直接证据**: `dayu/host/llm_compaction.py:839-854` `_single_range_endpoint_ref()` 定义；`:792-799` 和 `:1184-1191` 两处调用。
- **测试**: `test_range_endpoint_label_with_multiple_refs_is_rejected`（多 ref）和 `test_range_endpoint_label_without_ref_is_rejected`（零 ref）均验证抛出 `LLMCompactionProposalError`。
- **回归检查**: 无。原来 `start_refs[0]` 在零 ref 时会抛 `IndexError`（未捕获），现在抛 `ValueError` 被 `compact()` 包装为 `LLMCompactionProposalError`，错误处理更一致。多 ref 场景从静默截断变为显式拒绝，是行为改进。

### A4 — PASS — Compact material provenance must preserve locator/artifact refs

- **修复方式**: `RunInputMaterialBlock` 新增 `artifact_refs` 和 `source_locator_refs` 字段；`_provenance_from_evidence_blocks()` 从 source block 读取而非硬编码空 tuple；`run_input.py` 的 `build_accepted_tool_evidence_material_blocks()` 从 `InitialEvidenceMaterial` 传播 refs；新增 `_require_opaque_evidence_ref_tuple()` 校验。
- **直接证据**: `compact_material.py:167-168` 字段定义；`:1644-1645` provenance 从 source 读取；`run_input.py:1175-1176` 传播；`:212-219` 校验。
- **测试**: `test_evidence_labels_are_prompt_local_and_map_to_canonical_evidence` 验证非空 `artifact_refs` 和 `source_locator_refs` 在 evidence map 中保留。
- **回归检查**: 无。新增字段默认空 tuple，所有现有构造点无需修改。校验函数 `_require_opaque_evidence_ref_tuple` 确保类型安全。

### A5 — PASS — Dispatch lag repair failure must not leave records permanently running

- **修复方式**: 持续 lag repair 失败时不再 `return "skipped"`，改为调用 `_safe_closeout_worker_startup_timeout()` 做 terminal closeout（Run → FAILED, Attempt → FAILED, dispatch record → CANCELLED），然后 `return "timed_out"`。
- **直接证据**: `dispatch.py:2243-2266` 新逻辑：try/finally 确保 lane token 释放，`_safe_closeout_worker_startup_timeout` 执行 terminal closeout。
- **测试**: `test_persistent_memory_lag_repair_failure_closes_starting_run` 验证 `result.timed_out == 1`、`builder.calls == 2`、`factory.created == 0`、Run/Attempt 为 FAILED、dispatch record 为 CANCELLED。
- **回归检查**: 行为从"skip + 回到 queued"变为"terminal closeout"，是有意的改进。单次 lag repair 仍走原有 rebuild + retry 路径（`except` 块前半部分），只有持续失败才触发 terminal closeout。

### A6 — PASS — Evidence-backed facts must not be starved by lower-value stable blocks

- **修复方式**: `_memory_stable_blocks()` 排序从 `goals → subjects → facts → assumptions` 改为 `goals → facts → subjects → assumptions`，evidence-backed facts 优先于 confirmed subjects 进入预算。
- **直接证据**: `run_input.py:1920-1931` facts block 在 subjects block 之前构造。
- **测试**: `test_stable_budget_prioritizes_evidence_backed_facts_over_subjects` 构造 12 个 subjects 压缩预算的场景，验证 facts 出现在 messages 中而 subjects 被跳过，且产生 `BUDGET_LIMIT_REACHED` diagnostic。
- **回归检查**: 无负面回归。subjects 被 facts 挤出时仍产生 diagnostic，可观测性保留。fix artifact 声明的 residual risk（facts block 本身超预算仍被跳过）是已知边界行为，由现有 budget diagnostic 覆盖。

### A7 — PASS — Empty evidence labels must not disable evidence-backed guard rails

- **修复方式**: 新增 `_evidence_labels_missing_for_known_facts()` 检查 `evidence_backed_fact_refs` 非空但 `material_pack.evidence_labels` 为空时返回 `True`；`check_compaction_candidate()` 调用该函数并 emit `CompactQualityIssue.EVIDENCE_LABELS_MISSING`。
- **直接证据**: `context_governance.py:212-224` 新函数；`:71-72` 调用点。`compaction.py:67` 新增枚举值。
- **测试**: `test_quality_rejects_known_fact_refs_without_evidence_labels` 构造无 evidence labels 的 material pack，验证 `EVIDENCE_LABELS_MISSING` 被 emit 且 candidate 被拒绝。
- **回归检查**: 无。该检查只在 `evidence_backed_fact_refs` 非空且 `evidence_labels` 为空时触发，不影响正常有 labels 的路径。

### A8 — PASS — Accept barrier payload descriptor existence

- **修复方式**: `DefaultHostToolFactAcceptPort.accept_tool_fact()` 在写 accepted events 前调用 `_candidate_payload_descriptor_exists()` 校验 payload descriptor 存在性；不存在时返回 `PAYLOAD_REFERENCE_INVALID` 拒绝。
- **直接证据**: `tool_runtime.py:2026-2033` 校验调用点；`:3339-3357` `_candidate_payload_descriptor_exists()` 实现。`payload.py:read_payload_descriptor` 已存在，复用无新增依赖。
- **测试**: `test_accept_rejects_missing_payload_descriptor_before_writing_events` 构造缺失 payload descriptor 的 candidate，验证返回 `ToolFactRejectedAck` 且 `reason_code` 为 `PAYLOAD_REFERENCE_INVALID`，无 tool events 写入。
- **回归检查**: 无。`candidate.payload_ref is None` 时直接返回 `True`（不校验），不影响无 payload 的 candidate。增加一次 durable read，但 accept 路径本身已有多次 durable 操作，边际成本可忽略。

## 回归风险总评

| 风险项 | 评估 |
|--------|------|
| schema CHECK 扩展 | 无风险。纯追加值，遵循"全新 schema"规则 |
| timeout 包装改变异常类型 | 低风险。`compaction_operation.py` 的 `except Exception` 兜底仍有效；上层现在收到 `LLMCompactionProposalError` 而非 `TimeoutError`，分类更一致 |
| range endpoint 从截断变拒绝 | 低风险。原 `IndexError` 在零 ref 时已不可控；现在统一为 `LLMCompactionProposalError` |
| dispatch closeout 行为变更 | 有意改进。从永久挂起变为 terminal closeout，单次 lag 仍走 rebuild retry |
| stable block 排序变更 | 有意改进。facts 优先于 subjects 符合 P12.6 目标 |
| accept barrier 新增 payload read | 低风险。`payload_ref is None` 短路，不影响无 payload 路径 |

## Validation Commands & Results

```bash
# 受影响测试
source .venv/bin/activate && python -m pytest \
  tests/host/test_memory_projection.py \
  tests/host/test_llm_compaction.py \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_compaction_contract.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_toolruntime_accept_barrier.py \
  --tb=short -q
# Result: 220 passed in 4.77s

# 全量验证测试
source .venv/bin/activate && python -m pytest \
  tests/host/test_compaction_operation.py \
  tests/host/test_memory_projection.py \
  tests/host/test_llm_compaction.py \
  tests/host/test_compaction_contract.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_compact_material.py \
  tests/service/test_host_assembly.py \
  tests/host/test_compact_artifact_store.py \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/runtime/test_config_loader.py \
  --tb=short -q
# Result: 315 passed in 4.84s

# pyright
source .venv/bin/activate && python -m pyright dayu/ tests/
# Result: 0 errors, 0 warnings, 0 informations

# 空白字符检查
git diff --check HEAD -- '*.py'
# Result: 无问题
```

## 结论

从 re-review 视角，A1-A8 全部正确修复，测试覆盖充分，无阻断回归。修复 artifact 已就绪，可进入 accepted PR review commit 流程。

## Stop Status

Re-review artifact 已写入。未执行 commit、push、PR 状态变更或 merge。
