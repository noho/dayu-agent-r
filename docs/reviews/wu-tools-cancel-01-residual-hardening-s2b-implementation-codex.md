# WU-TOOLS-CANCEL-01 Residual Hardening S2B Implementation

## Scope

- Work unit: `WU-TOOLS-CANCEL-01`
- Slice: S2B `Playwright Cleanup Smoke`
- Gate: implementation
- Agent: AgentCodex
- Timestamp: 2026-07-05 15:39:12 CST
- Branch: `phase/wu-tools-cancel-01`

## Changed Files

- `dayu/tools/web/web_playwright_backend.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/README.md`

## Implementation Summary

- Replaced the Web Playwright raw worker cleanup helper's direct `terminate()` / `kill()` implementation with S2A's shared `interrupt_multiprocessing_process(...)` primitive.
- Kept the existing raw `multiprocessing.Process` Playwright worker path. No migration to `InterruptibleProcessHandle` was needed because S2A's primitive accepts the raw process cleanup protocol directly.
- Added `enter_new_process_session_if_supported()` inside `_playwright_process_entry(...)`, before the worker callable can launch Playwright/browser/nested subprocesses. The Host/main process does not perform this setup.
- Returned private cleanup diagnostics from `_terminate_playwright_process(...)` so tests can verify whether the cleanup claim is process-group cleanup or direct-child fallback.
- Added deterministic synthetic worker coverage that starts a nested long-lived child and verifies POSIX group cleanup removes the nested child.

## Implementation-Fix Summary

- Finding 01 fixed: `_terminate_playwright_process(...)` now calls the async runtime primitive through a private sync bridge. If the current thread already has a running asyncio loop, the bridge runs `asyncio.run(...)` inside a short-lived helper thread and propagates the result or exception.
- Finding 02 fixed: `_terminate_playwright_process(...)` logs debug cleanup diagnostics for terminate/kill stages, including reason, direct/group signal flags, exited, exitcode, and elapsed seconds. It does not log URL, content, or headers.
- Finding 03 fixed: functional timing assertions now use Web production cleanup grace `_PW_PROCESS_TERMINATE_GRACE_SECONDS` instead of coupling the test wall-clock assertion to Host `ProcessCapsuleInterruptPolicy` defaults. S2B still records separate evidence that the measured synthetic cleanup is below the S1 `0.2 / 0.2` defaults.
- Finding 04 fixed: added an optional/manual live browser cleanup smoke guarded by `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`. Default pytest skips it; when explicitly enabled it launches a real Chromium-backed worker path, observes descendants through POSIX `ps` when available, terminates via shared cleanup, and verifies observed descendants disappear.

## Cleanup Diagnostic Claim

Current S2B validation host is POSIX/Darwin. The synthetic cleanup measurement returned:

- `diagnostic.reason=group_signaled`
- `diagnostic.group_signal_sent=True`
- `diagnostic.direct_signal_sent=True`
- nested synthetic child PID no longer existed after cleanup.

This supports the S2B synthetic claim: Web Playwright raw worker cleanup uses the S2A shared runtime primitive and, when the child process has entered a separate POSIX session, the primitive can signal the child process group instead of only the direct worker process.

Unsupported or unsafe diagnostic paths remain direct-child fallback only. The new test skips the nested-child claim if S2A reports `UNSUPPORTED`, pgid unavailable, pgid matching the current/parent process group, or group signal failure.

## Synthetic Timing Result

File-backed measurement was required because Python `multiprocessing` spawn cannot re-import a stdin script. The successful file-backed measurement returned:

- `terminate_elapsed_seconds=0.002593`
- `cleanup_elapsed_seconds=0.003577`
- `child_absent_wait_seconds=0.000006`
- `web_cleanup_grace_seconds=1.000000`
- `default_terminate_grace_seconds=0.200000`
- `default_kill_grace_seconds=0.200000`

The functional Web cleanup assertion is now bounded by the production Web cleanup grace of `1.0s`. The measured synthetic SIGTERM cleanup also finished well under the S1 `ProcessCapsuleInterruptPolicy` defaults of `0.2 / 0.2`. No grace default adjustment is needed from S2B evidence.

## Optional Live Browser Status

- Environment probe: `playwright_chromium_launch=available`.
- Optional/manual smoke added: `tests/tools/web/test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort`.
- Default status: skipped unless `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1` is set.
- Current environment explicit run: `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest tests/tools/web/test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort -q` passed. The test remains best-effort because descendant inspection depends on POSIX `ps` visibility and browser subprocess observability.

## Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py::test_playwright_worker_process_cleanup_kills_synthetic_nested_child_on_posix -q`
  - Result: `1 passed in 1.29s`
- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q`
  - Result after fixes: `33 passed, 1 skipped in 3.63s`
- `source .venv/bin/activate && DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest tests/tools/web/test_web_tools_provider.py::test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort -q`
  - Result: `1 passed in 2.12s`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed with no output

## Docs Decision

- `dayu/tools/web/` has no README trigger in `AGENTS.md`.
- `tests/` changed, so `tests/README.md` was checked and minimally updated to record deterministic synthetic Playwright cleanup coverage and the explicit opt-in env var for optional live browser cleanup smoke.

## Residual Risks

- Real Chromium/browser process tree cleanup remains environment-dependent even with the optional smoke because descendant inspection depends on POSIX `ps` visibility and the current browser process tree shape. Classification: covered in current slice as optional/manual best-effort evidence; any stronger browser-specific process-tree proof should be assigned to later work if maintainers require it.
- Concrete Doc / Fins / Web process envelope helper migration and AAPL XBRL spawned-process fixture breadth remain covered by later approved slice S3.
- Final docs/control-state/full validation matrix remains covered by later approved slice S4.
- PID / PGID reuse remains the POSIX limitation already recorded by S2A. Classification: tracked by S2A residual risk; not widened by S2B.

## Completion Status

S2B implementation-fix is complete for the controller accepted findings. No review, commit, push, PR readiness change, or external issue update was performed.
