# WU-SEMANTIC-OWNERSHIP-01 P3-I S2 Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub-WU: `P3-I`
- Slice: `S2 CLI Terminal Cursor After Successful Render`
- Reviewed implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-ds.md`

## Owner Boundary

- Fact producer: Host/Service terminal result remains the source of truth for terminal status, terminal event id, event sequence, final answer, error, cancel reason, and lost-run reason.
- Validator/projector: CLI terminal renderers decide terminal presentation and renderer exit code from Host/Service terminal facts.
- Durable local delivery state: CLI terminal cursor store persists which terminal event has been successfully delivered locally.
- User-visible output: CLI stdout/stderr is derived from renderer output; cursor persistence must not rewrite Host/Service terminal facts or renderer exit-code policy.

## Findings Adjudication

### DS-F1: Interactive `terminal is None` path lacks explicit cursor non-advancement assertion

- Source: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-ds.md`
- Severity: low
- Decision: accepted
- Reasoning: code behavior is already correct, but the invariant belongs to the CLI cursor boundary and should be guarded by a direct regression test.
- Fix target: `tests/cli/test_interactive_command.py`

### DS-F2: Cursor write failure propagation path lacks tests

- Source: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-ds.md`
- Severity: low
- Decision: accepted
- Reasoning: plan intentionally keeps cursor write failures uncaught as local CLI delivery persistence failures. That contract should be tested at all three S2 call sites.
- Fix target:
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_interactive_command.py`

### MiMo

- Source: `docs/reviews/wu-semantic-ownership-01-p3-i-s2-code-review-mimo.md`
- Decision: no material findings.

## Controller Decision

S2 is not accepted until DS-F1 and DS-F2 are fixed and re-reviewed. The fixes must stay in tests and must not change Host/Service facts, renderer policy, or cursor store semantics.
