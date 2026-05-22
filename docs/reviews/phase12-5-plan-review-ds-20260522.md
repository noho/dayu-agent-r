# Phase 12.5 Plan Review — AgentDS Independent Review

## Review Metadata

- **Reviewer**: AgentDS (independent review agent)
- **Date**: 2026-05-22
- **Plan under review**: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- **Controller handoff**: `docs/reviews/phase12-5-plan-handoff-controller-20260522.md`
- **Design truth**: `docs/host/design.md`
- **Control doc**: `docs/host/implementation-control.md`
- **Review lens**: adversarial implementation-ready plan review

## Gate Conclusion

**PASS** — The plan is handoff-ready and code-generation-ready. No blocking findings. Six residual risks are noted below, all with clear owners and destinations.

---

## 1. Evidence Verification Summary

### 1.1 Codebase Claims Verified

The plan's description of current code matches reality. Verified at:

| Claim | Evidence | Verdict |
|-------|----------|---------|
| `VerifiedFactView` exists in `dayu/host/memory.py` | `memory.py:369` | Match |
| `ConversationMemorySnapshot.verified_facts` exists | `memory.py:782` | Match |
| `MemoryProjectionPolicy.max_verified_facts` exists | `memory.py:622` | Match |
| `_verified_fact_from_projection_event()` synthesizes neutral fallback fact when `fact_summary is None` | `memory.py:1329-1354` — calls `_neutral_tool_fact_fallback()` and returns `VerifiedFactView` with `MISSING_FACT_SUMMARY_FALLBACK` diagnostic | Match |
| `CompactionCandidate` lacks `evidence_backed_fact_candidates` / `minimum_preserve_item_candidates` | `compaction.py:644-667` — only has `episode_summary_candidate`, `pinned_state_patch_candidate`, preservation fields | Match |
| `CompactionRequest.verified_fact_refs` exists | `compaction.py:176` | Match |
| `_memory_verified_fact_message()` renders `fact_summary` and `digest_ref`, not `claim_text + evidence_refs` | `run_input.py:1730-1734` | Match |
| `stable:verified_facts` block id exists | `run_input.py:1618` | Match |
| `max_verified_facts` in `execution_profiles.json` (4 profiles) | `execution_profiles.json:26,92,158,224` | Match |
| Durable memory item kind `verified_fact` | `durable/memory.py:77` — `_ITEM_KIND_VERIFIED_FACT = "verified_fact"` | Match |
| `TOOL_RESULT_ACCEPTED` payload currently has no `accepted_evidence_envelope` | `tool_runtime.py:3473-3512` — payload fields are tool identity, outcome, truncation, governance, not evidence envelope | Match |

### 1.2 Design Conformance Verified

| Design Requirement (§24, §25, §18) | Plan Coverage | Verdict |
|-------|-------|---------|
| §24: `evidence_backed_facts` only from accepted tool evidence | §4.6 + §5.5 — projection materializes only from `CONTEXT_COMPACTED` | Conforms |
| §24: minimum contract = `claim_text + evidence_refs` | §4.6 `EvidenceBackedFactView` fields include both | Conforms |
| §24: no neutral fallback fact when no acceptable candidate | §4.7 diagnostics + §5.5: "TOOL_RESULT_ACCEPTED alone creates zero facts" | Conforms |
| §24: minimum preserve only continuity, not fact | §4.4 `MinimumPreserveItemCandidate` + §5.5 continuity materialization | Conforms |
| §24: `recent_raw_turns_floor` keeps name, continuity only | §2 non-goals + §5.2: "只影响 raw turn continuity inclusion" | Conforms |
| §24: RunInputBuilder renders `claim_text + evidence_refs`, not digest-only | §5.6 + Slice 5 tests | Conforms |
| §25: compactor output includes `evidence_backed_fact_candidates` and `minimum_preserve_item_candidates` in same structured JSON proposal | §4.3, §4.4, §5.3 | Conforms |
| §25: Context Governance doesn't directly write memory | §5.5: "Projection 是 read model，不直接写 EventLog" | Conforms |
| §18: tool fact must go through Host-mediated accept barrier | §5.1 data flow from `TOOL_RESULT_ACCEPTED` to evidence envelope | Conforms |
| Implementation-control.md Phase 12.5: scope and prohibited changes | §2 non-goals + §10 stop conditions | Conforms |

### 1.3 Handoff Coverage Verified

