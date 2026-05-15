# Host Phase 5 P5-S1 Dispatch Schema And Transition Primitives Implementation

- gate: Host Phase 5 implementation
- slice: P5-S1 Dispatch Schema And Transition Primitives
- approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`
- implementation date: 2026-05-14
- role: implementation agent

## Scope

Allowed production files changed:

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`

Allowed test files changed:

- `tests/host/test_state_schema.py`
- `tests/host/test_run_attempt_transitions.py`

Allowed files not changed:

- `tests/host/test_weak_typing_guard.py`

Non-goals honored:

- Did not modify scheduler, RunInputBuilder, LocalProxy, Engine ingest, command facade, README, or implementation-control.
- Did not introduce old schema compatibility reads or migration logic.
- Did not treat dispatch record status, lane diagnostics, or owner ids as lease, fencing, takeover proof, or active worker truth.

## Implemented Plan Items

- Bumped fresh Host durable schema version to `3`.
- Extended dispatch record schema status set to:
  - `pending`
  - `waiting_for_lane`
  - `dispatching`
  - `cancelled`
- Added dispatch diagnostic columns:
  - `waiting_for_lane_at`
  - `lane_name`
  - `lane_claim_id`
  - `lane_owner_id`
  - `lane_acquired_at`
  - `dispatching_at`
  - `worker_accepted_at`
  - `worker_accept_event_id`
  - `worker_accept_event_sequence`
- Added fresh-schema nullability checks for all four dispatch statuses.
- Extended `DispatchRecordStatus`, `DispatchRecordRow`, row codecs, insert path, and validation helpers.
- Added state helpers:
  - `mark_dispatch_waiting_for_lane_row`
  - `mark_dispatching_after_lane_row`
  - `mark_dispatch_worker_accepted_row`
  - `cancel_starting_dispatch_record_row`
  - `mark_attempt_running_row`
  - `mark_run_cancelling_row`
- Added run transition helpers:
  - `accept_worker_running_in_transaction`
  - `request_active_attempt_cancel_in_transaction`
- Generalized `cancel_predispatch_starting_in_transaction` so pending, waiting_for_lane, and pre-accept dispatching can direct cancel.
- Rejected pre-worker direct cancel when dispatching already has worker accept refs.
- Added `ATTEMPT_RUNNING` append path and CAS from Attempt `STARTING` to `RUNNING`.
- Added active cancel primitive that writes `RUN_CANCELLING` only on first `RUNNING -> CANCELLING` transition.

## Tests Added Or Updated

- Schema accepts all four dispatch statuses and rejects invalid status.
- Schema rejects invalid nullability shape for `waiting_for_lane`.
- State/transition path covers pending -> waiting_for_lane -> dispatching -> worker accept refs while dispatch status remains dispatching.
- Direct cancel covers pending, waiting_for_lane, and pre-accept dispatching.
- Direct cancel rejects dispatching with worker accepted refs.
- `mark_attempt_running_row` only allows STARTING -> RUNNING.
- Active cancel duplicate call keeps a single `RUN_CANCELLING` event.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_weak_typing_guard.py -q
```

Result:

```text
33 passed in 0.27s
```

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Passed:

```bash
git diff --check
```

Result: no whitespace errors.

## Documentation Decision

No README or implementation-control update was made because the slice instructions explicitly prohibited README and implementation-control changes. This artifact is the required completion record for the slice.

## Residual Risks

- Multiprocess orphan proof, restart recovery, and positive orphan detection remain Phase 11 owner work.
- Scheduler/lane token release and WorkerProxy final pre-call recheck are not implemented in this slice; they remain later Phase 5 slices.
- Active cancel propagation to LocalProxy / WorkerProxy is not implemented in this slice; this slice only provides the durable primitive.

## Stop Status

No stop condition was hit.
