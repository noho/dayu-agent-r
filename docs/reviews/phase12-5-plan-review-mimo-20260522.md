# Phase 12.5 Implementation-Ready Plan Review: AgentMiMo

## 0. Review Context

- Gate: Phase 12.5 plan review.
- Role: independent review agent AgentMiMo.
- Plan under review: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`.
- Controller handoff: `docs/reviews/phase12-5-plan-handoff-controller-20260522.md`.
- Design truth: `docs/host/design.md`.
- Control doc: `docs/host/implementation-control.md`.
- Review lens: adversarial implementation-ready plan review.

## 1. Overall Assessment

**PASS with conditions.** The plan is handoff-ready and code-generation-ready at a structural level. It correctly diagnoses the current codebase state, proposes the right migration direction, covers all handoff-required slices and tests, and respects scope boundaries. However, there are findings that must be addressed before or during implementation to avoid scope blow-up or silent design drift.

## 2. Findings

### Finding 1: LLM Compactor Rewrite Scope Is Underestimated

**Severity: HIGH (non-blocking but requires explicit scoping)**
**Location: Plan §7 Slice 3, design.md §25**

The plan states:

> "Update `LLMContextCompactor` prompt to request strict JSON only; parse JSON into typed candidates. Plain text summary-only output must become proposal failure / repair input, not accepted compact."

This framing drastically underestimates the change. The current `llm_compaction.py` is a **plain text summary compactor**:

- System prompt (`llm_compaction.py:63-68`): *"return only the summary text"*.
- User prompt (`llm_compaction.py:305`): *"Return a concise summary in plain text only."*
- `compact()` method (`llm_compaction.py:155`): takes `outcome.content.strip()` as a plain string, no JSON parsing.
- `_candidate_from_summary()` (`llm_compaction.py:335-388`): manually constructs `CompactionCandidate` from the summary text and request refs.

Switching to structured JSON proposal requires:

1. Rewriting the system prompt to request a specific JSON schema with `episode_summary_candidate`, `pinned_state_patch_candidate`, `evidence_backed_fact_candidates`, and `minimum_preserve_item_candidates`.
2. Implementing JSON parsing with schema validation, type coercion, and error handling for malformed LLM output.
3. Defining the JSON schema contract between the prompt and the parser.
4. Handling partial parse failures (e.g., valid episode summary but invalid fact candidates).
5. Updating `_candidate_from_summary()` to become `_candidate_from_json_proposal()`.
6. Updating all existing tests in `tests/host/test_llm_compaction.py` that assume plain text output.

This is not a prompt tweak; it is an architectural change to the compactor's output contract. The plan should either:

- (a) Explicitly scope this as a significant sub-task within Slice 3 with its own stop condition ("if JSON parsing cannot be made robust within bounded repair attempts, stop"), or
- (b) Split the compactor rewrite into its own slice between the current Slice 2 and Slice 3.

**Evidence:** `dayu/host/llm_compaction.py:63-68, 155, 177, 180, 305, 335-388`.

### Finding 2: CompactionRequest Evidence Envelope Data Flow Is Unspecified

**Severity: MEDIUM (non-blocking but requires implementation clarification)**
**Location: Plan §5.2, §7 Slice 5**

Plan §5.2 states:

> "Context Governance builds CompactionRequest -> includes accepted_evidence_envelopes / accepted_evidence_refs from TOOL_RESULT_ACCEPTED"

But the current code tells a different story:

- `dispatch.py:1255-1256`: `CompactionRequest` is constructed with `tool_fact_refs=()` and `verified_fact_refs=()` (hardcoded empty tuples).
- `engine_ingest.py:2981-2982`: Same — hardcoded empty tuples.
- Neither file references `accepted_evidence` or `evidence_envelope` anywhere.

The plan identifies these as touch points in §6.1 and §7 Slice 5 but does not specify:

- Where the accepted evidence envelopes are read from (EventLog query? Memory projection? A new accumulator in Context Governance?).
- How the data flows from `TOOL_RESULT_ACCEPTED` events into the `CompactionRequest` construction site.
- Whether `CompactionRequest` needs a new field `accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]` or whether the existing `tool_fact_refs` field is repurposed.

Without this, the implementation agent must design the data flow independently, which violates the "code-generation-ready" contract.

**Evidence:** `dayu/host/dispatch.py:1242-1256`, `dayu/host/engine_ingest.py:2968-2982`.

### Finding 3: EvidenceBackedFactView Provenance Source Unspecified

**Severity: MEDIUM (non-blocking but requires implementation clarification)**
**Location: Plan §4.3, §4.6**

Plan §4.3 defines `EvidenceBackedFactCandidate` with fields: `candidate_id`, `claim_text`, `evidence_kind`, `evidence_refs`, `attributes`.

Plan §4.6 defines `EvidenceBackedFactView` with a required `provenance: MemoryProvenanceRef` field.

Design.md §24 requires each `evidence_backed_fact` to include "producer / extraction operation ref、`event_id` / `event_sequence`".

The plan does not specify where `provenance` fields (`event_id`, `event_sequence`, `producer_name`, `digest_ref`) are sourced during materialization in Slice 4. Options include:

- Deriving from the `CONTEXT_COMPACTED` event itself (operation_id + event_id).
- Deriving from the `candidate_id`.
- Requiring the compactor to include them in the candidate.

This must be explicitly decided to avoid the implementation agent inventing a scheme that later proves un-auditable.

**Evidence:** Plan §4.3, §4.6; design.md §24 line 2549-2554.

### Finding 4: claim_text Length Bound Not Explicit in Validation Contract

**Severity: LOW (non-blocking)**
**Location: Plan §4.7, §7 Slice 3**

Design.md §24 (line 2557) requires: "`claim_text` non-empty and **length受限**".

Plan §7 Slice 3 validation rules state: "`claim_text` non-empty and bounded" — but does not specify the bound or where it is defined (policy constant? config? hardcoded?).

This is a minor gap. The implementation agent will need to choose a bound. The plan should at least specify whether this is a policy-driven constant or a hardcoded safety limit.

**Evidence:** design.md §24 line 2557; plan §7 Slice 3.

### Finding 5: MemoryIncludedReason Enum Rename Cascade Not Explicit

**Severity: LOW (non-blocking)**
**Location: Plan §4.6**

Plan §4.6 states:

> "`MemoryIncludedReason.TOOL_VERIFIED_FACT` 改为 `EVIDENCE_BACKED_FACT`."

The plan's affected files list (§6.1) does not explicitly call out all files that reference `MemoryIncludedReason.TOOL_VERIFIED_FACT`. This enum value is likely referenced in:

- `dayu/host/memory.py` (projection logic).
- `tests/host/test_memory_projection.py` (assertions).
- Possibly `dayu/host/durable/memory.py` (serialization).

The Slice 1 "focused compile/type fallout" clause partially covers this, but the plan should be explicit that enum value renames cascade to all comparison/match sites.

**Evidence:** Plan §4.6, §7 Slice 1.

### Finding 6: Durable Snapshot Old Schema Deserialization Not Addressed

**Severity: LOW (non-blocking, acknowledged in residual risks)**
**Location: Plan §4.1, §11**

Plan §4.1 states: "旧库按全新 schema 起库处理" and §11 acknowledges "Existing old durable snapshots are not compatible."

However, the plan does not specify what happens when the durable memory reader encounters an existing snapshot with `item_kind="verified_fact"`. Options:

- Fail with a clear error message.
- Silently skip unknown item kinds.
- Require a clean database before testing.

This is partially a test environment concern, but the plan should specify the expected behavior for robustness.

**Evidence:** Plan §4.1, §11; `dayu/host/durable/memory.py:77`.

### Finding 7: Slice 3 File Count and Complexity Risk

**Severity: LOW (non-blocking)**
**Location: Plan §7 Slice 3**

Slice 3 covers 11 files (6 production + 5 test). Combined with Finding 1 (LLM compactor rewrite), this slice carries the highest risk in the plan. The plan's stop condition is:

> "If implementation requires a second normal-path LLM extraction call or eager extraction after each tool result, stop and report scope violation."

This stop condition addresses scope creep but not implementation complexity. A complementary stop condition should be added:

> "If the structured JSON proposal parsing cannot be made robust within the existing bounded repair budget (i.e., plain text fallback keeps being accepted), stop and report that the compactor output contract change needs its own slice."

**Evidence:** Plan §7 Slice 3.

### Finding 8: dispatch.py / engine_ingest.py Hardcoded Empty Fact Refs

**Severity: LOW (non-blocking, overlaps with Finding 2)**
**Location: Plan §7 Slice 5**

Both `dispatch.py:1255-1256` and `engine_ingest.py:2981-2982` construct `CompactionRequest` with hardcoded `tool_fact_refs=()` and `verified_fact_refs=()`. This means the current compaction path never passes existing fact refs to the compactor — the compactor has no way to know what facts already exist.

The plan's Slice 5 mentions updating these constructions but does not address this pre-existing gap. The implementation agent should verify whether this is intentional (compactor always starts from scratch) or a latent bug that P12.5 should fix.

**Evidence:** `dayu/host/dispatch.py:1255-1256`, `dayu/host/engine_ingest.py:2981-2982`.

## 3. Scope Boundary Verification

| Boundary | Status | Notes |
|---|---|---|
| No Engine Agent loop changes | PASS | Plan does not touch Engine. |
| No Runner provider contract changes | PASS | Plan does not touch Runner. |
| No real Fins tool changes | PASS | Plan does not touch `dayu.fins`. |
| No Service/UI workflow public methods | PASS | `host_assembly.py` changes are config mapping only, not public API. |
| No Host command/handle public methods | PASS | Plan explicitly states this in §2 Non-Goals. |
| No `open_host(options)` field changes | PASS | Not mentioned in any slice. |
| No `SubmitFollowupRequest` field changes | PASS | Not mentioned in any slice. |
| No long-term retrieval / vector index | PASS | Explicitly excluded. |
| No compatibility wrappers/re-exports | PASS | Plan §4.1 explicitly forbids. |
| No eager per-tool-result extraction | PASS | Design decision is compaction-gated. |
| No neutral fallback facts | PASS | Plan §4.7 and §7 Slice 3/4 enforce. |

## 4. Design.md Alignment Verification

| Design Requirement | Plan Coverage | Status |
|---|---|---|
| §24: `evidence_backed_facts` only from accepted tool evidence | §1.2, §4.2, §5.1, §7 S2/S4 | PASS |
| §24: Minimum contract is `claim_text + evidence_refs` | §4.3, §4.6 | PASS |
| §24: No neutral fallback fact | §4.7, §7 S3/S4 | PASS |
| §24: `recent_raw_turns_floor` retains name and semantics | §2, §5.5 | PASS |
| §24: `minimum_preserve_items` bounded continuity, not facts | §4.4, §4.6 | PASS |
| §24: RunInputBuilder renders `claim_text + evidence_refs` | §5.6, §7 S5 | PASS |
| §24: Host does not parse source/locator business semantics | §4.2, §7 S2/S3 | PASS |
| §25: Compactor outputs structured JSON proposal with all candidates | §5.3, §7 S3 | PASS (but scope underestimated per Finding 1) |
| §25: Context Governance does not write memory directly | §5.4, §5.5 | PASS |
| §25: `CONTEXT_COMPACTED` payload carries all candidates | §4.5 | PASS |
| §18: Tool fact accept barrier | §5.1, §7 S2 | PASS |
| §18: ToolRuntime submits fact candidate, not final fact | §5.1, §7 S2 | PASS |
| §23: RunInputBuilder stable layer order | §5.6 | PASS |
| §23: RunInputBuilder is only runtime input entry | §7 S5 | PASS |

## 5. Implementation-Control.md Alignment Verification

| Control Requirement | Plan Coverage | Status |
|---|---|---|
| Migrate `VerifiedFactView` to `EvidenceBackedFactView` | §4.1, §7 S1 | PASS |
| Tool result accept path forms accepted evidence envelope | §4.2, §7 S2 | PASS |
| Compaction-gated extraction, no eager extraction | §2, §5.3 | PASS |
| Smoke/integration tests for fact reuse, minimum preserve | §7 S6, §8 | PASS |
| No Engine/Fins/Service/UI scope creep | §2, §10 | PASS |
| pyright validation | §7 (each slice) | PASS |
| README sync | §9 | PASS |

## 6. Slice Quality Assessment

| Slice | Ownership | Tests | Stop Condition | Risk |
|---|---|---|---|---|
| S1: Contract Rename | Clear | Config + assembly tests | Old compat required | Low |
| S2: Evidence Envelope | Clear | Accept barrier + projection | Public API change needed | Low |
| S3: Compaction Candidates | Clear but complex | 4 test files | Second LLM call needed | **High** (Finding 1) |
| S4: Memory Projection | Clear | Projection tests | Business semantics parsing | Medium |
| S5: RunInputBuilder Wiring | Clear | Run input + compaction op | Engine/Runner/UI change | Low |
| S6: Integration Smoke | Clear | All + smoke | Scope violation | Low |

## 7. Residual Risks

1. **LLM extraction quality is model-dependent.** Acknowledged in plan §11. Not a plan defect.
2. **Fine-grained evidence ids deferred.** Acknowledged. P12.5 uses one evidence id per accepted tool result.
3. **Old durable snapshots incompatible.** Acknowledged. Finding 6 adds detail.
4. **Real Fins tool source/locator may be sparse.** Acknowledged. Envelope tolerates empty tuples.
5. **Structured JSON compactor robustness.** This is the primary implementation risk. If the LLM does not reliably produce valid JSON matching the expected schema, the entire P12.5 fact extraction pipeline degrades to "no facts extracted" with diagnostics only. The plan's bounded repair mechanism provides a safety net, but the compactor prompt engineering is untested.

## 8. Verdict

**PASS.** The plan satisfies design.md and implementation-control.md requirements, has clear slice ownership and test assignments, respects scope boundaries, and identifies stop conditions. The findings above are advisory implementation clarifications, not gate blockers.

Implementation should proceed with the following adjustments recommended:

- Finding 1: Explicitly scope the LLM compactor plain-text-to-JSON rewrite as a significant sub-task with its own internal validation step.
- Finding 2: Clarify the CompactionRequest evidence envelope data flow before starting Slice 5.
- Finding 3: Decide provenance sourcing for `EvidenceBackedFactView` before starting Slice 4.
- Finding 7: Add a complementary stop condition for Slice 3 compactor robustness.
