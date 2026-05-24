# P12.6 Plan Review — MiMo

## Gate

Handoff implementation-ready plan review. Verify plan is code-generation-ready: slices small enough, allowed files clear, tests tied to boundaries, no missing contract decisions, no public API drift, all accepted design findings converted to mandatory implementation requirements.

## Reviewed Artifacts

- `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md`
- `docs/host/implementation-control.md` current status & Phase 12.6
- `docs/host/design.md` §1, §24, §25
- `docs/reviews/p12-6-design-review-controller-adjudication-20260524.md`
- `docs/reviews/p12-6-design-rereview-mimo-20260524.md`
- `docs/reviews/p12-6-design-rereview-ds-20260524.md`
- Current source: `dayu/host/compaction.py`, `dayu/host/llm_compaction.py`, `dayu/host/compaction_evidence.py`, `dayu/host/dispatch.py`, `dayu/host/engine_ingest.py`

## Assumptions Tested

1. Plan correctly identifies current code as EventLog range dump starting from `start_event_sequence=1`.
2. Plan's `CompactionRequest` shape change is compatible with existing module boundaries.
3. All 4 controller-deferred items are addressed.
4. All 7 accepted findings are converted to mandatory implementation requirements.
5. Slice boundaries do not cross Engine / Fins / Service / UI.
6. New types are fully typed, no `Any` / `object` / extra payload.
7. Tests are tied to specific behavioral boundaries, not happy-path-only.

## Controller-Deferred Items Verification

### Deferred Item 1: CompactionRequest shape decision

**Plan §6.1**: Explicitly chooses material-pack-oriented contract. New typed dataclasses: `CompactMaterialSection`, `CompactMaterialBlockKind`, `CompactMaterialBlock`, `CompactEvidenceBlock`, `CurrentInputAnchor`, `CompactMaterialPack`, `CompactSegmentSelection`. Old fields (`input_event_refs`, `accepted_evidence_envelopes`, `compact_raw_context_items`, `CurrentMessageSummary`) deleted or demoted to internal migration objects.

**Verdict**: Addressed. Decision is clear and specific.

### Deferred Item 2: Deterministic algorithm for current input anchor short text / digest

**Plan §6.3 / Slice 2**: If display text ≤ `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS`, anchor text = full normalized text; otherwise bounded prefix + truncated marker. Full digest enters internal mapping only.

**Verdict**: Addressed. Rule is deterministic and testable.

### Deferred Item 3: V1 relevance strategy for bounded evidence-backed fact working set

**Plan §6.8**: Sorting priority: pinned subject match → current goal keyword overlap → recent user reference → newer extraction event sequence → policy top-K. Snapshot selection uses policy bounded working set; durable historical projection can save more.

**Verdict**: Addressed. Strategy is Host-neutral and does not require business-domain knowledge.

### Deferred Item 4: Edge handling for single evidence block exceeding compactor budget

**Plan §6.3 / Slice 3**: Within same canonical evidence provenance, split into `E1.1` / `E1.2` etc. using deterministic chunk size from module-level constant and policy budget derivation. Internal mapping preserves chunk ordinal.

**Verdict**: Addressed. Chunking is deterministic and preserves provenance.

## Accepted Findings → Implementation Requirements Verification

| # | Accepted Finding | Plan Location | Status |
|---|---|---|---|
| 1 | Compact segment boundary under-specified | §6.3 proactive/reactive selection rules | Mandatory |
| 2 | Material pack section mapping under-specified | §6.4 one-to-one section mapping + dedupe guard | Mandatory |
| 3 | Accepted evidence raw data path ambiguous | §6.5 fixed read path, envelope = provenance only | Mandatory |
| 4 | Long-session consolidation V1 owner ambiguous | §6.8 memory projection policy + bounded selection | Mandatory |
| 5 | Reactive multi-pass durable submission ambiguous | §6.7 single operation, single merged commit | Mandatory |
| 6 | Memory snapshot cursor handling missing | §6.6 cursor validation, catch-up/rebuild, fail closed | Mandatory |
| 7 | Episode summary bounded rendering vague | §6.8 segment-generated + policy-bounded recent | Mandatory |

