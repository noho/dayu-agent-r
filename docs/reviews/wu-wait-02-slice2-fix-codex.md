# WU-WAIT-02 Slice 2 Fix - Codex

## Slice

- Work unit: `WU-WAIT-02` / GitHub Issue #90
- Slice: Slice 2 - Backoff-Aware Poller Supervisor And Lifecycle
- Gate: fix
- Status: fix complete; no stage / commit / push / PR performed.

## Accepted Findings Fixed

- `S2-CR-F01`: removed the unsafe implicit `_DirectWaitPollerFactory` background path. `WaitPollerSupervisor` now requires an explicit `poller_factory: WaitPollerFactory`, so `open()` cannot silently reuse a caller-thread `HostTransactionRunner` in the supervisor thread.
- `S2-CR-F02`: removed the constructor parameters that only existed for the deleted default direct factory path: `transaction_runner`, `adapter_registry`, `resolver`, `context`, and `clock`.
- `S2-CR-F03`: `WaitPollerSupervisor.close()` now raises `RuntimeError` when called from the supervisor thread itself. A focused test verifies the loop records failed diagnostics for that unsupported call path.
- `S2-CR-F04`: `close()` now returns early for already terminal stopped / failed supervisors and clears the stored thread reference after close, preventing repeated close from moving diagnostics back to `closing`.
- `S2-CR-F05`: `WaitPollerRuntimePolicy.close_drain_timeout_seconds` is now `float | None`. `None` skips the first timeout diagnostic and waits directly for the in-flight poll path to stop; non-`None` values must remain positive.

## Changed Files

- `dayu/host/wait_adapter.py`
- `tests/host/test_wait_poller_runtime.py`
- `docs/reviews/wu-wait-02-slice2-fix-codex.md`

Pre-existing controller edits in `docs/host/issues-implementation-control.md` were preserved and not changed by this fix.

## Tests Added Or Updated

- Added signature regression coverage that `WaitPollerSupervisor` has no implicit direct-factory constructor path.
- Updated all supervisor runtime tests to supply an explicit thread-local poller factory.
- Added policy validation coverage for `close_drain_timeout_seconds=None`.
- Added close behavior coverage for `None` timeout: no close-drain timeout diagnostic is recorded and close still waits for the in-flight poll to finish.
- Added self-close coverage: close from the supervisor thread fails fast with `RuntimeError` and records loop-level failed diagnostics.
- Strengthened close idempotency coverage around repeated close terminal status.

## Validation

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py -q
```

Result:

```text
24 passed in 0.64s
```

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py -q
```

Result:

```text
57 passed in 0.61s
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

Read `dayu/host/README.md` and `tests/README.md` update constraints.

- `dayu/host/README.md` was not updated because this fix changes an internal Slice 2 supervisor primitive that is not wired into `open_host` and is not documented as a stable Host developer entry in the README.
- `tests/README.md` was not updated because this fix only adds cases inside the already listed `tests/host/test_wait_poller_runtime.py`; it does not add a new test layer, test file, test command, or maintenance rule.

## Residual Risks

- Future `open_host` wiring still must provide a thread-local `WaitPollerFactory`. Classification: Slice 3 integration requirement. Owner: WU-WAIT-02 Slice 3. Destination: production supervisor wiring.
- Synchronous adapter calls still cannot be forcibly interrupted by Python. Classification: accepted plan residual. Owner: future adapter contract owners. Destination: close waits for in-flight calls and records diagnostics when a finite drain timeout is configured.
- Re-review has not been performed in this fix gate. Classification: process state. Owner: controller / review agents. Destination: Slice 2 re-review gate.

## Stop Conditions

- No accepted finding required a separate claim table, Engine change, `open_host` wiring, public API wiring, or README/design source update.
- No pyright constraint forced `Any`, `object`, or untyped signatures.
