# WU-WAIT-04 Plan Fix Report - AgentCodex

## Artifact

- Fixed plan artifact: `docs/host/wu-wait-04-production-awaiting-e2e-smoke-plan.md`
- Fix report: `docs/reviews/wu-wait-04-plan-fix-codex.md`

## Fixed Findings

- Service/Fins poll adapter registry data flow: fixed. S1 now specifies `_tooling_options_from_discovery` must assign `HostToolingOptions.wait_poll_adapter_registry`, construct it only when Fins awaiting runtime and awaiting tool bindings both exist, return `None` otherwise, reuse the same runtime as binding / activation registries, and add enabled / disabled test expectations.
- Deterministic poll adapter synchronization: fixed. S2 now requires an explicit test gate such as `asyncio.Event` that keeps the adapter returning not-ready until public WAITING observation has happened, then allows ready.
- WAITING observation: fixed. S2 now requires `on_activity` to observe `EntrypointActivityStatus.WAITING`, with `get_run(...).status == RunStatus.WAITING` as an additional public snapshot assertion.
- Outbox reconnect/backfill path: fixed. S2 now uses direct public `host.read_outbox_terminal_items(ReadOutboxTerminalItemsRequest(..., after=OutboxTerminalCursor(...)))` after terminal; reconnect helper use is limited to the actual `startup_reconnect_entrypoint_session` only if deliberately testing reconnect semantics.
- S1/S2 dependency framing: fixed. The plan now states S1 is the production assembly slice and S2 is the public workflow smoke slice; S2 may direct-assemble public `OpenHostOptions` while still validating the same public poller contract.
- Forbidden-path validation: fixed. S2 now includes import-oriented forbidden guard patterns for durable and tool runtime modules, including `dayu.host.durable`, and requires explanation of any benign match in the implementation report while telling tests to avoid forbidden names in comments/docstrings.
- WaitPollAdapter typing boundary: fixed. The plan now states the smoke assertion path must not read durable rows or import durable helpers; if strict typing needs a public type alias/export or protocol-compatible signature, implementation must choose the minimal public-contract-preserving approach and pass pyright.

## Final Status

- Status: ready for plan re-review.
- No implementation, review, commit, push, PR, source-code, test, README, design-doc, or control-doc changes were made.

## Validation

- Passed: `git diff --check -- docs/host/wu-wait-04-production-awaiting-e2e-smoke-plan.md docs/reviews/wu-wait-04-plan-fix-codex.md`

## Open Questions / Blockers

- No blocker remains in the plan fix gate.
- Existing deferred product questions remain unchanged: whether wait poller enablement should later move into runtime config schema, and whether ordinary UI / Service callback wait-id discovery deserves a separate design gate.
