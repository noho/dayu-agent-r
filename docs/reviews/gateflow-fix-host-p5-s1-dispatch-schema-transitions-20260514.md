# Host Phase 5 P5-S1 Review Fix

- gate: Host Phase 5 P5-S1 code review fix
- slice: P5-S1 Dispatch Schema And Transition Primitives
- branch: `feat/host-phase5-local-dispatch`
- fix date: 2026-05-14
- source reviews:
  - `docs/reviews/gateflow-code-review-host-p5-s1-dispatch-schema-transitions-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p5-s1-dispatch-schema-transitions-ds-20260514.md`

## Controller Decision

DS M1 is accepted as a real semantic gap and fixed before slice acceptance. Although the original implementation preserved schema integrity, allowing `mark_dispatching_after_lane_row` to move `PENDING -> DISPATCHING` made the production helper contradict the approved state sequence:

```text
pending -> waiting_for_lane -> dispatching -> worker accepted refs
```

The fix keeps dispatch record diagnostics as local retry/dispatch diagnostics only; it does not introduce lease, fencing, owner truth, scheduler, LocalProxy, WorkerProxy, or Engine ingest behavior.

## Fixes Applied

- Restricted `mark_dispatching_after_lane_row` to `WAITING_FOR_LANE` source status only.
- Removed the `COALESCE(waiting_for_lane_at, dispatching_at)` behavior so dispatching can no longer synthesize a missing wait timestamp.
- Required `waiting_for_lane_at IS NOT NULL` and matching `lane_name` in the dispatching CAS.
- Added a dedicated mutation result classifier for lane-dispatching so `PENDING` source returns `INVALID_STATE` instead of being treated as a retryable dispatch-start CAS race.
- Added a regression test proving pending dispatch records cannot skip directly to dispatching.

## Review Items Left Nonblocking

- MiMo F1 remains a P5-S3 handoff risk: `ATTEMPT_RUNNING` payload must be extended when LocalProxy / scheduler provide `local_worker_id`, `worker_accepted_at`, `lane_name`, and `lane_claim_id`.
- DS M2 remains nonblocking: the `RUN_CANCELLING` append return value is intentionally unused by the current durable primitive.
- DS M3 remains nonblocking: the shared cancel validation helper has a broad event-id parameter naming issue but no behavioral or type-safety impact.
- DS L1/L2 remain nonblocking test-depth and test-helper cleanup opportunities for later slices.

## Files Changed By This Fix

- `dayu/host/durable/state.py`
- `tests/host/test_run_attempt_transitions.py`

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_weak_typing_guard.py -q
```

Result:

```text
34 passed in 0.30s
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

## Controller Status

Ready for P5-S1 code re-review.
