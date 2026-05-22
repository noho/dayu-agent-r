# Phase 12.5 Plan Re-Review: AgentMiMo

## 0. Re-Review Context

- Gate: Phase 12.5 plan re-review after controller-accepted plan fix.
- Role: independent review agent AgentMiMo.
- Updated plan: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`.
- Original reviews: `docs/reviews/phase12-5-plan-review-mimo-20260522.md`, `docs/reviews/phase12-5-plan-review-ds-20260522.md`.
- Controller adjudication: `docs/reviews/phase12-5-plan-review-controller-adjudication-20260522.md`.
- Task: verify whether A1-A7 are fully addressed without introducing new scope creep, design conflicts, or code-generation ambiguity.

## 1. A1-A7 Verification

### A1 — Scope the LLM compactor structured JSON rewrite explicitly

**Status: FULLY ADDRESSED**

| Required | Plan Location | Evidence |
|---|---|---|
| Own slice or explicit sub-slice with tests and stop condition | §7 Slice 4 (lines 613-654): "LLM Compactor Structured JSON Rewrite" — dedicated slice for `llm_compaction.py` + `test_llm_compaction.py` | Plan §7 Slice 4 |
| Plain-text summary success path removed or rejected | §5.3 (line 392): "Plain-text summary success path must be removed or rejected; it cannot be silently accepted as a compact success." Slice 4 exact changes (line 635): "Remove or reject the existing plain-text summary success path." | Plan §5.3, §7 Slice 4 |
| Stop condition for JSON robustness | Slice 4 stop condition (line 654): "If structured JSON parsing / schema validation cannot work within bounded repair attempts, stop and report Blocking Questions For Controller." Also §10 (line 832): "Structured JSON parsing / schema validation cannot work within bounded repair attempts." | Plan §7 Slice 4, §10 |
| Tests for plain text rejection | §8 (line 798): "Plain-text LLM compactor final answer is rejected, not silently accepted" → `test_llm_compaction.py`. Slice 4 tests (line 643): "plain text final answer is rejected and not accepted as compact success." | Plan §7 Slice 4, §8 |

### A2 — Freeze CompactionRequest accepted evidence data flow

**Status: FULLY ADDRESSED**

| Required | Plan Location | Evidence |
|---|---|---|
| Exact source: EventLog range read of TOOL_RESULT_ACCEPTED.accepted_evidence_envelope | §4.2 (lines 156-157): "Context Governance builds compact input by reading TOOL_RESULT_ACCEPTED.accepted_evidence_envelope from committed EventLog rows covered by the compaction request input range." §5.2 (line 372): "bounded EventLog read over the compact input range" | Plan §4.2, §5.2 |
| New fields on CompactionRequest | §4.2 (lines 160-163): `accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]` and `accepted_evidence_refs: tuple[str, ...]` | Plan §4.2 |
| Existing refs renamed | §4.2 (line 166): "Existing stable fact refs are separate and must be named evidence_backed_fact_refs" | Plan §4.2 |
| dispatch.py / engine_ingest.py bounded reads | §4.2 (lines 167-168): "dispatch.py proactive request construction and engine_ingest.py reactive request construction must replace current hardcoded empty refs with bounded EventLog reads." §7 Slice 6 (lines 730-731): same requirement. | Plan §4.2, §7 Slice 6 |
| Stop condition | §10 (lines 833-834): "Bounded EventLog reads cannot provide accepted_evidence_envelopes for compact input without changing public Host command APIs." | Plan §10 |

### A3 — Freeze EvidenceBackedFactView provenance source

**Status: FULLY ADDRESSED**

| Required | Plan Location | Evidence |
|---|---|---|
| event_id / event_sequence from CONTEXT_COMPACTED event | §4.6 (lines 260-261): "EvidenceBackedFactView.provenance.event_id and event_sequence must come from the accepted CONTEXT_COMPACTED event that materialized the fact." | Plan §4.6 |
| extraction_operation_ref / compact_artifact_ref from compacted payload | §4.6 (line 262): "extraction_operation_ref and compact_artifact_ref must come from trusted compacted payload / artifact metadata, not from LLM candidate text as authoritative provenance." | Plan §4.6 |
| candidate_id is diagnostic-only | §4.6 (line 263): "candidate_id is item-local diagnostic / dedupe metadata only." §4.3 (line 195): same statement. | Plan §4.3, §4.6 |
| Test for provenance sourcing | §7 Slice 5 (line 687): "created facts use the accepted CONTEXT_COMPACTED event id / sequence as provenance; candidate id is not authoritative provenance." | Plan §7 Slice 5 |

### A4 — Define bounded validation constants

**Status: FULLY ADDRESSED**

| Required | Plan Location | Evidence |
|---|---|---|
| Module constants for claim_text, min preserve text, candidate counts, attributes size | §4.8 (lines 308-317): 8 frozen constants with exact values (MAX_EVIDENCE_BACKED_FACT_CANDIDATES=64, MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES=32, MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS=2000, etc.) | Plan §4.8 |
| Constants in Host compaction/memory code, not runtime config | §4.8 (lines 303-304): "must define in Host compaction / memory contract code...不得放入 runtime config" | Plan §4.8 |
| Tests for empty/overlong claim_text and overlong min preserve text | §4.8 (line 325): "tests must reject empty and overlong claim_text, and overlong minimum preserve text at minimum." §8 (line 797): "Bounded validation rejects empty / overlong claim text and overlong minimum preserve text" → test_compaction_contract.py, test_llm_compaction.py. §7 Slice 3 (line 600): "overlong claim_text and overlong minimum preserve text are rejected." | Plan §4.8, §7 Slice 3, §8 |

### A5 — Expand old-name cleanup list and search criteria

**Status: FULLY ADDRESSED**

| Required | Plan Location | Evidence |
|---|---|---|
| Explicit cleanup for MemoryClaimStatus.TOOL_VERIFIED | §4.1 (line 100): "`MemoryClaimStatus.TOOL_VERIFIED` -> `EVIDENCE_BACKED`" | Plan §4.1 |
| Explicit cleanup for MemoryIncludedReason.TOOL_VERIFIED_FACT | §4.1 (line 101): "`MemoryIncludedReason.TOOL_VERIFIED_FACT` -> `EVIDENCE_BACKED_FACT`" | Plan §4.1 |
| Explicit cleanup for CompactQualityIssue.SUMMARY_PRETENDS_VERIFIED_FACT | §4.1 (line 102): "`CompactQualityIssue.SUMMARY_PRETENDS_VERIFIED_FACT` -> `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` 或等价新名" | Plan §4.1 |
| Explicit cleanup for _FIELD_PROPOSED_VERIFIED_FACT_REFS | §4.1 (line 103): "`_FIELD_PROPOSED_VERIFIED_FACT_REFS` -> `_FIELD_PROPOSED_EVIDENCE_BACKED_FACT_REFS`" | Plan §4.1 |
| Explicit cleanup for old JSON codec helpers | §4.1 (line 104): "old verified JSON codec helpers -> evidence-backed equivalents" | Plan §4.1 |
| Explicit cleanup for durable item kind constants | §4.1 (line 105): "durable constants such as `_ITEM_KIND_VERIFIED_FACT` -> `_ITEM_KIND_EVIDENCE_BACKED_FACT`" | Plan §4.1 |
| Extended search regex | §6.4 (lines 481-484): two search commands with comprehensive patterns. §7 Slice 7 (line 783): extended patterns including `TOOL_VERIFIED`, `PRETENDS_VERIFIED`, `proposed_verified`, `preserved_verified`, `stable:verified`, `max_verified`. §9 (line 819): same extended patterns for README search. | Plan §6.4, §7 Slice 7, §9 |

### A6 — Specify old durable snapshot behavior

**Status: FULLY ADDRESSED**

| Required | Plan Location | Evidence |
|---|---|---|
| Fail closed with clear validation error | §4.9 (lines 329-330): "conversation_memory_snapshot_from_json_value() must reject old verified_facts key and require evidence_backed_facts." "durable item row readers / validators must reject old item kind verified_fact with a clear validation error." | Plan §4.9 |
| No silent skip | §4.9 (line 333): "implementation must not silently skip old verified items." | Plan §4.9 |
| No compatibility reads | §4.9 (line 334): "implementation must not add compatibility reads, aliases or migration fallback." | Plan §4.9 |
| Tests for old key/kind rejection | §4.9 (line 335): "tests must cover old snapshot key rejection and old durable item kind rejection where current codec exposes those paths." §7 Slice 5 (line 692): test "old snapshot key verified_facts and old durable item kind verified_fact fail closed with clear validation errors." §8 (line 804): "Old durable snapshot key / old item kind fail closed" → test_memory_projection.py. | Plan §4.9, §7 Slice 5, §8 |

### A7 — Exhaustively check preserved_fact_refs consumers

**Status: FULLY ADDRESSED**

| Required | Plan Location | Evidence |
|---|---|---|
| Pre-implementation search step | §4.10 (lines 339-343): explicit search command "Before implementation edits, the implementation agent must run: rg -n 'preserved_fact_refs\|tool_fact_refs\|verified_fact_refs\|preserved_verified\|proposed_verified' dayu tests" | Plan §4.10 |
| Classify every hit | §4.10 (lines 345-348): "Every hit must be classified before coding: included in an explicit slice and renamed / semantically updated; or documented in the implementation report as not consuming the changed semantics, with direct reason." | Plan §4.10 |
| Add unlisted consumers to slices | §4.10 (lines 350-351): "Any hit outside the affected-file list...must be added to an explicit slice before implementation continues." §6.4 (line 486): "Every semantic consumer of the renamed contract must be included in an explicit slice or documented as unrelated to the changed semantics." | Plan §4.10, §6.4 |

## 2. Scope Creep / Design Conflict / Ambiguity Check

| Check | Status | Notes |
|---|---|---|
| New Slice 4 scope | PASS | Cleanly scoped to `llm_compaction.py` + `test_llm_compaction.py` + optionally `fake_compaction.py`. No new production modules. |
| §4.2 data flow additions | PASS | `dispatch.py` / `engine_ingest.py` were already in scope (§6.1). No new files added. |
| §4.6 provenance freeze | PASS | Aligns with design.md §24 requirement for "producer / extraction operation ref、event_id / event_sequence". |
| §4.8 constants | PASS | Module-local constants, not config. Consistent with "Host-neutral" design and "禁止魔法数字" constraint. |
| §4.9 fail-closed | PASS | Consistent with project policy "旧库按全新 schema 起库处理". |
| §4.10 consumer audit | PASS | Implementation guardrail, not new feature. Search commands are deterministic. |
| Slice count change | PASS | 6 → 7 slices. New Slice 4 is a clean split from old Slice 3 (compactor rewrite was underestimated complexity in original plan). |
| Design conflicts | PASS | No design.md requirements contradicted by the fixes. |
| Code-generation ambiguity | PASS | All A1-A7 fixes add specificity, not ambiguity. Each fix provides exact field names, exact constants, exact search commands, or exact stop conditions. |

## 3. Verdict

**PASS.** All seven accepted plan-fix items (A1-A7) are fully addressed in the updated plan. No new scope creep, design conflicts, or code-generation ambiguity were introduced. The plan can proceed to accepted plan commit.

### Summary of Changes Since Original Review

| Item | Original Plan | Updated Plan |
|---|---|---|
| A1: Compactor rewrite scope | Buried in Slice 3 as prompt tweak | Dedicated Slice 4 with own tests and stop condition |
| A2: Evidence data flow | Unspecified | Frozen in §4.2 with exact field names, bounded EventLog read requirement, and stop condition |
| A3: Provenance source | Unspecified | Frozen in §4.6 with four explicit sourcing rules |
| A4: Validation constants | Not defined | 8 frozen constants in §4.8 with test requirements |
| A5: Old-name cleanup | Partial list | Complete list in §4.1 (16 items) + extended search regex in §6.4 |
| A6: Old snapshot behavior | Acknowledged but unspecified | Fail-closed spec in §4.9 with test requirements |
| A7: Consumer audit | Not specified | Mandatory pre-implementation search + classification in §4.10 and §6.4 |