**Verdict**: All 7 accepted findings are converted to explicit, mandatory implementation requirements with specific implementation rules.

## Findings

### F1-未修复-中-Slice 间依赖链未声明，且 Slice 1 对现有测试的破坏范围未显式覆盖

- **位置**: §8 实施切片, Slice 1 允许修改文件列表
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: Slice 1 修改 `CompactionRequest` dataclass 字段（删除 `input_event_refs`、`accepted_evidence_envelopes`、`compact_raw_context_items`，新增 `material_pack` / `segment_selection`），列出 4 个新测试。"受影响文件与模块"列出 12 个现有测试文件。
- **反例/失败场景**: 当前代码中 `CompactionRequest` 被 96 处引用，分布在 10 个测试文件中。Slice 1 修改 dataclass 后，所有使用旧字段名的测试将立即 import 失败。若 implementation agent 只按 Slice 1 的 4 个新测试执行，其余 10 个测试文件全部 broken，后续 slice 无法运行验证。
- **为什么有问题**: plan 的"删除旧 old-key validator 分支中仅服务兼容的字段接受逻辑；测试改为 fail closed"暗示测试需要同步更新，但未明确列出哪些现有测试文件在 Slice 1 需要同步重写。implementation agent 可能只改 source 不改 test，导致 test suite 全面红灯。
- **直接证据**:
  - `dayu/host/compaction.py:290-294`: `input_event_refs`, `accepted_evidence_envelopes`, `compact_raw_context_items` 是当前 `CompactionRequest` 字段。
  - 96 处引用分布在 `test_compaction_contract.py`(13), `test_llm_compaction.py`(13), `test_compaction_operation.py`(20), `test_dispatch_scheduler.py`(7), `test_engine_ingest_mapping.py`(8), `fake_compaction.py`(21), `test_compact_artifact_store.py`(10), `test_context_compact_events.py`(2), `test_memory_projection.py`(1), `test_run_input_builder.py`(1)。
- **影响**: implementation agent 在 Slice 1 结束时无法运行受影响测试验证正确性；后续 slice 的测试基线不存在。
- **建议改法和验证点**: Slice 1 的"允许修改文件"列表应显式包含所有引用 `CompactionRequest` 旧字段的测试文件（至少 `test_compaction_contract.py`、`test_llm_compaction.py`、`test_compaction_operation.py`、`fake_compaction.py`、`test_compact_artifact_store.py`、`test_context_compact_events.py`、`test_dispatch_scheduler.py`、`test_engine_ingest_mapping.py`）。或者在 Slice 1 增加说明：旧字段先保留为 deprecated internal alias，Slice 2-5 逐步迁移后在 Slice 7 最终清理。验证点：Slice 1 结束后 `pytest tests/host/test_compaction_contract.py` 必须 PASS。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### F2-未修复-低-Slice 间依赖顺序未显式声明

- **位置**: §8 实施切片顺序
- **问题类型**: 最佳实践偏离
- **当前写法**: 7 个 slice 按编号顺序列出，但未显式声明依赖关系。
- **反例/失败场景**: Slice 4 (LLM prompt rendering) 依赖 Slice 2 的 `CompactMaterialPack` 类型和 Slice 1 的新 `CompactionRequest` shape。Slice 5 (Context Governance wiring) 依赖 Slices 2-4。若 implementation agent 并行执行或跳序，将产生类型缺失。
- **为什么有问题**: 虽然按编号顺序执行是隐含的合理假设，但 plan 应为 implementation agent 明确声明，避免歧义。
- **直接证据**: Slice 4 修改 `llm_compaction.py` 的 `_compaction_request_prompt_block` 渲染 material pack sections，但 `CompactMaterialPack` 类型在 Slice 2 才定义。
- **影响**: 低。按编号顺序执行即可避免。但显式声明更安全。
- **建议改法和验证点**: 在 §8 开头或每个 slice 开头增加依赖声明，例如 "Slice N depends on: Slice X types, Slice Y builder"。验证点：无。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Boundary Integrity Check

