# WU-TOOLS-CANCEL-01 Residual Hardening S2A Implementation

## Scope

- Work unit: `WU-TOOLS-CANCEL-01`
- Slice: S2A `Runtime Process Group Cleanup Primitive`
- Gate: implementation
- Agent: AgentCodex
- Timestamp: 2026-07-05 15:12:11 CST
- Branch: `phase/wu-tools-cancel-01`

## Changed Files

- `dayu/runtime/interruptible_process.py`
- `tests/runtime/test_interruptible_process.py`
- `tests/README.md`

## Implementation Summary

- Added layer-neutral runtime process cleanup primitives in `dayu.runtime.interruptible_process`:
  - `interrupt_multiprocessing_process(...)`
  - `enter_new_process_session_if_supported(...)`
  - `ProcessCleanupHandle`
  - `ProcessCleanupSignal`
  - `ProcessGroupCleanupResult`
  - `ProcessGroupCleanupReason`
- `InterruptibleProcessHandle.terminate(...)` and `.kill(...)` now call the shared primitive.
- Process-backed children enter a new POSIX session / process group before running the target when supported.
- Cleanup resolves a safe child pgid, signals the direct child first, and only then signals the child process group if the pgid is available and does not match the caller/current or caller-parent process group.
- Unsupported, unavailable, already-exited, and unsafe pgid paths are returned through `ProcessInterruptResult.cleanup` rather than being treated as proven nested cleanup.
- Added deterministic runtime smoke coverage for a nested subprocess that ignores SIGTERM and must be removed by POSIX process-group hard kill.
- Updated `tests/README.md` only to record the new runtime interruptible-process coverage.

## Implementation-Fix Summary

- DS-01 fixed: promoted the session-entry helper to public `enter_new_process_session_if_supported(...)`, exported it, kept `InterruptibleProcessHandle` using it through `_run_process_target`, and documented that raw process users need this or equivalent POSIX setup before spawning nested children.
- DS-02 fixed: added deterministic runtime tests for `CHILD_PID_UNAVAILABLE`, `CHILD_ALREADY_EXITED`, `CURRENT_PGID_UNAVAILABLE`, `PARENT_PGID_UNAVAILABLE`, `PGID_MATCHES_PARENT_PROCESS_GROUP`, and `GROUP_SIGNAL_FAILED`.
- DS-03 fixed: direct child signal now catches `OSError` like the group signal path and records `direct_signal_sent=False` while still allowing group diagnostic and join to proceed.
- MiMo-F01 fixed: unstarted / PID-unavailable raw process cleanup now returns `CHILD_PID_UNAVAILABLE` without calling signal or join.
- MiMo-F03 fixed: successful pgid lookup baseline now uses `NOT_REQUESTED`; final successful group signal still returns `GROUP_SIGNALED`.

## OS / POSIX Support Judgment

- Current validation host: Darwin, `os.name == "posix"`.
- On POSIX, S2A can claim runtime-level synthetic nested cleanup when `ProcessGroupCleanupResult.group_signal_sent` is true and `reason == GROUP_SIGNALED`.
- On unsupported OSes or when pgid lookup is unavailable/unsafe, S2A only claims direct-child fallback. The diagnostic reason remains observable.
- Public raw process users must ensure the child process enters a separate POSIX session / process group before it spawns nested children. The exported runtime helper for that is `enter_new_process_session_if_supported(...)`.

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_interruptible_process.py -q`
  - Result: `19 passed in 1.02s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed with no output

## Docs Decision

- Runtime code changes do not trigger a runtime README rule in `AGENTS.md`.
- `tests/` changed, so `tests/README.md` was checked and minimally updated because the runtime test coverage description now includes interruptible process-group cleanup.

## S2B Handoff

- S2B may reuse `interrupt_multiprocessing_process(...)` for a raw `multiprocessing.Process` path without duplicating process-group cleanup logic.
- S2B must arrange for the raw child process entrypoint to call `enter_new_process_session_if_supported(...)`, or perform equivalent POSIX session / process-group setup, before that child spawns nested processes. Without this setup, the cleanup primitive will correctly fall back to direct-child cleanup and S2B must not claim nested cleanup.
- On POSIX, S2B may claim synthetic nested cleanup only when the returned cleanup diagnostic shows `group_signal_sent=True` and `reason=GROUP_SIGNALED`.
- S2B must not claim real browser process tree cleanup from S2A alone. It still needs its own synthetic worker smoke and optional/manual real browser evidence.
- If S2B receives `UNSUPPORTED`, `PGID_UNAVAILABLE`, `PGID_MATCHES_CURRENT_PROCESS_GROUP`, `PGID_MATCHES_PARENT_PROCESS_GROUP`, or `GROUP_SIGNAL_FAILED`, it must report direct-child fallback only.

## Residual Risks

- Real Playwright / browser subprocess cleanup remains covered by later approved slice S2B.
- Concrete Doc / Fins / Web process envelope migration and AAPL XBRL fixture breadth remain covered by later approved slice S3.
- This slice does not tune Host `ProcessCapsuleInterruptPolicy` defaults; S2B still owns timing evidence for Web synthetic nested cleanup.

## Completion Status

S2A implementation is complete. No review, commit, push, PR readiness change, or external issue update was performed.
