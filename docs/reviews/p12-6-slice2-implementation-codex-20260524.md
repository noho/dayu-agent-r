# P12.6 Slice 2 Implementation Artifact

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 2 deterministic Segment Selection / Material Pack Builder
- Role: AgentCodex implementation specialist
- Approved plan: `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md`
- Design source: `docs/host/design.md` §24 / §25
- Control doc: `docs/host/implementation-control.md` read-only

## 动机判断

动机成立，且严重性没有被高估。设计真源要求 compactor input 不再从 Session 起点重放 EventLog ledger，而是从 ordinary Run input material list 或 frozen overflow material list 中确定性选择 compact segment。若 RunInputBuilder 与 compactor 各自维护 material 去重和保护规则，current input、recent raw turns、already represented 历史内容和 stable memory 可能重复进入 LLM-facing compact input，导致 proactive compaction 反而扩大输入并污染 provenance 语义。本 slice 直接修复 material selection / pack build 的同源与确定性问题。

## Scope / Non-goals

- 范围内：`dayu.host` 内部 typed view、deterministic selection、material pack builder、current input anchor 截断、duplicate section owner guard、snapshot cursor validation entrypoint、focused tests、README 稳定说明。
- 范围外：Engine、Service、Fins、Host public API、dispatch / engine-ingest 接线、raw evidence descriptor reader、LLM schema / parser hardening、reactive multi-pass durable wiring。

## 改动文件

- `dayu/host/compact_material.py`
- `dayu/host/compaction.py`
- `dayu/host/run_input.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_run_input_builder.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/p12-6-slice2-implementation-codex-20260524.md`

## 实现摘要

- 新增 `RunInputMaterialBlock` internal typed view 与 `run_input_material_block(...)`，作为 RunInputBuilder 和 compact builder 共享的 ordinary input material list source。
- `RunInputBuilder` 新增 internal `build_material_blocks(...)`，并提供 `build_run_input_material_blocks(...)`，保持 `AgentRunRequest` public shape 不变。
- 实现 `select_compact_segment(...)`：按 `(event_sequence, event_sub_index, block_kind_order, stable_block_id)` 排序，输出 selected block ids、protected exclusions、excluded reason codes、trigger、input cursor、memory snapshot cursor、policy digest 和 deterministic digest。
- Proactive selection 排除 current input anchor、protected recent raw floor、stable input 和 already represented blocks；reactive selection 只消费传入的 frozen overflow material list。
- 实现 `build_compact_material_pack(...)`：从 selected segment、memory snapshot / inline delta repair view、selected history / evidence material 和 current input 构造 stable / history / evidence / current anchor sections。
- current input anchor 使用 normalized text；超过 `CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS` 时只暴露 bounded prefix + truncation marker，完整 digest 只保留在 internal provenance mapping。
- Builder 对同一 canonical source ref set + content digest 进入多个 LLM-facing section 抛 `DuplicateMaterialSectionOwnerError`；同一 current input payload 不再重复进入 history raw turn。
- 实现 `check_compact_memory_snapshot_cursor(...)`：ready snapshot 直接返回，policy 阈值内可接受 inline delta repair view，缺失 / 损坏 / 超阈值 lag 抛 `CompactMemorySnapshotRepairRequired`，并显式 `requests_run_recovery=False`。
- `CompactSegmentSelection` 增加 typed `excluded_reason_codes`，便于 tests / trace / audit 解释 deterministic exclusion。

## 测试结果

- `source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q`
  - 结果：92 passed
- `source .venv/bin/activate && python -m pyright dayu/host/compact_material.py dayu/host/run_input.py dayu/host/memory.py dayu/host/memory_repair.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：passed

## README 决策

- 已更新 `dayu/host/README.md`：补充当前已实现的 compact material 同源 view、deterministic segment selection、protected exclusion 与 material pack builder 稳定语义。
- 已更新 `tests/README.md`：补充 `test_compact_material.py` 的测试职责与 focused command。

## 风险 / 未覆盖项

- 本 slice 尚未把 dispatch / engine-ingest proactive / reactive production path 改为调用新的 `select_compact_segment(...)` 与 `build_compact_material_pack(...)`；该接线属于后续 Slice 5。
- Raw evidence descriptor digest 校验、large evidence chunking 与 `PromptLocalEvidenceMap` hardening 尚未完成；按计划属于 Slice 3。
- LLM JSON schema / parser / accept barrier 对新 labels 的完整收紧尚未完成；按计划属于 Slice 4。
- Reactive multi-pass single-operation durable semantics 尚未完成；按计划属于 Slice 5。

## Completion

Slice 2 implementation complete. 未提交 commit，未 push，未修改 `docs/host/implementation-control.md`。
