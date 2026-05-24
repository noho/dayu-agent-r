## P12.6 Implementation Completion Report

### 摘要
- 完成 Slice 1 Material Pack contract deletion boundary 与 Direct Consumers Migration。
- 删除旧 `CompactionRequest` LLM-facing request carrier 字段，新增 material-pack-oriented request shape。
- 直接生产消费者已迁移到 `material_pack`、`segment_selection`、prompt-local labels 与 internal provenance map。
- 未修改 `docs/host/implementation-control.md`。

### 已完成切片
- Slice 1: Material Pack 契约删除边界与 Direct Consumers Migration。

### 修改文件
- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/compaction_evidence.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/compact_artifact.py`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- listed Slice 1 tests and `tests/host/fake_compaction.py`

### 契约 / Schema / 状态机变更
- `CompactionRequest` now carries `material_pack` and `segment_selection`.
- Added compact material sections, block kinds, current input anchor, prompt-local provenance entries, evidence map view, and segment selection contract.
- LLM prompt renders material pack sections only; Host provenance remains in internal mapping / artifact metadata.
- LLM proposal refs use prompt-local material/evidence labels and are mapped to canonical refs before `CompactionCandidate`.
- Context compacted/artifact paths record mapping/digest refs rather than raw prompt material.

### 新增或更新测试
- Updated contract, LLM compaction, compaction operation, compact artifact, context compact event, memory projection, run input builder tests.
- Updated fake compactor to consume material pack and emit canonical candidates through prompt-local material provenance.

### 验证
- `pytest tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py -q`: pass, 55 passed.
- `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`: pass, 205 passed.
- `python -m pyright ...Slice 1 files...`: pass, 0 errors.
- `rg -n "accepted_evidence_envelopes|compact_raw_context_items|current_message_summary|CurrentMessageSummary|CompactRawContextItem|compact_raw_context|accepted_evidence_refs|preserved_input_event_refs" ...Slice 1 production/prompt files...`: pass, no matches.
- `git diff --check`: pass.

### README 同步
- `dayu/host/README.md`: not needed because Slice 1 changed internal compaction carrier contracts, not stable Host public usage or documented public API.
- `tests/README.md`: not needed because test running commands and test layering did not change.
- other README: not needed because prompt asset schema changed internally without ConfigLoader / ScenePrepare or user-facing configuration entry changes.

### Plan Requirements Checklist
- deterministic segment selection: not done; Slice 1 only adds initial typed `CompactSegmentSelection`, full deterministic selection remains Slice 2 scope.
- one-to-one material pack sections: done for typed material pack construction guard.
- raw evidence path: partially done for Slice 1 initial evidence material collector; digest-checked hardening remains Slice 3 scope.
- snapshot cursor validation: not done; Slice 2 scope.
- reactive multi-pass single operation: not done; Slice 5 scope.
- V1 consolidation owner: not done; Slice 6 scope.
- bounded evidence / episode working set: not done; Slice 6 scope.
- no ledger dump / result_preview / Host provenance semantic input: done for Slice 1 prompt/request boundary.

### 剩余风险
- Slice 1 material construction is intentionally initial; full deterministic selection and already-represented pruning are deferred by plan.
- Evidence material collector still relies on current accepted evidence envelope for canonical mapping; raw evidence path hardening is deferred to Slice 3.
- Existing `dayu/host/run_input.py` still contains historical payload field names outside Slice 1 allowed files; not touched because this slice did not authorize RunInputBuilder migration.

### 触发的停止条件
- 无。