All items required by the controller handoff (§Required Plan Contents, §Required Slice Coverage, §Required Tests) are present. See plan §3.5 for the self-coverage checklist — each item maps to concrete plan sections.

---

## 2. Adversarial Findings

### Finding 1 — `MemoryClaimStatus.TOOL_VERIFIED` 枚举未在命名迁移表中显式列出

- **Severity**: Medium
- **Evidence**: `memory.py:126` — `class MemoryClaimStatus(StrEnum)` 包含 `TOOL_VERIFIED = "tool_verified"`；`memory.py:402` — `VerifiedFactView.__post_init__` 校验 `self.claim_status is not MemoryClaimStatus.TOOL_VERIFIED`；`memory.py:1371` — `_verified_fact_from_projection_event` 硬编码 `claim_status=MemoryClaimStatus.TOOL_VERIFIED`。
- **Why it matters**: `EvidenceBackedFactView` 不再有 `claim_status` 字段（plan §4.6），因此 `MemoryClaimStatus.TOOL_VERIFIED` 的使用点（尤其在 `_verified_fact_from_projection_event` 中）需要同步移除或改为 `EVIDENCE_BACKED_FACT`。plan §4.1 命名迁移表未列出此枚举值，implementation agent 可能在 Slice 4 投影重写时遗漏它。
- **Whether it blocks gate**: No。这是实现细节，implementation agent 重写投影逻辑时会自然触及 `_verified_fact_from_projection_event` 函数并移除整个函数体。但 controller 应确认实现完成报告覆盖此枚举清理。
- **Recommendation**: 在 plan §4.1 命名迁移表中补充 `MemoryClaimStatus.TOOL_VERIFIED` 的移除决策；或要求在 Slice 4 completion report 中显式报告该枚举值的清理结果。

### Finding 2 — `CompactQualityIssue.SUMMARY_PRETENDS_VERIFIED_FACT` 枚举值重命名未显式列出

- **Severity**: Medium
- **Evidence**: `compaction.py:39` — `SUMMARY_PRETENDS_VERIFIED_FACT = "summary_pretends_verified_fact"`；`context_governance.py:58-59` — `_summary_pretends_verified_fact()` 使用此枚举。plan §4.1 重命名了 `EpisodeSummaryCandidate.proposed_verified_fact_refs` 和 `CompactionCandidate.preserved_verified_fact_refs`，但未列出 `CompactQualityIssue.SUMMARY_PRETENDS_VERIFIED_FACT` 需要重命名。
- **Why it matters**: 函数 `_summary_pretends_verified_fact()` 引用的是已计划重命名的字段，但 quality issue 枚举名若不同步更新，会与"禁止旧名残留"的规则冲突。
- **Whether it blocks gate**: No。plan §4.1 的全面旧名清理命令（`rg -n "verified_facts|max_verified_facts|VerifiedFact|stable:verified_facts|tool-verified facts"`）会捕获此枚举字符串值。但若 `SUMMARY_PRETENDS_VERIFIED_FACT` 枚举名本身（不是值）未被搜索匹配，可能遗漏。
- **Recommendation**: 扩展 plan §6.3 / Slice 6 的旧名搜索正则，加入 `SUMMARY_PRETENDS_VERIFIED_FACT` 或更通用的 `PRETENDS_VERIFIED` 模式。

### Finding 3 — `CONTEXT_COMPACTED.preserved_fact_refs` 内部 JSON 结构变更可能影响下游 consumer

- **Severity**: Medium
- **Evidence**: `context_events.py:249-256` — 当前 `preserved_fact_refs` 子结构为 `{"tool_fact_refs": [...], "verified_fact_refs": [...]}`；plan §4.5 提议的新结构为 `{"accepted_evidence_refs": [...], "evidence_backed_fact_refs": [...]}` 外加 `quality_check_result` 中的新字段。当前 `validate_context_compacted_payload()` (`context_events.py:299`) 只校验 `preserved_fact_refs` 键存在，不校验内部 shape。
- **Why it matters**: 任何消费 `CONTEXT_COMPACTED` 事件的 tool trace、audit projection、render 或 compact artifact 展示组件如果读取了 `preserved_fact_refs.verified_fact_refs` 或 `preserved_fact_refs.tool_fact_refs`，会因 key 不存在而静默得到 `None`。plan 未列出需要检查的下游 consumer（仅列出 production files）。
- **Whether it blocks gate**: No。根据代码搜索，当前 preserved_fact_refs 的消费主要在 memory projection（`memory.py:1165` — `_validate_compact_summary_fact_refs`）和 durable compact artifact 写入路径，这些已在 plan 的 affected files 中覆盖。但仍存在 trace/render 消费风险。
- **Recommendation**: 在 Slice 3 启动前，先用 `rg "preserved_fact_refs|tool_fact_refs|verified_fact_refs" dayu/ tests/` 确认所有消费点都在 affected files 列表中。plan 当前 §6 的 affected files 列表已覆盖主要路径，但不保证 exhaustiveness。

