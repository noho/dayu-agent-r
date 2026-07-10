# WU-SEMANTIC-OWNERSHIP-01 P3-A S2 controller validation

## Status

pass

Validated at: 2026-07-10 12:01:41 CST.

Base accepted commit before S2: `b9e318a0`.

Implementation artifact:

- `docs/reviews/wu-semantic-ownership-01-p3-a-s2-implementation-codex.md`

## Controller Scope Check

S2 scope is the migration of existing terminal status / terminal EventLog producer consumers to the S1 owner helpers. The implementation stayed inside the planned S2 files:

- `dayu/host/durable/run_transition.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/admission.py`
- `dayu/host/durable/read_model.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/purge.py`
- affected Host tests

No S3-owned worker lifecycle synthetic `EngineEvent` path, nullable terminal reference handling, or pre-worker direct cancel predicate was intentionally changed.

## Owner Boundary

Run terminal EventLog type ownership:

```text
RunStatus
  -> dayu.host.lifecycle_events.run_terminal_event_type_for_status
  -> run_transition / engine_ingest producer EventLog event_type
  -> Host terminal transaction writes host_runs.status and EventLog in one durable boundary
```

Attempt closeout EventLog type ownership:

```text
AttemptStatus
  -> dayu.host.lifecycle_events.closeout_attempt_terminal_event_type_for_status
  -> run_transition / engine_ingest producer EventLog event_type
  -> Host terminal transaction writes host_attempts.status and EventLog in one durable boundary
```

Run status predicate / SQL filter ownership:

```text
_row_rules terminal values
  -> dayu.host.durable.state owner constants and helpers
  -> admission / read_model / durable read helpers / purge
```

This is the intended owner boundary for S2. The fix is not a downstream display or test-fixture workaround.

## Independent Validation

Focused required tests:

```text
source .venv/bin/activate && pytest tests/host/test_lifecycle_events.py tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_run_api.py tests/host/test_state_schema.py -q
203 passed in 1.62s
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

Diff whitespace:

```text
git diff --check
passed
```

Terminal producer duplicate scan:

```text
rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host/durable/run_transition.py dayu/host/engine_ingest.py
<no output>
```

## Controller Decision

S2 may enter implementation code review by AgentMiMo and AgentDS.

Residuals remain as planned S3 or later-source-of-truth work:

- worker lifecycle synthetic `EngineEvent(type=RUN_FAILED)` path in `engine_ingest.py`
- `_late_rejection_reason` nullable terminal reference handling
- dispatch pre-worker direct cancel predicate migration
- downstream terminal constants in projection / memory consumers outside the S2 producer boundary
