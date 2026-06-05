# WU-CM-01 Compact Contract Closure Implementation Retry - Codex

## Production

- `dayu/host/compaction.py` 删除旧 compact candidate family、旧 quality result、旧 patch/evidence/minimum preserve 类型与 `ContextCompactorVNext`，`ContextCompactor` 只保留单一 public `compact(request, cancellation_token) -> ConversationCompactOutputVNext`。
- `CompactMaterialPack` 收敛到 vNext material fields：`previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`，`to_json()` / `llm_json()` 不再输出 `stable_input`、`history_input`、`evidence_input`。
- `dayu/host/llm_compaction.py` 删除旧 parser / prompt request / candidate builder path，`LLMContextCompactor.compact()` 只渲染 vNext input 并解析 `ConversationCompactOutputVNext`；旧 schema fail closed。
- `dayu/host/context_governance.py` 改为 vNext-only checker：只暴露 `check_conversation_compact_output_vnext`，按 vNext source section 校验 label。
- `dayu/host/compaction_operation.py` 改为调用 `compactor.compact()`，accepted / rejected / repair exhausted / failed fallback closeout 使用 vNext quality 与 candidate。
- `dayu/host/compact_artifact.py` / `compact_payload.py` 改为 vNext artifact / payload helper，artifact 写入请求接受 `ConversationCompactOutputVNext` 与 `CompactQualityCheckResultVNext`。
- `dayu/host/context_events.py` 保留 vNext event contract builder / validator；旧 compact fields 只作为私有 unsupported-field denylist，用于 fail closed，不作为 public event contract。
- `dayu/host/compaction_evidence.py` 从 vNext `accepted_candidate.evidence_backed_facts` 派生 stable fact refs，不再读取旧 `evidence_backed_fact_candidates` / `preserved_fact_refs`。
- `dayu/host/memory.py` 切断对 `dayu.host.compaction` 旧 public symbols 的依赖，新增 memory-owned projection enum；同时用 memory-local typed parser 保留 legacy memory projection fixture shape，并新增 vNext `accepted_candidate` projection path。
- `dayu/host/run_input.py` 不再从 `compact_payload` 导入旧 payload reader；旧 projection text summary helper 改为本模块私有实现，material section / kind 改为 vNext。
- `dayu/config/prompts/scenes/conversation_compaction*.md` 同步到 vNext schema，避免 production LLM prompt 继续要求旧 candidate fields。

## Tests

- 重写 `test_compaction_contract.py`、`test_llm_compaction.py`、`test_compact_artifact_store.py` 为 vNext-focused tests。
- 更新 `test_compaction_operation.py`、`test_compact_material.py`、`test_memory_projection.py`、`test_run_input_builder.py`、`test_public_compact_smoke.py`、fake compactor 与相关 helper tests 到 `compact()` / vNext material / vNext event payload。
- 条件触发后同步并运行 `test_package_exports.py` 与 `test_public_compact_smoke.py`。

## README

- 更新 `dayu/host/README.md`：Memory projection 说明从旧 `CONTEXT_COMPACTED.evidence_backed_fact_candidates` 改为 vNext `CONTEXT_COMPACTED.accepted_candidate.evidence_backed_facts`。
- 更新 `tests/README.md`：public compact smoke 与 P12.6 测试说明改为 `evidence_material`、vNext fact/reference continuity。
- 检查 `dayu/config/README.md`：该文档只说明 prompt 目录职责，不记录 compactor output schema，无需修改。

## Direct Evidence

- closeout production files 中无旧 compact class / protocol / public method：`CompactionCandidate`、`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`PinnedPatchOperation`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`、`PreservationEvidence`、`CompactQualityIssue`、`CompactQualityCheckResult`、`EvidenceBackedFactCandidate`、`ContextCompactorVNext` 均已从 production closeout contract 移除。
- `rg compact_request_vnext|compact_vnext dayu tests utils` 只剩 `test_compaction_contract.py` 中验证旧 method 缺席的字符串断言。
- `memory.py` / `run_input.py` 不再引用旧 compact candidate symbols；`run_input.py` 仅从 `dayu.host.compaction` 导入 vNext material enum。
- `CompactMaterialPack` JSON / LLM JSON tests 覆盖旧 `stable_input`、`history_input`、`evidence_input` 缺席。
- `LLMContextCompactor.compact()` tests 覆盖 prompt 中包含 vNext material fields，且不包含旧 material fields / `candidate_id`；旧 candidate schema parser fail closed。

## Remaining Old Names

- `dayu/host/context_events.py` 中旧 field name 常量仍存在，但仅用于私有 denylist `_reject_old_compacted_fields`，owner 为 vNext event accept barrier；它们不是 public export、不是 writer/helper contract。
- `dayu/host/memory.py` 保留 `MemoryEvidenceBackedFactKind` 和 legacy memory projection field constants，owner 为 Conversation Memory read model；它们不从 `dayu.host.compaction` 导入，不作为 compact compatibility contract 导出。
- tests 中保留旧 field names仅用于 fail-closed 或 legacy memory projection fixture。

## EvidenceBackedFactCandidate

旧 `EvidenceBackedFactCandidate` 已删除，不做 alias、wrapper 或 re-export。vNext compactor 输出只使用 `EvidenceBackedFactCandidateVNext`。Memory projection 使用本模块自有 `EvidenceBackedFactView` / `MemoryEvidenceBackedFactKind` 表达 read model，并在 vNext payload 下从 `accepted_candidate.evidence_backed_facts` 物化 facts。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_compact_artifact_store.py -q`  
  Result: `87 passed in 0.41s`
- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`  
  Result: `99 passed in 0.64s`
- Conditional public exports / fake smoke: `source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_public_compact_smoke.py -q`  
  Result: `15 passed, 1 skipped in 0.75s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`  
  Result: `0 errors, 0 warnings, 0 informations`

## Residual Risks

- External `ContextCompactor` implementors using `compact_request_vnext()` / `compact_vnext()` will break; this is intentional contract closure and not bridged.
- Memory projection still contains a memory-owned legacy fixture/parser path for existing read-model tests; it is not exported as compact public contract, but later slices should remove or migrate that legacy shape when durable memory schema / full vNext memory prompt assembly is in scope.
- Current stash was not applied or restored.
