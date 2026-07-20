# WU-SEMANTIC-OWNERSHIP-01 P3-K S2 Implementation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-K - Test harness semantic coupling cleanup`
- Gate: implementation slice S2 - Durable Diagnostic Helper Boundary
- Agent: Codex
- Base / previous accepted commit supplied by controller: `b5bcf767`
- Allowed production behavior change: none

## Changed Files And Helper Dispositions

- `tests/host/public_smoke_support.py`
  - `_diagnostic_event_type_count(...)`: retained raw SQL as `diagnostic-only`.
  - Added docstring boundary: this is a cross-Run EventLog event type count used for point-in-time public smoke synchronization, not EventLog truth and not a replacement for run-scoped EventLog owner helpers.
  - Active wait id path remains on production owner helper `read_active_wait_records_for_run(...)` through the Host durable transaction runner; no raw wait SQL was introduced.

- `tests/host/recovery_support.py`
  - `force_owner_pid_missing_and_heartbeat_stale(...)`: retained raw SQL as `fault-injection-only`.
    Production liveness APIs must not fabricate missing pid / stale heartbeat states.
  - `force_memory_projection_lag(...)`: retained raw SQL as `fault-injection-only`.
    Production checkpoint helpers initialize or monotonically advance checkpoints and do not expose a backwards-move / clear-`checkpoint_event_id` operation.
  - `event_type_count(...)`: retained raw SQL as `diagnostic-only` for cross-Run EventLog event type counting.
  - `projection_checkpoint_sequence(...)`: replaced direct raw SQL query against `host_projection_checkpoints` with production owner helper `read_projection_checkpoint(transaction, _MEMORY_CONSUMER_ID)` through `open_host_durable_store(...).transaction_runner.run_read(...)`, returning `row.checkpoint_event_sequence` or `None`.

- `tests/host/stress_support.py`
  - `read_latest_event_sequence(...)`: retained raw SQL as `diagnostic-only` global `MAX(event_sequence)` stress lag / point-in-time diagnostic.
  - `read_event_log_count(...)`: retained raw SQL as `diagnostic-only` global EventLog row count.
  - `read_host_instances(...)`: retained raw SQL as `diagnostic-only` all-instance liveness view; no production list API was added solely for tests.

No `tests/host/durable_diagnostics.py` helper was added because the exact S2 cleanup did not create meaningful duplication that justified a new shared test-only owner.

## Tests And Validation

- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q`
  - Passed: `18 passed, 1 skipped`.
- `source .venv/bin/activate && pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q`
  - Passed: `9 passed`.
- `source .venv/bin/activate && pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q`
  - First run: `4 passed, 1 failed`.
  - Second run: `3 passed, 2 failed`.
  - Failures were outside the edited helper semantics:
    - `test_sustained_watch_slow_consumer_reconnect_stress`: dispatch failed while recording runner-call manifest with `HostPayloadReferenceError: EventLog canonical_fact payload_json exceeds inline payload limit`.
    - `test_scheduler_liveness_long_run_mixed_flow_stress`: summary `failure_boundary` was `active_cleanup`, with captured logs around deterministic stream exception / clean EOF and scheduler close.
  - S2 did not change production dispatch, runner-call manifest recording, payload inline policy, scheduler cleanup, or stress scenario behavior. This remains residual validation risk for controller review, not an S2 implementation change.
- Non-stress import / syntax checks for stress helper consumers:
  - `source .venv/bin/activate && python -m compileall -q tests/host/public_smoke_support.py tests/host/recovery_support.py tests/host/stress_support.py`
    - Passed.
  - `source .venv/bin/activate && python -c "import tests.host.public_smoke_support; import tests.host.recovery_support; import tests.host.stress_support"`
    - Passed.
- Source scan / classification:
  - `rg -n "def projection_checkpoint_sequence|host_projection_checkpoints|checkpoint_event_sequence|diagnostic-only|fault-injection-only|read_projection_checkpoint|read_events_after|read_events_after_matching|read_active_wait_records_for_run" tests/host/public_smoke_support.py tests/host/recovery_support.py tests/host/stress_support.py`
  - Result: `projection_checkpoint_sequence(...)` now calls `read_projection_checkpoint(...)`; remaining `host_projection_checkpoints` raw SQL appears only in `force_memory_projection_lag(...)`, which is documented `fault-injection-only`; retained diagnostic helpers are documented `diagnostic-only`; no `read_events_after(...)` or `read_events_after_matching(...)` routing was introduced; wait records still use `read_active_wait_records_for_run(...)`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Passed.

## README Trigger Decision

Read `tests/README.md` before deciding documentation changes.

Decision: `tests/README.md` no update needed.

Reason: S2 did not add a new shared helper, new test layer, or durable diagnostics responsibility section. Existing README already documents that public smoke synchronization should go through centralized `public_smoke_support.py` helpers, stress suite requires explicit `stress` marker execution, and production code must not import test helpers.

## Propagation Audit For Durable Diagnostic Semantics

- Durable read truth:
  - Projection checkpoint row semantics remain owned by `dayu.host.durable.projection`.
  - `projection_checkpoint_sequence(...)` now consumes that owner helper and no longer redefines the checkpoint row projection with test-local SQL.

- Diagnostic-only raw SQL:
  - Cross-Run EventLog counts in `public_smoke_support.py` and `recovery_support.py` remain test synchronization diagnostics because existing production helpers are run-scoped and not exact equivalents.
  - Stress global latest sequence and row count remain point-in-time lag / consumer-cancel diagnostics. They were not routed through cursor replay helpers.
  - Stress all-instance liveness read remains diagnostic-only because production liveness helper reads a known instance id, not an all-instance stress view.

- Fault-injection-only raw SQL:
  - Missing pid / stale heartbeat mutation remains a test recovery injection state that production liveness APIs intentionally must not create.
  - Memory projection lag mutation remains a test recovery injection state that production checkpoint APIs intentionally must not create.

- Wait records:
  - Active wait id lookup remains through production `read_active_wait_records_for_run(...)`.
  - No raw SQL wait record query was added.

## Residual Risks / Uncovered Areas

- The explicit stress suite currently has unrelated failing cases in scheduler / runner-call manifest payload paths. Those failures pre-existed or are outside this slice's edited helper semantics based on direct failure traces, but they prevent a clean stress validation pass for this implementation run.
- Other raw SQL helpers outside the S2 approved file/function list were not modified.
- No production durable API was added, by design.

## Stop Status

ready-for-controller-validation
