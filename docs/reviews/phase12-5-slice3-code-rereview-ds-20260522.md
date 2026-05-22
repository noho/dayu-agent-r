# Phase 12.5 Slice 3 Re-Review: LOW-1 Repair + MiMo F2 Coverage

## 元信息

- **Review 类型**：定向 re-review（DeepReview），不修改生产或测试代码
- **基线 Review**：docs/reviews/phase12-5-slice3-code-review-ds-20260522.md
- **修复范围**：LOW-1（`_summary_pretends_evidence_backed_fact` 语义精度）+ MiMo F2（旧 `proposed_verified_fact_refs` key reject 专项测试）
- **审查日期**：2026-05-22

## Re-Review 结论

**PASS** — 三项修复全部正确，无剩余阻塞发现。

---

## 修复验证

### R1: `_summary_pretends_evidence_backed_fact` 语义收窄 ✓

- **文件**：`dayu/host/context_governance.py:199`
- **修复前**：
  ```python
  allowed_fact_refs = set(request.accepted_evidence_refs).union(
      set(request.evidence_backed_fact_refs)
  )
  ```
- **修复后**：
  ```python
  allowed_fact_refs = set(request.evidence_backed_fact_refs)
  ```
- **验证**：`allowed_fact_refs` 仅包含 `evidence_backed_fact_refs`（已有 fact refs），不再包含 `accepted_evidence_refs`（evidence 信封 ids）。summary 的 `confirmed_fact_refs` 现在只能引用已有 stable fact refs，不能引用 evidence 信封 id。
- **正向路径不受影响**：fake compactor 将 `confirmed_fact_refs` 设为 `request.evidence_backed_fact_refs`（均为 `("fact-existing-1",)` 形式），`issubset(allowed_fact_refs)` 仍然通过。

### R2: `confirmed_fact_refs` 引用 evidence id 的拒绝测试 ✓

- **文件**：`tests/host/test_compaction_contract.py:269`
- **测试**：`test_quality_rejects_summary_confirmed_fact_ref_to_accepted_evidence`
- **场景**：设置 `confirmed_fact_refs=("evidence:accepted-1",)`，即把 evidence 信封 id 写入 summary 的 confirmed fact refs
- **断言**：`CompactQualityIssue.SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT in result.rejection_reasons`
- **验证**：evidence id 无法通过 `allowed_fact_refs = set(request.evidence_backed_fact_refs)` 的子集检查（`"evidence:accepted-1"` 不在 `{"fact-existing-1"}` 中），正确触发拒绝。

### R3: 旧 `proposed_verified_fact_refs` key 的 JSON validator 拒绝测试 ✓

- **文件**：`tests/host/test_context_compact_events.py:169`
- **测试**：`test_compacted_payload_rejects_old_summary_proposed_verified_fact_refs`
- **场景**：在 `episode_summary_candidate` JSON payload 中注入旧 key `proposed_verified_fact_refs`
- **断言**：`pytest.raises(ValueError, match="old proposed verified fact refs")`
- **验证**：`context_events.py:335-336` 的 `_FIELD_OLD_PROPOSED_VERIFIED_FACT_REFS` 检查正确触发，旧 key fail-closed。

### MiMo F2 覆盖确认

MiMo F2（来自 plan §4.7 diagnostics 要求 "FACT_CANDIDATE_FORBIDDEN_SOURCE" 相关语义）在 accept barrier 层面的覆盖：

| 拒绝路径 | 测试 | Quality Issue |
|----------|------|---------------|
| Fact candidate 引用非 evidence ref | `test_quality_rejects_fact_candidate_referencing_non_evidence_ref` | `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` |
| Summary 引用 evidence id 当 fact ref | `test_quality_rejects_summary_confirmed_fact_ref_to_accepted_evidence` | `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` |
| 旧 `proposed_verified_fact_refs` key | `test_compacted_payload_rejects_old_summary_proposed_verified_fact_refs` | ValueError |

三个覆盖路径互相独立，分别覆盖：(a) LLM 直接伪造 evidence refs，(b) LLM 把 evidence id 错当 fact ref 填入 summary，(c) 旧 JSON 格式的残留 key。

---

## Scope 与 Regressions

| 检查项 | 结果 |
|--------|------|
| 修改触及超出 Slice 3 范围的文件 | 无（仅触及 context_governance.py + 2 测试文件） |
| 引入新 pyright 错误 | 无 |
| 破坏已有测试 | 无（52/52 通过） |
| 修改 FakeContextCompactor 行为 | 无 |
| 修改 context_events.py / compact_artifact.py 生产代码 | 无 |
| 修改 compaction.py 新 dataclass | 无 |

---

## 验证结果

```
=== pytest ===
tests/host/test_compaction_contract.py .............. (24 tests)
tests/host/test_context_compact_events.py .......... (24 tests)
tests/host/test_compaction_operation.py .... (4 tests)
52 passed in 0.63s
```

---

## Residual Risks

原审查中的 LOW-2（v1 artifact 读路径守卫）和 LOW-3（helper 重复）仍然存在，possession 不变：

| Risk | Owner | Slice |
|------|-------|-------|
| 旧 v1 compact artifact 无版本守卫 | Slice 5 | Memory Projection Materialization |
| `_fact_candidate_list_json` 三处重复 | Followup | 后续 polish |

---

## 审查签署

- **审查者**：DeepReview Agent (Claude)
- **结论**：**PASS** — LOW-1 已正确修复，MiMo F2 已覆盖，无新增 scope violation 或 regression。Slice 3 可推进。
