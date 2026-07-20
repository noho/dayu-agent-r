# WU-SEMANTIC-OWNERSHIP-01 P2-C implementation review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-C`
- Gate: implementation review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-review-ds.md`

## Owner Boundary

P2-C changes the Engine `AgentPolicy` contract so `fallback_prompt` and
`continuation_prompt` become caller-resolved required LLM-facing text. The
semantic owner boundary is:

1. Runtime/config owner resolves profile-scoped prompt text.
2. Service assembly owner passes resolved prompt text into Engine policy.
3. Host durable restore owner preserves the explicit prompt fields.
4. Engine contract owner validates only presence and non-blank text; it does
   not own any LLM-facing default prompt text.
5. Engine contract tests own regression coverage for required prompt fields and
   blank prompt rejection.

Accepted fixes must therefore land in the Engine contract test boundary unless
reviewers show direct evidence of a production propagation bug.

## Review Decision

### P2C-IMPL-F01: `continuation_prompt` blank-value test coverage is asymmetric

- Source: AgentMiMo F01.
- Severity: LOW.
- Decision: accepted.
- Evidence: `tests/engine/test_agent_phase3_tool_call.py::test_agent_policy_rejects_invalid_values` covers `fallback_prompt` blank values with `("", "   ", "\n\t")`, but covers `continuation_prompt` only with a single blank string case.
- Root cause: test migration did not keep the two required LLM-facing prompt fields symmetric after `continuation_prompt` became explicit required contract input.
- Required fix: replace the single `continuation_prompt=" "` negative case with a loop over the same invalid blank-value set used for `fallback_prompt`.
- Production change required: no.

### AgentDS material findings

- Decision: none accepted.
- Evidence: AgentDS concluded `pass` with no material finding. Residual notes are either already known umbrella risks or explicit future-product decisions.

### Broad suite failure classification

- Decision: controller classification accepted.
- Evidence: both review agents independently confirmed the eight broad-suite failures are not P2-C-introduced and are not owned by P2-C. The known public compact smoke failure remains an umbrella residual to handle before final closeout.

## Required Next Gate

AgentCodex must fix `P2C-IMPL-F01`, rerun focused Engine contract tests,
pyright, and `git diff --check`, then produce a fix artifact. Controller will
rerun validation and send the fix to AgentMiMo / AgentDS re-review before
accepting the implementation.
