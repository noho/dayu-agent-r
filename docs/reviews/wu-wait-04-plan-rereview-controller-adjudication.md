# WU-WAIT-04 Plan Re-review Controller Adjudication

## Scope

- Work unit: WU-WAIT-04 UI / Service production-grade awaiting E2E smoke.
- Gate: plan re-review.
- Fixed plan artifact: `docs/host/wu-wait-04-production-awaiting-e2e-smoke-plan.md`.
- Fix artifact: `docs/reviews/wu-wait-04-plan-fix-codex.md`.
- Re-review artifacts:
  - `docs/reviews/plan-review-20260705-202521.md`
  - `docs/reviews/plan-review-20260705-202539.md`

## Controller Decision

Plan re-review is accepted. Both re-review artifacts conclude `pass`, and all controller-accepted findings are reported as `已修复`.

## Final Finding Status

| Finding | Final status | Controller rationale |
|---|---|---|
| Service/Fins poll adapter registry data flow | 已修复 | The fixed plan now specifies the `_tooling_options_from_discovery` guard, assignment path, runtime reuse, and enabled / disabled test expectations. |
| Deterministic poll adapter synchronization | 已修复 | The fixed plan requires a test-controlled gate, such as `asyncio.Event`, holding `WaitPollReady` until public WAITING observation has happened. |
| WAITING activity observation | 已修复 | The fixed plan requires both `on_activity` observation of `EntrypointActivityStatus.WAITING` and a public `get_run(...).status == RunStatus.WAITING` snapshot assertion. |
| Outbox public backfill path | 已修复 | The fixed plan replaces the nonexistent helper with direct public `host.read_outbox_terminal_items` usage, with `startup_reconnect_entrypoint_session` only as an optional deliberate reconnect path. |
| S1/S2 framing | 已修复 | The fixed plan clarifies S1 as production assembly and S2 as public workflow smoke, with S2 allowed to direct-assemble public opener options while validating the same poller contract. |
| Forbidden-path validation | 已修复 | The fixed plan uses import-oriented guard patterns including `dayu.host.durable` and requires benign matches to be explained. |
| WaitPollAdapter typing boundary | 已修复 | The fixed plan preserves the public-contract-only smoke boundary and treats typing gaps as a minimal public-contract-preserving implementation concern, not authorization to read durable rows or mutate waits. |

## Residual Risk

No unclassified residual risk remains for the plan gate. Low-risk implementation concerns around async input assembly, poller timing, and protocol typing are documented in the fixed plan and have explicit validation or stop conditions.

## Next Gate

Proceed to accepted plan commit, then implementation gate for Slice S1.
