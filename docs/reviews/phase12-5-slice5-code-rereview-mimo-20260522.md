# Phase 12.5 Slice 5 Re-Review: Memory Projection Materialization Repair

- Review Agent: MiMo
- Date: 2026-05-22
- 初审: `docs/reviews/phase12-5-slice5-code-review-mimo-20260522.md`
- Repair 范围: schema CHECK、validation 降级逻辑、typed constructor 验证、budget 测试

## 逐项验证

### MiMo F1 [CRITICAL] Schema diagnostic reason CHECK — FIXED

**验证**: `schema.py:789-799` 已将 `'missing_fact_summary_fallback'` 替换为 `'evidence_backed_fact_candidate_invalid'`。

新测试 `test_invalid_fact_candidate_diagnostic_survives_durable_snapshot_write()` 走完整 durable path（`ProjectionRunner` → `write_memory_snapshot` → `_replace_snapshot_diagnostics`），验证 diagnostic 可通过 CHECK 约束并持久化。47 passed 确认无回归。

### MiMo F3 [LOW] Budget 上限测试 — FIXED

**验证**: 新测试 `test_evidence_backed_fact_budget_keeps_latest_facts_and_records_diagnostic()` 使用 `_small_fact_budget_policy()`（`max_evidence_backed_facts=2`），提交 3 个 fact candidates（分属 3 个 compact events），断言：

- `snapshot.evidence_backed_facts` 只保留最新 2 条（`"kept fact one"`, `"kept fact two"`）
- 最旧的 `"oldest fact"` 被丢弃
- 存在 `BUDGET_LIMIT_REACHED` diagnostic，message 为 `"evidence-backed facts limited by memory policy"`

### DS Finding 1 non-fact validation error masking — FIXED

**验证**: `memory.py:1396-1398` — 当清除 fact candidates 后 payload 仍不合法时，`raise non_fact_exc from exc` 直接抛出非 fact 字段的原始错误。

测试 `test_fact_candidate_error_does_not_mask_non_fact_candidate_error()` 构造同时包含非法 evidence ref（fact 层面）和超长 minimum preserve text（非 fact 层面）的 payload，断言 `pytest.raises(ValueError, match="minimum preserve text exceeds maximum length")`。

### DS Finding 2 typed constructor validation — FIXED

**验证**: `memory.py:1458-1475` — `_evidence_backed_facts_from_compacted_event()` 将原始 candidate JSON 传入 `EvidenceBackedFactCandidate(...)` typed constructor，由 `compaction.py` 的 `__post_init__` 执行共享 bounds 校验（claim_text ≤ 2000 字符、evidence_refs ≤ 16、attributes JSON ≤ 4096 字符）。`_minimum_preserve_items_from_compacted_event()` 同理使用 `MinimumPreserveItemCandidate`（text ≤ 1200、label ≤ 120、source_refs ≤ 16）。

测试 `test_overlong_fact_candidate_records_diagnostic_without_fact()` 验证超长 claim_text 触发 `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` diagnostic 而非进入 stable facts。

### DS Finding 3 extra SQL query — DEFERRED

controller 决策：deferred，不阻塞本 slice。

## 新引入变更审查

repair 引入的变更无新 blocker：

1. `raise non_fact_exc from exc` — 正确保留异常链，不吞 error。
2. typed constructor 注入 — raw JSON 必须先通过 `EvidenceBackedFactCandidate` / `MinimumPreserveItemCandidate` 的 bounds 校验，才能进入 `EvidenceBackedFactView` / `ConversationContinuityItem`。共享常量在 `compaction.py`，memory 模块 import 使用。
3. `_small_fact_budget_policy()` — 测试 helper，`max_evidence_backed_facts=2`，仅用于 budget 测试。

## 结论

**PASS**。MiMo F1、F3，DS Finding 1、2 全部修复。无新 blocker。DS Finding 3 按 controller 决策 deferred。
