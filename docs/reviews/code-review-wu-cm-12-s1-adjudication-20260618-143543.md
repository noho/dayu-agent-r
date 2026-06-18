# WU-CM-12 S1 Code Review Adjudication

## Scope

- Work unit: WU-CM-12 Conversation Memory design refinement and implementation drift repair
- Gate: code review
- Slice: S1 Material Block And Policy Owner Convergence
- Reviewed artifacts:
  - `docs/reviews/code-review-20260618-142551.md`
  - `docs/reviews/code-review-20260618-143243.md`

## Verdict

- AgentDS: accepted 1 finding, deferred 1 pre-existing finding.
- AgentMiMo: no material findings.
- Controller verdict: fix required before S1 acceptance.

## Accepted Findings

### DS-F1 accepted

- Finding: `_facts_from_accepted_event` loses previously accumulated oversized-fact budget diagnostics when a later fact candidate has empty evidence labels.
- Evidence: S1 introduced a local `diagnostics` accumulator for oversized facts, but the empty-label early return rebuilt the diagnostics tuple from only `_fact_candidate_invalid_diagnostic(...)`.
- Required fix: preserve accumulated diagnostics in that early return and add a mixed oversized + empty-label regression fixture.

## Deferred Findings

### DS-F2 deferred-with-owner

- Finding: the same empty-label early return drops previously accumulated valid facts.
- Reason: this behavior predates S1 and changes the semantic contract from "invalid candidate invalidates fact materialization for this compact event" to "skip invalid candidate and keep valid candidates." The accepted S1 design only covers no silent truncation, whole-item budget drop, diagnostics preservation, and `turn_group_id`; it does not decide mixed valid/invalid fact selection semantics.
- Owner: WU-CM-12 follow-up during S3 provenance guard / compact fact rendering review, where invalid candidate handling can be decided against the full selected-id provenance contract.

## Fix Dispatch

- Owner: AgentCodex.
- Required artifact: `docs/reviews/wu-cm-12-s1-fix-codex-20260618.md`.
- Required validation:
  - targeted mixed diagnostic regression test;
  - affected Host tests;
  - focused pyright for changed files.
