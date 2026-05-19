# Phase 11 Slice 4 Implementation - AgentCodex - 2026-05-19

## Scope

Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening.

Assigned slice: Slice 4. RECOVERING Cancel, Graceful Shutdown, And Public Contract Preservation.

Role constraint: implementation specialist only. No commit, no push, no PR, no review gate, no next slice.

## Changed Files

- `dayu/host/durable/run_transition.py`
- `dayu/host/admission.py`
- `dayu/host/command.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_public_cancel_smoke.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/phase11-slice4-implementation-codex-20260519.md`

Pre-existing dirty file not touched by this slice:

- `docs/host/implementation-control.md`

## Implemented Plan Items

- Added durable `CancelRecoveringRunInput` and `cancel_recovering_run_in_transaction(...)`.
- RECOVERING cancel appends canonical `CANCEL_REQUESTED` then `RUN_CANCELLED` in one transaction and moves only the Run to `CANCELLED`.
- RECOVERING cancel does not append `ATTEMPT_CANCELLED`, does not mutate the old Attempt, and does not cancel dispatch records.
- `cancel_run` now handles `RunStatus.RECOVERING` directly and records idempotency under unchanged `(run_id, client_request_id)` scope.
- `cancel_session_runs` now treats RECOVERING as a supported session-scope target and no longer fail-closes merely because a RECOVERING Run exists.
- Session-scope idempotency behavior remains unchanged: replay returns the current Session snapshot and does not cancel Runs created after the original session-scope command result.
- Public facade deferred-cancel classification no longer marks RECOVERING as unsupported.
- Added/updated tests for:
  - `cancel_run` on RECOVERING emits only Run-level cancel facts and leaves the Attempt state unchanged.
  - `cancel_session_runs` includes RECOVERING and still cancels queued Runs in the same command.
  - public `open_host` path does not propagate RECOVERING cancel to an active worker registry entry.
- Graceful shutdown code path was inspected and preserved. Existing close ordering already sets the public closed gate first, closes scheduler, flushes projection, and closes the command handle without appending user cancel or synthetic terminal facts. No scheduler/open_host code changes were required.

## Validation

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py tests/host/test_watch_session_events.py -q
```

Result:

```text
19 passed in 0.65s
```

Command:

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Command:

```bash
git diff --check
```

Result: passed with no output.

## Docs Decision

README update was required by repo rules because this slice changed `dayu/host/` behavior and `tests/` coverage facts.

- `dayu/host/README.md` now states that `cancel_run` and `cancel_session_runs` cover recovering state and clarifies that RECOVERING can be cancelled before recovery dispatch commit without appending an old Attempt terminal fact.
- `tests/README.md` now replaces the old unsupported RECOVERING cancel coverage description with RECOVERING cancel coverage for public command and smoke tests.

No root `README.md` update was needed because no user-facing CLI, install, configuration, trace/render, or project-level workflow changed.

## Residual Risks / Owners

- Multi-process race hardening around recovery dispatch versus RECOVERING cancel remains owned by Slice 5. This slice uses durable transaction CAS for the Run row but does not introduce lane/runtime multiprocess hardening.
- Tests construct RECOVERING state directly for focused public cancel contract coverage. Full startup recovery creation of RECOVERING and recovery dispatch integration remains covered by Slice 2/3 tests and later multiprocess coverage.
- Existing watcher close behavior was intentionally preserved; no new lifecycle error was introduced.

## Conclusion

HANDOFF_IMPLEMENTED
