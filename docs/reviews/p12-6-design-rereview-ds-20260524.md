# P12.6 Design Re-Review — DS Verification Of Accepted Finding Fixes

## Re-Review Metadata

- **Re-Reviewer**: DS (Design Reviewer)
- **Target**: Controller-accepted finding fixes applied to `docs/host/design.md` §24 and §25
- **Gate**: Design re-review, not implementation
- **Timestamp**: 2026-05-24T20:30:00+08:00
- **Prior artifacts**:
  - `docs/reviews/p12-6-design-review-ds-20260524.md` (DS independent review, 4 findings)
  - `docs/reviews/p12-6-design-review-mimo-20260524.md` (MiMo independent review, 4 findings)
  - `docs/reviews/p12-6-design-review-controller-adjudication-20260524.md` (Controller adjudication, 7 accepted findings)
- **Truth sources**: `docs/host/design.md` §1, §24, §25; `docs/host/implementation-control.md` Phase 12.6

## Scope

Verify that the seven controller-accepted findings are correctly fixed in `docs/host/design.md`, and that the fixes do not introduce:

1. New public API drift
2. Engine dependency
3. Fins / tool-provider leakage
4. Extra payload escape hatch
5. Overdesigned retention system
6. Contradiction with Host governance boundaries

## Fix Verification

### Fix 1: Compact Segment Boundary (DS F1 / Controller Item 1)

**Design location**: §25 lines 2754-2766

**Verification**: The new text defines compact segment as a collection of compressible material blocks selected from ordinary run input material list or reactive overflow material list. It specifies:
- Proactive upper bound: ordinary input excluding `current_input_anchor` and protected recent raw turns floor
- Proactive lower bound: oldest material block not yet sufficiently represented by accepted compact output
- Reactive: frozen overflow material list, older prefix priority
- Block-based selection, not round-count-based
- Deterministic output given input cursor, memory snapshot cursor, policy, and material list

**Verdict**: Fixed. The segment selection rules are deterministic, testable, and prevent EventLog range dump reintroduction.

### Fix 2: Material Pack Section Mapping (MiMo 01 / Controller Item 2)

**Design location**: §25 lines 2768-2779

**Verification**: The new text defines one-to-one section mapping:
- `stable_input` ← memory snapshot bounded stable layer view only
- `current_input_anchor` ← bounded anchor from current `USER_INPUT_ACCEPTED`; same payload not repeated in `history_input`
- `history_input` ← user/assistant continuity and non-evidence raw turns; accepted tool result raw content NOT repeated here
- `evidence_input` ← accepted tool evidence blocks only

**Verdict**: Fixed. The mapping prevents content duplication across sections. Implementation agent cannot inadvertently render the same canonical content in two LLM-facing sections.

### Fix 3: Accepted Evidence Raw Data Path (DS F2 / Controller Item 3)

**Design location**: §25 lines 2775-2779

**Verification**: The text now explicitly states:
- Raw evidence content comes from `TOOL_RESULT_ACCEPTED` canonical fact's digest-checked Host payload / raw result descriptor
- Accepted evidence envelope provides only evidence id, query/provenance mapping, and source locator metadata
- Envelope is NOT a lossy result preview or fact content container

The controller wisely corrected the wording from "read from EventLog row" to "read from canonical fact's digest-checked descriptor" — this is implementation-independent while preserving the correct data flow direction (canonical fact → raw result, not envelope → artifact store).

**Verdict**: Fixed. No ambiguity remains. Implementation agent cannot mistakenly route through artifact store.

### Fix 4: Long-Session Consolidation V1 Owner (MiMo 02 / Controller Item 4)

**Design location**: §24 lines 2592-2595

**Verification**: The text now states:
- V1 consolidation is executed by memory projection policy and RunInputBuilder / compactor input bounded selection
- V1 does NOT require compactor to output independent `memory_retention_candidate`
- Future retention intent remains optional, Host-accepted, consumed by memory projection policy
- LLM cannot directly rewrite memory truth

**Verdict**: Fixed. V1 consolidation path is clear: policy-driven bounded selection, no new compactor output schema, no overdesigned retention system.

### Fix 5: Reactive Multi-Pass Durable Submission (DS F3 / Controller Item 5)

**Design location**: §25 lines 2802-2807

**Verification**: The text now states:
- Reactive multi-pass is one compaction operation
- Does NOT append additional `CONTEXT_COMPACTION_REQUESTED`
- Does NOT separately consume `max_reactive_compactions_per_run`
- Each pass's external LLM proposal consumes `max_compaction_attempts_per_operation` budget
- Intermediate pass output is operation-level transient artifact only
- Host commits one merged `CONTEXT_COMPACTED` after all required passes pass quality/budget gate
- If intermediate pass fails and repair budget exhausted, entire operation writes one final `CONTEXT_COMPACTION_FAILED`
- No orphaned partial compacted events; memory projection does not consume intermediate output

**Verdict**: Fixed. Durable semantics are unambiguous. No partial-commit inconsistency possible.

### Fix 6: Memory Snapshot Cursor Handling For Compaction (MiMo 04 / Controller Item 6)

**Design location**: §25 lines 2781-2783