### Public API Drift

Plan §5 明确列出禁止修改的 public surface：`Host` public method shape、`OpenHostOptions`、`SubmitFollowupRequest`、`open_host(options)`、Engine public contracts、ConfigLoader / ScenePrepare、Fins storage / tools。所有新增类型在 `dayu/host/` 内部，不进入 public API。Slice 停止条件均包含 "需要修改 Host public API" 检查。

**Verdict**: Clean.

### Engine Dependency

Plan 不修改 Engine Agent loop、Runner provider contract、Engine context overflow event contract。`LLMContextCompactor` 依赖 Engine `run_agent_and_wait` 是既有依赖方向（Host → Engine），不引入反向依赖。Engine 不理解 material pack、memory snapshot 或 Host provenance。

**Verdict**: Clean.

### Fins / Tool-Provider Leakage

Plan 不修改 Fins、财报工具实现、财报文档仓储。Tool provider 只产生 `TOOL_RESULT_ACCEPTED`；fact extraction 是 Host-governed compactor 工作。Material pack 从 canonical facts 读取 raw evidence，不从 Fins storage 读取。

**Verdict**: Clean.

### Extra Payload / Any / Object / Lazy Seam

Plan §4 明确禁止 `Any`、`object`、无类型参数、无类型返回值和裸容器。§3.2 不做列表禁止 extra payload escape hatch。新增类型均使用 frozen dataclass with slots and strict typing。

**Verdict**: Clean.

### Overdesigned Retention

Plan §6.8 明确 V1 consolidation 不新增 retention-intent schema，不要求 compactor 输出 `memory_retention_candidate`。Owner 固定为 memory projection policy 和 bounded selection。

**Verdict**: Clean.

### Host Governance Boundaries

Context Governance 是 orchestrator，不直接写 memory snapshot。Compactor 是 Host-owned typed port。Memory projection 只消费 canonical facts。`evidence_backed_facts` 只来自 accepted evidence refs。`final_answer` 不能升级为 `evidence_backed_fact`。

**Verdict**: Clean.

## Open Questions

无阻塞 open questions。

## Residual Risks

1. **大 session rebuild performance**: Plan 承认本 phase 只要求语义正确、bounded、可测试，不把性能优化作为 blocker。后续需要 production hardening。**建议追踪**: implementation-control.md 追踪区或独立 issue。
2. **Prompt-local label 到 canonical provenance mapping 扩大 Host internal artifact / diagnostic 面**: Review 必须确认未把 raw prompt 或敏感 provider payload 写入 EventLog。**建议追踪**: Slice 4 review gate。
3. **V1 relevance strategy 使用 Host-neutral text overlap / recency / subject refs**: 不能理解财报业务语义；后续真实财报工具需提供更高质量 retrieval。**建议追踪**: Fins / tool provider work unit。
4. **Reactive multi-pass 消耗有限 LLM proposal budget**: 预算耗尽 fail closed 是设计选择，不应被实现改成无限 retry。**建议追踪**: Slice 5 review gate。

## Conclusion

**PASS**

Plan is handoff-ready and code-generation-ready. All 4 controller-deferred items are addressed with specific implementation decisions. All 7 accepted design findings are converted to mandatory implementation requirements. Architecture boundaries are maintained: no public API drift, no Engine dependency, no Fins leakage, no extra payload, no overdesigned retention. Slices are appropriately scoped with clear allowed-files lists, test assertions, verification commands, and stop conditions.

One medium-severity finding (F1): Slice 1's `CompactionRequest` shape change will break 96 references across 10 test files, but the plan does not explicitly list which existing test files need concurrent update in Slice 1. Recommend adding affected test files to Slice 1's allowed-modification list or clarifying the migration strategy. One low-severity finding (F2): slice dependency ordering should be explicitly declared for implementation agent clarity.

No blockers. Plan can proceed to implementation after addressing F1.
