# WU-TOOL-01 Implementation Slice 1 Codex

## Gate / Work Unit / Slice

- Gate: implementation
- Work unit: WU-TOOL-01 Attempt-scoped Duplicate Governance
- Slice: 1 - Typed Policy And Attempt-scoped Duplicate State
- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Controller plan pass: `docs/reviews/wu-tool-01-plan-rereview-controller-adjudication-20260601.md`
- Accepted plan commit: `c9a0c71`

## Scope / Non-goals / Allowed Files

- Allowed source files: `dayu/host/tool_runtime.py`, `dayu/host/tool_duplicate_governance.py`
- Allowed test file: `tests/host/test_toolruntime_duplicate_governance.py`
- Artifact: `docs/reviews/wu-tool-01-implementation-slice1-codex-20260601.md`
- Non-goals followed: no dispatch/tooling/tool_trace/README edits, no commit, no push, no PR, no review gate.

## Changed Files

- `dayu/host/tool_duplicate_governance.py`
- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `docs/reviews/wu-tool-01-implementation-slice1-codex-20260601.md`

## Implemented Plan Items

- Added Host-layer typed duplicate governance module with:
  - `DuplicateDecisionKind`
  - `DuplicateGovernanceScope`
  - `DuplicateGovernanceRequest`
  - `DuplicateDecision`
  - `DuplicateAcceptedEntry`
  - `DuplicateDurableMissingReason`
  - `DuplicateGovernanceMessages`
  - `DuplicateGovernancePolicy`
  - `InMemoryAttemptDuplicateGovernance`
  - typed private in-flight state helpers
- Moved ToolRuntime duplicate governance contracts to imports from `dayu.host.tool_duplicate_governance`.
- Added attempt scope to duplicate requests/decisions; key generation now includes `DuplicateGovernanceScope.attempt_id` and still excludes `index_in_iteration`.
- Made `DuplicateGovernancePort` async and updated ToolRuntime calls to await `decide_duplicate`, `record_accepted`, and `record_durable_missing`.
- Implemented attempt-local in-flight governance with one `asyncio.Condition`.
- Ensured tool callable execution and Host accept are outside duplicate governance condition ownership.
- Added owner terminal handling so accept rejected, accept timeout, callable exception, awaiting/policy pre-accept exits, and bounded cancellation paths record durable missing instead of leaving waiters blocked.
- Waiters observing durable missing now receive a governed duplicate failure with `duplicate_prior_accept_missing` and do not execute a second real tool call in the same in-flight window.
- Added duplicate scope to accept candidates and `TOOL_CALL_GOVERNED` payload projection when governed events are written.
- Added default duplicate messages matching prior zero-config text; message config rejects empty/whitespace values.
- Updated duplicate governance tests for attempt id in key, concurrent reuse, durable-missing accept rejected/timeout/tool exception, allow concurrent/post-owner completion, and message validation.

## Validation

```text
source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_duplicate_governance.py
```

Result: passed, 24 tests.

```text
source .venv/bin/activate && pyright
```

Result: passed, 0 errors.

```text
rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py
```

Original implementation result: non-empty. Remaining matches were unrelated truncation wording plus old dispatch-facing duplicate registry protocol/class/field names.

Fix-pass update: CR2 removed the old dispatch-facing duplicate registry protocol/class/field names from source and tests. Remaining run-scope terminology in `tool_runtime.py` is truncation-related.

## Docs Decision

No README was edited. `dayu/host/README.md` would normally be checked because `dayu/host/` changed, but this handoff explicitly forbids README edits in Slice 1. Documentation update remains owned by later allowed slice/review flow.

## Plan Gaps

- Fixed in code-fix: the old run-scoped duplicate registry protocol/classes, dispatch registry wiring, and scheduler registry lifecycle assertions were removed under CR2.
- Fixed in code-fix: owner cancellation now has a direct controllable cancellation-token concurrent test under CR4.

## Residual Risks

- Fixed in code-fix: no dispatch-facing duplicate registry compatibility surface remains in the allowed source/test files.
- README synchronization is deferred by explicit slice boundary. Owner: later docs-authorized slice/review flow.

## Completion / Stop Status

Status: completed for allowed Slice 1 files with a documented boundary residual. No stop condition required broader edits during validation: affected tests pass and full pyright passes without editing files outside the allowed set.
