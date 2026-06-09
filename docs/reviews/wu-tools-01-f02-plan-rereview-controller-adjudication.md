# WU-TOOLS-01-F02 Plan Re-Review Controller Adjudication

## Gate

- Work unit: `WU-TOOLS-01-F02`
- Current gate: re-review adjudication
- Plan artifact: `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Fix artifact: `docs/reviews/wu-tools-01-f02-plan-fix-codex.md`
- MiMo re-review artifact: `docs/reviews/wu-tools-01-f02-plan-rereview-mimo.md`
- DS re-review artifact: `docs/reviews/wu-tools-01-f02-plan-rereview-ds.md`
- Decision date: 2026-06-09

## Overall Decision

Plan re-review verdict is `pass`.

Both re-review agents confirmed all 10 Controller-accepted plan review findings are fixed or have preserved evidence in the plan. There are no blocking findings, no scope creep, and no need for another plan fix loop.

## Accepted Finding Status

| Finding group | Status | Controller judgment |
|---|---|---|
| sync / async bridge | fixed | Plan now specifies synchronous CLI, `asyncio.run()` only at current async callable boundary, sync Playwright helper, and no nested event-loop API in F02. |
| raw requests header source | fixed | Plan now states the helper-vs-local selection rule and requires diagnostic path labeling when using local headers. |
| CLI config mapping | fixed | Plan now maps CLI values to current `WebToolsConfig` / `ToolsDiscoveryProviderSpec.config` fields and JSON value types. |
| batch child-process crash | fixed | Plan now defines `child_process_error` / equivalent non-comparison status and summary handling. |
| diagnostic cancellation token | fixed | Plan now requires a private never-cancelled `_DiagnosticCancellationToken` implementing the current protocol. |
| `discover_tools` ambiguity | fixed | Plan now names the Web provider entry and forbids runtime aggregate discovery for this utility. |
| tests vs `utils/` exemption | fixed | Plan now explains why parser / classifier / current-contract adapter need deterministic tests despite `utils/` coverage exemption. |
| F03 minimal utility schema | fixed | Plan now defines the stable subset and leaves schema mismatch policy to F03. |
| comparison bucket decision tree | fixed | Plan now contains a deterministic decision tree over current outcome shapes and non-success states. |
| user authorization and `utils` coding boundary | fixed / evidence preserved | Original plan boundary remains intact and is now reinforced. |

## New Findings

MiMo and DS both noted that the challenge-detection exception in the comparison bucket decision tree leaves "low confidence hint" to deterministic tests. Controller adjudication:

- Decision: `accepted`
- Severity: low
- Owner: WU-TOOLS-01-F02 implementation, Slice 3 deterministic tests
- Rationale: This is not a plan-blocking ambiguity. The plan already requires deterministic tests for bucket behavior, and implementation is the right point to encode concrete challenge fixture semantics without over-specifying production challenge detection in the plan.

## Residual Risks

All residual risks are classified and have owners:

- Live network instability: accepted as explicit opt-in diagnostic evidence, not default CI.
- Playwright/browser installation variance: accepted as diagnostic profile failure.
- Diagnostic utility schema: stable F02 subset defined; F03 owns smoke dependency and mismatch policy.
- Sensitive headers / storage state: implementation owns redaction and no-inline rules.
- Challenge low-confidence exception: WU-TOOLS-01-F02 Slice 3 deterministic tests.

## Next Gate

Proceed to accepted plan commit, then implementation gate.

