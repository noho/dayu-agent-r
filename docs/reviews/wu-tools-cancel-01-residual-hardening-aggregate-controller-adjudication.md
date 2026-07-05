# WU-TOOLS-CANCEL-01 Residual Hardening Aggregate Controller Adjudication

## Scope

- Work unit: WU-TOOLS-CANCEL-01 residual hardening reopen
- Gate: aggregate / final review
- Branch: `phase/wu-tools-cancel-01`
- Review range: reopened residual hardening commits from `6166d0e9..HEAD`
- Aggregate review artifacts:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-review-ds.md`
- Aggregate fix artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-fix-codex.md`
- Aggregate re-review artifacts:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-rereview-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-aggregate-rereview-ds.md`

## Decision

PASS.

The reopened residual hardening gates are accepted after aggregate review, accepted test fixes, targeted re-review, and controller validation. All five user-mandated residuals are closed by code, tests, and docs evidence.

## Finding Disposition

- MiMo-001 LOW: config `process_capsule_interrupt_policy` unknown fields lacked a focused regression test.
  - Decision: accepted and fixed.
  - Closure: `tests/runtime/test_config_loader.py::test_host_runtime_process_capsule_policy_rejects_unknown_fields` now covers unknown-field rejection through `ConfigLoader.load_host_runtime()`.

- MiMo-002 LOW: default factory wiring path for custom `ProcessCapsuleInterruptPolicy` lacked end-to-end coverage.
  - Decision: accepted and fixed.
  - Closure: `tests/host/test_toolruntime_executor.py::test_tool_runtime_default_factory_wires_process_capsule_interrupt_policy` now proves a custom policy reaches the process-backed capsule close path through `DefaultToolRuntimeFactory` and declared `ProcessBackedToolExecutionCapability`.

- MiMo-003 / DS Doc generic hint consistency: rejected as current fix.
  - Rationale: `hint` is optional by contract, and the Doc generic exception path has no concrete recovery hint. Adding a vague LLM-facing hint would not improve correctness.

- DS Web blank-input fallback and numeric int acceptance findings: rejected as current fix.
  - Rationale: both are low-risk style / strictness observations with correct current behavior and no cancellation robustness impact.

## Controller Validation

Controller reran validation after the accepted aggregate fixes:

```bash
source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/host/test_toolruntime_executor.py -q
source .venv/bin/activate && pyright
git diff --check
```

Results:

- `pytest tests/runtime/test_config_loader.py tests/host/test_toolruntime_executor.py -q`: 114 passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

## Residual Risk

- Live Chromium process-tree cleanup remains environment-dependent. The deterministic synthetic nested-child path is covered by always-on tests; live Chromium cleanup remains opt-in via `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`.
- Web process cold-start remains deferred as performance-only unless future evidence shows cancellation robustness impact.
- POSIX PID/PGID reuse remains the same runtime limitation recorded by S2A and was not expanded by S2B.

## Next Entry Point

Proceed to the existing draft PR #170 closeout/update gate. Do not mark PR #170 ready, merge, close #87 directly, request reviewers, delete the branch, or publish external closeout comments without explicit authorization.
