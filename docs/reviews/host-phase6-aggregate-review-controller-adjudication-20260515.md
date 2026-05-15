# Host Phase 6 Aggregate Review Controller Adjudication

## Scope

- Gate: Phase 6 aggregate review
- Branch: `feat/host-phase-6-toolruntime`
- Reviewed range: `a5863ce` through `203a69a`
- Design truth: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Review artifacts:
  - `docs/reviews/host-phase6-aggregate-review-mimo-20260515.md`
  - `docs/reviews/host-phase6-aggregate-review-ds-20260515.md`

## Review Summary

Both independent aggregate reviews returned `BLOCKED`.

Both reviewers found the same Phase 6 exit blocker: duplicate governance is currently implemented as ToolRuntime-instance-local memory, while the design and control docs require Run-local semantics across same-Run, same-process multi-Attempt paths.

## Findings Adjudication

### P6-AGG-F1: Run-local duplicate governance is still ToolRuntime-instance-local

- Source reviewers:
  - AgentMiMo: blocking, severe.
  - AgentDS: blocking, severe.
- Controller decision: accepted as blocking.
- Owner: Phase 6 aggregate fix.
- Required outcome: aggregate re-review must confirm fixed before PR creation.

Direct evidence:

- `docs/host/design.md` §18.3 states that run-local duplicate governance is a Run-scoped governance semantic, not an Attempt or ToolRuntime instance lifecycle semantic. Same-Run, same-process new Attempts created by `WAITING -> resolve_wait -> resume`, steer, or recovery must continue to reuse the Run duplicate index.
- `docs/host/implementation-control.md` marks this as a Phase 6 exit standard and says an implementation tied only to a ToolRuntime instance lifecycle is a Phase 6 blocker.
- `dayu/host/dispatch.py` creates a new ToolRuntime handle during scheduler dispatch.
- `dayu/host/tool_runtime.py` creates a new `InMemoryRunLocalDuplicateGovernance` inside `DefaultToolRuntimeFactory.create_tool_runtime`.
- `InMemoryRunLocalDuplicateGovernance` stores accepted records in an instance-local `_entries_by_key` dictionary.
- `tests/host/test_toolruntime_duplicate_governance.py` still contains a test asserting a new ToolRuntime does not inherit the duplicate index, which now contradicts the Phase 6 exit standard for same-Run same-process paths.

Risk:

If a Run creates a new Attempt in the same Host process, the second Attempt can repeat a tool call already accepted by the first Attempt and the duplicate governance index will be empty. That violates the P6 Run-local duplicate governance requirement and can repeat tool work, including paid or side-effect-sensitive calls that should have been reused, hinted, justified, or stopped.

Required fix criteria:

- Introduce a Run-scoped in-memory duplicate governance owner or registry that is reused by same-Run, same-process ToolRuntime handles.
- Preserve the design boundary that P6 does not introduce a durable duplicate ledger and does not promise crash/restart recovery of duplicate memory.
- Ensure different Runs do not share duplicate memory.
- Ensure terminal or closed scheduler lifecycle does not leak Run duplicate index memory.
- Update tests so the same-Run same-process multi-Attempt path inherits duplicate memory, while different Runs remain isolated.
- Update `dayu/host/README.md` if the current ToolRuntime description still says duplicate memory only exists in the current ToolRuntime instance.

### P6-AGG-F2: Repeated factory allocation in scheduler

- Source reviewers:
  - AgentDS: non-blocking maintainability observation.
- Controller decision: accepted as non-blocking optional cleanup.
- Owner: Phase 6 aggregate fix only if it naturally falls out of F1; otherwise ToolRuntime hardening.

Rationale:

The current factory/builder allocation is not a correctness issue because the involved objects are lightweight and stateless today. F1 may require introducing scheduler-owned duplicate registry or factory dependencies; if the implementation naturally centralizes factory ownership, this observation can be closed. It must not distract from the Run-local semantic fix.

## Aggregate Gate Decision

`BLOCKED`.

Phase 6 cannot proceed to PR creation until P6-AGG-F1 is fixed and aggregate re-review confirms the fix. The next action is Phase 6 aggregate fix handoff.
