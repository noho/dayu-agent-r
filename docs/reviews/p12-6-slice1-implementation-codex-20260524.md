## P12.6 Implementation Completion Report

### 摘要
- Slice 1 的动机成立：旧 compaction request 仍把 EventLog refs、accepted evidence envelope metadata 与 raw context item 混在 LLM-facing request 内，违背 `docs/host/design.md` §24 / §25 的 material pack 输入边界。
- 本轮未实施源码修改，因为当前授权源文件不足以完成“删除旧 `CompactionRequest` 字段且不保留兼容路径”的目标。
- 触发停止条件：完成 Slice 1 需要修改授权范围外的 Host 源文件，或者在 `CompactionRequest` 上保留旧字段兼容属性；二者均被本轮指令禁止。

### 已完成切片
- Slice 1: not done；已完成 scope audit，并在实施前停止。

### 修改文件
- `docs/reviews/p12-6-slice1-implementation-codex-20260524.md`

### 契约 / Schema / 状态机变更
- 无。

### 新增或更新测试
- 无。

### 验证
- `pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`: not run；未修改源码，且已触发停止条件。
- `python -m pyright dayu/host/compaction.py dayu/host/context_events.py dayu/host/compact_artifact.py tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py`: not run；未修改源码，且已触发停止条件。
- `git diff --check`: pass。

### README 同步
- `dayu/host/README.md`: not needed because no Host source behavior or stable contract was changed.
- `tests/README.md`: not needed because no test layout, command, or convention was changed.
- other README: not needed because no code, CLI, config, prompt asset, or architecture boundary changed.

### Plan Requirements Checklist
- deterministic segment selection: not done；Slice 2 scope。
- one-to-one material pack sections: not done；blocked by Slice 1 source scope.
- raw evidence path: not done；Slice 3 scope。
- snapshot cursor validation: not done；Slice 2 scope。
- reactive multi-pass single operation: not done；later slice scope。
- V1 consolidation owner: not done；later slice scope。
- bounded evidence / episode working set: not done；later slice scope。
- no ledger dump / result_preview / Host provenance semantic input: not done；blocked by source scope.

### 剩余风险
- `dayu/host/llm_compaction.py` still imports and renders old request fields such as `current_message_summary`, `input_event_refs`, `accepted_evidence_envelopes`, and `compact_raw_context_items`.
- `dayu/host/context_governance.py` still validates candidates against old request fields such as `current_message_summary` and `input_event_refs`.
- `dayu/host/dispatch.py` and `dayu/host/engine_ingest.py` still construct `CompactionRequest` with old fields.
- `dayu/host/compaction_evidence.py` still produces `accepted_evidence_envelopes` and `compact_raw_context_items`.
- Removing old `CompactionRequest` fields only inside `dayu/host/compaction.py` would break these modules and the required tests; keeping derived old-named properties would be a compatibility path, which is explicitly forbidden.
- `docs/host/implementation-control.md` was already modified before this turn and was intentionally not touched.

### 触发的停止条件
- 需要修改允许列表外的 Host 源文件：`dayu/host/llm_compaction.py`, `dayu/host/context_governance.py`, `dayu/host/dispatch.py`, `dayu/host/engine_ingest.py`, `dayu/host/compaction_evidence.py`。
- 若不修改这些文件，只能通过 deprecated alias / compat wrapper / old-field derived property 保持运行；本轮指令禁止该路径。
