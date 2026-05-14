# Host Phase 3 Plan Re-Review Controller Adjudication

- **gate name**: Phase 3 plan re-review / controller adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **plan path**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **review artifacts**:
  - `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-mimo-20260514.md`
  - `docs/reviews/gateflow-plan-re-review-host-p3-session-run-attempt-admission-mimo-20260514.md`
- **fix artifact**: `docs/reviews/gateflow-plan-fix-host-p3-session-run-attempt-admission-codex-20260514.md`
- **artifact path**: `docs/reviews/gateflow-plan-re-review-host-p3-session-run-attempt-admission-controller-adjudication-20260514.md`

## Finding Final Status

### F1

- **controller decision**: accepted
- **final status**: fixed
- **evidence**: AgentMiMo plan re-review confirms `submit_followup(queue)` no-active path now appends `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_STARTED(start_reason=initial)` and `ATTEMPT_STARTED`, and P3-S4 tests assert the four canonical facts in EventLog order.

### F2

- **controller decision**: accepted
- **final status**: fixed
- **evidence**: AgentMiMo plan re-review confirms `submit_followup_queue` idempotency now distinguishes active and no-active creation paths while sharing `USER_INPUT_ACCEPTED` as first event ref, with retry behavior specified for both paths.

### F3

- **controller decision**: accepted
- **final status**: fixed
- **evidence**: AgentMiMo plan re-review confirms `resolved_execution_target` is now an explicit Phase 3 internal admission input for follow-up queue, is persisted to `host_runs.execution_target`, is not inferred from metadata or active Run state, and does not introduce Phase 4 policy provider implementation.

## Residual Risk Tracking

- `resolved_execution_target` retry semantics are intentionally stable: same idempotency key and same semantic digest return the first persisted Run even if a later policy/default would resolve a different target. Owner: Phase 4 Host Public API Command Path, which must record or diagnose policy resolution refs when wiring public command path policy resolution.

## Gate Decision

- **blocking findings**: 0
- **unresolved accepted findings**: 0
- **deferred findings**: 0
- **decision**: Phase 3 plan gate passed; create accepted plan commit and proceed to implementation gate.
