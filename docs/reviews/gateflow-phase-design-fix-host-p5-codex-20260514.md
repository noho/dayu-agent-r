# Phase 5 Design Fix: Terminal Closeout And Dispatch Cancel Race

## Source Review

Source artifacts:

- `docs/reviews/gateflow-phase-design-re-review-host-p5-ds-20260514.md`
- `docs/reviews/gateflow-phase-design-re-review-host-p5-controller-adjudication-20260514.md`

Accepted blocking findings:

- DS F1: Stream EOF / worker crash / startup reject terminal closeout policy lacks concrete criteria.
- DS F2: `dispatching` committed but WorkerProxy not yet called cancel window is undefined.

## Fix Summary

Updated `docs/host/design.md` §17 and §22 to define:

- Phase 5 local execution terminal closeout policy table.
- Phase 5 no automatic `RECOVERING` / new Attempt behavior for local execution failures or unsupported recovery signals.
- Lane token lifecycle: acquired before durable recheck, held by dispatch supervisor / worker execution context until terminal closeout or dispatch abort.
- `dispatching + Attempt STARTING` as the pre-worker committed window.
- Cancel in that window closes directly to `ATTEMPT_CANCELLED` / `RUN_CANCELLED`, marks dispatch record `cancelled`, wakes scheduler, and requires scheduler final pre-call recheck to release lane and skip WorkerProxy.

Updated `docs/host/implementation-control.md` current status to record:

- DS F1 / F2 accepted as blocking.
- Fix artifact path.
- Design re-review remains required before entering plan gate.

## Deferred Plan Checks

The fix does not attempt to solve DS F3-F6 or MiMo observation findings in design truth. These are accepted as plan-gate checks:

- minimal canonical payload schema for Phase 5 EngineEvent mappings;
- dispatch record diagnostic columns and nullability;
- RunInputBuilder real vs noop provider set;
- `cancel_session_runs` partial completion idempotency;
- `dispatching` final record status after worker accept;
- `usage_reported` handling;
- context compaction / unsupported recovery handling in Phase 5.

## Validation

- `git diff --check` must pass after this fix.
- No production code changed in this design fix.

