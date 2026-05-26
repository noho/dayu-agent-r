# Phase 12.5 Plan Re-Review — AgentDS

## Review Metadata

- **Reviewer**: AgentDS (independent review agent)
- **Date**: 2026-05-22
- **Review type**: Plan re-review after controller-adjudicated plan fix
- **Updated plan**: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- **Controller adjudication**: `docs/reviews/phase12-5-plan-review-controller-adjudication-20260522.md`
- **Original reviews**: MiMo (`phase12-5-plan-review-mimo-20260522.md`), DS (`phase12-5-plan-review-ds-20260522.md`)
- **Scope**: Verify A1-A7 are fully addressed without scope creep, design conflicts, or code-generation ambiguity

## Gate Verdict

**PASS** — All seven adjudicated fix items (A1-A7) are fully addressed in the updated plan. No scope creep, design conflicts, or code-generation ambiguity introduced. The plan can proceed to accepted plan commit.

---

## Fix Item Verification

### A1 — LLM Compactor Structured JSON Rewrite Scoped ✓

| Requirement | Evidence | Status |
|---|---|---|
| Compactor rewrite is its own slice with own tests and stop condition | Plan §7 Slice 4: "LLM Compactor Structured JSON Rewrite" — standalone slice with `test_llm_compaction.py`, 7 exact changes, 5 test scenarios, `pyright` + `pytest` validation commands | ✓ |
| Plain-text success path is removed or rejected, not silently accepted | Plan §5.3: "Plain-text summary success path must be removed or rejected; it cannot be silently accepted as a compact success." Slice 4 exact changes: "Remove or reject the existing plain-text summary success path. A final answer containing only plain text must not produce accepted CompactionCandidate." | ✓ |
| Stop condition: if structured JSON parsing fails within bounded repair, stop | Plan §7 Slice 4 stop condition + §10 global stop condition: "Structured JSON parsing / schema validation cannot work within bounded repair attempts." | ✓ |
| Not a second normal-path LLM call | Slice 4: "Do not add a second normal-path LLM call for fact extraction." | ✓ |

Slice structural change verified: `test_llm_compaction.py` correctly moved from old Slice 3 to new Slice 4. Old Slice 3 validation commands correctly removed `test_llm_compaction.py` from pytest call.

### A2 — CompactionRequest Accepted Evidence Data Flow Frozen ✓

| Requirement | Evidence | Status |
|---|---|---|
| Exact source specified: EventLog read over compact input range | Plan §4.2: "Context Governance builds compact input by reading `TOOL_RESULT_ACCEPTED.accepted_evidence_envelope` from committed EventLog rows covered by the compaction request input range." | ✓ |
| `accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]` on `CompactionRequest` | Plan §4.2 contract block | ✓ |
| `accepted_evidence_refs: tuple[str, ...]` derived from envelopes, not LLM output | Plan §4.2: "`accepted_evidence_refs` is derived from `accepted_evidence_envelopes[*].evidence_id` during request construction, not supplied by LLM output." | ✓ |
| `evidence_backed_fact_refs` separate from `accepted_evidence_refs` | Plan §4.2: "Existing stable fact refs are separate and must be named `evidence_backed_fact_refs: tuple[str, ...]`." | ✓ |
| `dispatch.py` / `engine_ingest.py` hardcoded empty refs replaced by bounded EventLog reads | Plan §4.2: "must replace current hardcoded empty refs with bounded EventLog reads over the compact input range." Slice 6 exact changes echo this. | ✓ |
| Empty tuples allowed only when range has no accepted evidence | Plan §4.2: "They may pass explicit empty tuples only when that bounded range contains no `TOOL_RESULT_ACCEPTED` with accepted evidence." | ✓ |
| Bounded read scoped to same session and compact input cursor/range | Plan §4.2: "The bounded read must not scan unrelated sessions or unbounded history; it only reads rows in the same session and compact input cursor/range." | ✓ |

### A3 — EvidenceBackedFactView Provenance Source Frozen ✓

| Requirement | Evidence | Status |
|---|---|---|
| `provenance.event_id` and `event_sequence` from `CONTEXT_COMPACTED` event | Plan §4.6: "`EvidenceBackedFactView.provenance.event_id` and `event_sequence` must come from the accepted `CONTEXT_COMPACTED` event that materialized the fact." | ✓ |
| `extraction_operation_ref` and `compact_artifact_ref` from payload/artifact, not LLM | Plan §4.6: "`extraction_operation_ref` and `compact_artifact_ref` must come from trusted compacted payload / artifact metadata, not from LLM candidate text as authoritative provenance." | ✓ |
| `candidate_id` is local diagnostic/dedupe only | Plan §4.6: "`candidate_id` is item-local diagnostic / dedupe metadata only." + §4.3: "`candidate_id` 只用于 candidate-local diagnostics / dedupe，不是 authoritative provenance." | ✓ |
| Evidence origin in `evidence_refs` pointing to accepted evidence envelopes | Plan §4.6: "Evidence origin remains in `evidence_refs`, which point to accepted evidence envelopes from earlier `TOOL_RESULT_ACCEPTED` events." | ✓ |
| New view fields: `extraction_operation_ref`, `compact_artifact_ref`, `candidate_id` | Plan §4.6 typed fields all present | ✓ |

