# WU-SEMANTIC-OWNERSHIP-01 P3-A S1 code review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A`
- Slice: S1 - Lifecycle/status owner helpers
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-controller-validation.md`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s1-code-review-ds.md`

## Verdict

S1 is not accepted yet. Both reviewers reported `pass-with-findings` with zero blockers, but the medium finding about Attempt durable terminal events versus closeout-supported terminal events must be fixed before S2 starts.

Next gate is S1 fix by AgentCodex.

## Accepted Findings

### S1-F01 [medium] Attempt terminal helper needs durable-terminal versus closeout-supported clarity

Sources:

- AgentMiMo 001
- AgentDS 1

Disposition: accepted.

Rationale:

- S1 correctly reflects durable Attempt terminal truth: `SUSPENDED` and `STEERED` are terminal Attempt statuses.
- However, P3-A S2/S3 closeout migration must not treat all Attempt terminal statuses as Run/Attempt terminal closeout-supported pairs. `SUSPENDED` maps to Run `WAITING`; `STEERED` follows steer-specific lifecycle.
- The owner helper and docs/tests must make this distinction explicit before S2 consumes the helper.

Required fix:

- Add a closeout-supported Attempt terminal subset or equivalent fail-fast helper / doc-test boundary.
- Make `SUSPENDED` and `STEERED` explicit durable terminal but not closeout-supported statuses.
- Add tests preventing S2 from treating `SUSPENDED` / `STEERED` as closeout-supported by accident.

### S1-F02 [low] Terminal predicate tests should name the predicates explicitly

Sources:

- AgentMiMo 002

Disposition: accepted.

Required fix:

- Add or rename tests so `is_terminal_run_status` and `is_terminal_attempt_status` are explicitly covered by test names/docstrings.

### S1-F03 [low] `serialized_run_status_values` frozenset ordering should be explicit

Sources:

- AgentMiMo 003

Disposition: accepted.

Required fix:

- Add a focused assertion for unordered frozenset input such as `frozenset({RunStatus.LOST, RunStatus.SUCCEEDED})`, proving output follows `RunStatus` definition order.

### S1-F04 [low] Lifecycle event module/class docstrings should reflect Attempt ownership

Sources:

- AgentDS 2, 3

Disposition: accepted.

Required fix:

- Update module docstring to include Attempt terminal event type ownership.
- Clarify `HostAttemptEventType` is terminal-only in P3-A and non-terminal Attempt event ownership remains residual/future EventLog hardening scope.

## Next Gate

S1 fix by AgentCodex.

Allowed files:

- `dayu/host/lifecycle_events.py`
- `dayu/host/durable/state.py` only if needed for the closeout-supported helper
- `tests/host/test_lifecycle_events.py`
- `tests/host/test_state_schema.py`
- `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-codex.md`

Required validation:

- Focused S1 tests
- Import-cycle validation
- Pyright
- `git diff --check`
