# WU-TOOLS-01 Plan Re-Review Controller Adjudication

Gate: plan re-review  
Work unit: WU-TOOLS-01  
Controller: phaseflow  
Date: 2026-06-05  
Decision: accepted plan

## Inputs

- Plan artifact: `docs/host/wu-tools-01-migration-plan.md`
- Plan fix artifact: `docs/reviews/wu-tools-01-plan-fix-codex.md`
- Initial plan reviews:
  - `docs/reviews/wu-tools-01-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-plan-review-ds.md`
- Initial controller adjudication: `docs/reviews/wu-tools-01-plan-review-controller-adjudication.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-01-plan-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-plan-rereview-ds.md`

## Re-Review Result

AgentMiMo and AgentDS both returned `PASS`.

Both reviewers verified that the plan fix resolved all Controller accepted findings:

- A1 adapter collector / adapter API now has concrete class and function names, typed signatures, collector output shape, and `ToolDefinition` adapter output shape.
- A2 path metadata and enforcement boundary is explicit: migrated Doc tool function bodies do not own path safety; `file_path_params` is metadata consumed by the outer adapter / provider boundary; `register_allowed_paths(...)` is not trusted enforcement.
- A3 truncation is anchored on current `dayu.contracts.tool_schema.ToolTruncateSpec`; OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, and OLD truncation / fetch-more projection remain out of scope.
- A4 input projection and response projection now have concrete adapter APIs, pass-through conditions, coercion / validation rules, success mapping, old envelope mapping, and failure mapping.
- A5 Fins ingestion has a conservative default and a concrete blocker artifact destination if synchronous completed / failed mapping cannot be proven.
- A6 old sync callables have an explicit concurrency boundary around `asyncio.to_thread`, defaulting to per-tool serialization unless direct evidence and tests justify wider concurrency.
- A7 ambiguous helper wording and slice stop conditions were tightened with explicit import-closure inventory requirements and S6 ToolRuntime accept stop conditions.
- N1 old helper import closure is handled as an implementation-time inventory requirement rather than a guessed plan-time helper list.

## Controller Decision

The plan is accepted for WU-TOOLS-01 implementation.

The accepted plan keeps the user-specified migration constraints:

- Do not migrate OLD `ToolRegistry`.
- Do not migrate OLD `TruncationManager`.
- Do not migrate OLD `fetch_more`.
- Use current `ToolTruncateSpec` declarations for migrated tools that need truncation.
- Keep path safety outside migrated Doc tool function bodies.
- Put typed config, ToolDiscovery, ToolRuntime, query projection, and response projection adaptation in outer adapter / provider / assembly code.
- Preserve migrated OLD class / function signatures and function bodies except for allowed import, package, declaration, and minimal adapter changes.

## Residual Risk Handling

The following residual risks remain open intentionally and move from plan-gate questions to implementation-time tracking:

- `WU-TOOLS-01-R1`: path safety adapter.
- `WU-TOOLS-01-R2`: typed config adapter.
- `WU-TOOLS-01-R3`: ToolDiscovery / ToolRuntime adapter.
- `WU-TOOLS-01-R4`: truncation / fetch_more owner.
- `WU-TOOLS-01-R5`: query / response projection adapter.

These are no longer blockers for accepting the plan because the plan specifies owner, boundary, stop conditions, and tests. They must be revisited after WU-TOOLS-01 migration is complete to decide whether a better long-term design is needed.

## Next Gate

Proceed to accepted plan commit, then dispatch AgentCodex for the first implementation slice defined by the accepted plan.
