# WU-WAIT-02 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: WU-WAIT-02 / GitHub Issue #90
- Gate: aggregate deepreview
- Branch: `work/wu-wait-02-issue-90`
- Base: `main`
- Accepted implementation commits:
  - Plan: `350e1dbf`
  - Plan bookkeeping: `8568467c`
  - Slice 1: `b7447316`
  - Slice 2: `2974b5a2`
  - Slice 3: `1486e5a9`
- Aggregate review artifacts:
  - `docs/reviews/code-review-20260701-155500.md`
  - `docs/reviews/code-review-20260701-160040.md`

## Controller Decision

Decision: pass.

Both aggregate reviews found no material correctness defect across the full WU-WAIT-02 change set. The implementation is accepted for draft PR preparation after final validation and accepted deepreview commit.

## Cross-Slice Closure

- Durable wait record schema and Python validation are aligned at schema version 18.
- Poll claim / release / abandon CAS paths have direct tests and terminal transitions clear poll claim state.
- `WaitPoller.poll_once()` keeps adapter calls outside Host transactions and ready / lost results on the shared `resolve_wait` command path.
- `WaitPollerSupervisor` provides bounded lifecycle behavior, explicit factory injection, close gate checks, shutdown-skipped retry, and runtime-only diagnostics.
- `open_host` uses construction-time `wait_poller_policy` / `wait_poll_adapter_registry`, preserves the default no-poller path, and fails fast when an enabled policy lacks a registry.
- The production poller factory creates thread-local durable access per poll round and uses the existing command path with a thread-safe scheduler wakeup port.
- Public handle close and open-failure cleanup close poller before scheduler.
- Host / Engine boundary is preserved; Engine remains unaware of poll records, poller runtime, and wait resolution ownership.
- Design / README / tests documentation updates are in scope and consistent with the implementation.

## Residual Risk Disposition

- Service configuration mapping for `wait_poller_policy` / `wait_poll_adapter_registry`: non-goal for WU-WAIT-02 implementation slices; owner remains Service composition follow-up when production config enables poller wiring.
- `WaitPollerRuntimePolicy` package-root export: non-blocking ergonomics issue; current stable import path is `dayu.host.wait_adapter`.
- Synchronous poll adapters cannot be forcibly interrupted: accepted design tradeoff; close waits for in-flight adapter calls and emits diagnostics when a finite drain timeout is configured.
- Missing adapter remains capped-delay retryable instead of terminal: accepted plan residual; owner is WU-WAIT-03 or provider lifecycle policy if future product semantics require terminalization.
- External job physical cancel / revoke / abandon remains WU-WAIT-03 / GitHub Issue #92.
- UI / Service production-grade awaiting E2E smoke remains WU-WAIT-04 after WU-WAIT-03.

## Validation Considered

- AgentDS aggregate review reported 110 tests passing and pyright clean.
- AgentMiMo aggregate review reported 110 tests passing, pyright clean, and `git diff --check` clean.
- Slice 3 controller validation before review: open_host / wait poller / resolve focused tests 51 passed, public lifecycle smoke 2 passed, pyright 0 errors, and `git diff --check` passed.

## Next Gate

Update `docs/host/issues-implementation-control.md` to `ready-to-open-draft-PR`, run final validation, create the accepted aggregate deepreview commit, then proceed to draft PR gate.
