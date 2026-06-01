# WU-TOOL-01 Slice 1 Code Fix

## Gate / Role

- Gate: code fix
- Role: fix specialist; only fixed controller accepted findings CR1-CR6.
- Work unit: WU-TOOL-01 Attempt-scoped Duplicate Governance
- Slice: 1 - Typed Policy And Attempt-scoped Duplicate State
- Source reviews:
  - `docs/reviews/wu-tool-01-code-review-slice1-mimo-20260601.md`
  - `docs/reviews/wu-tool-01-code-review-slice1-ds-20260601.md`
- Controller adjudication: `docs/reviews/wu-tool-01-code-review-slice1-controller-adjudication-20260601.md`

## Accepted Finding Fix Status

| Finding | Status | Fix summary |
|---|---|---|
| CR1 | fixed | Removed duplicate governance typed contracts and implementation symbols from `tool_runtime.py.__all__`; ToolRuntime keeps only internal imports where needed. |
| CR2 | fixed | Deleted `RunScopedDuplicateGovernanceRegistry`, `InMemoryRunScopedDuplicateGovernanceRegistry`, and `ToolRuntimeBuildRequest.duplicate_governance_registry`; removed dispatch registry import/field/clear calls/build argument; removed scheduler tests that inspected registry lifecycle. |
| CR3 | fixed | Moved `DuplicateGovernancePort` into `dayu.host.tool_duplicate_governance`; `tool_runtime.py` imports it for internal typing and does not re-export it. |
| CR4 | fixed | Added controllable cancellation-token concurrent test; waiter receives `duplicate_prior_accept_missing`, no second real call starts in the same in-flight window, and later caller becomes fresh owner. |
| CR5 | fixed | Strengthened accept-timeout durable-missing test with owner/waiter outcome assertions, waiter hint assertion, and later fresh-owner assertion. |
| CR6 | fixed | Removed `_duplicate_message()` fallback; duplicate decisions/candidates now fail fast when configured message/diagnostic fields are missing. |

## Changed Files

- `dayu/host/tool_duplicate_governance.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/dispatch.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_dispatch_scheduler.py`
- `docs/reviews/wu-tool-01-implementation-slice1-codex-20260601.md`
- `docs/reviews/wu-tool-01-fix-slice1-codex-20260601.md`

## Validation

```text
source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_duplicate_governance.py
```

Result: passed, 26 tests.

```text
source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py
```

Result: passed, 57 tests.

```text
source .venv/bin/activate && pyright
```

Result: passed, 0 errors.

Additional check:

```text
rg -n "RunScopedDuplicateGovernanceRegistry|InMemoryRunScopedDuplicateGovernanceRegistry|duplicate_governance_registry|_duplicate_governance_registry|active_run_count|_duplicate_message|DuplicateGovernancePort" dayu/host/tool_runtime.py dayu/host/tool_duplicate_governance.py dayu/host/dispatch.py tests/host/test_dispatch_scheduler.py tests/host/test_toolruntime_duplicate_governance.py
```

Result: no old run-scoped duplicate registry, registry lifecycle, or `_duplicate_message` matches in source/tests. `DuplicateGovernancePort` remains only in `tool_duplicate_governance.py` and internal ToolRuntime type annotations.

## Residual Risks

- Deferred DS M3 awaiting fanout remains out of this fix by controller instruction.
- Deferred DS L3 `tool_trace.py` `duplicate_scope` projection remains out of this fix by controller instruction.
- README synchronization was not performed because this fix handoff did not allow README edits.

## Stop Status

No stop condition triggered. Fix pass completed for CR1-CR6 within allowed files; no commit, push, PR, or re-review was performed.
