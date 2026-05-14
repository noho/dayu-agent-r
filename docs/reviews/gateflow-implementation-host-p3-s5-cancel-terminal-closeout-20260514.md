# Gateflow Implementation Artifact: Host Phase 3 P3-S5 Cancel And Terminal Closeout Orchestration

- **gate**: implementation
- **work-unit**: Host Phase 3 Session / Run / Attempt admission state machine
- **slice**: P3-S5 Cancel And Terminal Closeout Orchestration
- **approved plan**: `docs/host/phase3-session-run-attempt-admission-plan.md` P3-S5
- **baseline**: `f45dc3f`
- **branch**: `feat/host-phase3-admission-state-machine`

## Scope

Allowed production files:

- `dayu/host/admission.py`
- `dayu/host/durable/run_transition.py`

Allowed test files:

- `tests/host/test_admission_queue.py`
- `tests/host/test_run_attempt_transitions.py`

Artifact file:

- `docs/reviews/gateflow-implementation-host-p3-s5-cancel-terminal-closeout-20260514.md`

Explicit non-goals preserved:

- No Engine/Fins/Service/UI/runtime changes.
- No active worker cancel propagation.
- No wait cancellation.
- No recovery cancellation.
- No session-scope cancel facade.
- No public facade, scheduler, lane, WorkerProxy, or Engine dispatch.

## Implementation Summary

- Added admission-level `cancel_run(...) -> CancelRunResult`.
- Added admission-level `closeout_attempt_terminal(...) -> TerminalCloseoutResult`.
- Added typed internal input/result dataclasses for terminal closeout and cancel orchestration.
- Bound cancel idempotency to `(run_id, client_request_id)` with `CANCEL_REQUESTED` as first event ref.
- Implemented queued cancel path:
  - appends `CANCEL_REQUESTED`;
  - appends `RUN_CANCELLED`;
  - updates Run to `CANCELLED`;
  - creates no Attempt.
- Implemented pre-dispatch STARTING cancel path:
  - requires `Run RUNNING + Attempt STARTING + dispatch pending`;
  - appends `CANCEL_REQUESTED`, `ATTEMPT_CANCELLED`, `RUN_CANCELLED`;
  - marks dispatch record `cancelled`;
  - marks Attempt `CANCELLED`;
  - marks Run `CANCELLED`;
  - does not notify WorkerProxy or dispatch the cancelled Attempt.
- Implemented commit-after-release promotion orchestration:
  - active cancel and terminal closeout commit first;
  - then wake queue promotion and call `promote_next_queued_run` in a new transaction;
  - promotion reuses existing CAS/FIFO behavior and may skip if another process wins.
- Tightened Phase 3 terminal preconditions in durable transition helper:
  - terminal closeout now requires `Run RUNNING` and `Attempt STARTING`;
  - `WAITING`, `RECOVERING`, `CANCELLING`, and `Attempt RUNNING` return `invalid_state` in this phase.
- Terminal closeout supports matched `succeeded`, `failed`, and `lost` facts; cancellation terminal remains owned by cancel path.

## Tests Added Or Updated

- Admission queue tests now cover:
  - queued cancel writes no Attempt and is idempotent;
  - pre-dispatch active cancel cancels dispatch/Attempt/Run and promotes exactly one queued Run;
  - terminal closeout promotes exactly one queued Run after commit;
  - terminal Run cancel returns `invalid_state` and appends no new facts;
  - Attempt `RUNNING` cancel returns `invalid_state` in Phase 3;
  - rollback before cancel commit does not invoke wakeup or promotion.
- Durable transition tests now cover:
  - terminal closeout failure and lost concrete terminal facts;
  - Attempt `RUNNING` terminal closeout returns `invalid_state`.

## Validation

Executed:

```bash
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q
```

Result:

- `29 passed in 0.27s`

Executed:

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result:

- `0 errors, 0 warnings, 0 informations`

Executed:

```bash
git diff --check
```

Result:

- passed with no output

## Docs Decision

`dayu/host/` production code changed, so `dayu/host/README.md` would normally be reviewed under the repository README trigger rules. This work unit explicitly restricted editable files to the two production files, two test files, and this implementation artifact, so no README was modified in this slice. The implemented behavior remains internal Phase 3 orchestration and does not add a public facade.

## Plan Gaps

No blocking plan gaps found. The plan references dispatching / waiting-for-lane as unsupported or future-owned states; current Phase 3 schema only represents dispatch `pending` / `cancelled`, so tests cover the available unsupported Attempt `RUNNING` state and terminal Run rewrite rejection.

## Residual Risks

- Multi-process cancel/promotion race hardening remains assigned to P3-S6, per plan.
- Active worker cancel propagation, dispatching cancel, wait cancellation, and recovery cancellation remain future phase work.
- README synchronization is intentionally not performed because of the user's file-scope constraint.

## Completion Status

Implementation slice complete.
