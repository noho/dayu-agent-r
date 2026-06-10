# WU-TOOLS-01-F02 Plan Review Controller Adjudication

## Gate

- Work unit: `WU-TOOLS-01-F02`
- Current gate: plan review adjudication
- Plan artifact: `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- MiMo review artifact: `docs/reviews/wu-tools-01-f02-plan-review-mimo.md`
- DS review artifact: `docs/reviews/wu-tools-01-f02-plan-review-ds.md`
- Decision date: 2026-06-09

## Overall Decision

Plan review verdict is `fix-required`.

Both review agents judged the plan code-generation-ready in broad architecture and scope, but their findings identify small missing implementation decisions that should be fixed in the plan before accepted-plan commit. None of the findings require changing the goal, design source, Host / Engine / ToolRuntime public contract, or F02 scope.

## Findings Adjudication

| Source | Finding | Controller Decision | Required plan fix |
|---|---|---|---|
| MiMo F-1 | sync-to-async bridge strategy is not explicit | accepted | Add a concrete CLI execution model: synchronous CLI entry, `asyncio.run()` only around current async `ToolDefinition.callable`, Playwright remains sync API inside optional browser helper, and no nested event-loop support in F02. |
| MiMo F-2 | raw requests profile header source tradeoff is unresolved | accepted | Add a clear selection rule for raw requests headers: prefer current Web helper only when it does not expand production public surface; otherwise use local diagnostic headers and mark them as raw diagnostic path, not production fetch path. |
| MiMo F-3 | CLI args to `WebToolsConfig` mapping not expanded | accepted | Add exact CLI-to-provider-config field mapping and JSON value types for current `WebToolsConfig`. |
| MiMo F-4 | batch child-process crash propagation not defined | accepted | Add explicit `child_process_error` handling for batch rows / summary, or an equivalent non-comparison status that preserves stderr prefix and diagnostic path absence. |
| DS Finding 1 | `CancellationToken` concrete implementation not specified | accepted | Add private `_DiagnosticCancellationToken` plan detail implementing the current protocol with never-cancelled semantics. |
| DS Finding 2 | `discover_tools` name ambiguity | accepted | Specify the exact provider import path: `dayu.tools.web.provider.discover_tools` or `dayu.tools.web.discover_tools` provider entry, returning `ToolsDiscoveryProviderOutput.definitions`, not runtime aggregate discovery. |
| DS Finding 3 | plan does not explain why tests exceed `utils/` default exemption | accepted | Add rationale: parser / classifier / current-contract adapter are non-trivial and deserve deterministic tests despite `utils/` coverage exemption; shell wrapper/corpus checks can remain light. |
| DS Finding 4 | diagnostic JSON stability for F03 is underdefined | accepted | Add minimal stable utility schema subset for F03: `schema_version`, `url`, `comparison_bucket`, per-path sampled/ok/elapsed/error/status fields, and schema mismatch behavior deferred to F03. |
| DS Finding 5 | comparison bucket algorithm not defined | accepted | Add a concise deterministic classification decision tree, including current outcome shapes and non-success outcomes. |
| DS Finding 6 | user supplemental authorization handled correctly | accepted | No plan fix required beyond preserving existing boundary. This is confirming evidence. |
| DS Finding 7 | `utils/` strong typing and Chinese docstring requirements covered | accepted | No plan fix required. This is confirming evidence. |

## Deferred / Rejected

No findings are rejected or deferred. No finding requires a new owner, external issue, or design-source change.

## Next Gate

Dispatch plan fix to AgentCodex.

Expected fix artifact: `docs/reviews/wu-tools-01-f02-plan-fix-codex.md`.

Accepted findings above are the only allowed fix scope. The fix must update `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md` and write the fix artifact. It must not modify implementation code, tests, README, controller artifacts, commit, push, PR, or enter re-review.

