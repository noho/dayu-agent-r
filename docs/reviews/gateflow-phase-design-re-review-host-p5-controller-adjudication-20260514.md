# Phase 5 Design Re-Review Controller Adjudication

## Scope

Gate: Phase 5 design re-review.

Reviewed artifacts:

- `docs/reviews/gateflow-phase-design-re-review-host-p5-mimo-20260514.md`
- `docs/reviews/gateflow-phase-design-re-review-host-p5-ds-20260514.md`
- `docs/reviews/gateflow-phase-design-host-p5-codex-20260514.md`
- `docs/host/design.md`
- `docs/host/implementation-control.md`

## Verdict

Phase 5 design refinement is not ready for plan gate until DS F1 and DS F2 are fixed and re-reviewed.

MiMo found no blocking finding and identified six plan-phase observations. DS found two blocking findings and four non-blocking findings. Controller accepts DS F1 and DS F2 as blocking because both point to design-truth ambiguity that would force the plan agent to invent state-machine policy.

## Finding Decisions

| Finding | Source | Decision | Reason |
| --- | --- | --- | --- |
| F1 Stream EOF / worker crash / startup reject terminal closeout policy lacks concrete criteria | DS | accepted-blocking | Phase 5 plan cannot safely define tests without a minimal FAILED / LOST / RECOVERING decision table. |
| F2 `dispatching` committed but WorkerProxy not yet called cancel window undefined | DS | accepted-blocking | This is a real race between durable dispatch ownership and cancel governance; plan must not invent lane-token ownership or terminal behavior. |
| F3 EngineEvent canonical payload minimum fields absent | DS | accepted-non-blocking-plan-check | Important for plan review, but payload shape can be defined in handoff plan if it obeys §13.4 and existing event family tables. |
| F4 dispatch diagnostic fields absent from row schema | DS | accepted-non-blocking-plan-check | Plan must define schema fields, but design already constrains semantics as diagnostic only, not lease / fencing. |
| F5 RunInputBuilder minimum provider set not separated from future providers | DS / MiMo | accepted-non-blocking-plan-check | Plan must enumerate real vs noop providers; design refinement already makes this a plan readiness item. |
| F6 `cancel_session_runs` partial completion idempotency not expanded | DS | accepted-non-blocking-plan-check | Plan must cover it for Phase 5 cancel slice; not required to block design refinement after F2 is fixed. |
| MiMo F-O1 dispatching final record state | MiMo | accepted-non-blocking-plan-check | Plan should state whether `dispatching` remains the durable dispatch state after worker accept; fifth state requires new design discussion. |
| MiMo F-O4 context compaction failure handling | MiMo | accepted-non-blocking-plan-check | Plan must keep Phase 5 from implementing Phase 10 compaction recovery. |
| MiMo F-O5 usage reported handling | MiMo | accepted-non-blocking-plan-check | Plan may choose diagnostic / preview handling without changing design truth. |

## Required Fix

Write back to `docs/host/design.md`:

- Phase 5 local terminal closeout policy table for startup reject, startup timeout, clean stream EOF without terminal, Engine structured `run_failed`, worker crash, and unsupported recovery / context compaction path.
- Lane token ownership lifecycle from acquire through terminal / dispatch abort.
- Cancel behavior for `dispatching + Attempt STARTING` before WorkerProxy accept.

Update `docs/host/implementation-control.md` current state to record the accepted blocking findings, fix artifact, and required re-review.

