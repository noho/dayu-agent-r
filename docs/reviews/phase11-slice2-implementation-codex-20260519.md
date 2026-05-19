# Phase 11 Slice 2 Implementation - AgentCodex - 2026-05-19

## Changed Files

- `dayu/host/recovery.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/event_log.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_run_attempt_transitions.py`
- `dayu/host/README.md`

Note: `docs/host/implementation-control.md` was already dirty in the working tree and was not modified for this slice.

## Implemented Plan Items

- Added startup recovery scanner classification for `ACCEPTED`, `QUEUED`, `WAITING`, `RUNNING`, `CANCELLING`, and `RECOVERING`.
- Preserved `ACCEPTED`, `QUEUED`, and `WAITING` without state mutation or Attempt creation; `WAITING` returns diagnostic-only fallback classification.
- Added positive orphan closeout transition with CAS recheck over Run, Attempt, dispatch record, owner instance row, owner heartbeat, and stale policy input.
- Added same-transaction ordered EventLog + state-index closeout for `ATTEMPT_LOST -> RUN_RECOVERING` and `ATTEMPT_LOST -> RUN_LOST`.
- Added canonical EventLog recovery dispatch count helper filtered by `run_id`, canonical `RUN_STARTED`, and payload `start_reason=recovery`.
- Added `RECOVERING` scan behavior that marks ready for later dispatch while under limit, and `RUN_LOST` when committed recovery dispatch count reaches the startup limit.
- Added tests proving projection checkpoint lag does not affect startup recovery classification or recovery dispatch limit decisions.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q`
  - Result: `38 passed in 0.44s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Docs Decision

- Updated `dayu/host/README.md` because this slice changes stable Host recovery module behavior under `dayu/host/`.
- No root README update: no public CLI, install, configuration, trace/render, or user workflow changed.

## Residual Risks / Owners

- Actual `RECOVERING` dispatch, scheduler wake integration, and `open_host(...)` startup hook remain Slice 3 owner.
- Public cancel semantics for `RECOVERING` remain Slice 4 owner.
- Startup scanner currently returns wake/diagnostic classifications for `ACCEPTED`, `QUEUED`, and `WAITING`; concrete scheduler or wait-adapter wake wiring is outside Slice 2.

## Conclusion

HANDOFF_IMPLEMENTED
