# Phase 12.5 Slice 3 Re-Review: Repair Verification

## Re-Review Metadata

- **Review Agent**: MiMo
- **Date**: 2026-05-22
- **Initial Review**: `docs/reviews/phase12-5-slice3-code-review-mimo-20260522.md`
- **Scope**: 3 targeted repairs after initial review

## Verdict: PASS

All 3 repair items verified. 52 tests pass, pyright 0 errors. No new blocking findings.

---

## Repair Verification

### Repair 1: DS LOW-1 — `confirmed_fact_refs` 不再允许 accepted evidence refs

- **文件**: `dayu/host/context_governance.py:197`
- **变更**: `allowed_fact_refs = set(request.tool_fact_refs).union(set(request.verified_fact_refs))` → `allowed_fact_refs = set(request.evidence_backed_fact_refs)`
- **验证**: `confirmed_fact_refs` 现在只能引用 `request.evidence_backed_fact_refs`（已存在于 memory 的 stable facts），不能引用 `accepted_evidence_refs`（来自本次 compact input 的 tool evidence）。语义正确：summary 只能确认已有的 stable fact，不能把 raw accepted evidence id 当 confirmed fact。
- **回归风险**: 正常路径中 `confirmed_fact_refs` 由 FakeContextCompactor 从 `request.evidence_backed_fact_refs` 构造，不受影响。✓

### Repair 2: 新增 `confirmed_fact_refs` 引用 accepted evidence 的拒绝测试

- **文件**: `tests/host/test_compaction_contract.py:269-289`
- **测试**: `test_quality_rejects_summary_confirmed_fact_ref_to_accepted_evidence`
- **行为**: `confirmed_fact_refs=("evidence:accepted-1",)` 触发 `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` 拒绝。
- **验证**: accepted evidence id `evidence:accepted-1` 不在 `request.evidence_backed_fact_refs`（请求中为 `("fact-existing-1",)`），因此被拒绝。与 Repair 1 的语义一致。✓

### Repair 3: 旧 `proposed_verified_fact_refs` 拒绝的显式测试（MiMo F2）

- **文件**: `tests/host/test_context_compact_events.py:169-178`
- **测试**: `test_compacted_payload_rejects_old_summary_proposed_verified_fact_refs`
- **行为**: 注入旧 key `proposed_verified_fact_refs` 到 summary，断言 `ValueError` 匹配 `"old proposed verified fact refs"`。
- **验证**: 生产代码 `context_events.py:335` 已有 `_FIELD_OLD_PROPOSED_VERIFIED_FACT_REFS in summary` 检查，测试覆盖了该 fail-closed 路径。✓

---

## Side-Effect Check

- 无新增文件、无新增依赖。
- `_summary_pretends_evidence_backed_fact` 其余逻辑（`proposed_evidence_backed_fact_refs` 非空检查、`preserved_evidence_backed_fact_refs ⊆ request.evidence_backed_fact_refs`）未受影响。
- 测试从 50 增至 52（+2 新测试），无测试删除或修改。
- pyright 0 errors。✓

---

## Residual From Initial Review

- MiMo F1（三模块重复 `_fact_candidate_list_json`）：仍未修复，LOW 风险，计划在 Slice 7 清理。
- 其余 residual risks 不变，见初始 review artifact。
