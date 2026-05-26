# Code Review

## Scope

- Mode: current changes (uncommitted workspace changes only)
- Branch: feat/phase-12-5-conversation-memory-optimize
- Base: main
- Output file: docs/reviews/phase12-5-slice7-code-review-ds-20260522.md
- Included scope:
  - `dayu/config/README.md`
  - `dayu/host/README.md`
  - `tests/README.md`
  - `tests/host/test_compact_artifact_store.py`
  - `tests/host/test_compaction_contract.py`
  - `tests/host/test_memory_projection.py`
  - `tests/host/test_public_contracts.py`
  - `tests/host/test_resolve_wait_command.py`
  - `tests/host/test_run_input_builder.py`
- Excluded scope:
  - All committed production code changes (Slices 1-6, already reviewed and accepted)
  - `docs/host/design.md` 和 `docs/host/implementation-control.md` 作为 truth source 参考但不属于变更 scope
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 验证清单逐项通过

1. **Accepted evidence envelope**: `dayu/host/evidence.py` 定义了 `AcceptedEvidenceEnvelope` typed contract（evidence_id, producer_event_ref, tool_name, tool_call_id, tool_query, result_ref, source_refs, locator_refs）。`dayu/host/tool_runtime.py:3473` 在 accept path 中构造 envelope 并通过 `accepted_evidence_envelope_to_json_value` 写入 `TOOL_RESULT_ACCEPTED.accepted_evidence_envelope`。`tests/README.md:118` 将 `test_toolruntime_accept_barrier.py` 归入 P12.5 memory semantic smoke，语义正确。

2. **Compaction-gated fact candidates**: `dayu/host/memory.py:1189-1193` 中 `TOOL_RESULT_ACCEPTED` 的处理体为 `pass`（不做 fact 物化）；`dayu/host/memory.py:1205-1219` 中 `CONTEXT_COMPACTED` 的处理体才是 fact 物化入口。`test_memory_projection.py` 新增 `test_compaction_confirmed_facts_do_not_drift_or_create_summary_fact` 验证 summary 引用 facts 时不应改写或自建 fact。`test_resolve_wait_command.py` 重命名为 `test_resolve_wait_committed_tool_result_catches_up_memory_without_fact` 并断言 `evidence_backed_facts == ()`（第 277 行），验证 tool result alone 不产生 stable facts。

3. **CONTEXT_COMPACTED materialization**: `dayu/host/memory.py:1425-1495` `_evidence_backed_facts_from_compacted_event` 从 `CONTEXT_COMPACTED.evidence_backed_fact_candidates` 构造 `EvidenceBackedFactView`，包含 `claim_text`、`evidence_refs`、`evidence_kind`、`extraction_operation_ref`、`provenance`（含 event_id/sequence）。新增测试验证物化事实的 `claim_text`、`evidence_refs` 与 `candidate_id` 一致。

4. **RunInputBuilder post-compaction gross margin follow-up**: `test_run_input_builder.py` 新增 `test_gross_margin_followup_uses_post_compaction_evidence_backed_facts`（第 952-1013 行），通过 `_append_compacted_gross_margin_facts` 写入 TOOL_RESULT_ACCEPTED 与 CONTEXT_COMPACTED（含 Revenue/Gross profit fact candidates），执行 memory catch-up 后，断言渲染出的 message 包含 `claim_text=Revenue was 100.`、`claim_text=Gross profit was 40.`、`evidence_refs=evidence:memory-tool`，且不含旧 raw text。

5. **Minimum preserve continuity**: `test_run_input_builder.py` 新增 `test_minimum_preserve_resolves_second_factor_without_full_long_input`（第 1015-1098 行），构造长输入 compact 后，验证 memory 渲染只包含 `Memory minimum preserve continuity:` block（含 `label=第二个因素`、`text`、`source_refs=event-long-input`），不保留整段长原文。`dayu/host/run_input.py:1819-1850` `_memory_minimum_preserve_message` 按 `MINIMUM_PRESERVE_ITEM` item_kind 过滤并渲染 label/text/source_refs/preserve_reason，注入位置在 recent raw turns 之后、episode summaries 之前（第 1589-1593 行）。

