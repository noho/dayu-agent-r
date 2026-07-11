# WU-SEMANTIC-OWNERSHIP-01 P3-K S2 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-K - Test harness semantic coupling cleanup`
- Gate: implementation slice S2 controller validation
- Slice: S2 Durable Diagnostic Helper Boundary
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-k-s2-implementation-codex.md`
- Base / previous accepted commit: `b5bcf767`
- Changed files:
  - `tests/host/public_smoke_support.py`
  - `tests/host/recovery_support.py`
  - `tests/host/stress_support.py`

## First-Principles Check

The S2 motivation remains valid and correctly scoped. The issue is not that tests may never use raw SQL. The defect is narrower: test helpers must not create a second owner for durable facts when an exact production durable helper already exists. Conversely, diagnostic global aggregates and fault-injection states are test-owned by design and should not be forced through mismatched production APIs.

The implementation follows that boundary:

- `projection_checkpoint_sequence(...)` now reads the memory projection checkpoint through `read_projection_checkpoint(...)` inside a Host durable read transaction and returns `row.checkpoint_event_sequence` or `None`.
- Cross-Run EventLog counts remain raw SQL and are documented as diagnostic-only because run-scoped count helpers are not exact equivalents.
- Missing owner PID / stale heartbeat and projection lag mutation remain raw SQL and are documented as fault-injection-only because production APIs intentionally must not fabricate those states.
- Stress global EventLog max/count and all-instance liveness reads remain raw SQL and are documented as diagnostic-only.
- Active wait id lookup remains on `read_active_wait_records_for_run(...)`; no raw wait-record SQL was introduced.

## Validation Commands

- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q`
  - Result: `18 passed, 1 skipped`
- `source .venv/bin/activate && pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q`
  - Result: `9 passed`
- `source .venv/bin/activate && python -m compileall -q tests/host/public_smoke_support.py tests/host/recovery_support.py tests/host/stress_support.py`
  - Result: pass
- `source .venv/bin/activate && python -c "import tests.host.public_smoke_support; import tests.host.recovery_support; import tests.host.stress_support"`
  - Result: pass
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: pass

## Source Scan

Command:

```text
rg -n "def projection_checkpoint_sequence|host_projection_checkpoints|checkpoint_event_sequence|diagnostic-only|fault-injection-only|read_projection_checkpoint|read_events_after|read_events_after_matching|read_active_wait_records_for_run" tests/host/public_smoke_support.py tests/host/recovery_support.py tests/host/stress_support.py
```

Result:

- `projection_checkpoint_sequence(...)` calls `read_projection_checkpoint(...)`.
- `host_projection_checkpoints` remains only inside `force_memory_projection_lag(...)`, which is documented `fault-injection-only`.
- Retained diagnostic helpers contain `diagnostic-only` docstring markers.
- Retained fault-injection helpers contain `fault-injection-only` docstring markers.
- No `read_events_after(...)` or `read_events_after_matching(...)` routing was introduced.
- `public_smoke_support.py` still uses `read_active_wait_records_for_run(...)` for active wait records.

## Stress Validation Residual

Command:

```text
source .venv/bin/activate && pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
```

Result: `3 passed, 2 failed`

Failures:

- `test_scheduler_liveness_long_run_mixed_flow_stress`: `failure_boundary` was `active_cleanup`, with captured logs around deterministic stream exception, clean EOF closeout, and scheduler close.
- `test_sustained_watch_slow_consumer_reconnect_stress`: `accepted count did not reach 12: 11`; captured log shows `HostPayloadReferenceError` while recording runner-call manifest canonical payload inline size.

Controller classification: non-blocking residual validation risk for S2.

Reason:

- S2 changed only durable diagnostic helper boundaries in test support code.
- The failing stress paths are production dispatch / scheduler cleanup and runner-call manifest payload recording paths.
- The edited stress helpers used by these failures had only docstring/classification changes for `read_event_log_count(...)` and `read_host_instances(...)`; their SQL behavior did not change.
- The implementation artifact already records stress failures as outside this slice's edited helper semantics.

This residual remains evidence for later stress / scheduler / payload work if needed, but it is not a blocker for S2 durable diagnostic helper acceptance.

## README Decision

`tests/README.md` was read before deciding documentation changes. No update is required because S2 did not add a new shared helper file, reusable assertion convention, new test layer, or documented helper responsibility. The existing README already states that public smoke synchronization must use centralized `public_smoke_support.py` helpers and that production code must not import test helpers.

## Propagation Audit

- Producer / owner: projection checkpoint durable row semantics remain owned by `dayu.host.durable.projection`.
- Validation owner: `projection_checkpoint_sequence(...)` now consumes `read_projection_checkpoint(...)` rather than independently projecting checkpoint SQL rows.
- Fault injection owner: recovery tests still own impossible-state injection for missing owner PID, stale heartbeat, and projection lag.
- Diagnostic projection owner: public smoke / stress helpers own point-in-time aggregate diagnostics and clearly state that those values are not EventLog or liveness truth.
- Durable state / audit / LLM-facing output: no production durable schema, EventLog semantics, trace, memory, prompt, or tool schema changed.

## Completion Status

Controller validation accepts S2 implementation for code review. There is one classified non-blocking residual validation risk from the stress suite. No blocking open question is present. Next gate: S2 code review by AgentMiMo and AgentDS.
