# PR 99 Full-Repo Review Fix Pass1 Controller Adjudication

## Scope

- Branch: `feat/host-purge-audit-reconciliation`
- Gate: post full-repo review fix loop
- Implementation artifact: `docs/reviews/repo-review-fix-pass1-codex-20260531.md`
- Re-review artifacts:
  - `docs/reviews/repo-review-fix-pass1-rereview-mimo-20260531.md`
  - `docs/reviews/repo-review-fix-pass1-rereview-ds-20260531.md`

## Decision

**PASS**.

Both re-review agents returned PASS. The fixed findings have direct code changes, targeted tests, and pyright validation. `RuntimeFileLock`, `LaneClock`, and `_AsyncAgent` are not treated as closed; each has an explicit deferred owner and work unit.

## Accepted Fixed Items

- schema v15 test helpers now seed active Run `started_event_id` / `started_event_sequence`.
- `cancel_waiting_run_in_transaction` allows cancel while wait records are already resolved and the Run is still `WAITING`.
- `cancel_queued_run_row` and `cancel_running_run_row` include terminal refs in their defensive SQL CAS guards.
- accept barrier validates payload descriptor digest, not just descriptor existence.
- ToolExecutor internal `CancelledError` emits a warning when the run-level cancellation token was not cancelled.
- `opaque_ref.py` boundary tests raise single-file coverage to 100%.
- fallback mode closed set is centralized in a private runtime constant module without crossing layer boundaries.

## Deferred With Owner

- `RuntimeFileLock.release` lifecycle bug remains open and is deferred to `WU-RUNTIME-01` in `docs/host/host-core-followup-implementation-control.md`.
- `_LaneClock` cross-process TTL time-source risk remains open and is deferred to `WU-RUNTIME-02` in `docs/host/host-core-followup-implementation-control.md`.
- `_AsyncAgent` responsibility overload remains open and is deferred to `WU-MAINT-07` in `docs/host/maintainability-implementation-control.md`.

## Validation

- AgentCodex reported targeted pytest: `50 passed`.
- AgentCodex reported full test suite: `1796 passed, 1 skipped`.
- AgentCodex reported pyright: `0 errors, 0 warnings, 0 informations`.
- AgentCodex reported `opaque_ref.py` coverage: `100%`.
- AgentMiMo independently verified targeted scope, pyright, full tests, and opaque_ref coverage.
- AgentDS independently verified targeted tests, pyright, and opaque_ref coverage.
- Controller ran `git diff --check`: passed.

## Residual Risk

Residual risk is not closed by this pass. It is tracked in control documents with explicit owners:

- `RR-HCF-01` / `WU-RUNTIME-01`: runtime file lock wrapper contraction.
- `RR-HCF-02` / `WU-RUNTIME-02`: runtime lane clock and cancellation simplification.
- `RR-MAINT-03` / `WU-MAINT-07`: Engine `_AsyncAgent` responsibility decomposition.
