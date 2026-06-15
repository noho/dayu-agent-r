# WU-CLI-01 Plan Review Controller Adjudication

## Gate

- Work unit: WU-CLI-01 CLI entrypoint integration aligned with dayu-agent CLI
- Gate: plan review adjudication
- Plan artifact: `docs/host/wu-cli-01-cli-entrypoint-plan.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260614-130113.md`
  - `docs/reviews/wu-cli-01-plan-review-ds.md`

## Controller Decision

Plan direction is accepted, but the plan is not yet code-generation-ready. Proceed to plan fix gate before implementation.

The plan correctly preserves the user-confirmed scope, treats CLI as a UI adapter, adapts old CLI / Fins business semantics to the new Service / Fins / Host public contracts, avoids mechanical migration of old implementation structure, and fixes the Host live-watch fast-terminal race with submit-before-watch correction. Review findings identify contract details that must be made explicit before implementation.

## Finding Adjudication

| Review finding | Decision | Reason |
|---|---|---|
| DS F01 / MiMo 01: `CancelRunRequest` construction incomplete | accepted | `CancelRunRequest` requires `HostCallContext`, `client_request_id`, `reason`, and `CancelMode`; implementation cannot safely infer idempotency and context construction. |
| DS F02: `ReadOutboxTerminalItemsRequest` cursor / projection handling missing | accepted | Outbox fallback is part of the race-free terminal wait strategy; cursor, seen ids, `LAGGED`, `FAILED`, and caught-up-without-match behavior must be specified using public API only. |
| DS F03 / MiMo 01 / MiMo 05: `HostCallContext` construction strategy missing | accepted | CLI / reusable Service boundary must define how UI adapter identity, request id, authorization claims, and operation context are built or passed through without CLI-specific hardcoding inside reusable Service logic. |
| DS F04: submit follow-up override helper strategy ambiguous | accepted | The plan must choose a concrete helper shape so implementation does not decide between mutating existing helper behavior and adding a sibling helper. |
| DS F05: Fins upload direct methods vs `FinsIngestionRuntime.start_upload` mapping unclear | accepted | The Service-facing convenience methods must explicitly construct typed upload requests and call the actual union-based runtime API. |
| DS F06: interactive watcher lifecycle unclear | accepted | Multi-turn interactive must close or isolate each watcher, avoid event leakage, and define per-turn lifecycle cleanup. |
| DS F07: explicit config overlay error behavior unspecified | accepted | Explicit `--config` path should have a clear fail-fast or fallback contract; silent fallback for explicit user input would be surprising. |
| DS F08 / MiMo 03: `--ticker` to scene context slot mapping not explicit | accepted | Current manifest slots should be named in the plan so implementation does not guess. |
| DS F09 / MiMo 02: `init --reset` deletion whitelist not enumerated | accepted | Reset is destructive; allowed paths and excluded Fins data paths must be explicit. |
| DS F10: unsupported old debug / trace / duplicate flags wording inconsistent | accepted | Unsupported old flags must have one consistent behavior: parse if retained, fail fast with a user-facing unsupported error, and never silently ignore or raw-payload forward. |
| MiMo 04: Fins direct job poll interval unspecified | accepted | Direct Fins job polling must define a default interval and testable behavior to avoid excessive file-store churn or poor UX. |
| MiMo 06: interactive failed terminal fatal / non-fatal policy unspecified | accepted | Interactive loop needs deterministic behavior for `FAILED`, `CANCELLED`, `LOST`, Host handle errors, and user cancellation. |
| DS open question: third terminal source for contract violation | rejected-with-reason | The plan can model caught-up-without-terminal as a Service error/diagnostic instead of a third successful terminal source; no additional terminal source enum is required for implementation. |

## Required Plan Fix Scope

AgentCodex should update only `docs/host/wu-cli-01-cli-entrypoint-plan.md` to address all accepted findings above. It must not modify production code, tests, README, control doc, or review artifacts.

The fix should preserve the core plan decisions:

- Migrate old CLI/Fins business semantics, user-visible behavior, parameter surface, and cancel semantics; do not migrate old implementation structure.
- Keep reusable Service semantics reusable by future WeChat / GUI.
- Keep prompt / interactive on `ConfigLoader -> ScenePrepare -> ToolsDiscovery -> Service assembly -> Host public API`.
- Keep Fins direct commands on approved Service / Fins boundary with cancel support.
- Use only public Host APIs; do not read Host durable internals.

## Residual Risks

No unowned residual risk remains at this gate. Accepted findings are owned by WU-CLI-01 plan fix and must be re-reviewed before accepting the plan.
