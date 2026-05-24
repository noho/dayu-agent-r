# P12.6 Design Review Controller Adjudication And Fix

## Gate

P12.6 design refinement review.

## Reviewed Artifacts

- `docs/reviews/p12-6-design-review-mimo-20260524.md`
- `docs/reviews/p12-6-design-review-ds-20260524.md`
- `docs/reviews/p12-6-design-refinement-controller-20260524.md`
- `docs/host/design.md` §24 and §25

## Controller Judgment

Both reviews passed the design direction but identified real design-truth gaps. Based on the Host design goal and first principles,
these findings should not be left to the planning agent as open design choices because they control the exact compact I/O root cause
that P12.6 exists to fix.

## Accepted Findings And Fixes

### Accepted: compact segment boundary is under-specified

Decision: accepted.

Reason: Phase 12.6 must remove Session-start EventLog range dump. Without deterministic compact segment selection, an implementation
agent could reintroduce the same root cause.

Fix: `docs/host/design.md` now defines compact segment selection from ordinary run input material list or reactive overflow material
list, with proactive / reactive upper and lower boundaries, block-based selection, and deterministic traceable output.

### Accepted: material pack section mapping is under-specified

Decision: accepted.

Reason: The material pack only prevents duplication if each canonical content item has one LLM-facing section owner.

Fix: `docs/host/design.md` now defines one-to-one section mapping for `stable_input`, `history_input`, `evidence_input` and
`current_input_anchor`, including the rule that accepted tool result raw content appears only in `evidence_input`.

### Accepted: accepted evidence raw data path is ambiguous

Decision: accepted with corrected implementation-independent wording.

Reason: The reviewer correctly identified ambiguity, but the design should not require raw result bytes to live inside the EventLog
row. The stable contract is that raw evidence comes through the canonical `TOOL_RESULT_ACCEPTED` fact and its digest-checked Host
payload / raw result descriptor, not through a lossy evidence envelope preview.

Fix: `docs/host/design.md` now states that accepted evidence envelope is provenance metadata and not a result-content container.

### Accepted: long-session consolidation V1 owner is ambiguous

Decision: accepted.

Reason: P12.6 requires bounded memory semantics, but V1 does not need to add a new compactor retention-intent schema before plan gate.

Fix: `docs/host/design.md` now states that V1 consolidation is owned by memory projection policy and bounded selection; future
`memory_retention_candidate` remains optional and Host-accepted.

### Accepted: reactive multi-pass durable submission is ambiguous

Decision: accepted.

Reason: Partial `CONTEXT_COMPACTED` commits would let memory projection consume a failed operation's intermediate output.

Fix: `docs/host/design.md` now states that reactive multi-pass is one compaction operation, intermediate pass output is transient,
and only one merged `CONTEXT_COMPACTED` or one final `CONTEXT_COMPACTION_FAILED` is committed.

### Accepted: memory snapshot cursor handling for compaction is missing

Decision: accepted.

Reason: Compactor `stable_input` must not be based on stale memory without repair, and memory lag must not become Run recovery.

Fix: `docs/host/design.md` now requires snapshot cursor validation and catch-up / rebuild or inline delta repair before material pack
build.

### Accepted: episode summary bounded rendering wording is vague

Decision: accepted.

Reason: Episode summaries are history pool input, but all older summaries cannot be blindly rendered into compactor input.

Fix: `docs/host/design.md` now limits `history_input` episode summaries to segment-generated and policy-bounded recent summaries.

## Deferred To Planning

The following are implementation strategy details and should be mandatory plan requirements, not unresolved design blockers:

- whether to keep the current `CompactionRequest` shape with a material pack builder or refactor it to a material-pack-oriented
  contract;
- exact deterministic algorithm for current input anchor short text / digest;
- V1 relevance strategy for bounded evidence-backed fact working set;
- edge handling for a single evidence block that exceeds compactor budget.

## Re-review Request

Re-review should verify that the accepted findings above are fixed in `docs/host/design.md` and that no new public API drift, Engine
dependency, Fins leakage, extra payload escape hatch or over-designed retention system was introduced.
