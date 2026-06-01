# WU-STRESS-01 Aggregate Deepreview Controller Adjudication

## Gate

- **Gate**: aggregate deepreview adjudication
- **Work Unit**: WU-STRESS-01 Host Production Stress Suite
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- **Aggregate review artifacts**:
  - `docs/reviews/wu-stress-01-aggregate-deepreview-mimo-20260601.md`
  - `docs/reviews/wu-stress-01-aggregate-deepreview-ds-20260601.md`

## Controller Position

Both aggregate reviewers returned **PASS**. MiMo found no substantive issues. DS reported two low findings that it described as inherited from earlier Slice 3 review. Direct inspection of the current branch shows both are stale findings already closed by Slice 3 final focused fix and verified by Slice 3 final re-review.

No additional code fix is required before accepting aggregate deepreview.

## Finding Decisions

### DS-AGG-01: `consumer_cancel_ok` docstring says four-step validation

- **Decision**: rejected as stale evidence.
- **Current evidence**: `tests/host/test_host_production_stress.py:502-510` now says the property covers only the two structured diagnostics fields: EventLog count unchanged and worker cancel count unchanged. It explicitly states that the public `get_run` non-terminal check and release-to-terminal check are performed separately in the test body.
- **Reason**: The finding describes an old Slice 3 state. The current docstring is precise and matches the property body, so no fix is needed.

### DS-AGG-02: primary watcher try/finally double close

- **Decision**: rejected as stale evidence.
- **Current evidence**: `tests/host/test_host_production_stress.py:1750` initializes `primary_watchers_closed`; the normal close path sets `primary_watchers_closed[index] = True`; the finally block at `tests/host/test_host_production_stress.py:2011-2014` closes only watchers whose flag remains false.
- **Reason**: The double-close path was removed by Slice 3 final focused fix. The current code has explicit close-state tracking and fallback cleanup only for unclosed watchers.

## Accepted Residual Risks

- The stress suite is deterministic bounded hardening coverage, not randomized fuzzing or long-duration soak.
- `pytest-timeout` can still terminate a process before internal summary JSON generation if the event loop is globally wedged.
- `RUN_LOST` is not currently modeled as a live `HostEventKind`; Slice 4/5 therefore prove it through public `RunStatus.LOST` snapshots and EventLog count diagnostics.
- Watch lag diagnostics are test diagnostics based on fresh short reads and terminal-count watermarks, not production SLOs or replay cursor truth.

## Controller Validation Evidence

Controller reran the WU validation matrix after Slice 5:

```bash
source .venv/bin/activate
pytest --markers
pytest tests/host/test_package_exports.py tests/host/test_host_production_stress.py -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest --collect-only tests/host/test_host_production_stress.py -q
pytest -o addopts="" --collect-only tests/host/test_host_production_stress.py -q
pytest tests/host/test_recovery_multiprocess.py tests/host/test_watch_session_events.py tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py -q
python -m pyright dayu/ tests/ utils/
pytest tests/host -q
```

Results:

- `pytest --markers`: `stress` and `timeout` markers present.
- Default package + stress file command: `10 passed, 5 deselected`.
- Explicit stress suite: `5 passed`.
- Default collect-only on stress file: exit code 5 with `no tests collected (5 deselected)`, expected because default pytest excludes stress tests.
- Override collect-only: `5 tests collected`.
- Recovery/watch/dispatch/liveness regression: `75 passed`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Full `tests/host`: `1044 passed, 1 skipped, 5 deselected`.

README decision remains unchanged: `tests/README.md` already documents the stress marker, default exclusion and explicit stress command; no further README change is required.

## Final Aggregate Decision

Aggregate deepreview is accepted. WU-STRESS-01 may proceed to `ready-to-open-draft-PR` after the accepted deepreview commit and control-doc readiness update.
