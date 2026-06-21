# WU-TOOLS-AWAIT-FANOUT-01 Plan Fix - AgentCodex

## Gate

- Gate: plan-fix
- Work unit: WU-TOOLS-AWAIT-FANOUT-01
- GitHub issue: #111
- Plan artifact fixed: `docs/host/wu-tools-await-fanout-01-plan.md`
- Fix agent: AgentCodex

## Input Review Artifacts And Controller Adjudication

Input artifacts:

- `docs/reviews/wu-tools-await-fanout-01-plan-review-mimo.md`
- `docs/reviews/wu-tools-await-fanout-01-plan-review-ds.md`
- `docs/reviews/wu-tools-await-fanout-01-plan-review-controller-adjudication.md`
- Control source: `docs/host/issues-implementation-control.md`

Controller decision: changes requested for plan-fix.

Controller accepted the correction that the original plan overstated current production reachability of duplicate awaiting fanout. Current Host ToolRuntime stops remaining batch calls after the first `ToolAwaitingOutcome` by returning `run_suspended_by_tool_awaiting` governed failures, so same-batch later calls do not currently reach an `AWAITING_FANOUT` waiter path. The plan therefore had to narrow the root-cause fix to accepted awaiting duplicate cleanup state.

## Changes Made To Plan Artifact

Updated `docs/host/wu-tools-await-fanout-01-plan.md` only.

- Reframed the goal from current owner / waiter fanout closure to accepted awaiting cleanup terminal marker correctness.
- Stated the precise root cause: after awaiting accept accepted ack, ToolRuntime returns `ToolAwaitingOutcome` without marking duplicate governance terminal, so `_execute_one.finally` can incorrectly call `record_durable_missing`.
- Clarified current production reachability: remaining batch calls after awaiting continue to receive `run_suspended_by_tool_awaiting` governed failure and do not start a second job or reach `AWAITING_FANOUT`.
- Downgraded `AWAITING_FANOUT` to optional defensive Host internal state, not a required current Engine / ToolRuntime end-to-end path.
- Removed `engine_ingest.py` alias confirmation from required implementation scope unless implementation first proves alias awaiting records can reach Engine ingest in the current production path.
- Added `DuplicateDecision.prior_outcome` / `prior_awaiting_outcome` mutual-exclusion semantics for any retained defensive fanout decision.
- Specified the resume material edit location: append shared-result guidance after the existing `_resume_wait_message_from_current_start(...)` accepted wait result projection, without replacing current result lines.
- Updated the implementation slice name and done signal to `S1 轻量 awaiting cleanup terminal marker`.
- Reworked the test matrix to prioritize cleanup terminal behavior, rejected / timeout durable-missing behavior, existing batch governed failure behavior, and LLM-facing resume material safety.

## Accepted Findings Addressed

### MIMO-01: `AWAITING_FANOUT` Current Reachability Is Overstated

Addressed.

- The plan now states that current Host ToolRuntime returns `run_suspended_by_tool_awaiting` governed failures for remaining batch calls after the first `ToolAwaitingOutcome`.
- `AWAITING_FANOUT` is explicitly defensive Host internal state only.
- The core fix is now `record_awaiting_accepted(...)` or an equivalent terminal marker that suppresses erroneous durable-missing cleanup after accepted ack.

### MIMO-02: `DuplicateDecision.prior_outcome` Vs `prior_awaiting_outcome` Semantics Unclear

Addressed.

- The plan now states ordinary duplicate reuse uses `prior_outcome` with `prior_awaiting_outcome=None` and `prior_wait_id=None`.
- Defensive `AWAITING_FANOUT` uses `prior_awaiting_outcome` and `prior_wait_id` with `prior_outcome=None`.
- The plan also allows the simpler marker-only option, provided awaiting outcome never enters the ordinary accepted index or `_accept_reuse`.

### MIMO-03: Resume Material Edit Location Underspecified

Addressed.

- The plan now names `_resume_wait_message_from_current_start(...)` as the edit location.
- It requires appending shared duplicate result guidance after the existing accepted wait result lines.
- It explicitly forbids replacing the existing `tool_name`, `resolution_kind`, `tool_fact_kind`, and `result` projection.

### MIMO-04: Engine Alias Confirmation Path Is Underspecified

Addressed.

- `engine_ingest.py` is no longer in the default allowed implementation files.
- The plan says implementation must not modify Engine alias confirmation unless it first proves current Host ToolRuntime emits alias awaiting records that reach Engine ingest.
- Any future alias confirmation is scoped as defensive diagnostic only: no second wait record, no extra canonical awaiting facts, no Run / Attempt / wait state mutation.

### DS-F01: Engine Alias Confirmation Path Is Incomplete

Addressed.

- Same correction as MIMO-04.
- The plan now treats Engine ingest alias handling as out of default scope, not as a required implementation path.
- The stop condition requires direct evidence and controller decision before modifying `engine_ingest.py` for alias confirmation.

### DS-F02: `prior_awaiting_outcome` / `prior_outcome` Type Semantics

Addressed.

- Same correction as MIMO-02.
- The plan makes the two fields mutually exclusive and states awaiting fanout must not be treated as ordinary completed-result reuse.

### DS-F03: 3+ Waiter Test Gap

Addressed if defensive fanout is retained.

- The plan now requires unit-level tests for multiple waiter decisions if `AWAITING_FANOUT` remains.
- Those tests must show every waiter gets the same owner wait fanout decision and no waiter re-competes for owner.
- The plan also states this does not imply current production e2e reachability.

## Lightweight Constraint Status

Status: preserved.

- No durable follower ledger.
- No durable duplicate table.
- No `host_wait_records` schema expansion.
- No public await lifecycle contract.
- No issue-129 two-phase activation.
- No heavy waiter queue or cross-Attempt duplicate mechanism.

## Schema / Public Contract Decision

Schema/public contract: none.

- Durable schema remains unchanged.
- Host public `resolve_wait` contract remains unchanged.
- Engine public contract remains unchanged.
- Any new marker or optional `AWAITING_FANOUT` decision remains Host internal / ToolRuntime internal.

## Validation Performed

Commands run during this plan-fix artifact work:

```bash
git status --short
test -e docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md && sed -n '1,240p' docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md || true
rg -n "MIMO-01|MIMO-02|MIMO-03|MIMO-04|DS-F01|DS-F02|DS-F03|AWAITING_FANOUT|run_suspended_by_tool_awaiting|engine_ingest|prior_outcome|_resume_wait_message_from_current_start|S1" docs/host/wu-tools-await-fanout-01-plan.md docs/reviews/wu-tools-await-fanout-01-plan-review-controller-adjudication.md
```

Validation scope:

- Confirmed the target artifact did not already exist before writing.
- Confirmed the plan contains the required fix themes for production reachability, defensive fanout, Engine ingest scope, field exclusivity, resume append location, and S1 rename.
- Tests and pyright were not run because this gate only writes plan-fix artifacts and does not modify production code or tests.

## Residual Risks / Blocking Questions

Residual risks:

- Implementation must still prove the accepted awaiting terminal marker prevents `record_durable_missing` after accepted ack.
- If implementation later proves current production path emits alias awaiting records into Engine ingest, that must be returned to controller before touching `engine_ingest.py`.
- If defensive `AWAITING_FANOUT` is retained, unit-level tests must cover field exclusivity and multiple waiter decisions without claiming production e2e reachability.

Blocking questions: none.

## Completion Report

Artifact: `docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md`

Decision: fixed

Validation performed: read-only status / existence / targeted `rg` checks listed above; no tests or pyright run for this artifact-only gate.

Blocking questions: none
