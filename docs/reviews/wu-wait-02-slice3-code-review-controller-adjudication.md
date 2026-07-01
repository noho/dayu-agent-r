# WU-WAIT-02 Slice 3 Code Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-02 / GitHub Issue #90
- Gate: Slice 3 code review
- Slice: `open_host` integration, public construction wiring, docs, and final validation
- Baseline: accepted Slice 2 commit `2974b5a2`
- Implementation artifact: `docs/reviews/wu-wait-02-slice3-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/code-review-20260701-154721.md`
  - `docs/reviews/code-review-20260701-154834.md`

## Controller Decision

Decision: pass.

Both reviewers found no material correctness defect. Slice 3 correctly wires the production wait poller into `open_host` while preserving the Host / Engine boundary, keeping default no-poller behavior, and using a thread-local poller factory so the supervisor thread does not reuse the opener-thread `HostTransactionRunner`.

No fix gate is required before accepted Slice 3 commit.

## Review Conclusions

- `OpenHostOptions.wait_poller_policy=None` preserves the existing no-poller path.
- `WaitPollerRuntimePolicy.enabled=False` validates the policy object but does not start a poller and does not require a poll adapter registry.
- Enabled poller policy without `HostToolingOptions.wait_poll_adapter_registry` fails fast at construction time.
- `_OpenHostWaitPollerFactory` opens a fresh durable store / command handle inside the supervisor thread for each poll round.
- Poller ready / lost outcomes continue through the shared command `resolve_wait` path.
- `_ThreadsafeSchedulerWakeupPort` uses `call_soon_threadsafe` to wake the current scheduler from the supervisor thread.
- Public handle close and open-failure cleanup both close the poller before closing the scheduler.
- Runtime diagnostics remain out of EventLog.
- `docs/host/design.md`, `dayu/host/README.md`, and `tests/README.md` were updated within their stated responsibility.

## Validation Considered

- AgentCodex reported open_host / poller / resolve focused tests: 51 passed.
- AgentCodex reported public lifecycle smoke: 2 passed.
- AgentCodex reported pyright: 0 errors.
- AgentCodex reported `git diff --check`: passed.
- Controller reran the same validation with 51 passed, 2 passed, pyright 0 errors, and `git diff --check` passed.
- AgentDS reported 53 tests passed and pyright clean.

## Residual Risk

- Service configuration mapping to populate `wait_poller_policy` / `wait_poll_adapter_registry` remains a non-goal for this slice.
- `WaitPollerRuntimePolicy` is not re-exported from `dayu.host` package root because package-root export was outside the accepted Slice 3 file list.
- Synchronous poll adapters still cannot be forcibly interrupted by Python; close waits for in-flight calls.
- `_ThreadsafeSchedulerWakeupPort` blocks the poller thread while waiting for scheduler wakeup callback execution; reviewers classified this as low risk because the callback is a short in-memory scheduler wakeup and the event loop is still alive during poller close.

## Next Gate

Update `docs/host/issues-implementation-control.md` to `accepted-slice`, run final lightweight validation, and create the accepted Slice 3 commit. After that, proceed to aggregate deepreview for WU-WAIT-02.