### Finding 4 — `EvidenceBackedFactView` 移除 `evidence_anchor` 和 `subject_refs` 后，JSON codec 需同步更新

- **Severity**: Low
- **Evidence**: `memory.py:2883-2918` — `_verified_fact_to_json_value()` 和 `_verified_fact_from_json_value()` 序列化/反序列化 `evidence_anchor` 和 `subject_refs`；`evidence_anchor` 的类型 `OpaqueMemoryRef` 定义在 `memory.py` 中。plan §4.6 的新 `EvidenceBackedFactView` 不含这些字段，但 plan 未显式列出旧 JSON codec 函数的移除/重写需求。
- **Why it matters**: implementation agent 可能只改 dataclass 而遗留旧 codec 函数，导致未使用 dead code 或 pyright 报错。
- **Whether it blocks gate**: No。实现时对 `VerifiedFactView` 做全量 rename 自然会涉及 codec，且 plan Slice 1 的 pyright 命令会捕获类型不一致。
- **Recommendation**: 无需 plan 修改；在 Slice 1 completion report 中要求显式确认旧 codec 已移除。

### Finding 5 — LLM compactor 提示词从 plain text + JSON 到 strict JSON-only 的迁移风险被正确识别但缓解不足

- **Severity**: Low
- **Evidence**: plan §11 第一条 residual risk 指出 "LLM fact extraction quality remains model-dependent"；plan Slice 3 说 "Plain text summary-only output must become proposal failure / repair input"。`llm_compaction.py` 当前没有 `evidence_backed_fact` 相关字段引用。
- **Why it matters**: 将 LLM compactor 输出从允许 plain text summary 迁移到强制 structured JSON（包含 `evidence_backed_fact_candidates` 和 `minimum_preserve_item_candidates`），本质上是该组件的 breaking change。prompt engineering 变更可能影响 compaction 成功率或事实提取质量。
- **Whether it blocks gate**: No。plan 正确识别了此风险，且有 bounded repair 路径保底。测试要求（Slice 3 tests）覆盖了 parse failure 和 plain text rejection。
- **Recommendation**: 无需 plan 修改。但 implementation agent 应在 Slice 3 completion report 中报告 JSON proposal 解析成功率（在 fake/测试 compactor 下的统计）。

### Finding 6 — `_FIELD_PROPOSED_VERIFIED_FACT_REFS` 常量名未在命名迁移表中列出

- **Severity**: Low
- **Evidence**: `context_events.py:75` — `_FIELD_PROPOSED_VERIFIED_FACT_REFS = "proposed_verified_fact_refs"`。plan §4.1 只列出了 `EpisodeSummaryCandidate.proposed_verified_fact_refs -> proposed_evidence_backed_fact_refs`（dataclass 字段），未列出 `context_events.py` 中的模块私有常量需要同步重命名。
- **Why it matters**: 遗漏此常量会导致 `context_events.py` 中残留旧字符串 key `"proposed_verified_fact_refs"`，与新 dataclass JSON key 不一致。
- **Whether it blocks gate**: No。Slice 3 同时修改 `context_events.py`，实现时会自然触及所有相关字段 key。
- **Recommendation**: 建议在 Slice 3 completion report 中显式要求报告所有 `_FIELD_*` 常量的最终状态。

---

## 3. Architecture / State Machine / Schema Risk Assessment

### 3.1 Architecture boundaries

Plan properly protects all four architecture boundaries declared in control doc:
- Engine Agent loop: not modified (§2, §10)
- Fins storage / real tool implementations: not modified (§2, §10)
- Service / UI workflows: not modified (§2, §10)
- Host public command/handle APIs: not modified (§2, §10)

No architecture boundary violation found.

### 3.2 State machine impact

