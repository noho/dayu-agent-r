# WU-TOOLS-AWAIT-FANOUT-01 Plan Re-Review Controller Adjudication

## Gate

- Work unit: WU-TOOLS-AWAIT-FANOUT-01
- Gate: plan re-review
- Plan artifact: `docs/host/wu-tools-await-fanout-01-plan.md`
- Plan fix artifact: `docs/reviews/wu-tools-await-fanout-01-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-await-fanout-01-plan-rereview-mimo.md`
  - `docs/reviews/wu-tools-await-fanout-01-plan-rereview-ds.md`

## Decision

Decision: pass

Controller accepts the fixed plan. Both re-review agents report:

- unfixed accepted findings: 0;
- new blocking findings: 0;
- lightweight-await constraint preserved;
- one implementation slice remains appropriate;
- no durable schema or public contract change is planned.

## Accepted Finding Status

| Finding | Final status | Controller decision |
|---|---|---|
| MIMO-01: `AWAITING_FANOUT` current reachability overstated | fixed | Plan now states current Host ToolRuntime returns `run_suspended_by_tool_awaiting` for remaining batch calls after first awaiting; fanout is optional defensive internal state only. |
| MIMO-02 / DS-F02: `prior_outcome` vs `prior_awaiting_outcome` semantics | fixed | Plan now defines mutual exclusivity and allows simpler marker-only implementation. |
| MIMO-03: resume material edit location | fixed | Plan now targets `_resume_wait_message_from_current_start(...)` and requires appending shared-result guidance after existing result projection. |
| MIMO-04 / DS-F01: Engine alias confirmation path | fixed | Plan now excludes `engine_ingest.py` by default and requires stop-and-return-to-controller before any alias-confirmation change. |
| DS-F03: 3+ waiter test gap | fixed / not applicable | Plan requires multiple-waiter unit tests only if defensive `AWAITING_FANOUT` is retained. |

## Residual Risks

| Risk | Status | Owner / destination |
|---|---|---|
| `record_awaiting_accepted` / terminal marker implementation may fail to suppress durable-missing cleanup | accepted for implementation validation | WU-TOOLS-AWAIT-FANOUT-01 implementation gate |
| Engine alias records may prove reachable during implementation | stop condition | Controller裁决 required before modifying `engine_ingest.py` |
| Resume material could leak internal refs if implemented carelessly | accepted for implementation review | WU-TOOLS-AWAIT-FANOUT-01 code review; LLM-facing constraint applies |
| Future Engine / ToolRuntime concurrency could make defensive fanout production-reachable | deferred-with-owner | Future Engine / ToolRuntime concurrency work unit if needed |

## Next Gate

Next gate: accepted plan commit

After committing the accepted plan artifacts, proceed to implementation gate for slice `S1 轻量 awaiting cleanup terminal marker`.