**Verification**: The text now requires:
- Snapshot cursor validation before material pack build starts
- If cursor cannot cover EventLog cursor needed for `stable_input` and compact segment, Host must first execute memory projection catch-up/rebuild or inline delta repair within policy limits
- Failure closes as compaction failure / pre-dispatch failure
- This is NOT Run crash recovery; Run must not enter `RECOVERING`

**Verdict**: Fixed. Compaction operation now has the same cursor validation discipline as RunInputBuilder.

### Fix 7: Episode Summary Bounded Rendering (DS F4 / Controller Item 7)

**Design location**: §25 lines 2746-2748

**Verification**: The text now limits `history_input` episode summaries to:
- Segment-generated (new) episode summaries
- Policy-bounded recent episode summaries
- Older summaries beyond policy limit or unrelated to current segment: only artifact/EventLog refs retained

This aligns with §24 line 2590's bounded rendering principle.

**Verdict**: Fixed. Episode summary accumulation in compactor input is bounded by policy.

## Boundary Integrity Check

### Public API Drift

No public API changes. All design refinements are Host-internal: material pack builder, compactor typed port, memory projection policy, Context Governance orchestration. Phase 12.6 scope explicitly prohibits modification of `Host.handle()`, `SubmitFollowupRequest` fields, `open_host(options)` fields, and Service/UI workflow.

**Verdict**: Clean. No drift.

### Engine Dependency

The design consistently states Context Governance is Host responsibility. Engine does not understand Host compaction attempt state machine. The reactive path consumes Engine's `context_compaction_requested` event, but this is an existing Engine→Host event flow, not a new dependency direction. Engine provider/transport retry is separate from Host semantic repair.

**Verdict**: Clean. No new Engine dependency.

### Fins / Tool-Provider Leakage

Tool provider only produces `TOOL_RESULT_ACCEPTED`. Fact extraction is Host-governed LLM compactor work. Material pack reads raw evidence from canonical facts, not from Fins storage. `evidence_id` is Host-generated at accept barrier, not by tool provider. The design explicitly says "不让 tool provider 生成 memory facts."

**Verdict**: Clean. No Fins leakage.

### Extra Payload Escape Hatch

`context_window_size` and `reserved_output_tokens` are explicit typed inputs from Service/composition root. Host does not read budget from per-run metadata or extra payload. §25 line 2675-2676 explicitly forbids this.

**Verdict**: Clean. No extra payload escape hatch.

### Overdesigned Retention

V1 consolidation is policy-driven bounded selection in memory projection, not a separate retention system with its own schema, compactor output, or LLM intent. `memory_retention_candidate` is explicitly deferred to future, optional, and Host-gated. No new `RetentionPolicy`, `RetentionIntent`, or `MemoryRetentionManager` abstractions.

**Verdict**: Clean. No overdesigned retention.

### Host Governance Boundaries

The relationship chain is one-way:
1. EventLog canonical facts (truth source)
2. Memory projection consumes canonical facts → memory snapshot (read model)
3. Context Governance reads memory snapshot → makes budget/compact decisions → writes `CONTEXT_COMPACTED` canonical facts
4. Memory projection consumes `CONTEXT_COMPACTED` → updates memory snapshot

Context Governance does not directly write memory snapshot. LLM produces candidates; Host validates and accepts. No circular dependency, no LLM direct memory write, no bypass of accept barrier.

**Verdict**: Clean. Host governance boundaries intact.

## Residual Observations

### RO1: Multi-Pass Budget Collapses Two Concepts

The design folds material-block pass proposals and semantic repair attempts into a single `max_compaction_attempts_per_operation` budget. This means each material block pass consumes at least 1 from the budget, and any repair on that pass consumes more. With a default budget, many-block sessions could exhaust the budget before all blocks are processed. However, this is a deliberate design choice — the budget is a true hard limit on LLM calls — and the reactive path's fail-closed semantics handle the exhaustion case correctly.

**Severity**: Observation only. Not a finding. The fail-closed behavior is correct; the budget just gates how much work can be done before failing closed.

### RO2: "充分代表" (Sufficiently Represented) In Segment Lower Bound

The proactive segment lower bound uses the phrase "已被 accepted compact output 的 stable layer / episode summary 充分代表的 material block" (§25 line 2759-2760). "充分代表" is qualitative. However, the deterministic output requirement on lines 2765-2766 compensates: given the same inputs, segment selection must produce the same block ids. The implementation must make this judgment rule-based (e.g., "a material block is sufficiently represented if its entire event_sequence range is covered by at least one accepted episode summary or stable fact with a later event_sequence"). The planning agent should pin down the exact rule.

**Severity**: Observation only. Not a finding. Deterministic output requirement provides adequate constraint.

## Conclusion

**PASS** — All seven controller-accepted findings are correctly fixed in `docs/host/design.md` §24 and §25. The fixes do not introduce public API drift, Engine dependency, Fins leakage, extra payload escape hatch, overdesigned retention, or contradiction with Host governance boundaries.

The design is ready for plan gate handoff. The four items deferred to planning by the controller (CompactionRequest shape decision, current input anchor digest algorithm, V1 relevance strategy, single evidence block edge handling) remain appropriate planning-level concerns, not design blockers.

No remaining findings.