Plan changes only read model (memory projection) and event payload contents, not state transitions. `TOOL_RESULT_ACCEPTED` event type remains; `CONTEXT_COMPACTED` event type remains; their payloads gain new fields without removing old governance-critical fields. No Run/Attempt/Session state machine changes. No new event types.

Risk: Low.

### 3.3 Schema migration risk

Plan adopts "全新 schema 起库" strategy (§4.1, §11): old durable snapshots are incompatible. This is an explicit controller decision documented in implementation-control.md Phase 12.5 "关键设计裁决" and plan §11 residual risk #3.

Risk: Accepted. No blocking issue.

### 3.4 Slice dependency chain

Slice 1 → Slice 2 → Slice 3 → Slice 4 → Slice 5 → Slice 6 is a clean linear dependency chain. Each slice has a clear stop condition. No hidden circular dependency found.

---

## 4. Test Coverage Assessment

### 4.1 Handoff-required tests: all covered

All eight test requirements from controller handoff are mapped to concrete test files in plan §8. Test scenarios cover both unit (accept barrier, contract validation, projection, rendering) and integration/smoke (no-compaction follow-up, post-compaction reuse, minimum preserve resolution, fact drift prevention).

### 4.2 Test gap identified

Plan §8 says "post-compaction revenue / gross-profit facts reused for gross-margin follow-up" test lives in `test_run_input_builder.py` or "existing public lifecycle smoke if already wired." This is a conditional assignment — the implementation agent must decide whether to create new integration test or extend existing smoke. Plan could be stronger by prescribing one location.

Severity: Low. Both options are valid; the ambiguity is acceptable because the implementation agent will discover which file has the right test infrastructure.

### 4.3 Config rejection test

Plan requires "old `max_verified_facts` is rejected" test in Slice 1. This test is correctly assigned to `tests/runtime/test_config_loader.py`. Verified that current test file (`test_config_loader.py:130`) references `max_verified_facts` — this test will need updating, and the plan accounts for it.

---

## 5. Residual Risks (all pre-identified by plan, confirmed by review)

| Risk | Plan §11 Owner | Review Assessment |
|------|---------------|-------------------|
| LLM fact extraction quality model-dependent | Context Governance / compactor tests | Correctly assigned; bounded repair path mitigates |
| Fine-grained item-level evidence ids deferred | Later evidence granularity work | Acceptable for first version |
| Old durable snapshots not compatible | Controller decision; new schema start | Explicitly accepted |
| Real Fins tool source/locator descriptors may be sparse | Later Fins/tool provider work unit | Plan correctly tolerates empty opaque refs |
| Cross-session retrieval out of scope | Later phases | Explicitly excluded in §2 |

No new residual risks found beyond those the plan already identifies.

---

## 6. README Sync Assessment

Plan §9 correctly identifies required vs conditional README updates per project CLAUDE.md rules. The `rg` search command in plan §9 and Slice 6 is appropriate for detecting stale terms.

One observation: plan says `tests/README.md` must mention "P12.5 memory projection / compaction / run input test responsibilities if not already covered." Project CLAUDE.md says tests/README.md covers "测试分层、运行方式、约定与维护规则" — P12.5 doesn't change test layering or conventions, so a P12.5-specific mention may violate the "不写未来计划" rule. Implementation agent should verify whether current `tests/README.md` already covers these test areas generically, and only add if gaps exist.

---

## 7. Stop Condition Assessment

All seven stop conditions in plan §10 are well-specified and trigger at clear architectural boundaries. Each slice also has a local stop condition. The conditions are falsifiable (each states a concrete scenario that would trigger a stop).

No missing stop condition found.

---

## 8. Final Assessment

**Gate Verdict: PASS**

The plan is:
- **Handoff-ready**: All required plan contents (§1-§6, §8-§11, §13-§14 + handoff checklist §3.5) are present and internally consistent.
- **Code-generation-ready**: Six slices have exact file lists, exact changes, validation commands, and stop conditions. An implementation agent can execute each slice without additional design decisions.
- **Design-conformant**: All design.md §24/§25/§18 requirements are mapped to concrete implementation steps. No design deviation found.
- **Scope-protected**: Non-goals (§2) and stop conditions (§10) jointly fence prohibited areas.

Six findings identified (Section 2 above), none blocking. Three recommendations for implementation agents to address in slice completion reports. Residual risks (Section 5) all have clear owners.

---

## Appendix: Verification Commands Run

None — review agent does not modify production code or tests, and does not run tests. All evidence from static code reading.
