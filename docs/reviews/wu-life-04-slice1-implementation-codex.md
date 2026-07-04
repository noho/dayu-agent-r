# WU-LIFE-04 Slice 1 Implementation Artifact

## Scope

- Work unit: WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout
- Gate: implementation
- Slice: Slice 1 - Design And Public Contract Cleanup
- Implementer: AgentCodex

## Changed Files

- `docs/host/design.md`
- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/README.md`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_dispatch_scheduler.py`

`docs/host/issues-implementation-control.md` was not modified.

## Exact Changes

- Updated Host design cancel text to remove the public independent active-cancel timeout contract and describe the watchdog as an accepted-cancel closeout supervisor with no post-cancel timeout budget.
- Updated Host design startup recovery text to remove the timeout-option opt-out and state that accepted-cancel `CANCELLING` runs are handled by watchdog closeout or existing terminal/recovery proof, not by missing timeout configuration.
- Removed `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS` from `dayu/host/api.py`.
- Removed `OpenHostOptions.active_cancel_timeout_seconds`, its docstring entry, and its validation.
- Removed `HostLocalExecutionOptions.active_cancel_timeout_seconds`, its docstring entry, and its validation.
- Removed `OpenHostOptions -> HostLocalExecutionOptions` projection of `active_cancel_timeout_seconds` in `dayu/host/open_host.py`.
- Changed startup recovery wiring in `open_host` to defer accepted-cancel `CANCELLING` runs to watchdog unconditionally instead of checking a timeout option.
- Updated `dayu/host/README.md` public contract text after reading its Agent update constraints. The README no longer lists active cancel timeout as part of `OpenHostOptions` and no longer describes a public post-cancel timeout budget.
- Updated constructor/import fallout in Host tests:
  - Added a public contract test proving `OpenHostOptions` dataclass fields and constructor signature do not include the removed field.
  - Removed direct construction with the removed field from affected open-host/runtime helper tests.
  - Removed one constructor argument in `tests/host/test_dispatch_scheduler.py` that only existed to pass the removed local execution field.

## README Decision

`dayu/host/README.md` required an update because `dayu/host/` public construction contract changed. The README's own Agent update constraints say it should describe current implemented Host package contracts and stable boundaries, not work-unit process state. The update is therefore limited to public contract and mechanism wording.

No root `README.md`, `dayu/README.md`, or `tests/README.md` update was made because this slice did not change user-facing install/CLI/workflow behavior, global layering, or test category documentation.

## Validation

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_open_host_runtime.py -q
```

Result: failed.

Observed result: 12 passed, 15 failed.

Direct cause: `dayu/host/dispatch.py` still reads `HostLocalExecutionOptions.active_cancel_timeout_seconds` in `HostDispatchScheduler.open()` / watchdog startup. `dayu/host/dispatch.py` is explicitly forbidden for this slice and belongs to Slice 2 watchdog behavior cleanup.

Command:

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: failed.

Errors:

- `dayu/host/dispatch.py:1063` unknown attribute `active_cancel_timeout_seconds`
- `dayu/host/dispatch.py:1083` unknown attribute `active_cancel_timeout_seconds`
- `dayu/host/dispatch.py:2554` unknown attribute `active_cancel_timeout_seconds`
- `tests/host/test_active_cancel_dispatch.py:938` no parameter named `active_cancel_timeout_seconds`

Direct cause: remaining Slice 2 production watchdog logic and the explicitly forbidden Slice 2 active-cancel dispatch test helper still reference the removed local execution field.

Command:

```bash
git diff --check
```

Result: passed.

Command:

```bash
rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md
```

Result: failed.

Remaining matches:

- `dayu/host/dispatch.py`: 3 production watchdog references.
- `tests/host/test_active_cancel_dispatch.py`: constructor/helper references for Slice 2 active-cancel dispatch tests.

Direct cause: both remaining locations are outside this slice by explicit instruction. `dayu/host/dispatch.py` and `tests/host/test_active_cancel_dispatch.py` were not modified.

## Stop Condition Status

- No production code path or test helper references `OpenHostOptions.active_cancel_timeout_seconds`: met for modified scope; no remaining direct `OpenHostOptions.active_cancel_timeout_seconds` references were observed.
- No production code path or test helper references `HostLocalExecutionOptions.active_cancel_timeout_seconds`: not met globally because `dayu/host/dispatch.py` and `tests/host/test_active_cancel_dispatch.py` still reference the removed local execution field.
- No internal disable flag or timeout-option opt-out exists for the accepted-cancel watchdog in modified files: met. No replacement public option, internal disable flag, or timeout opt-out was added.
- Required `rg` leaves no live usage: not met globally due remaining Slice 2 files listed above.

## Residual Risks / Owners

- Owner: Slice 2 watchdog behavior implementation.
  - Remove `dayu/host/dispatch.py` dependency on `HostLocalExecutionOptions.active_cancel_timeout_seconds`.
  - Convert watchdog eligibility from post-cancel timeout scanning to accepted-cancel closeout with no extra budget.
  - Update `tests/host/test_active_cancel_dispatch.py` helper/tests to stop passing the removed field and to assert no-extra-budget closeout semantics.
- Until Slice 2 completes, `open_host` cannot start successfully because scheduler startup still touches the removed field.
- Until Slice 2 completes, whole-repo pyright cannot pass because the forbidden Slice 2 files still reference the removed field.

## Slice 2 Boundary

This implementation did not modify:

- `dayu/host/dispatch.py`
- `dayu/host/durable/run_transition.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_engine_ingest_mapping.py`
- `docs/host/issues-implementation-control.md`

The implementation did not rename durable timeout reasons, helper names, payload fields, or watchdog closeout logic. Those remain Slice 2 responsibilities.
