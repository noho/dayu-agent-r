# Phase 12.5 Plan Review Controller Adjudication

## Context

- Gate: Phase 12.5 plan review.
- Plan: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`.
- Reviews:
  - `docs/reviews/phase12-5-plan-review-mimo-20260522.md`.
  - `docs/reviews/phase12-5-plan-review-ds-20260522.md`.
- Design truth: `docs/host/design.md`.
- Control doc: `docs/host/implementation-control.md`.

## Controller Verdict

Plan review is not yet accepted for local plan commit. Both reviewers returned PASS, but several "non-blocking" findings are plan-quality issues under the current gate's code-generation-ready bar. They should be fixed in the plan before re-review.

Reasoning: P12.5 changes memory truth semantics, compactor output contract and config/schema names. If the plan leaves evidence data flow, provenance source or JSON migration constants to implementation judgment, implementation agents would be forced to redesign cross-module contracts. That violates the plan gate even if the high-level direction is correct.

## Accepted Plan-Fix Items

### A1 — Scope the LLM compactor structured JSON rewrite explicitly

- Source findings: MiMo Finding 1, MiMo Finding 7, DS Finding 5.
- Decision: Accepted.
- Required plan fix:
  - Split the compactor plain-text-to-structured-JSON rewrite into its own slice, or make it an explicit sub-slice with its own tests and stop condition.
  - Plan must state that existing plain-text summary success path is removed or rejected, not silently accepted.
  - Add stop condition: if structured JSON parsing / schema validation cannot work within bounded repair attempts, stop and report to controller.

### A2 — Freeze CompactionRequest accepted evidence data flow

- Source findings: MiMo Finding 2, MiMo Finding 8.
- Decision: Accepted.
- Required plan fix:
  - Specify exact source: Context Governance builds compact input by reading `TOOL_RESULT_ACCEPTED.accepted_evidence_envelope` from the EventLog range covered by the compaction request.
  - Add `accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]` and derived `accepted_evidence_refs: tuple[str, ...]` to `CompactionRequest`.
  - Existing stable fact refs should be renamed to `evidence_backed_fact_refs`; they are separate from accepted evidence refs.
  - `dispatch.py` and `engine_ingest.py` hardcoded empty refs must be replaced by bounded EventLog reads or explicit empty only when the compact input range truly contains no accepted tool evidence.

### A3 — Freeze EvidenceBackedFactView provenance source

- Source finding: MiMo Finding 3.
- Decision: Accepted.
- Required plan fix:
  - `EvidenceBackedFactView.provenance.event_id` and `event_sequence` come from the accepted `CONTEXT_COMPACTED` event that materialized the fact.
  - extraction operation / compact artifact refs come from the compacted payload / artifact metadata, not from the LLM candidate as trusted provenance.
  - `candidate_id` is an item-local id used for diagnostics / dedupe only, not the authoritative event provenance.
  - evidence origin remains in `evidence_refs`, which point to accepted evidence envelopes.

### A4 — Define bounded validation constants

- Source findings: MiMo Finding 4 and minimum preserve validation references in both reviews.
- Decision: Accepted.
- Required plan fix:
  - Define first-version module constants for `claim_text`, minimum preserve `text`, candidate counts and opaque attributes JSON size.
  - Constants should live with Host compaction / memory contract code, not in runtime config.
  - Tests must cover boundary rejection for at least empty and overlong `claim_text`, and overlong minimum preserve text.

### A5 — Expand old-name cleanup list and search criteria

- Source findings: MiMo Finding 5, DS Findings 1, 2, 4, 6.
- Decision: Accepted.
- Required plan fix:
  - Explicitly list cleanup for `MemoryClaimStatus.TOOL_VERIFIED`, `MemoryIncludedReason.TOOL_VERIFIED_FACT`, `CompactQualityIssue.SUMMARY_PRETENDS_VERIFIED_FACT`, `_FIELD_PROPOSED_VERIFIED_FACT_REFS`, old verified JSON codec helpers and durable item kind constants.
  - Extend final stale-term search beyond `verified_facts` to include `VerifiedFact`, `verified fact`, `verified_fact`, `TOOL_VERIFIED`, `PRETENDS_VERIFIED`, `proposed_verified`, `preserved_verified`, `stable:verified` and `max_verified`.

### A6 — Specify old durable snapshot behavior

- Source findings: MiMo Finding 6, DS Finding 4.
- Decision: Accepted.
- Required plan fix:
  - Since project policy is new schema start, old durable memory snapshot JSON / item kind should fail closed with a clear validation error in current readers.
  - Do not silently skip old `verified_fact` items and do not add compatibility reads.
  - Tests should cover old key / old item kind rejection where relevant to current codec.

### A7 — Exhaustively check `preserved_fact_refs` consumers

- Source finding: DS Finding 3.
- Decision: Accepted.
- Required plan fix:
  - Add pre-implementation search step for `preserved_fact_refs`, `tool_fact_refs`, `verified_fact_refs`, `preserved_verified`, `proposed_verified` across `dayu/` and `tests/`.
  - Any consumer not in the plan's affected-file list must either be added to an explicit slice or documented as not consuming the changed semantics.

## Rejected / Deferred Findings

- DS test-location observation for post-compaction gross-margin smoke: rejected as blocker. The plan may allow either `test_run_input_builder.py` or an existing public lifecycle smoke if implementation proves the chosen location has the correct harness. Controller will review actual test coverage in implementation.
- DS `tests/README.md` observation: accepted as documentation caution, not a plan-fix blocker. Implementation must only update `tests/README.md` if test responsibilities or conventions actually change.

## Next Gate

Send plan fix to AgentCodex. After the plan is updated, run re-review with AgentMiMo and AgentDS before creating the accepted plan commit.
