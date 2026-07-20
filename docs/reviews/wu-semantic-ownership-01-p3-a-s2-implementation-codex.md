# WU-SEMANTIC-OWNERSHIP-01 P3-A S2 implementation

## Status

completed

Slice: S2 - Migrate terminal status/event consumers.

## Changed Files

- `dayu/host/durable/run_transition.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/admission.py`
- `dayu/host/durable/read_model.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/purge.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_state_schema.py`

## Implementation Summary

- `run_transition.py` removed local terminal producer constants for `RUN_*` / `ATTEMPT_*` succeeded, failed, cancelled and lost events.
- Run terminal event strings now come from `run_terminal_event_type_for_status(...).value`.
- Run / Attempt joint terminal closeout Attempt event strings now come from `closeout_attempt_terminal_event_type_for_status(...).value`; `SUSPENDED` and `STEERED` remain durable-only Attempt terminal statuses and fail fast for joint closeout.
- `_TERMINAL_STATUS_PAIRS` is now a derived transition invariant from durable terminal status owner sets and lifecycle closeout helper support, not a hand-written durable truth.
- `engine_ingest.py` terminal closeout plans, active cancel closeout event ids, duplicate terminal id calculation, context recovery Attempt failure and recovering Run failure now use lifecycle owner helpers for terminal event type strings.
- `admission.py` terminal Run status check now calls `state.is_terminal_run_status`.
- `read_model.py` removed its local terminal Run status set and consumes `state.is_terminal_run_status`.
- `state.py` moved the three affected Run status SQL filters to `run_status_in_clause(...)` over `START_BLOCKING_RUN_STATUSES` or `NON_TERMINAL_RUN_STATUSES`.
- `purge.py` derives status value sets through `serialized_run_status_values(...)`.
- Tests now cover closeout helper ownership, derived terminal pair invariant, engine ingest terminal plan helper values, public Run snapshot status owner use, and SQL helper query equivalence.

## Validation

Required focused tests:

```text
source .venv/bin/activate && pytest tests/host/test_lifecycle_events.py tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_run_api.py tests/host/test_state_schema.py -q
203 passed in 1.72s
```

Import-cycle validation:

```text
source .venv/bin/activate && python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
import-ok
```

Pyright:

