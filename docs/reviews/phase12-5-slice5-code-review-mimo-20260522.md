# Phase 12.5 Slice 5 Code Review: Memory Projection Materialization

- Review Agent: MiMo
- Date: 2026-05-22
- Baseline: `e2a7332` gateflow: accept phase 12.5 slice 4
- Scope: Slice 5 — Memory Projection Materialization
- Plan: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md` §7 Slice 5

## 变更文件

| 文件 | 变更类型 |
|------|----------|
| `dayu/host/memory.py` | EvidenceBackedFactView 重写、CONTEXT_COMPACTED 物化、minimum preserve、budget、fail-closed |
| `dayu/host/durable/memory.py` | item kind CHECK、durable JSON codec、old item kind 校验 |
| `dayu/host/durable/schema.py` | `minimum_preserve_item` 加入 item_kind CHECK |
| `tests/host/test_memory_projection.py` | Slice 5 全量测试 |
| `dayu/host/README.md` | Memory Projection 描述同步 |

## Findings

### F1 [CRITICAL] Schema diagnostic reason CHECK 缺少 `evidence_backed_fact_candidate_invalid`

**文件**: `dayu/host/durable/schema.py:789-799`

**证据**: `MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` 的值为 `"evidence_backed_fact_candidate_invalid"`（`memory.py:197-199`），但 `_HOST_MEMORY_DIAGNOSTICS_DDL` 的 `reason CHECK` 约束仍为旧集合：

```sql
reason IN (
  'missing_fact_summary_fallback',
  'inline_delta_repair_included',
  'snapshot_missing',
  'snapshot_damaged',
  'unsupported_event_type',
  'snapshot_lag_over_threshold',
  'budget_limit_reached',
  'empty_event_log_snapshot'
)
```

当 `CONTEXT_COMPACTED` 携带无效 fact candidates 时，`_validate_compacted_payload_for_memory_projection()` 会构造 `reason=EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` 的 `MemoryDiagnostic`。该 diagnostic 经 `_replace_snapshot_diagnostics()` 写入 `TABLE_HOST_MEMORY_DIAGNOSTICS`，此时 SQLite CHECK 约束拒绝 `"evidence_backed_fact_candidate_invalid"`，导致整个 snapshot 写入事务 rollback。

**影响**: 任何含无效 fact candidates 的 `CONTEXT_COMPACTED` 事件都会导致 durable snapshot 写入失败，memory projection 卡死。

**修复建议**: 将 `_HOST_MEMORY_DIAGNOSTICS_DDL` 的 reason CHECK 更新为：

```sql
reason IN (
  'evidence_backed_fact_candidate_invalid',
  'inline_delta_repair_included',
  'snapshot_missing',
  'snapshot_damaged',
  'unsupported_event_type',
  'snapshot_lag_over_threshold',
  'budget_limit_reached',
  'empty_event_log_snapshot'
)
```

同时移除旧的 `'missing_fact_summary_fallback'`（代码中已无写入路径）。schema 按全新设计处理，不做兼容读取。

---

### F2 [LOW] Schema reason CHECK 残留 `'missing_fact_summary_fallback'`

**文件**: `dayu/host/durable/schema.py:791`

**证据**: `MemoryDiagnosticReason` 枚举已移除 `MISSING_FACT_SUMMARY_FALLBACK`，改为 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID`。schema CHECK 中 `'missing_fact_summary_fallback'` 是孤立条目，无代码写入路径。

**影响**: 不影响功能（CHECK 只约束写入），但增加认知负担，且与代码枚举不一致。

**修复建议**: 随 F1 一并清理。

---

### F3 [INFO] 测试未覆盖 `max_evidence_backed_facts` budget 上限路径

**文件**: `tests/host/test_memory_projection.py`

**证据**: `test_context_compacted_fact_candidates_materialize_evidence_backed_facts()` 测试单个 fact candidate 物化。但 `_limit_evidence_backed_facts()` 的 budget 上限路径（`len(items) > policy.max_evidence_backed_facts` 时保留最新 N 条并生成 `BUDGET_LIMIT_REACHED` diagnostic）无直接测试。

当前 `_policy()` 设置 `max_evidence_backed_facts=16`，测试只提交 1 个 fact candidate，未触达上限。

**影响**: budget 上限逻辑的正确性未被验证（保留策略为 `items[-max:]` 即保留最新，diagnostic 指向被丢弃的最旧 item）。

**修复建议**: 补充测试：提交超过 `max_evidence_backed_facts` 个 fact candidates，验证保留最新 N 条且生成 budget diagnostic。

---

## 审查点逐项结论

### 1. TOOL_RESULT_ACCEPTED 是否不直接 materialize EvidenceBackedFactView

