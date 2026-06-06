# WU-TOOLS-01 Plan Review Controller Adjudication

Gate: plan review  
Work unit: WU-TOOLS-01  
Review artifacts:

- `docs/reviews/wu-tools-01-plan-review-mimo.md`
- `docs/reviews/wu-tools-01-plan-review-ds.md`

## Controller Decision

Plan review outcome: needs plan fix.

Both reviewers accepted the overall migration direction: one combined work unit, shared document foundations outside Engine/runtime, providers entering through `ToolsDiscovery`, Host-owned `ToolRuntime`, Fins storage under `dayu.fins.storage`, and no migration of old UI files. The plan also covers the user constraints around old `ToolRegistry`, old `TruncationManager`, old `fetch_more`, current `ToolTruncateSpec`, input projection and response projection.

The plan is not accepted yet because several findings affect code-generation readiness for the first implementation slices.

## Accepted Findings

### A1 Adapter API Is Not Code-Generation-Ready

Source: AgentDS Finding 1.

Decision: accepted.

Reason: S2 is the shared contract that later Doc/Fins/Web provider slices depend on, but the plan does not define concrete interfaces for the new adapter collector and definition adapter. Leaving these APIs for implementation would force the implementation agent to design rather than execute.

Required plan fix:

- Define concrete class/function names and typed signatures for the new adapter collector and definition adapter.
- Define the collector output shape consumed by provider slices.
- Define the adapter output shape as current `ToolDefinition` values with async `ToolCallable`.

### A2 Path Metadata And Enforcement Boundary Must Be Unambiguous

Source: AgentDS Finding 2; AgentMiMo Finding F2.

Decision: accepted.

Reason: User explicitly裁决迁移后的 Doc tools 不负责路径安全机制. The plan must avoid old `ToolRegistry.register_allowed_paths` semantics leaking into a new collector. The collector may collect metadata; path whitelist / fail-closed enforcement belongs to provider/adapter/assembly/ToolRuntime boundary.

Required plan fix:

- Rename or restate the collector API so it does not imply old `ToolRegistry.register_allowed_paths` enforcement.
- Specify that `file_path_params` metadata is collected from old decorators and consumed by provider/adapter path validation.
- Specify failed path validation maps to current `ToolFailedOutcome`.
- Add tests proving Doc function bodies are not responsible for path safety.

### A3 Current `ToolTruncateSpec` Declaration Must Be Fully Specified

Source: AgentDS Finding 5; AgentMiMo Finding F1; user裁决.

Decision: accepted.

Reason: The user explicitly required migrated tools to use the new `ToolTruncateSpec` declaration and not migrate old truncation / `fetch_more` implementation. The current plan says old metadata is converted, but does not fully specify how old decorator imports/declarations avoid becoming an old runtime contract.

Required plan fix:

- State that migrated tool declarations use current `dayu.contracts.tool_schema.ToolTruncateSpec`.
- If an old decorator or helper is retained as an adapter declaration helper, it may only accept/currently emit current `ToolTruncateSpec`; it must not copy old `ToolTruncateSpec` as runtime contract.
- Add a mapping table or explicit rule for each old truncate declaration field used by Doc/Fins/Web tools into current `ToolTruncateSpec`.
- Add tests that no old `ToolTruncateSpec`, old `TruncationManager`, old `fetch_more`, or old truncate/fetch-more projection is imported or used.

### A4 Input And Response Projection Needs Concrete Adapter Contract

Source: user裁决; AgentMiMo residual R5 review; AgentDS related observations.

Decision: accepted.

Reason: The plan added R5, but implementation still needs a precise adapter contract for projecting `ToolCallRequest.arguments` into old function keyword arguments and old returns/errors into current outcomes.

Required plan fix:

- Define the input projection API and error behavior.
- Define when direct pass-through is allowed and when coercion/validation is required.
- Define response projection API for success, old `ok/value` envelopes, dict/list/string returns, business errors and adapter validation failures.
- Add slice-level tests for direct pass-through, projected/coerced input, success response projection, and failure response projection.

### A5 Fins Ingestion Conditional Stop Needs Artifact Destination

Source: AgentDS Finding 3; AgentMiMo Finding F4.

Decision: accepted.

Reason: The plan correctly avoids inventing wait semantics, but the conditional stop must have a durable artifact path and handoff format so the Controller can classify the residual.

Required plan fix:

- Specify blocker artifact path, for example `docs/reviews/wu-tools-01-s4-ingestion-blocker-codex.md`.
- Specify required blocker content: affected tools, direct evidence, why completed/failed mapping is insufficient, required wait/awaiting semantics, proposed owner/destination.
- State the conservative default: migrate read tools first; include ingestion tools only when synchronous completed/failed mapping is directly proven.

### A6 `asyncio.to_thread` Requires Concurrency Boundary

Source: AgentDS Finding 4.

Decision: accepted.

Reason: The plan chooses `asyncio.to_thread` for old sync functions but does not classify thread-safety risk. Because old business function bodies must not be changed, the adapter plan must define a conservative execution boundary.

Required plan fix:

- Add a thread-safety decision for old sync callables.
- Define whether adapter execution is per-tool serialized by default, provider-serialized for known non-thread-safe tools, or explicitly allowed concurrent only after evidence.
- Add tests for concurrent ToolRuntime calls or a documented stop condition if a provider cannot be safely concurrent.

### A7 Slice Stop Conditions And Ambiguous "May" Wording Need Tightening

Source: AgentDS Findings 6 and 7.

Decision: accepted.

Reason: Plan wording should not leave implementation scope open. S6 must stop on provider ToolRuntime accept failures; optional helper migration must be an explicit include/exclude list.

Required plan fix:

- Replace ambiguous `may` wording with explicit allowed helper lists or explicit per-slice inventory steps.
- Add S6 stop condition for any provider failing ToolRuntime accept integration.
- Add dependency inventory checks for old helper files such as `utils_tools.py`, classifying them as included, excluded, or needs-more-evidence before implementation proceeds.

## Needs More Evidence

### N1 Exact Old Helper Import Closure

Source: AgentMiMo Finding F3.

Decision: needs-more-evidence.

Reason: MiMo identified possible old helper files such as `utils_tools.py`, but did not complete a full import closure because old-repo reads were interrupted. The plan fix should not guess which helpers are required.

Required plan fix:

- Add an explicit import-closure inventory step before each migration slice copies old files.
- Require the implementation agent to classify every old helper as included, excluded-with-reason, or blocker.

## Rejected Findings

None.

## Residual Risk Classification

- `WU-TOOLS-01-R1`: accepted into plan fix A2.
- `WU-TOOLS-01-R2`: remains covered by S2/S3/S4/S5 typed config work; no additional fix beyond adapter API clarity.
- `WU-TOOLS-01-R3`: accepted into plan fix A1/A4.
- `WU-TOOLS-01-R4`: accepted into plan fix A3.
- `WU-TOOLS-01-R5`: accepted into plan fix A4.
- Fins ingestion waiting semantics: accepted into plan fix A5.
- Old sync callable concurrency: accepted into plan fix A6.
- Old helper import closure: needs-more-evidence N1, to be handled by plan fix as an implementation inventory requirement.

## Next Gate

Dispatch AgentCodex to plan fix. Expected artifact remains `docs/host/wu-tools-01-migration-plan.md`; optional fix report path is `docs/reviews/wu-tools-01-plan-fix-codex.md`.
