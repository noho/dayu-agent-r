# A4 Code Review Controller Adjudication

- **Date**: 2026-05-14
- **Gate**: full repository review fix work unit A4
- **Scope**: Engine parser/provider robustness
- **Source adjudication**: `docs/reviews/repo-review-controller-adjudication-20260514.md`
- **Implementation artifact**: `docs/reviews/repo-review-fix-a4-engine-parser-provider-robustness-20260514.md`
- **Code review artifacts**:
  - `docs/reviews/repo-review-code-review-a4-engine-parser-provider-robustness-mimo-20260514.md`
  - `docs/reviews/repo-review-code-review-a4-engine-parser-provider-robustness-glm-20260514.md`

## Decision

A4 is accepted.

Both MiMo and GLM reviewed the current unstaged A4 diff against the controller-accepted
A4 items and reported no substantive finding. The implementation stays inside the
accepted parser/provider hardening scope:

- `run_agent_and_wait` now reuses `TERMINAL_ENGINE_EVENT_TYPES`.
- Closed-union `match` sites in OpenAI payload and reasoning protocol now have
  `assert_never` guards.
- Context overflow marker detection covers bounded 5xx error bodies.
- `ClientPayloadError` documentation now matches the existing `NETWORK_ERROR`
  classification.
- `payload.py` no longer lazy-imports `json`.
- Exception diagnostic truncation now adds an explicit marker while preserving the
  `_EXCEPTION_MESSAGE_MAX_LENGTH` body invariant.
- SSE non-object choices now produce diagnostic logs without changing parser behavior.
- Non-stream parser dead `fatal_emitted` state was removed.
- Touched helpers have complete Chinese docstrings.

The malformed `usage` behavior remains unchanged by design. `GeminiToolCallState`,
public provider-state contracts, runner factory/provider injection, config JSON
findings, and other accepted work units were not changed.

## Review Decisions

- **MiMo**: pass, no findings.
- **GLM**: pass, no findings.

GLM's initial artifact omitted an explicit `Verdict` section even though the pane
conclusion was pass; GLM appended the missing verdict in the same scoped review
thread without modifying code or other artifacts.

## Validation Evidence

Reviewer validation:

- MiMo: targeted A4 test set -> 64 passed.
- MiMo: `python -m pyright dayu/engine tests/engine` -> 0 errors.
- GLM: targeted A4 test set -> 64 passed.
- GLM: `pytest tests/engine/runners/openai -q` -> 187 passed.
- GLM: `python -m pyright dayu/engine tests/engine` -> 0 errors.
- GLM: `git diff --check` -> passed.

Controller validation:

- `pytest tests/engine/runners/openai/test_context_overflow_classifier.py tests/engine/runners/openai/test_http_error_classification.py tests/engine/runners/openai/test_protocol_error.py tests/engine/test_agent_phase2.py -q` -> 64 passed.
- `pytest tests/engine/runners/openai -q` -> 187 passed.
- `python -m pyright dayu/engine tests/engine` -> 0 errors.
- `git diff --check` -> passed.

## Residual Risk

No blocking A4 residual risk remains.

Known non-blocking residuals:

- 5xx context overflow detection still depends on the runner having already read the
  bounded error body text.
- SSE non-object choices keep the existing skip behavior and only add diagnostics.
- Malformed `usage` handling still requires a separate design decision before any
  protocol strictness change.

## Next Work Unit

After the A4 accepted commit, continue with A2 Host liveness hardening unless the
controller records a different queue order.
