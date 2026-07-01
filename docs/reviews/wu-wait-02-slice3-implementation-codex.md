# WU-WAIT-02 Slice 3 Implementation - Codex

## Slice

- Work unit: `WU-WAIT-02` / GitHub Issue #90
- Slice: Slice 3 - `open_host` Integration, Public Construction Wiring, Docs, And Final Validation
- Status: implementation complete; no stage / commit / push / PR performed.

## Changed Files

- `dayu/host/api.py`
- `dayu/host/tooling.py`
- `dayu/host/open_host.py`
- `dayu/host/wait_adapter.py`
- `tests/host/test_open_host_runtime.py`
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-wait-02-slice3-implementation-codex.md`

Pre-existing controller update in `docs/host/issues-implementation-control.md` was preserved and not edited by this implementation.

## Behavior Implemented

- Added `OpenHostOptions.wait_poller_policy`; `None` keeps the existing no-poller behavior.
- Added `HostToolingOptions.wait_poll_adapter_registry` for construction-time production poll adapters.
- Added `WaitPollerRuntimePolicy.enabled`; `enabled=False` validates the policy object but does not start a poller.
- Wired `open_host(...)` to create and open `WaitPollerSupervisor` only when policy is enabled and a poll adapter registry is present.
- Added construction-time fail-fast behavior for enabled poller policy without `wait_poll_adapter_registry`.
- Implemented an `open_host` poller factory that creates a fresh durable store / command handle inside the supervisor thread for each poll round, avoiding reuse of the opener-thread `HostTransactionRunner`.
- Added a thread-safe scheduler wakeup port so poller `resolve_wait` can wake the asyncio scheduler from the supervisor thread without bypassing the command path.
- Updated public handle close ordering to close poller before scheduler; startup failure cleanup also closes an already-created poller before scheduler / projection / durable cleanup.
- Kept Engine and Service-facing wait APIs unchanged.

## Tests Added Or Updated

- `test_open_host_wait_poller_policy_without_poll_registry_fails_fast`
- `test_open_host_disabled_wait_poller_policy_without_poll_registry_opens`
- `test_open_host_wait_poller_resolves_waiting_run_in_background`
- `test_public_host_close_closes_wait_poller_before_scheduler`
- `test_open_host_startup_failure_closes_poller_before_scheduler`

Existing no-poller `open_host` tests continue to cover default disabled behavior.

## Validation

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_resolve_wait_command.py -q
```

Result:

```text
51 passed in 1.00s
```

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_public_lifecycle_smoke.py -q
```

Result:

```text
2 passed in 0.32s
```

Command:

```bash
source .venv/bin/activate && pyright
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

`pyright` also printed a tool version notice: `v1.1.409 -> v1.1.411`.

Command:

```bash
git diff --check
```

Result: passed with no output.

## Docs Decision

Read `dayu/host/README.md` Agent update constraints and `tests/README.md` update boundary before editing.

- Updated `docs/host/design.md` minimally for durable poll claim / backoff lifecycle semantics, runtime diagnostics staying out of EventLog, and `open_host` optional poller wiring.
- Updated `dayu/host/README.md` because `open_host` construction wiring and close ordering changed.
- Updated `tests/README.md` because existing `test_open_host_runtime.py` now covers production wait poller construction wiring and cleanup behavior.

## Residual Risks

- Synchronous poll adapters still cannot be forcibly interrupted. Classification: accepted design tradeoff. Owner: future adapter contract owners. Destination: adapter implementations must keep bounded calls; Host close waits for in-flight poll work to return.
- `wait_poller_policy` is available on `OpenHostOptions`, but package-root export of `WaitPollerRuntimePolicy` was not added because `dayu/host/__init__.py` was outside the allowed Slice 3 file list. Classification: construction ergonomics. Owner: follow-up public namespace decision. Destination: later API surface cleanup if Service composition wants package-root import.
- Service configuration mapping to pass `wait_poller_policy` / `wait_poll_adapter_registry` is not implemented in this slice. Classification: explicit non-goal. Owner: Service composition owner. Destination: later Service wiring if production deployment wants poller enabled by config.

## Stop Conditions

- `open_host` can close poller before scheduler without broad lifecycle redesign.
- Poller factory did not need opener-thread `HostTransactionRunner`; it creates thread-local durable access per poll round.
- Docs updates did not reveal a Host / Engine design boundary mismatch.
- No pyright constraint forced `Any`, `object`, or untyped signatures.