```text
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

Diff check:

```text
git diff --check
passed
```

Additional SQL helper focused test:

```text
source .venv/bin/activate && pytest tests/host/test_state_schema.py::test_run_status_in_clause_matches_durable_read_queries -q
1 passed in 0.29s
```

## Terminal Event Source Scan

Mandatory scan:

```text
rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host
dayu/host/compact_material.py:_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
dayu/host/compact_material.py:            _EVENT_TYPE_RUN_SUCCEEDED,
dayu/host/compact_material.py:            _EVENT_TYPE_RUN_SUCCEEDED,
dayu/host/compact_material.py:        elif row.event_type == _EVENT_TYPE_RUN_SUCCEEDED:
dayu/host/compact_material.py:        payload_label=_EVENT_TYPE_RUN_SUCCEEDED,
dayu/host/memory.py:_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
dayu/host/memory.py:    elif event.event_type == _EVENT_TYPE_RUN_SUCCEEDED:
dayu/host/run_input.py:_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
dayu/host/run_input.py:    if row.event_type != _EVENT_TYPE_RUN_SUCCEEDED:
dayu/host/outbox.py:_EVENT_TYPE_RUN_FAILED = "RUN_FAILED"
dayu/host/outbox.py:_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
dayu/host/outbox.py:    if event.event_type != _EVENT_TYPE_RUN_FAILED:
dayu/host/outbox.py:    if event.event_type != _EVENT_TYPE_RUN_CANCELLED:
dayu/host/durable/memory.py:_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
dayu/host/durable/memory.py:    _EVENT_TYPE_RUN_SUCCEEDED,
dayu/host/durable/memory.py:    if event.event_type != _EVENT_TYPE_RUN_SUCCEEDED:
```

Producer-scope scan:

```text
rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host/durable/run_transition.py dayu/host/engine_ingest.py
<no output>
```

Interpretation: S2 producer duplicates are removed from `run_transition.py` and `engine_ingest.py`. Remaining matches are downstream projection / memory consumers outside S2 allowed scope. They are not terminal event producers and should be treated as residual input for later EventLog / projection source-of-truth hardening, not as S2 blockers.

Known non-terminal constants intentionally out of S2:

- `run_transition.py`: `RUN_ACCEPTED`, `RUN_QUEUED`, `RUN_STARTED`, `ATTEMPT_STARTED`, `RUN_RECOVERING`, `ATTEMPT_RUNNING`, `CANCEL_REQUESTED`, `RUN_CANCELLING`, `RESUME_REQUESTED`, `TOOL_RESULT_ACCEPTED`.
- `engine_ingest.py`: `ENGINE_EVENT_REJECTED`, `ENGINE_EVENT_DIAGNOSTIC`, `PROVIDER_PROTOCOL_ERROR`, `RUN_RECOVERING`, `TOOL_AWAITING`, `RUNNER_CALL_INPUT_ASSEMBLED`, `RUNNER_CALL_INPUT_ITERATION_LINKED`, `RUN_WAITING`, `ATTEMPT_SUSPENDED`.

## SQL / Query-Plan Validation

`state.py` now generates these affected filters through `run_status_in_clause(...)`:

- `read_active_run_for_session`: `START_BLOCKING_RUN_STATUSES`
- `read_non_terminal_runs_for_session`: `NON_TERMINAL_RUN_STATUSES`
- `read_non_terminal_runs`: `NON_TERMINAL_RUN_STATUSES`

The targeted test `test_run_status_in_clause_matches_durable_read_queries` seeds accepted, queued, running and terminal Run rows, compares the durable read helper results against explicit SQL built from the same helper clause/params, and asserts `EXPLAIN QUERY PLAN` returns planner rows for all three query shapes. This avoids relying on unstable exact SQLite planner row counts while still validating generated `IN (?, ...)` behavior and result equivalence.

Observed planner output from an equivalent SQLite schema:

```text
active
(5, 0, 62, 'SEARCH host_runs USING INDEX idx_host_runs_session (session_id=?)')
(46, 0, 0, 'USE TEMP B-TREE FOR ORDER BY')
session_non_terminal
(4, 0, 62, 'SEARCH host_runs USING INDEX idx_host_runs_session (session_id=?)')
(43, 0, 0, 'USE TEMP B-TREE FOR ORDER BY')
all_non_terminal
(3, 0, 82, 'SEARCH host_runs USING COVERING INDEX idx_host_runs_status_sequence (status=?)')
(39, 0, 0, 'USE TEMP B-TREE FOR ORDER BY')
```

## README Decision

Inspected:

- `dayu/host/README.md`
- `tests/README.md`

Decision: no README update.

Reasoning: `dayu/host/README.md` describes stable Host architecture, public contract and major lifecycle boundaries; this slice only migrates internal consumers to existing S1 owner helpers without changing public Host behavior, architecture boundary or user-visible workflow. `tests/README.md` requires updates for new test layers or running modes; this slice only adds assertions to existing Host test files and does not introduce a new test category or command.

## Propagation Audit

Run terminal event type:

```text
RunStatus
  -> lifecycle_events.run_terminal_event_type_for_status
  -> run_transition / engine_ingest EventLog event_type
  -> terminal closeout transaction updates host_runs.status in same transaction
  -> read model / outbox / memory / run input consumers read committed EventLog/status
```

S2 confirms producer event types now come from lifecycle owner helper. Remaining downstream constant consumers are residual and not producer truth.

Attempt terminal event type:

```text
AttemptStatus
  -> lifecycle_events.closeout_attempt_terminal_event_type_for_status for joint closeout
  -> run_transition / engine_ingest Attempt terminal EventLog event_type
  -> terminal closeout transaction updates host_attempts.status in same transaction
  -> recovery / cancel / diagnostic consumers read durable Attempt status/EventLog
```

`SUSPENDED` and `STEERED` remain durable Attempt terminal states but are excluded from Run / Attempt joint closeout. Tests assert they do not enter `_TERMINAL_STATUS_PAIRS`.

Run status predicates and SQL filters:

```text
_row_rules.TERMINAL_RUN_STATUS_VALUES
  -> state.TERMINAL_RUN_STATUSES / NON_TERMINAL_RUN_STATUSES / START_BLOCKING_RUN_STATUSES
  -> state.is_terminal_run_status / run_status_in_clause / serialized_run_status_values
  -> admission / read_model / durable read helpers / purge
```

No S2 consumer now owns a separate terminal Run tuple or manual SQL status placeholder list for the affected paths.

Durable state, EventLog and projections remain consistent because S2 only changes how terminal event type/status filter values are sourced before the same existing transaction writes EventLog and row status. It does not split a fact across separate truth sources.

## Residual Risks / S3 Handoff

- Worker lifecycle synthetic `EngineEvent(type=RUN_FAILED)` path in `engine_ingest.py` was intentionally not changed; it is S3 scope.
- `_late_rejection_reason` nullable terminal ref usage remains S3 scope.
- Dispatch pre-worker direct cancel predicate migration remains S3 scope.
- Downstream terminal constants in `outbox.py`, `memory.py`, `compact_material.py`, `run_input.py`, and `durable/memory.py` remain outside S2 allowed files and should be handled by a later projection/EventLog source-of-truth slice.
- Non-terminal EventLog constants remain out of P3-A S2 and are residual input for P3-J / future EventLog schema hardening.
