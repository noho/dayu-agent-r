# P10.5 Slice 2 Implementation Report

## Gate

- Gate: P10.5 implementation Slice 2 handoff
- Slice: Production Composition Root, Handle Lifecycle And Command Wakeup
- Role: P10.5 implementation specialist
- Stop status: Slice 2 implementation complete; did not enter Slice 3/4/5/6; no commit, no push, no PR

## Changed Files

- `dayu/host/open_host.py`
- `dayu/host/api.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `dayu/host/README.md`

## Implemented Plan Items

- Replaced Slice 1 `open_host` placeholder with a production composition root that opens durable store, builds internal `HostCommandHandleOptions`, builds internal `HostLocalExecutionOptions`, creates shared `ActiveWorkerRegistry`, opens `HostDispatchScheduler`, and connects admission after-commit wakeup to scheduler.
- Added public async handle delegation for `ensure_session`, `create_session`, `get_session`, `get_run`, `submit_followup`, `resolve_wait`, `retry_run`, `replay_run`, `cancel_run`, `cancel_session_runs`, and `close_session`, with public handle-open validation and `HostClosedError` after close.
- Kept `watch_session_events` as a Slice 4 placeholder with closed-handle validation; no session-level live fanout implemented.
- Wired memory projection catch-up as an internal projection catch-up port used by admission/scheduler and flushed during opener close.
- Mapped `OpenHostOptions.compactor_baseline` into `HostLocalExecutionOptions`, including `context_compactor`, compactor runner spec/options, compactor policy ref, compact artifact root, and compact artifact directory policy. `compactor_baseline=None` maps to no compaction capability rather than fake defaults.
- Implemented idempotent `host.close()` / `__aexit__` shutdown order: close public gate, stop scheduler and active workers/lane waits, flush memory projection, then close durable store.
- Preserved opener close semantics: no `CANCEL_REQUESTED`, `RUN_CANCELLED`, or `RUN_FAILED` facts are written merely because the opener closes.

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py -q`
  - Result: PASS, `4 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: PASS, `0 errors, 0 warnings, 0 informations`

## Docs Decision

- Updated `dayu/host/README.md` because Slice 2 changed current Host runtime behavior: `open_host(options)` now wires durable store, scheduler, shared registry, memory catch-up, compactor baseline, command wakeup, and idempotent opener close.
- Kept docs minimal and current-fact only. Session-level live fanout remains documented as later-slice work.

## Residual Risks / Open Questions

- `watch_session_events(...)` remains a placeholder until Slice 4.
- `SubmitFollowupRequest` field migration and effective per-run config/tool-set freeze remain Slice 3 work.
- Steer/retry/replay command semantics and WAITING public resume smoke remain later-slice work; Slice 2 only delegates existing primitives where present.
- Opener close leaves already-running durable Run state untouched, as required. Recovery/orphan classification for such work remains Phase 11.
- Existing Slice 1 option test still describes the old placeholder context behavior; it was not in the Slice 2 allowed test file list and was not modified.
