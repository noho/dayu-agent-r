# WU-TOOL-01 Aggregate Review Controller Adjudication

## Gate

- Work unit: WU-TOOL-01 Duplicate Governance Concurrency and Cross-attempt Semantics
- Gate: aggregate review
- Branch: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- Base: `07cf34d397fe076979146163f34238b5c460ca7d`
- Controller role: adjudication only。

## Inputs

- Approved plan: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- Accepted slice commits:
  - Slice 1: `bd782be`
  - Slice 2: `5f09506`
  - Slice 3: `98ccd7a`
  - Slice 4: `660561a`
- Aggregate review:
  - `docs/reviews/wu-tool-01-aggregate-review-mimo-20260601.md`
  - `docs/reviews/wu-tool-01-aggregate-review-ds-20260601.md`

## Adjudication

No blocking findings. WU-TOOL-01 aggregate review passes.

Accepted conclusions:

- Duplicate key and governance scope are attempt-scoped; cross-Attempt fresh request and restart/non-durable behavior are tested.
- Same Attempt in-flight owner/waiter behavior is coordinated through async state and covered for accepted, cancellation, tool exception, accept rejection, accept timeout, and policy-driven `allow` paths.
- Production dispatch uses `HostToolingOptions.duplicate_governance_policy`; scheduler run-scoped registry lifecycle was removed.
- `TOOL_CALL_GOVERNED.payload.duplicate_scope`, tool trace `trace_summary["duplicate_scope"]`, and duplicate diagnostic messages are consistent with approved plan.
- README and tests README were synchronized within their documented responsibilities.
- No durable duplicate ledger, EventLog reconstruction of duplicate refs, SQLite schema change, compatibility wrapper/re-export, untyped signatures, reverse dependency, or over-coupling was found.

## Residual Risk Disposition

- `RR-TOOL-01` remains `deferred-with-owner`: awaiting fanout broader concurrency hardening is outside the accepted WU-TOOL-01 duplicate governance scope and has no concrete failure evidence in this work unit.
- `RR-TOOL-02` is closed by Slice 3: `tool_trace.py` now preserves `duplicate_scope` in trace summary and tests cover hot/cold projection.

## Controller Verification

Controller already ran the WU-TOOL-01 target gate during Slice 4 acceptance:

```bash
source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_dispatch_scheduler.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_tooling_options.py
source .venv/bin/activate && pyright
rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host tests/host dayu/host/README.md tests/README.md
```

Result:

- Targeted pytest: 123 passed
- `pyright`: 0 errors, 0 warnings, 0 informations
- Terminology grep: remaining matches are accepted truncation cursor, reactive compaction token, or test data id contexts.

## Decision

WU-TOOL-01 passes aggregate review and may move to local gate closeout / ready-to-open-draft-PR once the control document records the aggregate artifacts and residual risk dispositions.
