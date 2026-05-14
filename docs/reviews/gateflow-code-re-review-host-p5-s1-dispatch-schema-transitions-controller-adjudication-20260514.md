# Host Phase 5 P5-S1 Code Re-Review Controller Adjudication

- gate: Host Phase 5 P5-S1 code re-review adjudication
- slice: P5-S1 Dispatch Schema And Transition Primitives
- branch: `feat/host-phase5-local-dispatch`
- adjudication date: 2026-05-14
- design source: `docs/host/design.md`
- control source: `docs/host/implementation-control.md`
- approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`

## Inputs

- implementation artifact: `docs/reviews/gateflow-implementation-host-p5-s1-dispatch-schema-transitions-20260514.md`
- first code reviews:
  - `docs/reviews/gateflow-code-review-host-p5-s1-dispatch-schema-transitions-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p5-s1-dispatch-schema-transitions-ds-20260514.md`
- fix artifact: `docs/reviews/gateflow-fix-host-p5-s1-dispatch-schema-transitions-20260514.md`
- re-reviews:
  - `docs/reviews/gateflow-code-re-review-host-p5-s1-dispatch-schema-transitions-mimo-20260514.md`
  - `docs/reviews/gateflow-code-re-review-host-p5-s1-dispatch-schema-transitions-ds-20260514.md`

## Controller Judgment

P5-S1 is accepted for commit.

The accepted DS M1 / MiMo F2 semantic issue has been fixed at the correct layer. `mark_dispatching_after_lane_row` now requires `WAITING_FOR_LANE` source state, preserves the existing `waiting_for_lane_at` instead of synthesizing it, checks lane-name consistency, and uses a dedicated mutation result classifier where `PENDING` source is `INVALID_STATE`.

This matches the approved Phase 5 local dispatch state sequence:

```text
pending -> waiting_for_lane -> dispatching -> worker accepted refs
```

No reviewer reported a new blocker after the fix.

## Finding Disposition

| Finding | Controller disposition | Owner |
|---|---|---|
| DS M1 / MiMo F2: `PENDING -> DISPATCHING` skip | Accepted and fixed in this slice | P5-S1 |
| MiMo F1: `ATTEMPT_RUNNING` payload missing LocalProxy/scheduler fields | Deferred as P5-S3 handoff risk | P5-S3 |
| DS M2: unused `RUN_CANCELLING` append result | Accepted as nonblocking, no code change | None |
| DS M3: shared cancel validation parameter name | Accepted as nonblocking readability issue | Later cleanup only if touched |
| DS L1/L2 | Accepted as nonblocking test-depth/test-helper cleanup | Later slices if relevant |

## Validation

Controller validation before re-review:

```text
pytest tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_weak_typing_guard.py -q
34 passed in 0.30s

python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations

git diff --check
passed
```

Reviewer validation:

- MiMo reconfirmed 34 tests passed, pyright clean, diff check passed.
- DS reconfirmed 34 tests passed, pyright clean, diff check passed.

## Residual Risk Tracking

- P5-S3 must extend `AcceptWorkerRunningInput` and `ATTEMPT_RUNNING` payload when LocalProxy / scheduler provide `local_worker_id`, `worker_accepted_at`, `lane_name`, and `lane_claim_id`.
- Scheduler, RunInputBuilder, LocalProxy, WorkerProxy, Engine event ingest, lane token release, and active cancel propagation remain outside P5-S1 and are owned by later Phase 5 slices.

## Decision

P5-S1 is ready to commit as an accepted implementation slice.