Slice 5 tests explicitly cover: "created facts use the accepted `CONTEXT_COMPACTED` event id / sequence as provenance; candidate id is not authoritative provenance." ✓

### A4 — Bounded Validation Constants Defined ✓

| Requirement | Evidence | Status |
|---|---|---|
| Constants defined in Host compaction/memory code, not runtime config | Plan §4.8: "必须定义在 Host compaction / memory contract code 中...不得放入 runtime config，也不得由 Service / UI 配置覆盖." | ✓ |
| All required constants present with values | Plan §4.8: `MAX_EVIDENCE_BACKED_FACT_CANDIDATES=64`, `MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES=32`, `MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS=2000`, `MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS=1200`, `MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS=120`, `MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS=4096`, `MAX_EVIDENCE_REFS_PER_FACT=16`, `MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM=16` | ✓ |
| Validation rules: non-empty claim_text, bounded lengths, bounded counts | Plan §4.8 validation requirements | ✓ |
| Tests cover boundary rejection for empty/overlong claim_text and minimum preserve text | Plan §4.8 + §8 test matrix row: "Bounded validation rejects empty / overlong claim text and overlong minimum preserve text" assigned to `test_compaction_contract.py` + `test_llm_compaction.py` | ✓ |
| Slice 3 references constants from §4.8 | Slice 3 exact changes: "Use constants from §4.8 for claim text, minimum preserve text, candidate counts, evidence refs per fact and attributes JSON size." | ✓ |
| Slice 4 tests include overlong rejection via shared constants | Slice 4 tests: "structured JSON with overlong `claim_text` or minimum preserve `text` is rejected via the shared constants." | ✓ |

### A5 — Old-Name Cleanup List Expanded ✓

| Requirement | Evidence | Status |
|---|---|---|
| `MemoryClaimStatus.TOOL_VERIFIED` → `EVIDENCE_BACKED` | Plan §4.1 cleanup list | ✓ |
| `MemoryIncludedReason.TOOL_VERIFIED_FACT` → `EVIDENCE_BACKED_FACT` | Plan §4.1 cleanup list | ✓ |
| `CompactQualityIssue.SUMMARY_PRETENDS_VERIFIED_FACT` → equivalent new name | Plan §4.1: "`SUMMARY_PRETENDS_VERIFIED_FACT` -> `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` 或等价新名." | ✓ |
| `_FIELD_PROPOSED_VERIFIED_FACT_REFS` → `_FIELD_PROPOSED_EVIDENCE_BACKED_FACT_REFS` | Plan §4.1 cleanup list | ✓ |
| Old JSON codec helpers listed | Plan §4.1: "old verified JSON codec helpers such as `_verified_fact_to_json_value()` / `_verified_fact_from_json_value()` -> evidence-backed equivalents." | ✓ |
| Durable constants listed | Plan §4.1: "durable constants such as `_ITEM_KIND_VERIFIED_FACT` -> `_ITEM_KIND_EVIDENCE_BACKED_FACT`." | ✓ |

Expanded stale-term search (Plan §6.4):
```bash
rg -n "verified_facts|max_verified_facts|VerifiedFact|verified fact|verified_fact|TOOL_VERIFIED|PRETENDS_VERIFIED|proposed_verified|preserved_verified|stable:verified|max_verified" dayu tests docs README.md
```
Covers: `VerifiedFact` (was missing), `verified fact` (was missing), `verified_fact` (was missing), `TOOL_VERIFIED` (was missing), `PRETENDS_VERIFIED` (was missing), `proposed_verified` (was missing), `preserved_verified` (was missing), `stable:verified` (was missing), `max_verified` (was missing). ✓

### A6 — Old Durable Snapshot Fail-Closed Specified ✓

| Requirement | Evidence | Status |
|---|---|---|
| Readers fail closed on old `verified_facts` key, require `evidence_backed_facts` | Plan §4.9: "`conversation_memory_snapshot_from_json_value()` must reject old `verified_facts` key and require `evidence_backed_facts`." | ✓ |
| Durable item row readers reject old `verified_fact` kind with clear error | Plan §4.9: "durable item row readers / validators must reject old item kind `verified_fact` with a clear validation error." | ✓ |
| No silent skip of old verified items | Plan §4.9: "implementation must not silently skip old verified items." | ✓ |
| No compatibility reads, aliases, migration fallback | Plan §4.9: "implementation must not add compatibility reads, aliases or migration fallback." | ✓ |
| Tests cover old key rejection and old item kind rejection | Plan §4.9 + §8 test matrix row: "Old durable snapshot key / old item kind fail closed" → `tests/host/test_memory_projection.py` | ✓ |
| Residual risk updated | Plan §11: "Old durable snapshots / item rows fail closed by design. Owner: implementation Slice 5 tests." | ✓ |

