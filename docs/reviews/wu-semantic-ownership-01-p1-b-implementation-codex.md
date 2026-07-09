# WU-SEMANTIC-OWNERSHIP-01 P1-B Implementation - Codex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-B`
- Plan: `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- Gate: implementation
- Commit / push: not performed per task instruction.

## Owner Boundary

- Producer: Host durable transition layer produces Run lifecycle facts and accepted cancel facts. Cancel commands append `CANCEL_REQUESTED` and the corresponding Run lifecycle / terminal fact in one transaction.
- Validator: Host durable transition and row codec validate terminal status shape, typed cancel link shape, same-Run `CANCEL_REQUESTED` references, and first-committer-wins CAS preconditions.
- Durable truth: EventLog remains audit truth for `CANCEL_REQUESTED`, `RUN_CANCELLING`, `RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED`, and `RUN_LOST`; `host_runs.cancel_request_event_id` is the typed durable link for accepted cancel lifecycle.
- Projection: Outbox, Read Model, Read API, Tool Trace, Engine ingest, Dispatch and Recovery consume Host lifecycle helpers or the typed Run row link. They do not parse `RUN_CANCELLING` payload as critical cancel linkage.

## Changed Files

- Design / docs: `docs/host/design.md`, `dayu/host/README.md`
- Host lifecycle helper: `dayu/host/lifecycle_events.py`
- Terminal consumers: `dayu/host/outbox.py`, `dayu/host/durable/outbox.py`, `dayu/host/read_model.py`, `dayu/host/tool_trace.py`, `dayu/host/read_api.py`
- Cancel durable linkage: `dayu/host/durable/schema.py`, `dayu/host/durable/state.py`, `dayu/host/durable/run_transition.py`, `dayu/host/engine_ingest.py`, `dayu/host/dispatch.py`, `dayu/host/recovery.py`
- Tests: focused Host tests under `tests/host/`

`docs/host/issues-implementation-control.md` was already dirty at task start and was not edited by this implementation pass.

## Design Update

- Insertion location: `docs/host/design.md`, immediately after the Run state transition matrix and before the `RUN_STARTED` paragraph.
- Added structure: Host terminal / lifecycle event set; public outbox terminal item set; non-public terminal fact skip / diagnostic behavior.
- Reason: readers see `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` in the transition table first, then immediately see why `RUN_LOST` is Host/read-model `lost` terminal but not a public outbox terminal item.

## Schema Decision

- `HOST_SCHEMA_VERSION` advanced to `21`.
- `host_runs` fresh schema now has nullable `cancel_request_event_id TEXT`.
- `CANCELLING` and `CANCELLED` Run rows must carry the typed link.
- No old schema compatibility or migration path was added, per task and schema policy.

## Implementation Notes

- Added `dayu.host.lifecycle_events` as Host-owned source-of-truth for Run lifecycle event types, Host terminal set, public outbox terminal item set, and terminal status mapping from raw EventLog strings.
- `durable/outbox.py` now computes latest public terminal sequence from `PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES`, excluding `RUN_LOST`.
- `tool_trace.py` now observes the shared Host lifecycle event set from `dayu.host.lifecycle_events`. This intentionally expands the older local subset to the complete Host lifecycle event set so Tool Trace uses the same lifecycle semantics as other Host projections.
- Active watchdog, Engine cooperative cancel, Dispatch active cancel candidate selection and Recovery accepted-cancel defer now read `RunRow.cancel_request_event_id` and validate the referenced same-Run `CANCEL_REQUESTED`.
- Removed `_cancel_request_event_id_from_cancelling`; malformed `RUN_CANCELLING` payload is no longer a lifecycle blocker when typed link exists.

## Residual Grep Classification

Command:

```bash
source .venv/bin/activate && rg -n "_TERMINAL_STATUS_BY_EVENT_TYPE|_TERMINAL_EVENT_TYPES|_cancel_request_event_id_from_cancelling|payload\\.get\\(\"cancel_request_event_id\"\\)|event_payload_object\\(.*RUN_CANCELLING" dayu/host tests/host
```

Findings:

- Allowed source-of-truth: `dayu/host/lifecycle_events.py` owns Host terminal/public-outbox sets and mapping.
- Allowed derived values: `dayu/host/outbox.py` and `dayu/host/durable/outbox.py` derive string tuples from lifecycle helper constants.
- Deferred / existing test support: `tests/host/stress_support.py` still has stress-test terminal tuples, outside P1-B focused migration scope.
- No remaining `_cancel_request_event_id_from_cancelling`, `payload.get("cancel_request_event_id")`, or critical `event_payload_object(...RUN_CANCELLING...)` match in `dayu/host`.

## README Decisions

- `dayu/host/README.md`: updated because Host lifecycle, public outbox terminal semantics and cancellation durable linkage changed.
- `tests/README.md`: checked; no update needed because no new test layer or running convention was introduced.
- Root `README.md` and `dayu/README.md`: not triggered; no user-facing CLI/Web workflow or layering/assembly boundary changed.

## Propagation Audit

Terminal event/status:

1. Producer: durable transition / Engine ingest / Recovery produce Host terminal facts.
2. Durable: EventLog stores `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST`; Run row stores terminal refs and status.
3. Projection: Read Model, Read API and Tool Trace use the Host lifecycle helper; Tool Trace deliberately observes the complete shared Host lifecycle event set instead of its older local subset; `RUN_LOST` remains `lost`.
4. Outbox: only public outbox terminal item set creates items; `RUN_LOST` is skipped/diagnostic and does not advance latest public terminal requirement.
5. User / LLM visible: HostEvent/read API can expose lost terminal; outbox does not deliver lost as success/failure/cancel.

Cancel linkage:

1. Producer: cancel command appends `CANCEL_REQUESTED`.
2. Validator: durable transition writes and validates `host_runs.cancel_request_event_id`.
3. Durable: Run row carries typed link; EventLog keeps audit-readable payload.
4. Closeout/projection: Engine ingest, watchdog, dispatch and recovery validate same-Run `CANCEL_REQUESTED` through the typed link.
5. Diagnostics: missing/invalid typed link fails closed; malformed `RUN_CANCELLING` payload no longer blocks typed-link closeout.

## Validation

- `pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py` -> 148 passed.
- `pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_smoke.py tests/host/test_public_cancel_session_runs.py tests/host/test_open_host_runtime.py` -> 47 passed.
- `pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_recovery_scan.py` -> 168 passed.
- `pytest tests/host/test_projection_read_model.py tests/host/test_public_host_event.py tests/host/test_context_compact_events.py tests/host/test_tool_trace*.py` -> 104 passed.
- `pytest tests/host/test_outbox*.py tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py` -> 15 passed. `tests/host/test_durable_outbox*.py` does not exist; actual durable outbox coverage is `tests/host/test_outbox_durable.py`.
- Combined final focused reruns:
  - schema/cancel/open group -> 195 passed.
  - dispatch/engine/recovery/read-model/tool-trace/outbox group -> 287 passed.
- `pyright` -> 0 errors, 0 warnings.
- `git diff --check` -> passed.

## Blockers / Residual Risks

- No blocker remains for P1-B implementation.
- Stress support still has local terminal tuples for stress assertions; classified as deferred test support outside this focused migration.
- No compatibility migration was implemented for older Host DB schema, by explicit task policy.
