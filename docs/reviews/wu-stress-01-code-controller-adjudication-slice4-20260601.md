# WU-STRESS-01 Slice 4 Code Review Controller Adjudication

## Gate

- **Gate**: Slice 4 code review adjudication
- **Work Unit**: WU-STRESS-01 Host Production Stress Suite
- **Slice**: Slice 4 scheduler / liveness long-run stress
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- **Implementation artifact**: `docs/reviews/wu-stress-01-implementation-slice4-codex-20260601.md`
- **Review artifacts**:
  - `docs/reviews/wu-stress-01-code-review-slice4-mimo-20260601.md`
  - `docs/reviews/wu-stress-01-code-review-slice4-ds-20260601.md`

## Controller Position

Both reviewers returned **PASS**. Slice 4 covers the intended public proof chain without production code changes or Slice 5 behavior. A focused cleanup fix is still required before acceptance because several findings are cheap to close and improve the long-term readability of this stress helper surface.

The controller rejects any fix that exposes production scheduler internals or changes Host behavior. All required fixes must stay inside the approved test/helper files and review artifact.

## Finding Decisions

### DS-01: `RUN_LOST` terminal dedupe proof is not explicit enough

- **Decision**: accepted, fix before re-review.
- **Reason**: The implementation's count-level check can prove current correctness, but the helper boundary is easy to misread because `terminal_events_for_runs()` intentionally excludes `RUN_LOST`. The stress suite should make that proof explicit.
- **Required fix**: Add Chinese docstring/comment text at the Slice 4 diagnostics boundary explaining that `RUN_LOST` is counted through `_terminal_event_count_for_runs()` because `HostEventKind` / `HostTerminalStatus` do not model lost terminal observations. If low-risk, add a small helper name or predicate that makes the count-level proof explicit.

### MiMo-01: unused `InspectableStressWorkerFactory.wait_accepted_run`

- **Decision**: accepted, fix before re-review.
- **Reason**: The method is currently dead code. Keeping unused helper surface in a stress suite makes later slices harder to audit and conflicts with the project's preference for minimal helper APIs.
- **Required fix**: Either delete the method, or use it in Slice 4 where it materially improves the proof. Do not keep unused public test-helper surface.

### MiMo-02 / DS-03: repeated event type and DB filename constants

- **Decision**: accepted as documentation/localization fix, not as forced public export.
- **Reason**: Exporting module-private constants from `stress_support.py` would broaden the helper API. The immediate risk is unclear ownership and accidental drift.
- **Required fix**: Prefer moving the Slice 4 terminal count helper into `stress_support.py` so it can use the local constants, or add explicit comments/docstrings explaining why the test file owns Slice 4-only constants. Avoid compatibility re-export.

### DS-04: `verify_lane_released` hard-codes lane DB path

- **Decision**: accepted, fix before re-review.
- **Reason**: A lane release diagnostic that can accidentally connect to a new empty SQLite DB would become a false positive. The proof should use the same lane DB path as the Host options.
- **Required fix**: Change `verify_lane_released` to accept an explicit `lane_db_path: pathlib.Path` or an `OpenHostOptions` value and use that path. Update the call site to pass `options.lane_db_path`.

### DS-05: test stale threshold needs rationale

- **Decision**: accepted, fix before re-review.
- **Reason**: The threshold is test diagnostic policy, not production liveness truth. A short comment/docstring sentence should make that relationship explicit.
- **Required fix**: Document that the threshold only interprets rows after `force_owner_pid_missing_and_heartbeat_stale()` creates stale evidence and does not replace Host recovery policy.

### DS-02: `_is_terminal_status` now includes `LOST`

- **Decision**: accepted as documentation if touched, otherwise non-blocking.
- **Reason**: `LOST` is a Host public terminal state, so the semantic expansion is correct. The risk is only that earlier slices could be read as implicitly accepting lost in places where they do not produce lost.
- **Required fix**: If editing nearby code, update docstring/comment to state the helper is intentionally Host-public-terminal-wide; otherwise leave as residual non-blocking risk.

## Required Fix Validation

After the focused fix, run:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k scheduler_liveness -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py tests/host/test_public_cancel_session_runs.py -q
python -m pyright dayu/ tests/ utils/
```

If the dispatcher/liveness/cancel regression command hits the known isolated failure reported by both reviewers, the fix artifact must include whether the failure reproduces on a clean baseline or passes on single-test rerun. Do not hide a new failure.

## Next Gate

Dispatch a focused Slice 4 fix to AgentCodex. After the fix artifact is produced, request independent re-review from AgentMiMo and AgentDS before controller acceptance.

## Re-Review And Final Acceptance

### Re-review artifacts

- `docs/reviews/wu-stress-01-code-rereview-slice4-mimo-20260601.md`
- `docs/reviews/wu-stress-01-code-rereview-slice4-ds-20260601.md`
- `docs/reviews/wu-stress-01-code-final-rereview-slice4-mimo-20260601.md`
- `docs/reviews/wu-stress-01-code-final-rereview-slice4-ds-20260601.md`

MiMo and DS verified that all controller-accepted findings were closed. DS found one extremely low severity docstring mismatch after `wait_accepted_run` was removed; AgentCodex corrected the `InspectableStressWorkerFactory` class docstring and recorded the tiny follow-up in `docs/reviews/wu-stress-01-fix-slice4-codex-20260601.md`. The final focused re-review from both reviewers returned **PASS**.

### Controller validation

Controller reran:

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k scheduler_liveness -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py tests/host/test_public_cancel_session_runs.py -q
pytest tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Results:

- Slice 4 targeted stress passed: `1 passed, 3 deselected`.
- Full Host production stress file passed: `4 passed`.
- Scheduler/liveness/cancel regression command reproduced the known isolated failure `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering`: `1 failed, 74 passed`. The failure mode matched reviewer evidence: lane acquire timeout drove the seeded Run to `FAILED`.
- The isolated failing test passed on direct rerun: `1 passed`.
- Pyright reported `0 errors, 0 warnings, 0 informations`.
- `git diff --check` passed.

README decision: no `tests/README.md` update is required because Slice 4 did not change stress marker policy, default pytest exclusion, command syntax or test-running contract.

**Controller decision**: accept Slice 4 for local commit. Remaining residual risks are accepted for this work unit: deterministic bounded stress rather than fuzz/soak, test-scoped liveness stale diagnostic, and `RUN_LOST` proof split between public terminal observations and EventLog count diagnostics until public terminal view models lost directly.
