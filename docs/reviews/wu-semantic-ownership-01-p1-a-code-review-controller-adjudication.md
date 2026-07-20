# WU-SEMANTIC-OWNERSHIP-01 P1-A Code Review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A`
- Gate: code review
- P0-A accepted commit: `6731b451`
- P0-B accepted commit: `750af328`
- P1-A accepted plan commit: `fd630672`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p1-a-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p1-a-controller-validation.md`
- Code review artifacts:
  - `docs/reviews/code-review-20260709-p1-a-mimo.md`
  - `docs/reviews/code-review-20260709-p1-a-ds.md`
- Decision date: 2026-07-09

## Decision

`fix-required`

Controller accepts the main implementation direction: `dayu.host.accepted_result_projection` is the correct owner boundary, the consumer migration is broadly complete, and focused validation passed. However, several review items must be fixed before P1-A can proceed to accepted commit because they relate directly to P1-A's plan completion signals and LLM-facing single-source semantics.

## Accepted Findings

### P1A-CR-F01: Conversation Memory legacy fallback still reconstructs accepted result text downstream

- Source: AgentDS P1A-F01.
- Severity: medium.
- Decision: accepted.
- Rationale: `memory.py` should not reconstruct accepted tool evidence from envelope/raw outcome after durable projection fields are absent. Even if intended as historical degradation, it is a consumer-side fallback that can mask current projection drift and conflicts with the plan's "no old schema compatibility branch" direction.
- Required fix:
  - Remove or tighten the `accepted_evidence_envelope_from_payload(...)` / `accepted_tool_raw_outcome_text_from_payload(...)` fallback in Conversation Memory.
  - If projection fields are absent, emit a single limited-signal text or fail closed; do not rebuild query/source/result from payload in `memory.py`.
  - Add or update a focused test proving current accepted-result memory projection uses projection fields and missing projection fields do not trigger downstream reconstruction.

### P1A-CR-F02: Compact pipeline unavailable-query text is a second LLM-facing truth

- Source: AgentDS P1A-F02.
- Severity: low.
- Decision: accepted.
- Rationale: Projection owner now owns `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`. `compact_pipeline.py` still has a separate English unavailable-query fallback string. Even if display-level, the text is LLM-facing and should derive from the same owner.
- Required fix:
  - Replace `_UNAVAILABLE_TOOL_QUERY` with the projection owner constant, or remove the local constant and import `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`.
  - Keep import boundaries clean; do not introduce compatibility re-export.

### P1A-CR-F03: `_arguments_fallback_query(...)` signature suggests a payload fallback that is intentionally disallowed

- Source: AgentDS P1A-F03.
- Severity: low.
- Decision: accepted.
- Rationale: The current helper accepts `payload` and deletes it, obscuring the intentional owner-boundary decision that result payload must not become query source when request atom is unavailable.
- Required fix:
  - Rename or simplify the helper so it no longer accepts unused payload, or document the no-payload-fallback decision at the call site with a concise comment.
  - Preserve the behavior: request atom unavailable must produce projection-owned limited signal, not payload-derived query.

### P1A-CR-F04: Projection helper tests do not cover accepted plan completion signals

- Source: AgentDS P1A-C01.
- Severity: medium.
- Decision: accepted.
- Rationale: The accepted plan explicitly listed identity mismatch, wait-resolution status priority, source filtering, payload descriptor/resolved payload, unsafe argument key, raw outcome `result.ok`, and result details extraction as S1 completion signals. The implementation currently covers only a subset.
- Required fix:
  - Add focused tests for at least:
    - request atom identity mismatch;
    - wait-resolution `resolution_kind` priority over ordinary status;
    - internal source refs filtered from readable source;
    - resolved payload / payload descriptor diagnostic behavior;
    - unsafe argument keys produce limited-signal query;
    - raw outcome `result.ok == false` maps to failed;
    - result details extraction.
  - Use real durable store write/read style, not mock-only shortcuts.

### P1A-CR-F05: Cross-consumer equivalence test is missing

- Source: AgentDS P1A-C02.
- Severity: low.
- Decision: accepted.
- Rationale: P1-A's propagation audit requires proving the same accepted result projects consistently across Trace / Memory / RunInput / CompactMaterial. Current tests cover consumers individually but do not assert equivalence for one shared accepted result.
- Required fix:
  - Add a focused cross-consumer equivalence test or extend an existing test to construct one accepted result and verify equivalent query/status/source/result semantics across at least Tool Trace, Durable/Conversation Memory, RunInputBuilder, and CompactMaterial.
  - Keep the test at production boundary; do not duplicate projection logic in fixture assertions.

## Non-blocking / Rejected Observations

| Observation | Decision | Rationale |
|---|---|---|
| Tool Trace result details logic moved into projection owner | accepted-as-correct | This is the intended owner migration, not a defect. |
| `_accepted_evidence_query_unavailable_text()` local import in `memory.py` | accepted-as-risk-free | Local import is acceptable if it only breaks bootstrap cycle and the constant owner remains `accepted_result_projection.py`. |
| `_contains_unsafe_argument_key` heuristic is not exhaustive | deferred-with-owner | It is projection-owner logic and improves current behavior. Broader sensitive-key taxonomy can be future hardening if needed. |
| `source_note` schema field remains | rejected-with-reason | Field name is schema vocabulary; value must be projection-cleaned. |
| Read API PREVIEW/CANONICAL dispatch | accepted-as-correct | Dispatch boundary matches the accepted plan. |

## Next Gate

Proceed to P1-A code fix by AgentCodex. After fix and validation, send AgentMiMo and AgentDS through narrow re-review of P1A-CR-F01 through P1A-CR-F05 before P1-A can reach accepted commit.
