# WU-SEMANTIC-OWNERSHIP-01 P1-B Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-B`
- Gate: implementation controller validation
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p1-b-implementation-codex.md`
- Result: pass to code review.

## Motivation Check

The implementation motivation remains valid. Host Run terminal event sets, public outbox terminal item sets and active cancel linkage are Host lifecycle semantics. They must not be reconstructed independently by downstream projections or by parsing `RUN_CANCELLING` payload JSON in critical closeout paths.

## Owner Boundary Check

- Producer: Host durable transition layer appends Run lifecycle / terminal facts and writes accepted cancel linkage in the Run row.
- Validator: Host durable state mutations and typed helper validate event type classification, terminal status shape and same-Run `CANCEL_REQUESTED` linkage before closeout/projection consumers use the value.
- Durable truth: EventLog remains audit truth for lifecycle facts; `host_runs.cancel_request_event_id` is the typed durable link for accepted cancel lifecycle.
- Projection: Outbox, Read Model, Read API, Tool Trace, Dispatch, Engine ingest and Recovery consume Host-owned lifecycle helpers or typed Run row linkage, not private terminal tuples or `RUN_CANCELLING` payload parsing.

## Controller Findings

No controller-blocking implementation issue was found before code review.

Residual grep matches are classified as:

- Allowed source-of-truth: `dayu/host/lifecycle_events.py`.
- Allowed helper-derived string tuples: `dayu/host/outbox.py`, `dayu/host/durable/outbox.py`.
- Deferred test support: `tests/host/stress_support.py` still has local stress-test terminal tuples and is outside the focused P1-B migration scope.

No `_cancel_request_event_id_from_cancelling`, `payload.get("cancel_request_event_id")`, or critical `event_payload_object(...RUN_CANCELLING...)` match remains in `dayu/host`.

## Propagation Audit

Terminal event/status:

1. Host durable transition, Engine ingest and Recovery produce Host terminal facts.
2. EventLog stores `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST`; Run row stores terminal refs and status.
3. Read Model, Read API and Tool Trace use the Host lifecycle helper and retain `RUN_LOST` as `lost`.
4. Public outbox terminal item logic uses only succeeded / failed / cancelled; `RUN_LOST` is skipped/diagnostic and cannot create false latest-public-terminal lag.
5. User-visible HostEvent/read API can expose lost terminal; public outbox does not deliver lost as success/failure/cancel.

Cancel linkage:

1. Cancel command appends `CANCEL_REQUESTED`.
2. Durable transition writes `host_runs.cancel_request_event_id`.
3. EventLog keeps audit-readable payload; Run row carries the typed critical link.
4. Engine ingest, active watchdog, dispatch and recovery validate same-Run `CANCEL_REQUESTED` through the typed link.
5. Missing/invalid typed link fails closed; malformed `RUN_CANCELLING` payload is no longer a lifecycle blocker.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py` -> 148 passed.
- `source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py tests/host/test_public_cancel_session_runs.py tests/host/test_open_host_runtime.py` -> 47 passed.
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_recovery_scan.py` -> 168 passed.
- `source .venv/bin/activate && pytest tests/host/test_projection_read_model.py tests/host/test_public_host_event.py tests/host/test_context_compact_events.py tests/host/test_tool_trace*.py` -> 104 passed.
- `source .venv/bin/activate && pytest tests/host/test_outbox*.py tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py` -> 15 passed. The planned `tests/host/test_durable_outbox*.py` pattern has no matching file in this repository; `tests/host/test_outbox_durable.py` is covered by `test_outbox*.py`.
- `source .venv/bin/activate && rg -n "_TERMINAL_STATUS_BY_EVENT_TYPE|_TERMINAL_EVENT_TYPES|_cancel_request_event_id_from_cancelling|payload\\.get\\(\"cancel_request_event_id\"\\)|event_payload_object\\(.*RUN_CANCELLING" dayu/host tests/host` -> only classified residuals above.
- `source .venv/bin/activate && pyright` -> 0 errors, 0 warnings, 0 informations.
- `git diff --check` -> passed.

## Decision

Proceed to P1-B code review with AgentMiMo and AgentDS. P1-B is not accepted until both review lanes are adjudicated and all accepted findings, if any, are fixed and re-reviewed.
