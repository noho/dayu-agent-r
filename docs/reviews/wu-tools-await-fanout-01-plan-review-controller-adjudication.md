# WU-TOOLS-AWAIT-FANOUT-01 Plan Review Controller Adjudication

## Gate

- Work unit: WU-TOOLS-AWAIT-FANOUT-01
- Gate: plan review
- Plan artifact: `docs/host/wu-tools-await-fanout-01-plan.md`
- Review artifacts:
  - `docs/reviews/wu-tools-await-fanout-01-plan-review-mimo.md`
  - `docs/reviews/wu-tools-await-fanout-01-plan-review-ds.md`

## Decision

Decision: changes-requested

Both review artifacts have zero blocking findings, but controller accepts one medium-severity plan correction that must be fixed before accepted plan commit.

The accepted correction does not reject the lightweight approach. It narrows the plan so implementation does not spend effort on an overestimated current production path.

## Finding Adjudication

| Finding | Source | Decision | Controller reason |
|---|---|---|---|
| MIMO-01: `AWAITING_FANOUT` current reachability is overstated | AgentMiMo | accepted | Current Host ToolRuntime `execute()` stops remaining batch calls after the first `ToolAwaitingOutcome` by returning governed failures with `run_suspended_by_tool_awaiting`. Engine itself can carry multiple awaiting records from a batch outcome, but Host ToolRuntime currently prevents later calls in the same batch from becoming waiter fanout after owner awaiting accepted. Plan must not present Engine alias confirmation as a required implementation path without direct evidence. |
| MIMO-02 / DS-F02: `DuplicateDecision.prior_outcome` vs `prior_awaiting_outcome` semantics unclear | AgentMiMo / AgentDS | accepted | If a defensive awaiting fanout state remains in the plan, the internal contract must explicitly state field exclusivity. Awaiting fanout must not be treated as ordinary completed-result reuse. |
| MIMO-03: resume material edit location underspecified | AgentMiMo | accepted | Plan fix should state the resume material update is an append to `_resume_wait_message_from_current_start(...)` output, not a replacement of existing result projection. |
| MIMO-04 / DS-F01: Engine alias confirmation path is underspecified | AgentMiMo / AgentDS | accepted | Plan fix should remove Engine alias confirmation from required implementation unless direct code evidence shows Host ToolRuntime can emit alias awaiting records in current production path. If retained, it must be explicitly defensive and tested by direct unit-level data, not claimed as current end-to-end behavior. |
| DS-F03: 3+ waiter test gap | AgentDS | accepted-if-fanout-retained | If the plan keeps a defensive `AWAITING_FANOUT` state, it should include a unit test for multiple waiting callers against duplicate governance state. If the plan removes that state from current implementation, this becomes not applicable. |

## Required Plan Fix

AgentCodex must update `docs/host/wu-tools-await-fanout-01-plan.md` so that:

1. The root cause is stated precisely: after awaiting accept succeeds, ToolRuntime currently returns `ToolAwaitingOutcome` without marking duplicate governance terminal, so `finally` records durable-missing. This is a correctness bug in attempt-local duplicate cleanup state, even if current Host ToolRuntime batch execution prevents later calls in the same batch from becoming fanout waiters.
2. The implementation scope prioritizes the minimal root-cause fix: awaiting accepted must record a terminal duplicate state or otherwise suppress durable-missing cleanup after accepted ack.
3. Any `AWAITING_FANOUT` state is explicitly classified as defensive internal state, not a currently reachable Engine/ToolRuntime end-to-end path, unless the plan adds direct code evidence proving reachability.
4. Required implementation should not modify `engine_ingest.py` for alias confirmation unless implementation first proves current Host ToolRuntime can produce alias awaiting records that reach Engine ingest.
5. Tests must focus on:
   - awaiting accepted does not call `record_durable_missing`;
   - accept rejected / timeout still records durable-missing;
   - remaining batch calls after awaiting continue to get existing governed failure and do not start a second job;
   - RunInputBuilder resume material appends shared-result guidance without leaking internal refs.
6. If defensive `AWAITING_FANOUT` is retained, unit tests must cover its field semantics and multiple waiter decisions without implying current Engine production reachability.

## Residual Risks

| Risk | Status | Owner / destination |
|---|---|---|
| Current issue motivation may overstate production reachability of duplicate awaiting fanout waiter | accepted for plan fix | WU-TOOLS-AWAIT-FANOUT-01 plan-fix gate |
| Future Engine or ToolRuntime concurrency changes could make awaiting fanout reachable | deferred-with-owner | Future ToolRuntime concurrency or Engine batch behavior work unit; current WU may keep defensive internal tests only if lightweight |
| Resume material wording could leak Host internal refs | accepted for plan fix | WU-TOOLS-AWAIT-FANOUT-01 implementation plan and tests |

## Next Gate

Next gate: plan-fix

Dispatch AgentCodex to update the plan artifact only. No implementation, commit, push, or PR work is authorized in this gate.
