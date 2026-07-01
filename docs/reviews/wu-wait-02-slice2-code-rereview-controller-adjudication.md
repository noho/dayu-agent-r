# WU-WAIT-02 Slice 2 Code Re-Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-02 / GitHub Issue #90
- Gate: Slice 2 code re-review
- Slice: Backoff-aware poller supervisor and lifecycle
- Baseline: accepted Slice 1 commit `b7447316`
- Fix artifact: `docs/reviews/wu-wait-02-slice2-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/code-review-20260701-151948.md`
  - `docs/reviews/code-review-20260701-152140.md`

## Controller Decision

Decision: pass.

Both re-review agents verified that all controller-accepted Slice 2 findings are closed. No new material defect was reported. Slice 2 is ready for accepted slice commit after final validation.

## Finding Closure

| Finding | Controller status |
|---|---|
| S2-CR-F01 unsafe default direct factory | closed |
| S2-CR-F02 constructor dead parameters | closed |
| S2-CR-F03 self-close contract gap | closed |
| S2-CR-F04 double-close transient state | closed |
| S2-CR-F05 `close_drain_timeout_seconds=None` contract mismatch | closed |

## Closure Evidence

- `WaitPollerSupervisor` now requires explicit `poller_factory: WaitPollerFactory`; the unsafe implicit `_DirectWaitPollerFactory` path is removed.
- Supervisor constructor no longer accepts `transaction_runner`, `adapter_registry`, `resolver`, `context`, or `clock` parameters that were dead when an explicit factory was supplied.
- `close()` now fails fast when called from the supervisor thread itself; the loop records failed diagnostics through the existing fatal-exception path.
- Repeated `close()` on a stopped / failed supervisor returns without moving diagnostics back to `closing`, and the stored thread reference is cleared after close.
- `WaitPollerRuntimePolicy.close_drain_timeout_seconds` supports `float | None`; `None` means direct wait without first-timeout diagnostic.

## Validation Considered

- AgentCodex reported wait poller runtime focused tests: 24 passed.
- AgentCodex reported schema / wait record tests: 57 passed.
- AgentCodex reported pyright: 0 errors.
- AgentCodex reported `git diff --check`: passed.
- Controller reran wait poller runtime focused tests: 24 passed.
- Controller reran schema / wait record tests: 57 passed.
- Controller reran pyright: 0 errors.
- Controller reran `git diff --check`: passed.
- AgentDS re-review reported 81 tests passed and pyright clean.

## Residual Risk

- Slice 3 `open_host` wiring must provide a thread-local `WaitPollerFactory`. This is now an explicit typed handoff, not an implicit unsafe default.
- Synchronous adapter calls cannot be forcibly killed by Python. This remains an accepted plan residual; close waits for in-flight calls and records diagnostics when a finite drain timeout is configured.
- `shutdown_skipped` uses bounded normal backoff, so repeated close-during-result races can increase shared backoff up to the configured cap.

## Next Gate

Update `docs/host/issues-implementation-control.md` to `accepted-slice`, run final lightweight validation, and create the accepted Slice 2 commit. Slice 3 may start from the accepted Slice 2 commit.
