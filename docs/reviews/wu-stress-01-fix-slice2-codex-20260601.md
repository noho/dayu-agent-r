# WU-STRESS-01 Slice 2 Code Review Fix Artifact

## Scope

- Role: AgentCodex, Slice 2 implementation fix.
- Controller adjudication: `docs/reviews/wu-stress-01-code-controller-adjudication-slice2-20260601.md`.
- Scope limit: Slice 2 only; no Slice 3-5 implementation, no production code changes, no commit/push/PR.

## Changed Files

- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`

## Adjudication Status

- ADJ-S2-01: fixed.
  - Replaced the 15-parameter `_slice2_failure_boundary` with slice-local typed diagnostics.
  - Split diagnostics into focused dataclasses: live owner, recovery, terminal, attempt, and a small aggregate.
  - No naked `dict`, `Any`, or `object` was introduced.
- ADJ-S2-02: fixed.
  - `HostStressSummary.failure_boundary` and the test assertion now both reuse `Slice2StressDiagnostics.failure_boundary`.
  - Removed the duplicate per-field assertion block that independently reimplemented the same checks.
- ADJ-S2-03: fixed.
  - `scheduler_drained` is now derived from Slice 2 diagnostics: terminal coverage, public succeeded terminals, recovery accept count, attempt replacement, and attempt counts.
  - Added `_slice2_watch_lag_placeholder()` documenting that Slice 2 does not measure watch lag and the value is only a schema placeholder.
- ADJ-S2-04: fixed.
  - `start_and_crash_owner_for_stress` now only performs cleanup termination on the exception path when the process is still alive.
  - `_run_live_owner_probe` no longer terminates an already joined process on the normal path.
  - Cleanup failure is raised from the original exception to preserve context.
- ADJ-S2-05: deferred.
  - No terminal dedupe framework change was made.
  - The mixed terminal semantics question remains owned by Slice 5 implementation/review.

## Validation

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k repeated_startup_recovery_crash -q
```

Result: `1 passed, 1 deselected`.

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_multiprocess.py -q
```

Result: `3 passed`.

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

## Residual Risks

- Slice 2 still uses 3 crash cycles, the minimum accepted by the plan, to keep runtime stable.
- Watch lag remains intentionally unmeasured in Slice 2; Slice 3 owns real watch lag diagnostics.
- Terminal duplicate semantics remain unchanged for Slice 2 and are deferred to Slice 5 for mixed terminal scenarios.
