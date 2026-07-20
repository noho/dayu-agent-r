# WU-SEMANTIC-OWNERSHIP-01 P1-B Fix - Codex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-B`
- Gate: code review accepted findings fix
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-p1-b-code-review-controller-adjudication.md`
- Fix scope: only `Accepted Findings` `P1B-CODE-ACCEPTED-F01` through `P1B-CODE-ACCEPTED-F04`.
- Explicit non-goal: did not implement legacy schema compatibility; did not expand into P1-C / P2; did not implement the rejected AgentMiMo suggestion that non-`CANCELLED` terminal Runs must clear or reject cancel links.

## Accepted Finding Fix Summary

### P1B-CODE-ACCEPTED-F01

- File: `dayu/host/durable/run_transition.py`
- Updated `_active_watchdog_attempt_cancelled_event_request`, `_active_watchdog_run_cancelled_event_request`, and `_active_watchdog_cancelled_payload` docstrings.
- The `cancel_request_event_id` parameter now states that the id comes from typed `RunRow.cancel_request_event_id`, after same-Run `CANCEL_REQUESTED` validation, and is not parsed from `RUN_CANCELLING` payload.

### P1B-CODE-ACCEPTED-F02

- File: `tests/host/test_state_schema.py`
- Added focused regression `test_cancel_acceptance_status_requires_cancel_request_event_id`.
- The test uses fresh durable schema, creates valid `CANCELLING` and `CANCELLED` rows through existing test helpers, then clears `host_runs.cancel_request_event_id` and asserts SQLite CHECK rejection.
- This proves the durable schema/state owner rejects `status in ('cancelling', 'cancelled')` with `cancel_request_event_id IS NULL` without adding production compatibility logic.

### P1B-CODE-ACCEPTED-F03

- File: `docs/reviews/wu-semantic-ownership-01-p1-b-implementation-codex.md`
- Recorded that `tool_trace.py` now observes the shared Host lifecycle event set from `dayu.host.lifecycle_events`.
- The artifact now explicitly states that expanding from the older local subset to the complete Host lifecycle event set is intentional P1-B semantic convergence.

### P1B-CODE-ACCEPTED-F04

- File: `dayu/host/durable/state.py`
- Updated `cancel_cancelling_run_row` docstring.
- The docstring now states that `cancel_request_event_id` is fixed when the Run enters `CANCELLING`, schema guarantees `CANCELLING` rows carry that link, and the mutator preserves it when closing to `CANCELLED`.

## Owner Boundary

- Producer: Host durable transition code produces cancel lifecycle facts and writes the typed Run row cancel link when cancel is accepted.
- Validator: Host durable transition validates same-Run `CANCEL_REQUESTED`; fresh durable schema/state CHECK constraints enforce that `CANCELLING` and `CANCELLED` Run rows retain the typed link.
- Durable truth: `event_log` remains audit truth for lifecycle facts; `host_runs.cancel_request_event_id` is the durable typed cancel correlation link.
- Projection: watchdog closeout payloads, Tool Trace and other Host projections consume the typed link or shared Host lifecycle event set; they do not reconstruct critical cancel linkage from `RUN_CANCELLING` payload.
- Documentation owner: review artifacts record why the current propagation shape is intentional and what was fixed after code review.

## Propagation Audit

This fix does not change runtime semantics.

- F01 only corrects helper docstrings to match the existing typed-link data flow. Runtime reads still use `RunRow.cancel_request_event_id` and same-Run `CANCEL_REQUESTED` validation.
- F02 adds a regression test at the schema/state owner boundary. It proves an existing fresh-schema invariant; it does not add compatibility reads, fallback writes, or downstream special cases.
- F03 updates the implementation artifact so the existing `tool_trace.py` lifecycle-event convergence is documented. No Tool Trace code changed in this fix.
- F04 only documents the existing `CANCELLING -> CANCELLED` preservation invariant. The mutator still updates terminal refs and status while leaving the typed cancel link untouched.

End-to-end semantic path remains:

1. Cancel command appends `CANCEL_REQUESTED`.
2. Active cancel acceptance stores the same-Run event id in `host_runs.cancel_request_event_id`.
3. Fresh schema rejects `CANCELLING` / `CANCELLED` rows without that typed link.
4. Watchdog closeout and projections consume the typed link or shared Host lifecycle event set.
5. Audit-visible EventLog payloads remain diagnostic; they are not the critical source of cancel linkage.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py` -> 73 passed.
- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py tests/host/test_recovery_scan.py tests/host/test_outbox_durable.py` -> 147 passed.
- `source .venv/bin/activate && pyright` -> 0 errors, 0 warnings, 0 informations.
- `git diff --check` -> passed.

## README Decision

- `dayu/host/README.md`: checked per trigger because Host files were touched; no further update needed for this fix because runtime contracts did not change.
- `tests/README.md`: checked per trigger because a test was added; no update needed because no new test layer or running convention was introduced.

## Residual Risks

- No accepted finding remains intentionally unfixed in this pass.
- This pass does not re-review rejected/deferred findings and does not alter P1-C / P2 scope.
