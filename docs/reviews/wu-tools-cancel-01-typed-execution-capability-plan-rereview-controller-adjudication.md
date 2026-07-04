# WU-TOOLS-CANCEL-01 Typed Execution Capability Plan Re-Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-CANCEL-01 Tool/provider blocking I/O cancellation hardening`
- Gate: design/contract plan re-review
- Plan artifact: `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md`
- Initial plan review artifacts:
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-review-ds.md`
- Fix artifact: `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-rereview-ds.md`

## Accepted Findings

Controller accepted the material plan review findings from AgentDS and AgentMiMo:

- Process-backed target must not return broad `ToolExecutionOutcome`.
- Process-backed factory must not receive full `BatchToolExecutionContext`.
- `dayu.runtime.interruptible_process` must remain a layer-neutral `JsonValue` process helper.
- S2A must be split so contract/declaration/digest and Host factory wiring can be reviewed independently.
- Direct `ToolDefinition(...)` construction sites must be fully scanned and migrated.
- Provider lock semantics, `thread_backed` guard, Fins child-process feasibility, digest JSON shape, Web async close validation, timeout ownership, and pickle round-trip verification must be explicit in the plan.

## Closure

AgentCodex fixed the plan by selecting a single contract shape:

- `ToolDefinition.execution` remains the typed declaration source in `dayu.contracts`.
- `ProcessBackedToolTarget.__call__()` returns a `JsonValue` JSON envelope, not `ToolExecutionOutcome`.
- `ProcessBackedToolContext` is projected from `BatchToolExecutionContext` and contains only serializable scalar fields.
- Host capsule maps `completed` / `failed` envelopes to tool outcomes and owns cancel / timeout mapping.
- `dayu.runtime.interruptible_process` is not extended with tool outcome semantics.
- S2A is split into S2A1 contract/declaration/digest and S2A2 Host factory wiring.

AgentMiMo and AgentDS re-review both returned `PASS` with all accepted findings closed and no new findings.

## Verdict

Controller verdict: `PASS`.

The typed execution capability plan is accepted. The next gate is implementation starting with S2A1 `contract / declaration / digest`; S2A2 and the Doc / Fins / Web process-backed migrations must not start until their stated prerequisites and stop conditions are satisfied.

## Validation

- `git diff --check` -> passed.
