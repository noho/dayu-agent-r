# WU-SEMANTIC-OWNERSHIP-01 P2-D implementation review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-D`
- Gate: implementation review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-implementation-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p2-d-implementation-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-d-implementation-review-ds.md`

## Decision

P2-D implementation is accepted with no required fix gate.

AgentMiMo and AgentDS both concluded `pass` and reported no material finding.
The implementation fixes the accepted public compact smoke residual at the
shared accepted-result projection owner:

- `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` is defined only in
  `dayu/host/accepted_result_projection.py`.
- `AcceptedToolResultSourceProjection.text` is now non-optional `str`.
- `state` and `diagnostic_reason` still distinguish envelope missing from
  business source unavailable.
- Compact material, memory, RunInputBuilder and Tool Trace do not add downstream
  source fallback text.
- Internal refs and Host / ToolRuntime governance terms are not used as
  LLM-facing source.
- The public smoke `selected_recent_window_turn_floor=0` override is accepted
  as test-goal setup for immediate evidence compaction and does not change
  production selection policy.

## Controller Validation

Controller reran and passed:

- targeted public compact smoke: `1 passed`
- accepted-result projection tests: `13 passed`
- compact material / RunInputBuilder / memory tests: `206 passed`
- Tool Trace tests: `46 passed`
- pyright: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed
- source-leak scan: no leak in source-unavailable LLM-facing text

## Residuals

Tool Trace does not expose source text by design. P2-D does not close the
umbrella WU or other full-repository semantic ownership backlog items.