### A7 — preserved_fact_refs Consumer Audit Added ✓

| Requirement | Evidence | Status |
|---|---|---|
| Pre-implementation search step added | Plan §4.10: `rg -n "preserved_fact_refs|tool_fact_refs|verified_fact_refs|preserved_verified|proposed_verified" dayu tests` | ✓ |
| Results database covers both `dayu/` and `tests/` | Plan §4.10 scope explicitly covers both | ✓ |
| Every hit classified before coding: in-slice, explicitly renamed, or documented as unrelated | Plan §4.10: "Every hit must be classified before coding: included in an explicit slice and renamed / semantically updated; or documented in the implementation report as not consuming the changed semantics, with direct reason." | ✓ |
| Unrecognized consumers must be added to explicit slice | Plan §4.10: "Any hit outside the affected-file list...must be added to an explicit slice before implementation continues." | ✓ |
| Dual-search requirement in §6.4 for stale term + preserved_fact_refs search | Plan §6.4 includes both search commands | ✓ |
| Slice 7 validation repeats the search as gate check | Plan §7 Slice 7 validation commands include both searches | ✓ |

---

## Scope Creep, Design Conflict, and Ambiguity Check

### Scope creep: None detected

All seven slices operate within the same production files listed in original plan §6.1. One new file from A2 (EventLog read for evidence envelopes in `dispatch.py` / `engine_ingest.py`) was already in the original affected-file list. No new production files, no new packages, no new architecture layer touched.

### Design conflict: None detected

All A1-A7 changes align with `design.md` §18, §23, §24, §25 and `implementation-control.md` Phase 12.5. Specifically:

- A2 (EventLog read for evidence envelopes): conforms to design.md §24 "Accepted evidence envelope 至少记录 evidence id、producer event ref..."
- A3 (provenance from CONTEXT_COMPACTED): conforms to design.md §24 "每条 evidence_backed_fact 至少包含...producer / extraction operation ref、event_id / event_sequence"
- A4 (bounded constants): conforms to design.md §24 "Host 只校验...claim_text 非空且长度受限"
- A5 (expanded cleanup): conforms to implementation-control.md "旧 verified_facts 改名...不保留兼容层"
- A6 (fail-closed durable): conforms to implementation-control.md "旧库按全新 schema 起库处理"
- A7 (consumer audit): conforms to design.md §25 "Context Governance 不直接写 memory"

### Code-generation ambiguity: None detected

The updated plan leaves no material cross-module contract to implementation judgment:

- Accepted evidence envelope data flow path (A2) is fully specified from EventLog read through `CompactionRequest` construction
- `EvidenceBackedFactView` provenance sourcing (A3) has explicit field-level mapping
- Validation constants (A4) have frozen values and location
- Name migration (A5) has exhaustive enumeration of old symbols
- Durable behavior (A6) has explicit reject semantics
- Consumer audit (A7) has executable search commands and classification rules

### Minor observation (non-blocking)

`MemoryClaimStatus.TOOL_VERIFIED` → `EVIDENCE_BACKED` (A5, plan §4.1): The updated `EvidenceBackedFactView` in §4.6 does not include `claim_status` in its field list. If the implementation agent removes `claim_status` from the new view entirely, the renamed `MemoryClaimStatus.EVIDENCE_BACKED` would have no consumer and could become dead code. The implementation agent can decide whether to keep the renamed enum value for future use or remove it. Either choice is valid within the plan's intent. This is not a plan defect — it's a routine cleanup decision at implementation time.

---

## Slice Structure Assessment

| Slice | Original | Updated | Change |
|---|---|---|---|
| 1: Contract Rename | Same | Same | None |
| 2: Evidence Envelope | Same | Same | None |
| 3: Compaction Contract + Accept Barrier | Included LLM compactor | LLM compactor removed | A1 — scope narrowed |
| 4: LLM Compactor Rewrite | Did not exist | New standalone slice | A1 — new slice |
| 5: Memory Projection | Was Slice 4 | Was Slice 4, now Slice 5 | Numbering only |
| 6: RunInputBuilder + Wiring | Was Slice 5 | Was Slice 5, now Slice 6 | A2 data flow added |
| 7: Integration Smoke + README | Was Slice 6 | Was Slice 6, now Slice 7 | A7 search added |

Slice dependency chain remains linear: 1 → 2 → 3 → 4 → 5 → 6 → 7. No circular dependencies introduced.

---

## Conclusion

All seven controller-adjudicated fix items (A1-A7) are fully addressed with direct section-level evidence. No scope creep, no design conflicts, no code-generation ambiguity introduced. The original PASS verdict is confirmed and strengthened — the plan is now more precisely scoped than the original version.

**Gate Verdict: PASS. Plan can proceed to accepted plan commit.**
