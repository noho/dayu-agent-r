# WU-WAIT-02 Final Closeout

## Scope

- Work unit: WU-WAIT-02 / GitHub issue #90
- Draft PR: https://github.com/noho/dayu-agent-r/pull/165
- Branch: `work/wu-wait-02-issue-90`
- Accepted PR review commit: `0bfedacf`
- Issue closeout comment: https://github.com/noho/dayu-agent-r/issues/90#issuecomment-4852470129

## What Changed

- Added durable wait poll claim, claim expiry, backoff, last outcome, missing-adapter, shutdown-skipped, and abandoned metadata to Host wait records.
- Added claim-aware `WaitPoller.poll_once()` behavior for waiting, cancelled, ready, lost, missing adapter, adapter error, resolve error, claim conflict, and shutdown-skip paths.
- Added `WaitPollerRuntimePolicy`, `WaitPollerSupervisor`, lifecycle gate checks, diagnostics, cancellable sleep, close drain handling, and fatal-loop diagnostics.
- Wired optional production wait poller support into `open_host` using an explicit poll adapter registry, thread-local durable store / command handle factory, and scheduler wakeup bridge.
- Fixed the PR review double-abandon edge case: after `adapter.abandon_wait(record)` succeeds, lifecycle close can no longer skip durable `poll_abandoned_at` marking.

## What Was Verified

- `source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py -q`
  - Result: `25 passed`
- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py tests/host/test_open_host_runtime.py tests/host/test_resolve_wait_command.py tests/host/test_public_lifecycle_smoke.py -q`
  - Result: `86 passed`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed with no output
- `gh pr checks 165`
  - Result: no checks reported on branch `work/wu-wait-02-issue-90`

Total affected local tests after PR review fix: 111 passed.

## Docs Updates

- `docs/host/design.md` updated the Host wait poller design alignment.
- `dayu/README.md` updated the package-level Service / Host wait poller boundary.
- `dayu/host/README.md` updated Host public lifecycle / open_host assembly documentation.
- `tests/README.md` updated the Host test file map.
- `docs/host/issues-implementation-control.md` records final closeout pass and the next entry point.

## Finding Status

- Plan review findings: fixed before accepted plan commit `350e1dbf`.
- Slice 1 code review: no blocking current fix; accepted slice commit `b7447316`.
- Slice 2 code review findings S2-CR-F01 through S2-CR-F05: fixed and re-reviewed; accepted slice commit `2974b5a2`.
- Slice 3 code review: no blocking current fix; accepted slice commit `1486e5a9`.
- Aggregate deepreview: no blocking finding; accepted deepreview commit `346b5ae7`.
- PR review DS Finding 01: accepted and fixed; both re-review artifacts mark it fixed.
- PR review DS Finding 02: rejected-with-reason as a non-material branch-internal schema-history note.
- MiMo PR review F01-F06: non-blocking notes / design confirmations; no current fix required.

## Remaining Risks / Owners

- External abandon after stale-claim CAS conflict can still be retried by a new owner. Owner: future adapter / WU-WAIT-03 if a provider requires stronger external cancel idempotency.
- Synchronous adapter calls cannot be forcibly killed by Python. Owner: adapter implementation / provider integration.
- Missing adapter capped-delay retry and external job lifecycle visibility remain assigned to WU-WAIT-03.
- UI / Service production-grade awaiting E2E smoke remains assigned to WU-WAIT-04 after WU-WAIT-02 and WU-WAIT-03.
- GitHub PR checks are not configured for the branch. Owner: repo infrastructure; local validation is the current gate evidence.

No unclassified blocking residual risk remains for WU-WAIT-02.

## Issue Link And Closeout Status

- PR body uses `Closes #90`, so merging PR 165 is expected to close issue #90 automatically.
- Issue closeout comment was published at https://github.com/noho/dayu-agent-r/issues/90#issuecomment-4852470129.
- Issue #90 remains open until PR 165 is merged.

## Next Entry Point

WU-WAIT-02 is at `final-closeout-pass`. Do not mark ready, merge, close issue, request reviewers, or delete the branch without explicit authorization.

After the user / maintainer merges PR 165, pull the latest `main` and resume phaseflow from `docs/host/issues-implementation-control.md` at WU-WAIT-03 / GitHub issue #92.