6. **No stable facts from tool result alone**: `dayu/host/memory.py:1189-1193` `TOOL_RESULT_ACCEPTED` 处理体确认为 `pass`；`test_resolve_wait_command.py` 新断言 `evidence_backed_facts == ()` 验证。

### README 准确性逐条对照

- `dayu/config/README.md:87`: "其中 `max_evidence_backed_facts` 限制 stable evidence-backed facts 的数量" — 与 `dayu/host/memory.py:665` 字段定义一致。
- `dayu/host/README.md:239`: `` `evidence_backed_facts` `` — 与 `ConversationMemorySnapshot.evidence_backed_facts` 字段名一致（`dayu/host/memory.py:825`）。
- `dayu/host/README.md:243`: "通过 memory snapshot provider 接线读取" — 与 `run_input.py:1260-1284` `MemorySnapshotProvider` protocol 一致。
- `dayu/host/README.md:245`: "`TOOL_RESULT_ACCEPTED` 只提供 accepted evidence envelope 可用性；stable evidence-backed facts 采用 compaction-gated extraction" — 与 `memory.py:1189-1193` + `memory.py:1205-1219` 路径一致。追加的 "没有 compaction 的短链路追问继续依赖 recent raw turns" 准确。
- `tests/README.md:118`: P12.5 memory semantic smoke 行将每个测试文件映射到其验证语义，与对应测试文件中的实际测试函数覆盖一致。

### Stale Terminology / Old Field 检查

- `dayu/` 生产代码中无 `verified_facts` / `max_verified_facts` / `tool_fact_refs` / `verified_fact_refs` / `accepted_tool_fact_refs_retained` 活跃使用。旧字段名仅存于 fail-closed 常量定义与 rejection guard：
  - `dayu/host/context_events.py:100-104`: `_FIELD_OLD_*` 常量仅用于 `validate_context_compacted_payload:335-336`、`_reject_old_preserved_fact_ref_fields:943-945`、`_validate_quality_check_result:1069-1074` 的明确 rejection。
  - `dayu/host/memory.py:2736-2737`: 旧 `verified_facts` snapshot key 明确抛出 `ValueError`。
- `tests/` 中旧字段名仅存于 fail-closed 验证测试内（`test_old_max_verified_facts_key_fails_fast`、`test_old_snapshot_verified_facts_key_fails_closed`、`test_compacted_payload_rejects_old_summary_proposed_verified_fact_refs`），无残留活跃使用。

### Forbidden Scope 检查

Uncommitted 变更仅涉及 README 同步与测试。无生产代码修改，无 schema 变更，无跨层穿透。

## Open Questions

- `_minimum_preserve_only_snapshot` 辅助函数（`test_run_input_builder.py:1548-1630`）通过先构造 `snapshot_without_digest` 再重建带 digest 的 snapshot 来计算 digest。构造模式与 `memory.py:1268-1310` 一致，无问题。若后续 `ConversationMemorySnapshot` 新增字段，此 helper 需同步更新——这是测试 helper 的常规维护负担，不是 defect。

## Residual Risk

- P12.5 Slice 7 的测试覆盖为 SQLite durable EventLog 上的单元级 smoke。真实 compactor runner（LLM）端到端路径仍需 public-path smoke（如 `test_public_compact_smoke.py`）覆盖。该覆盖不在 Slice 7 scope，但 Slice 6 deferred findings 提及 `no-compaction / post-compaction follow-up 端到端 smoke 仍归 Slice 7`（control doc:1667-1668）。当前 Slice 7 已提供 RunInputBuilder 和 memory projection 层的 post-compaction smoke，但 no-compaction 短链路的端到端 public-path smoke 仍需 `test_public_tool_wiring_smoke.py` 或类似 public smoke 确认。
- Slice 6 deferred finding 中的 `bounded EventLog read session min sequence` 优化仍未在本 slice 处理；当前以 `start_event_sequence=1` 保守读取。

### 结论

PASS. 九文件变更均为文档同步与语义 smoke 测试，无生产代码修改，术语迁移完整，fail-closed guards 到位，pyright clean (0 errors)，221 targeted tests passed。README 与代码一致。两条 residual risks 已记录，不阻塞 Slice 7。
