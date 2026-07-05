# WU-WAIT-04 Plan Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-04 UI / Service production-grade awaiting E2E smoke.
- Gate: plan review.
- Plan artifact: `docs/host/wu-wait-04-production-awaiting-e2e-smoke-plan.md`.
- Review artifacts:
  - `docs/reviews/plan-review-20260705-201401.md`
  - `docs/reviews/plan-review-20260705-201420.md`

## Controller Decision

Plan review is accepted as `requires-plan-fix`.

Both reviewers concluded `pass-with-risks` and found no structural blocker, but the material findings expose underspecified plan details that would force the implementation agent to redesign test synchronization, outbox backfill, and Service/Fins poller wiring during implementation. That violates the code-generation-ready plan gate. The next gate is plan fix by AgentCodex.

## Finding Adjudication

| Finding | Source | Decision | Controller rationale | Required plan fix |
|---|---|---|---|---|
| Service/Fins poll adapter registry data flow is underspecified | DS F1 | accepted | The plan identifies the assembly gap but does not spell out the `_tooling_options_from_discovery` guard and assignment path. Implementation should not infer `None` handling or runtime reuse. | Specify exact `wait_poll_adapter_registry` construction: only when Fins awaiting runtime and awaiting tool bindings exist; otherwise `None`; reuse the same runtime as wait binding and activation registries; add tests for enabled and disabled cases. |
| Deterministic poll adapter transition can race WAITING observation | DS F2 / MiMo 02 | accepted | The user requires public workflow smoke, including observable `WAITING`. A simple NotReady-then-Ready counter can resolve before the Service test observes `WAITING`. | Specify a test-controlled synchronization primitive, preferably an event/gate that holds Ready until the public activity callback and/or `get_run` has observed `WAITING`. |
| WAITING activity may be proven only by `get_run` rather than live activity callback | DS F3 | accepted | `get_run` status is public and useful, but UI display path also depends on activity projection. The smoke should verify both where feasible. | Require `on_activity` to observe `EntrypointActivityStatus.WAITING`, and use `get_run(...).status == WAITING` as an additional public snapshot assertion. |
| Outbox reconnect helper name is wrong / nonexistent | DS F4 / MiMo 01 | accepted | `run_entrypoint_startup_reconnect` does not exist. Leaving a nonexistent helper in the plan makes S2 not directly implementable. | Replace with concrete public path: either direct `host.read_outbox_terminal_items` after terminal, or existing `startup_reconnect_entrypoint_session` if the test deliberately covers reconnect semantics. The simpler required smoke path is direct public outbox read. |
| S1/S2 dependency framing overstates code dependency | MiMo 03 | accepted as clarification | The two slices are logically ordered because S1 establishes production assembly, but S2 can construct public `OpenHostOptions` directly. | Clarify that S1 is the production assembly slice, while S2 is the public workflow smoke slice; S2 may use direct public opener assembly but must still validate the same public poller contract. |
| Forbidden-path grep may miss aliases or false-positive on comments | DS F5 / MiMo 04 | accepted | Grep is a guardrail, not proof. The plan should avoid brittle instructions that fail on comments while missing imports. | Refine validation with import-oriented grep patterns, include `dayu.host.durable`, and state that the implementation report must explain any benign match. |
| WaitPollAdapter implementation may require `WaitRecordRow` typing | DS open question | needs-more-evidence | `WaitPollAdapter` is public, but its parameter type is imported from `dayu.host.durable.state` and is not exported through `wait_adapter.__all__`. This may be a public typing leak or only a test annotation issue. | Plan fix must explicitly state the implementation must not read durable rows or import durable helpers in the smoke assertion path. If strict typing requires a public type alias/export or a local protocol-compatible adapter signature, the implementation slice must choose the minimal public-contract-preserving approach and validate with pyright. |

## Residual Risks

- No unowned residual risk remains at plan review gate.
- The public typing boundary around `WaitRecordRow` is classified as `needs-more-evidence` for implementation planning, not as authorization to use durable wait storage in the smoke.

## Next Gate

Dispatch AgentCodex for plan fix. The fix must update only `docs/host/wu-wait-04-production-awaiting-e2e-smoke-plan.md` and write a fix report under `docs/reviews/`. After plan fix, dispatch MiMo and DS for plan re-review.