**PASS**。`memory.py:1184-1188`：`TOOL_RESULT_ACCEPTED` 分支为 `pass`，不修改 `evidence_backed_facts`。测试 `test_tool_result_accepted_does_not_project_evidence_backed_fact()`、`test_missing_tool_fact_summary_does_not_use_neutral_fallback()` 等覆盖了多种 payload 变体。

### 2. CONTEXT_COMPACTED 是否从 accepted candidates materialize facts

**PASS**。`memory.py:1200-1233`：valid payload 时 `_evidence_backed_facts_from_compacted_event()` 物化 facts。`claim_text` 来自 candidate JSON，`evidence_refs` 来自 candidate JSON，`evidence_kind` 来自 candidate JSON，`attributes` 来自 candidate JSON，`provenance` 来自 `CONTEXT_COMPACTED` event。测试 `test_context_compacted_fact_candidates_materialize_evidence_backed_facts()` 覆盖。

### 3. provenance 是否来自 accepted CONTEXT_COMPACTED event

**PASS**。`memory.py:1431-1443`：`provenance.event_id = event.event_id`，`provenance.event_sequence = event.event_sequence`。`candidate_id` 仅存入 `EvidenceBackedFactView.candidate_id` 字段，不进入 provenance。测试 `test_context_compacted_fact_candidates_materialize_evidence_backed_facts()` 断言 `fact.provenance.event_id == "event-compact-fact"` 且 `fact.candidate_id != fact.provenance.event_id`。

### 4. minimum_preserve_item_candidates 是否只 materialize continuity item

**PASS**。`memory.py:1485-1532`：`_minimum_preserve_items_from_compacted_event()` 返回 `ConversationContinuityItem(item_kind=MINIMUM_PRESERVE_ITEM)`，不修改 `evidence_backed_facts`。durable item_kind 为 `"minimum_preserve_item"`（`schema.py:747` CHECK 已包含）。测试 `test_minimum_preserve_candidates_create_continuity_items_only()` 断言 `evidence_backed_facts == ()` 且 continuity item 正确。

### 5. old verified_facts snapshot key / verified_fact item kind 是否 fail closed

**PASS**。
- Snapshot JSON: `memory.py:2714-2715` — `if "verified_facts" in mapping: raise ValueError("old verified_facts snapshot key is not supported")`
- Durable item kind: `durable/memory.py:940-972` — `_validate_snapshot_item_kinds()` 检查 `_ITEM_KIND_OLD_VERIFIED_FACT` 并 raise `HostDurableError`
- JSON codec: `memory.py:2920-2921` — `if "fact_summary" in mapping or "evidence_anchor" in mapping: raise ValueError("old evidence-backed fact JSON shape is not supported")`
- 测试: `test_old_snapshot_verified_facts_key_fails_closed()`、`test_old_durable_verified_fact_item_kind_fails_closed()`

### 6. max_evidence_backed_facts budget / diagnostics

**PASS（逻辑正确，但测试覆盖不足）**。`_limit_evidence_backed_facts()` 在超出 budget 时保留最新 N 条（`items[-max:]`）并生成 `BUDGET_LIMIT_REACHED` diagnostic。测试未触达此路径（见 F3）。

### 7. 是否有禁止模式

**PASS**。无 financial source/locator parsing，无 assistant/user/summary 变成 evidence-backed fact，无 fallback fact，无 `Any`/`object`/untyped，无 `getattr`/`hasattr`。

### 8. 测试覆盖

**PASS（F3 除外）**。覆盖了 Slice 5 plan 所有核心测试要求和 S2-D1 deferred finding（`TOOL_RESULT_ACCEPTED` 不直接物化 fact）。

## Residual Risks

1. **F1 schema CHECK 缺失**: 必须在合并前修复，否则含无效 fact candidates 的 compact 会导致 durable 写入失败。
2. **Budget 上限测试缺口（F3）**: 逻辑正确但未验证，建议补充。
3. **后续 slice 依赖**: `run_input.py`、`dispatch.py`、`engine_ingest.py` 中对旧 `VerifiedFactView` / `fact_summary` / `evidence_anchor` 的引用将在 Slice 6 中处理，不在本 slice 范围。

## 结论

Slice 5 实现正确覆盖了 plan §7 的所有核心要求：`TOOL_RESULT_ACCEPTED` 不直接物化 fact，`CONTEXT_COMPACTED` 从 accepted candidates 物化 `EvidenceBackedFactView`，provenance 来自 compact event，minimum preserve 只进入 continuity，old key/kind fail closed。**F1（schema diagnostic reason CHECK 缺失新枚举值）是唯一必须在合并前修复的 blocking finding**。
