# Phase 5 Plan Fix: Review Findings

## Source Reviews

- `docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-mimo-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-ds-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-controller-adjudication-20260514.md`

## Fix Summary

Updated `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` to:

- specify `EngineEventCandidate.observed_at` as UTC-aware `datetime`;
- define deterministic Host event id derivation from `execution_id`, `worker_event_index`, event class, event type, and sub-index;
- clarify `worker_accept_event_id` / `worker_accept_event_sequence` are the `ATTEMPT_RUNNING` EventLog id and global `event_sequence`;
- bind `AgentRunRequest`, `RunnerSpec`, `RunnerCallOptions`, and `AgentPolicy` to existing `dayu.engine.contracts` modules, with Host building but not redefining or extending them;
- define `PROVIDER_PROTOCOL_ERROR.partial_tool_call_count = len(engine_event.data.partial_tool_calls)` and raw payload descriptor handling;
- correct the evidence statement for `EngineEvent.occurred_at`;
- clarify `AttemptDispatchSnapshot` versus provider-owned Engine request fields;
- add `cancel_session_runs` replay best-effort re-propagation test expectation.

## Validation

- `git diff --check` must pass after this plan-only fix.
- No production code changed.

