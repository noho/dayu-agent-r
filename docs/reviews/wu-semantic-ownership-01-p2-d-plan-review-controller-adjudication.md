# WU-SEMANTIC-OWNERSHIP-01 P2-D plan review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-D`
- Gate: plan review
- Plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-codex.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p2-d-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-d-plan-review-ds.md`

## Decision

P2-D plan is accepted for fix. Implementation must not start until the accepted
plan findings below are patched and re-reviewed.

## Accepted Findings

### P2D-PLAN-F01: consumer inventory must include durable memory projection

- Source: AgentDS `DS-F01`.
- Severity: MEDIUM.
- Decision: accepted.
- Evidence: `dayu/host/durable/memory.py` consumes `projection.source.text` and
  writes `_MemoryProjectionPayloadView.evidence_source_text`, but the plan's
  production affected-file inventory does not list it.
- Required plan fix: add `dayu/host/durable/memory.py` to affected production
  modules as a no-behavior-change consumer that must be validated for
  source-unavailable projection semantics.

### P2D-PLAN-F02: memory source docstring sync must be explicit

- Source: AgentMiMo `F-01`.
- Severity: LOW.
- Decision: accepted.
- Evidence: memory projection still uses optional `evidence_source_text` fields
  for non-accepted-result paths, but accepted-result normal path should receive
  non-empty source text from the projection owner after P2-D.
- Required plan fix: explicitly require implementation to check and, if needed,
  update memory projection docstrings so developers do not infer accepted-result
  source may remain `None` in the normal projection path.

### P2D-PLAN-F03: source-leak scan must include tests that assert the contract

- Source: AgentDS `DS-F03`.
- Severity: LOW.
- Decision: accepted.
- Evidence: the plan's optional source scan covers production projection but
  should also cover test assertions to avoid accidentally blessing internal refs
  in expected LLM-facing source text.
- Required plan fix: update the scan guidance to cover both
  `dayu/host/accepted_result_projection.py` and
  `tests/host/test_accepted_result_projection.py`.

## Non-blocking Notes

- AgentMiMo `F-02` and AgentDS `DS-F02` are accepted as implementation notes, not
  plan blockers. Implementation may keep or refine the source-unavailable
  wording if it stays business-neutral and self-explaining, and must make the
  final README decision after reading the target README update constraints.

## Next Gate

AgentCodex must patch the plan artifact only, produce a plan-fix artifact, and
then AgentMiMo / AgentDS must re-review the fixed plan before implementation.
