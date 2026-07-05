# WU-TOOLS-CANCEL-01 Residual Hardening Final Closeout

## Scope

- Work unit: WU-TOOLS-CANCEL-01 residual hardening reopen
- Branch: `phase/wu-tools-cancel-01`
- Draft PR: https://github.com/noho/dayu-agent-r/pull/170
- Final accepted commit: `ddbcef5b` (`WU-TOOLS-CANCEL-01: accept residual hardening aggregate review`)
- Status: reopened local gates passed; PR remains draft/open for maintainer/user handling

## What Changed

- S1 established the single-source process-backed envelope contract and typed process capsule cleanup policy.
- S2A added shared runtime process-group cleanup primitives and tests.
- S2B wired Playwright cleanup through the shared primitive, added deterministic nested-child cleanup smoke, running-loop cleanup coverage, debug diagnostics, and optional live Chromium cleanup smoke.
- S3 migrated Doc/Fins/Web process targets to `dayu.contracts` envelope helpers and added local AAPL XBRL spawned process-backed fixture coverage.
- S4 synced README/control docs and ran the final validation matrix.
- Aggregate review added two focused regression tests for process capsule policy config unknown fields and default factory wiring.

## Validation

Latest aggregate controller validation after accepted aggregate fixes:

- `pytest tests/runtime/test_config_loader.py tests/host/test_toolruntime_executor.py -q`: 114 passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

S4 final validation matrix:

- Host ToolRuntime / tooling / public options: 89 passed.
- Runtime interruptible process: 19 passed.
- Web provider: 34 passed, 1 skipped.
- Fins provider: 33 passed.
- Service host assembly: 52 passed.
- Import-boundary focused tests: 25 passed.
- Contracts tool declaration: 10 passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.

PR status check:

- `gh pr view 170`: PR is OPEN and draft, head `phase/wu-tools-cancel-01`, base `main`.
- `gh pr checks 170`: no checks reported on the branch.

## Closed User-Mandated Residuals

- `process envelope hint 结构化`: closed. Failed process envelope `hint` is a structured contract field and maps to `ToolResultFailure.hint`.
- `Playwright cleanup smoke`: closed. Deterministic nested-child cleanup coverage is always-on; live Chromium cleanup smoke is opt-in.
- `Fins XBRL fixture breadth`: closed. AAPL 2024 10-K XBRL fixture runs through process-backed `query_xbrl_facts`.
- `process envelope constants single-source`: closed. Doc/Fins/Web local envelope constants are removed; construction/parsing uses `dayu.contracts`.
- `process capsule grace tuning`: closed. Cleanup grace is a typed policy wired through config/service/Host/ToolRuntime and tested.

## Residual Risk

- Live Chromium process tree cleanup remains environment-dependent and opt-in via `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`.
- Web process cold-start remains classified as performance-only unless future evidence shows cancellation robustness impact.
- POSIX PID/PGID reuse remains the runtime limitation recorded by S2A and is bounded by safe pgid checks.

## External State

- No PR ready/merge/reviewer/branch-delete action was performed.
- No GitHub issue was closed directly.
- No external closeout comment was published.
- PR #170 remains draft/open pending maintainer/user handling.
